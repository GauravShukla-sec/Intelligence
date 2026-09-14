"""Explainable relevance & risk scoring.

The relevance score (0-100) follows the documented weighting model from the
product brief. Every point awarded carries a human-readable rationale so the
UI can show *why* a story scored the way it did — no unexplained numbers.

Input: a `signals` dict where each dimension maps to an intensity in [0, 1]
(0 = no relevance, 1 = full weight). The analyzer (heuristic or AI) produces
these signals from the story content. Scoring is pure and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# Dimension key -> (max points, label). Order defines display order.
RELEVANCE_MODEL: list[tuple[str, int, str]] = [
    ("people_safety", 20, "Threat to people or employee safety"),
    ("facility_assets", 15, "Threat to facilities or physical assets"),
    ("operational", 15, "Operational or business-continuity impact"),
    ("supply_chain", 15, "Supply-chain or transportation impact"),
    ("regulatory", 15, "Legal, regulatory, or compliance impact"),
    ("geopolitical", 10, "Geopolitical escalation potential"),
    ("cyber_physical", 5, "Cyber-physical impact"),
    ("reputational", 5, "Executive or reputational impact"),
]
MODEL_MAX = sum(pts for _, pts, _ in RELEVANCE_MODEL)  # == 100


# Impact tier boundaries.
#
# These are calibrated against the score distribution the analyzer actually
# produces, not against the 0-100 nominal range. A single news item rarely
# engages more than three of the eight dimensions, so the practical ceiling is
# far below 100: measured over 3,577 heuristic-analysed stories on 2026-09-14,
#
#     median 12 | p75 20 | p90 28 | p95 32 | p99 41 | max 52
#
# which puts Critical at about p99 and High at about p95 — the rarity the
# product brief describes. The brief's original 75/55 assumed scores used the
# whole range; left in place they held 3% of stories between them and put a
# deadly strike on a Kyiv warehouse below the cut for High.
#
# This couples the ladder to the analyzer: change the lexicon or the weights and
# these need re-measuring. `python run.py --rescore --dry-run` prints the
# resulting distribution, which is the check to run after any scoring change.
IMPACT_THRESHOLDS = {"Critical": 40, "High": 32, "Moderate": 20}


@dataclass
class ScoreBreakdown:
    total: int
    dimensions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"total": self.total, "max": MODEL_MAX, "dimensions": self.dimensions}


def _intensity_word(v: float) -> str:
    if v <= 0:
        return "no"
    if v < 0.34:
        return "limited"
    if v < 0.67:
        return "moderate"
    return "strong"


def score_relevance(signals: dict[str, float]) -> ScoreBreakdown:
    """Compute the 0-100 relevance score with a per-dimension rationale."""
    dims: list[dict[str, Any]] = []
    total = 0
    for key, max_pts, label in RELEVANCE_MODEL:
        intensity = _clamp01(signals.get(key, 0.0))
        pts = round(max_pts * intensity)
        total += pts
        rationale = (
            f"{_intensity_word(intensity).capitalize()} {label.lower()}: "
            f"awarded {pts} of {max_pts} points."
        )
        if intensity <= 0:
            rationale = f"No material {label.lower()}: 0 of {max_pts} points."
        dims.append(
            {
                "key": key,
                "label": label,
                "points": pts,
                "max": max_pts,
                "intensity": round(intensity, 2),
                "rationale": rationale,
            }
        )
    return ScoreBreakdown(total=min(total, MODEL_MAX), dimensions=dims)


def _clamp01(v: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


# --------------------------------------------------------------------------
# Categorical ratings derived from signals + explicit hints
# --------------------------------------------------------------------------
def derive_impact(score: int, signals: dict[str, float] | None = None) -> tuple[str, str]:
    """Impact tier + rationale, from the composite relevance score alone.

    This used to promote any story with people_safety >= 0.9 straight to
    Critical, and >= 0.6 to High, regardless of score. The effect on 3,693
    stored stories:

        Critical   817 (22%)   median relevance 30, minimum 20
        High       367 ( 9%)   median relevance 24
        Moderate   366 ( 9%)   median relevance 34   <-- higher than Critical
        Low       2143 (58%)   median relevance 14

    Moderate outranking Critical is not a tuning problem, it means the ladder
    did not measure one thing. 96% of Criticals (788 of 817) scored below 75
    and were there on the override alone, so "Critical" had come to mean "this
    story mentions harm to people" — which is most news, and 22% of the corpus.

    people_safety is already the heaviest dimension in RELEVANCE_MODEL, worth
    20 of 100 points. The override applied that same signal a second time and
    let it overrule every other dimension, so a wildfire with no bearing on any
    site, route or employee outranked a scored-out supply-chain rupture. Impact
    is now a pure function of the score: if life-safety deserves more weight,
    the honest place to say so is RELEVANCE_MODEL, where it is visible and
    explained, not in a bypass that silently contradicts it.

    Urgency keeps its life-safety override on purpose — see `derive_urgency`.
    """
    if score >= IMPACT_THRESHOLDS["Critical"]:
        return "Critical", "Composite relevance is very high across dimensions."
    if score >= IMPACT_THRESHOLDS["High"]:
        return "High", "Multiple material impact dimensions are engaged."
    if score >= IMPACT_THRESHOLDS["Moderate"]:
        return "Moderate", "Some impact dimensions are engaged but contained."
    return "Low", "Few impact dimensions are engaged."


def derive_urgency(velocity: str, signals: dict[str, float]) -> tuple[str, str]:
    """How fast to respond. Life-safety legitimately forces Immediate here.

    Unlike impact, this is a question about time, not size. A threat to people
    is time-critical whether or not it touches anything the business owns, so
    the override belongs on this axis. It cannot inflate the alert panel by
    itself: alerting also requires High or Critical impact.
    """
    life = _clamp01(signals.get("people_safety", 0))
    if velocity == "Immediate" or life >= 0.9:
        return "Immediate", "Fast-moving and/or an active life-safety dimension."
    if velocity == "Fast":
        return "24 Hours", "Situation is developing quickly; reassess within a day."
    if velocity == "Developing":
        return "7 Days", "Developing situation; monitor over the coming week."
    return "Long-Term", "Slow-moving structural or regulatory development."


def geo_scope_from_countries(country_count: int, is_global: bool) -> tuple[str, str]:
    if is_global or country_count >= 6:
        return "Global", "Affects many countries or global systems."
    if country_count >= 3:
        return "Regional", "Multiple neighbouring countries affected."
    if country_count == 2:
        return "National", "Concentrated in one to two countries."
    return "Local", "Concentrated in a single locality or country."


# --------------------------------------------------------------------------
# Confidence: derived from source tiers + corroboration (transparent rule)
# --------------------------------------------------------------------------
def derive_confidence(
    best_tier: int, source_count: int, has_primary: bool
) -> tuple[str, str]:
    """Map evidence quality to a confidence level with a rationale.

    Rule of thumb aligned to the brief's confidence definitions:
      Confirmed     : primary evidence AND >=2 reliable sources
      High          : tier<=2 AND >=2 sources (no primary)
      Moderate      : tier<=2 single source, or tier 3 multiple
      Low           : tier 3 single, or conflicting
      Unverified    : tier 4 / single social signal
    """
    if has_primary and source_count >= 2:
        return "Confirmed", (
            "Primary/authoritative evidence corroborated by multiple sources."
        )
    if best_tier <= 2 and source_count >= 2:
        return "High", "Strongly corroborated by reputable independent reporting."
    if (best_tier <= 2 and source_count == 1) or (best_tier == 3 and source_count >= 2):
        return "Moderate", "Credible reporting exists; some details unresolved."
    if best_tier == 3:
        return "Low", "Limited corroboration from specialist reporting only."
    return "Unverified", "Single or early-warning signal; not independently corroborated."


# --------------------------------------------------------------------------
# Composite alerting decision
# --------------------------------------------------------------------------
ALERT_MAX_EVENT_AGE_DAYS = 7


def is_critical_alert(score: int, urgency: str, impact: str, confidence: str,
                      *, status: str | None = None, event_time: str | None = None,
                      now: datetime | None = None) -> bool:
    """Only surface prompt-action developments as alerts.

    Keeps the Critical Alerts panel meaningful (avoids alert fatigue). A single
    permissive threshold previously flagged ~11% of all stories, including
    Level-2 travel advisories and a feature about earthquake-resistant
    architecture. The gate now requires all of:

      * not a travel advisory — those belong to Travel Risk, and level moves are
        reported by the advisory change feed
      * evidence worth acting on — Low/Unverified confidence never alerts
      * high impact AND near-term urgency
      * a RECENT event: "prompt action" is meaningless for something weeks old

    There used to be a further score floor (Critical 50+, High 65+). It existed
    to undo the inflation in `derive_impact`, which promoted a quarter of all
    stories to High or Critical on life-safety alone. With impact derived from
    the score, the floor re-applies the same test the tier already encodes, and
    keeping it cut the alert rate to 0.1%. Removing it leaves 0.6%, down from
    1.1%, with the High/Critical population falling from 931 stories to 30.
    """
    if (status or "").lower() == "advisory":
        return False
    if confidence in {"Unverified", "Low"}:
        return False
    if impact not in {"High", "Critical"}:
        return False
    if urgency not in {"Immediate", "24 Hours"}:
        return False
    return _event_is_recent(event_time, now)


def _event_is_recent(event_time: str | None, now: datetime | None = None) -> bool:
    """True when the event is within the alerting window (unknown dates pass).

    An unparseable/absent timestamp must not silently suppress a live alert, so
    the benefit of the doubt goes to alerting.
    """
    if not event_time:
        return True
    try:
        ts = datetime.strptime(str(event_time)[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return True
    ref = now or datetime.now(timezone.utc)
    return (ref - ts) <= timedelta(days=ALERT_MAX_EVENT_AGE_DAYS)
