"""Recompute derived tiers for stored stories from their existing scores.

`impact` and `is_alert` are written at ingestion time, so changing the rules in
`gsid.scoring` leaves everything already in the database on the old ladder. This
replays the derivation from the relevance breakdown that is already stored, so
it needs no analyzer and no network — the signals were persisted in
`scoring_json` precisely so the reasoning can be reproduced.

The relevance score itself is never recomputed. That would need the analyzer,
and it is not what changed.
"""

from __future__ import annotations

import json
import logging

from .scoring import derive_impact, is_critical_alert

log = logging.getLogger("gsid.rescore")


def _signals(scoring_json: str | None) -> dict[str, float]:
    """Recover per-dimension intensities from a stored breakdown."""
    try:
        dims = json.loads(scoring_json or "{}")["relevance"]["dimensions"]
    except (ValueError, KeyError, TypeError):
        return {}
    return {d["key"]: d.get("intensity", 0.0) for d in dims if "key" in d}


def rescore_all(conn, dry_run: bool = False) -> dict:
    rows = conn.execute("""
        SELECT id, relevance_score, urgency, confidence, status, event_time,
               impact, is_alert, scoring_json
          FROM story WHERE is_demo = 0
    """).fetchall()

    updates, moves = [], {}
    alerts_before = alerts_after = 0
    for row in rows:
        score = row["relevance_score"] or 0
        impact, reason = derive_impact(score, _signals(row["scoring_json"]))
        alert = is_critical_alert(
            score, row["urgency"] or "", impact, row["confidence"] or "",
            status=row["status"], event_time=row["event_time"],
        )
        alerts_before += 1 if row["is_alert"] else 0
        alerts_after += 1 if alert else 0
        if impact == row["impact"] and alert == bool(row["is_alert"]):
            continue
        if impact != row["impact"]:
            moves[f"{row['impact']} -> {impact}"] = moves.get(
                f"{row['impact']} -> {impact}", 0) + 1
        updates.append((impact, reason, 1 if alert else 0, row["id"]))

    if not dry_run and updates:
        # Keep the stored rationale in step with the tier, or the UI would
        # explain a rating the story no longer has.
        for impact, reason, alert, sid in updates:
            blob = conn.execute(
                "SELECT scoring_json FROM story WHERE id = ?", (sid,)).fetchone()[0]
            try:
                payload = json.loads(blob or "{}")
                payload.setdefault("ratings", {})["impact"] = {
                    "value": impact, "reason": reason}
                blob = json.dumps(payload)
            except ValueError:
                pass
            conn.execute(
                "UPDATE story SET impact = ?, is_alert = ?, scoring_json = ? WHERE id = ?",
                (impact, alert, blob, sid))
        conn.commit()

    log.info("rescore: scanned=%d changed=%d alerts %d -> %d dry_run=%s",
             len(rows), len(updates), alerts_before, alerts_after, dry_run)
    return {"scanned": len(rows), "changed": len(updates), "moves": moves,
            "alerts_before": alerts_before, "alerts_after": alerts_after,
            "dry_run": dry_run}
