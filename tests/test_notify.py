"""Webhook delivery: payload shaping, de-duplication, and failure safety."""

from __future__ import annotations

import json

from gsid import notify


class _Cfg:
    def __init__(self, url="", data_mode="live"):
        self.webhook_url = url
        self.data_mode = data_mode


def _alert(conn, sid, headline, **kw):
    conn.execute(
        "INSERT INTO story(id,headline,category,first_seen,last_updated,impact,"
        "urgency,confidence,relevance_score,event_time,is_alert,is_demo,location_text) "
        "VALUES (?,?,'geopolitical','t','t',?,?,?,?,?,1,0,?)",
        (sid, headline, kw.get("impact", "Critical"), kw.get("urgency", "Immediate"),
         kw.get("confidence", "High"), kw.get("score", 70),
         kw.get("event", "2099-01-01T00:00:00Z"), kw.get("where", "Nairobi")))


# ---- payload shaping --------------------------------------------------------

def test_payload_matches_the_service_in_the_url():
    slack = notify._payload("https://hooks.slack.com/services/X", "T", ["a"])
    discord = notify._payload("https://discord.com/api/webhooks/1/x", "T", ["a"])
    generic = notify._payload("https://example.org/hook", "T", ["a"])
    assert "text" in slack and "content" not in slack
    assert "content" in discord and "text" not in discord   # Discord's field
    assert "text" in generic                                 # safe default


def test_discord_content_is_truncated_to_its_limit():
    body = notify._payload("https://discord.com/api/webhooks/1/x", "T", ["x" * 5000])
    assert len(body["content"]) <= 1900


def test_post_is_a_noop_without_url_or_lines():
    assert notify.post("", "T", ["a"]) is False
    assert notify.post("https://example.org/hook", "T", []) is False


# ---- digest content ---------------------------------------------------------

def test_digest_reports_provenance_not_just_the_headline(conn):
    conn.execute("DELETE FROM story")
    _alert(conn, "a1", "Explosion at port facility")
    conn.commit()
    title, lines, ids = notify.build_digest(conn, "live")
    body = "\n".join(lines)
    assert "Explosion at port facility" in body
    assert "Critical impact" in body and "High confidence" in body  # provenance
    assert ids == {"a1"}
    assert "1 new critical alert" in title


def test_digest_is_empty_when_there_is_nothing_new(conn):
    conn.execute("DELETE FROM story")
    conn.commit()
    _, lines, ids = notify.build_digest(conn, "live")
    assert lines == [] and ids == set()


def test_digest_caps_the_number_of_items(conn):
    conn.execute("DELETE FROM story")
    for i in range(notify.MAX_ITEMS + 4):
        _alert(conn, f"a{i}", f"Incident {i}")
    conn.commit()
    _, lines, ids = notify.build_digest(conn, "live")
    assert len(ids) == notify.MAX_ITEMS + 4          # all counted
    assert "and 4 more" in lines[-1]                 # but not all listed


# ---- delivery, de-duplication, failure safety -------------------------------

def test_unconfigured_webhook_is_a_clean_noop(conn):
    assert notify.notify_new_alerts(conn, _Cfg(""))["sent"] is False


def test_alerts_are_not_sent_twice(conn, monkeypatch):
    conn.execute("DELETE FROM story")
    _alert(conn, "a1", "First incident")
    conn.commit()
    posted = []
    monkeypatch.setattr(notify, "post", lambda u, t, l: posted.append(l) or True)

    first = notify.notify_new_alerts(conn, _Cfg("https://example.org/hook"))
    second = notify.notify_new_alerts(conn, _Cfg("https://example.org/hook"))

    assert first["sent"] is True and first["alerts"] == 1
    assert second["sent"] is False and second["reason"] == "nothing new"
    assert len(posted) == 1


def test_a_failed_post_is_retried_next_cycle(conn, monkeypatch):
    """A dropped message must not be recorded as delivered."""
    conn.execute("DELETE FROM story")
    _alert(conn, "a1", "Incident during outage")
    conn.commit()

    monkeypatch.setattr(notify, "post", lambda u, t, l: False)      # webhook down
    assert notify.notify_new_alerts(conn, _Cfg("https://example.org/hook"))["sent"] is False

    monkeypatch.setattr(notify, "post", lambda u, t, l: True)       # recovered
    again = notify.notify_new_alerts(conn, _Cfg("https://example.org/hook"))
    assert again["sent"] is True and again["alerts"] == 1


def test_network_failure_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(notify.urllib.request, "urlopen", boom)
    assert notify.post("https://example.org/hook", "T", ["a"]) is False
