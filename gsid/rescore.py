"""Recompute derived tiers for stored stories from their existing scores.

Relevance, `impact` and `is_alert` are written at ingestion time, so changing
the scoring rules leaves everything already in the database on the old ladder.

For stories the heuristic analyzer scored, this re-runs it: it is deterministic
and local, and `story.summary` holds exactly the body the analyzer saw at
ingestion (see ingestion.pipeline), so the replay is faithful and needs no
network. Stories analysed by a model keep their signals — those did not come
from the lexicon and cannot be reproduced offline — but their tiers are still
re-derived, since the tier rules changed for everyone.
"""

from __future__ import annotations

import json
import logging

from .analysis.base import AnalysisInput
from .analysis.heuristic import HeuristicAnalyzer
from .scoring import derive_impact, derive_urgency, is_critical_alert, score_relevance

log = logging.getLogger("gsid.rescore")


def _signals(scoring_json: str | None) -> dict[str, float]:
    """Recover per-dimension intensities from a stored breakdown."""
    try:
        dims = json.loads(scoring_json or "{}")["relevance"]["dimensions"]
    except (ValueError, KeyError, TypeError):
        return {}
    return {d["key"]: d.get("intensity", 0.0) for d in dims if "key" in d}


def _provider(analysis_json: str | None) -> str:
    try:
        return json.loads(analysis_json or "{}").get("provider", "")
    except ValueError:
        return ""


def rescore_all(conn, dry_run: bool = False) -> dict:
    rows = conn.execute("""
        SELECT id, headline, summary, category, location_text, velocity,
               relevance_score, urgency, confidence, status, event_time,
               impact, is_alert, scoring_json, analysis_json
          FROM story WHERE is_demo = 0
    """).fetchall()

    analyzer = HeuristicAnalyzer()
    updates, moves = [], {}
    alerts_before = alerts_after = 0
    rescored = 0
    for row in rows:
        score = row["relevance_score"] or 0
        signals = _signals(row["scoring_json"])
        breakdown = None
        if _provider(row["analysis_json"]) == "heuristic":
            result = analyzer.analyze(AnalysisInput(
                headline=row["headline"] or "", body=row["summary"] or "",
                category=row["category"] or "",
                location_text=row["location_text"] or "", sources=[]))
            breakdown = score_relevance(result.signals)
            signals = result.signals
            if breakdown.total != score:
                rescored += 1
            score = breakdown.total

        impact, reason = derive_impact(score, signals)
        urgency = row["urgency"] or ""
        if breakdown is not None:
            urgency, _ = derive_urgency(row["velocity"] or "Developing", signals)
        alert = is_critical_alert(
            score, urgency, impact, row["confidence"] or "",
            status=row["status"], event_time=row["event_time"],
        )
        alerts_before += 1 if row["is_alert"] else 0
        alerts_after += 1 if alert else 0
        unchanged = (impact == row["impact"] and alert == bool(row["is_alert"])
                     and score == (row["relevance_score"] or 0)
                     and urgency == (row["urgency"] or ""))
        if unchanged:
            continue
        if impact != row["impact"]:
            key = f"{row['impact']} -> {impact}"
            moves[key] = moves.get(key, 0) + 1
        updates.append((impact, reason, 1 if alert else 0, score, urgency,
                        breakdown, row["id"]))

    if not dry_run and updates:
        # Keep the stored rationale in step with the tier, or the UI would
        # explain a rating the story no longer has.
        for impact, reason, alert, score, urgency, breakdown, sid in updates:
            blob = conn.execute(
                "SELECT scoring_json FROM story WHERE id = ?", (sid,)).fetchone()[0]
            try:
                payload = json.loads(blob or "{}")
                payload.setdefault("ratings", {})["impact"] = {
                    "value": impact, "reason": reason}
                if breakdown is not None:
                    payload["relevance"] = breakdown.to_dict()
                blob = json.dumps(payload)
            except ValueError:
                pass
            conn.execute(
                "UPDATE story SET impact = ?, is_alert = ?, relevance_score = ?, "
                "urgency = ?, scoring_json = ? WHERE id = ?",
                (impact, alert, score, urgency, blob, sid))
        conn.commit()

    scores = sorted(u[3] for u in updates)
    log.info("rescore: scanned=%d changed=%d relevance-rescored=%d "
             "alerts %d -> %d dry_run=%s",
             len(rows), len(updates), rescored, alerts_before, alerts_after, dry_run)
    return {"scanned": len(rows), "changed": len(updates), "rescored": rescored,
            "moves": moves, "alerts_before": alerts_before,
            "alerts_after": alerts_after, "dry_run": dry_run,
            "score_max": scores[-1] if scores else 0}
