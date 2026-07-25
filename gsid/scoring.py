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
def derive_impact(score: int, signals: dict[str, float]) -> tuple[str, str]:
    """Impact tier + rationale. Combines composite score with life-safety."""
    life = _clamp01(signals.get("people_safety", 0))
    if score >= 75 or life >= 0.9:
        return "Critical", (
            "Composite relevance is very high"
            + (" and a direct life-safety threat is present" if life >= 0.9 else "")
            + "."
        )
    if score >= 55 or life >= 0.6:
        return "High", "Multiple material impact dimensions are engaged."
    if score >= 30:
        return "Moderate", "Some impact dimensions are engaged but contained."
    return "Low", "Few impact dimensions are engaged."


def derive_urgency(velocity: str, signals: dict[str, float]) -> tuple[str, str]:
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
def is_critical_alert(score: int, urgency: str, impact: str, confidence: str) -> bool:
    """Only surface prompt-action developments as alerts.

    Keeps the Critical Alerts panel meaningful (avoids alert fatigue).
    """
    if confidence in {"Unverified"} and impact != "Critical":
        return False
    high_impact = impact in {"High", "Critical"}
    urgent = urgency in {"Immediate", "24 Hours"}
    return bool(high_impact and urgent and score >= 45)
