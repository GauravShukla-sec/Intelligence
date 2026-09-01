"""Push new critical alerts and advisory changes to a chat webhook.

The desk was pull-only: it had to be remembered and visited. This closes that
gap without adding a dependency, an account of ours, or a paid service — you
paste one incoming-webhook URL into GSID_WEBHOOK_URL and it posts there.

Provider-agnostic on purpose. Slack, Discord and Teams all accept a plain JSON
POST; only the field name differs, so the payload is shaped from the URL rather
than making the operator declare which service they use.

What makes this worth reading rather than another alert firehose: the message
carries the PROVENANCE. A commercial tool sends "Thailand: Level 3". This sends
the level, which governments disagree, and the source tier behind it — the
thing the desk knows that the alert-senders don't.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from . import db

log = logging.getLogger("gsid.notify")

USER_AGENT = "GSID-Intelligence-Desk/1.0 (+webhook-notifier)"
TIMEOUT = 15
MAX_ITEMS = 8          # a digest, not a firehose
SENT_KEY = "notified_alert_ids"


def _payload(url: str, title: str, lines: list[str]) -> dict:
    """Shape the body for whichever service the URL belongs to."""
    text = title + "\n" + "\n".join(lines)
    if "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
        # Discord caps content at 2000 chars.
        return {"content": text[:1900]}
    if "office.com" in url or "office365.com" in url or "webhook.office" in url:
        return {"text": text}          # Teams incoming webhook
    return {"text": text}              # Slack and generic receivers


def post(url: str, title: str, lines: list[str]) -> bool:
    """POST one message. Returns True on 2xx. Never raises."""
    if not url or not lines:
        return False
    body = json.dumps(_payload(url, title, lines)).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            code = getattr(resp, "status", 0) or resp.getcode() or 0
            return 200 <= code < 300
    except urllib.error.HTTPError as exc:
        log.warning("webhook rejected the message (HTTP %s)", exc.code)
    except Exception as exc:  # network failure must never break ingestion
        log.warning("webhook post failed: %s", exc)
    return False


def _sent_ids(conn) -> set[str]:
    row = conn.execute("SELECT value FROM preference WHERE key=?", (SENT_KEY,)).fetchone()
    if not row:
        return set()
    try:
        return set(json.loads(row["value"]))
    except (json.JSONDecodeError, TypeError):
        return set()


def _remember(conn, ids: set[str]) -> None:
    # Keep the tail bounded; old ids can never re-alert anyway.
    keep = list(ids)[-500:]
    conn.execute("INSERT OR REPLACE INTO preference(key,value) VALUES (?,?)",
                 (SENT_KEY, json.dumps(keep)))


def build_digest(conn, data_mode: str | None = None) -> tuple[str, list[str], set[str]]:
    """Compose the message for alerts not previously sent.

    Returns (title, lines, alert_ids). Empty lines means nothing new.
    """
    from . import repository

    already = _sent_ids(conn)
    alerts = [a for a in repository.list_alerts(conn, data_mode)
              if a["id"] not in already]

    lines: list[str] = []
    for a in alerts[:MAX_ITEMS]:
        where = a.get("location_text") or a.get("region_name") or "—"
        head = (a.get("headline") or "").replace("[DEMO] ", "")
        lines.append(f"• {head}")
        # Provenance is the point: say how confident and how well sourced.
        lines.append(f"    {a.get('impact')} impact · {a.get('urgency')} · "
                     f"{a.get('confidence')} confidence · {where}")
        wl = a.get("watchlist") or {}
        if wl.get("reasons"):
            lines.append(f"    ↳ {wl['reasons'][0]}")

    title = (f"*{len(alerts)} new critical alert"
             f"{'s' if len(alerts) != 1 else ''}* on the intelligence desk")
    if len(alerts) > MAX_ITEMS:
        lines.append(f"… and {len(alerts) - MAX_ITEMS} more.")
    return title, lines, {a["id"] for a in alerts}


def notify_new_alerts(conn, config) -> dict:
    """Send a digest of alerts not yet sent. No-op when unconfigured."""
    url = getattr(config, "webhook_url", "") or ""
    if not url:
        return {"sent": False, "reason": "no webhook configured"}

    title, lines, ids = build_digest(conn, getattr(config, "data_mode", None))
    if not lines:
        return {"sent": False, "reason": "nothing new"}

    ok = post(url, title, lines)
    if ok:
        # Only record as sent if it actually went — a failed post must be
        # retried next cycle, not silently swallowed.
        _remember(conn, _sent_ids(conn) | ids)
        db.audit(conn, "notifier", "webhook_digest",
                 detail={"alerts": len(ids)})
        conn.commit()
    return {"sent": ok, "alerts": len(ids)}
