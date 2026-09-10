"""Re-run analysis over stories already in the database.

Ingestion only analyses a story the first time it is seen — `save_story` merges
an already-known story and returns before the analyzer runs. That is the right
default (re-analysing every story on every poll would be enormously wasteful),
but it means switching to a better analyzer improves nothing retroactively: the
existing desk keeps whatever the old analyzer produced.

This re-runs the CURRENTLY configured analyzer over stored stories and rewrites
the derived fields — analysis, signals, relevance score, ratings and alert flag.
Source text, citations, claims and categories are untouched: this re-analyses,
it does not re-ingest.

Built for rate-limited free tiers: `limit` bounds the work, `pause` spaces the
calls out, and a story whose analysis fails is left exactly as it was rather
than being overwritten with heuristic output.
"""

from __future__ import annotations

import json
import logging
import time

from . import db
from .analysis.base import AnalysisInput, SourceRef
from .scoring import (
    derive_confidence, derive_impact, derive_urgency, geo_scope_from_countries,
    is_critical_alert, score_relevance,
)
from .taxonomy import (
    LIKELIHOOD_LEVELS, TREND_LEVELS, VELOCITY_LEVELS, clamp_scale,
)

log = logging.getLogger("gsid.reanalyze")


def _sources_for(conn, story_id: str) -> list[SourceRef]:
    rows = conn.execute(
        "SELECT c.title, c.url, c.published_at, c.is_primary, s.name, s.tier, "
        "s.country, s.language FROM citation c LEFT JOIN source s ON s.id = c.source_id "
        "WHERE c.story_id = ?", (story_id,)).fetchall()
    return [
        SourceRef(source_id=str(i), name=r["name"] or "unknown",
                  tier=r["tier"] if r["tier"] is not None else 4,
                  url=r["url"] or "", title=r["title"] or "",
                  published_at=r["published_at"], country=r["country"],
                  language=r["language"], is_primary=bool(r["is_primary"]))
        for i, r in enumerate(rows)
    ]


def reanalyze(conn, analyzer, *, limit: int = 25, only_provider: str | None = None,
              category: str | None = None, pause: float = 0.0,
              dry_run: bool = False) -> dict:
    """Re-analyse up to `limit` stories with `analyzer`.

    `only_provider` selects stories whose stored analysis came from a given
    provider — pass "heuristic" to upgrade exactly the ones a better analyzer
    would improve, and to make repeated runs pick up where the last stopped.
    """
    where = ["is_demo = 0", "(status IS NULL OR status != 'advisory')"]
    params: list = []
    if category:
        where.append("category = ?")
        params.append(category)
    if only_provider:
        # Stories carrying this provider in their stored analysis.
        where.append("COALESCE(json_extract(analysis_json, '$.provider'), 'heuristic') = ?")
        params.append(only_provider)

    rows = conn.execute(
        f"SELECT id, headline, summary, category, location_text, primary_region, "
        f"status, event_time FROM story WHERE {' AND '.join(where)} "
        f"ORDER BY relevance_score DESC LIMIT ?", (*params, limit)).fetchall()

    scanned = updated = failed = 0
    for r in rows:
        scanned += 1
        countries = [c["country"] for c in conn.execute(
            "SELECT country FROM story_country WHERE story_id=?", (r["id"],)).fetchall()]
        sources = _sources_for(conn, r["id"])

        ai = analyzer.analyze(AnalysisInput(
            headline=r["headline"], body=r["summary"] or "", category=r["category"],
            location_text=r["location_text"] or "", countries=countries, sources=sources))

        # A provider failure degrades to heuristic output. Overwriting good
        # stored analysis with that would be a regression, so skip instead.
        if getattr(ai, "provider", "") in ("", "heuristic") and analyzer.name != "heuristic":
            failed += 1
            # If the provider reported a spent hourly/daily quota, every
            # remaining story would fail the same way. Stop now so the run
            # ends in seconds instead of grinding through the whole batch.
            if getattr(analyzer, "quota_exhausted", False):
                log.warning("stopping early: provider quota exhausted after "
                            "%d updated, %d failed", updated, failed)
                break
            continue

        breakdown = score_relevance(ai.signals)
        best_tier = min((s.tier for s in sources), default=4)
        has_primary = any(s.is_primary or s.tier == 1 for s in sources)
        confidence, conf_reason = derive_confidence(best_tier, len(sources), has_primary)
        impact, impact_reason = derive_impact(breakdown.total, ai.signals)
        velocity = clamp_scale(ai.velocity, VELOCITY_LEVELS, "Developing")
        urgency, urg_reason = derive_urgency(velocity, ai.signals)
        geo_scope, geo_reason = geo_scope_from_countries(
            len(countries), r["primary_region"] == "global")
        likelihood = clamp_scale(ai.likelihood, LIKELIHOOD_LEVELS, "Possible")
        trend = clamp_scale(ai.trend, TREND_LEVELS, "Stable")
        alert = is_critical_alert(breakdown.total, urgency, impact, confidence,
                                  status=r["status"], event_time=r["event_time"])

        scoring_json = {
            "relevance": breakdown.to_dict(),
            "ratings": {
                "impact": {"value": impact, "reason": impact_reason},
                "urgency": {"value": urgency, "reason": urg_reason},
                "geo_scope": {"value": geo_scope, "reason": geo_reason},
                "confidence": {"value": confidence, "reason": conf_reason},
                "likelihood": {"value": likelihood,
                               "reason": "Derived from certainty language in reporting."},
                "velocity": {"value": velocity,
                             "reason": "Derived from pace/escalation cues in reporting."},
                "trend": {"value": trend,
                          "reason": "Derived from escalation vs de-escalation cues."},
            },
        }

        if not dry_run:
            conn.execute(
                "UPDATE story SET analysis_json=?, scoring_json=?, relevance_score=?, "
                "urgency=?, geo_scope=?, impact=?, likelihood=?, velocity=?, "
                "confidence=?, trend=?, is_alert=? WHERE id=?",
                (json.dumps(ai.to_dict()), json.dumps(scoring_json), breakdown.total,
                 urgency, geo_scope, impact, likelihood, velocity, confidence, trend,
                 1 if alert else 0, r["id"]))
        updated += 1
        # Commit per story rather than once at the end. A long run otherwise
        # holds SQLite's single write lock for its whole duration — blocking the
        # web process and the scheduler — shows no progress until it finishes,
        # and loses everything if interrupted.
        if not dry_run:
            conn.commit()
        if pause:
            time.sleep(pause)

    if updated and not dry_run:
        db.audit(conn, f"ai:{analyzer.name}", "reanalyze_stories",
                 detail={"updated": updated, "failed": failed})
        conn.commit()
    log.info("re-analysed %d/%d stories (%d skipped after provider failure)",
             updated, scanned, failed)
    return {"scanned": scanned, "updated": updated, "failed": failed,
            "analyzer": analyzer.name, "dry_run": dry_run}
