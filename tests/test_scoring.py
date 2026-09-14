"""Risk-scoring engine tests."""

from __future__ import annotations

from gsid.scoring import (
    MODEL_MAX, derive_confidence, derive_impact, derive_urgency,
    geo_scope_from_countries, is_critical_alert, score_relevance,
)


def test_model_max_is_100():
    assert MODEL_MAX == 100


def test_zero_signals_score_zero():
    b = score_relevance({})
    assert b.total == 0
    assert len(b.dimensions) == 8
    # every dimension has a rationale (no unexplained numbers)
    assert all(d["rationale"] for d in b.dimensions)


def test_full_signals_capped_at_100():
    signals = {k: 1.0 for k in [
        "people_safety", "facility_assets", "operational", "supply_chain",
        "regulatory", "geopolitical", "cyber_physical", "reputational"]}
    b = score_relevance(signals)
    assert b.total == 100


def test_people_safety_weight_is_highest():
    b = score_relevance({"people_safety": 1.0})
    dim = next(d for d in b.dimensions if d["key"] == "people_safety")
    assert dim["points"] == 20
    assert b.total == 20


def test_signal_clamped():
    b = score_relevance({"people_safety": 5.0})  # out of range
    assert b.total == 20


def test_derive_impact_ignores_life_safety_override():
    """Life-safety alone must not promote a low-scoring story.

    It used to award Critical on people_safety >= 0.9 at any score, which made
    22% of the corpus Critical at a median relevance of 30. people_safety is
    already worth 20 of the 100 points; the tier must not count it twice.
    """
    assert derive_impact(30, {"people_safety": 1.0})[0] == "Moderate"
    assert derive_impact(20, {"people_safety": 1.0})[0] == "Low"
    assert derive_impact(70, {"people_safety": 0.0})[0] == "Critical"


def test_derive_impact_is_monotonic_in_score():
    """Tiers must order the same way the score does.

    The old ladder put Moderate's median relevance (34) above Critical's (30) —
    a sign it was not measuring one thing.
    """
    order = ["Low", "Moderate", "High", "Critical"]
    seen = [derive_impact(s, {})[0] for s in range(0, 101)]
    assert [t for i, t in enumerate(seen) if i == 0 or t != seen[i - 1]] == order


def test_derive_urgency_immediate_on_fast_life():
    urg, _ = derive_urgency("Immediate", {"people_safety": 0.95})
    assert urg == "Immediate"


def test_confidence_confirmed_requires_primary_and_multiple():
    level, _ = derive_confidence(best_tier=1, source_count=2, has_primary=True)
    assert level == "Confirmed"


def test_confidence_unverified_for_tier4_single():
    level, _ = derive_confidence(best_tier=4, source_count=1, has_primary=False)
    assert level == "Unverified"


def test_geo_scope_scaling():
    assert geo_scope_from_countries(1, False)[0] == "Local"
    assert geo_scope_from_countries(2, False)[0] == "National"
    assert geo_scope_from_countries(4, False)[0] == "Regional"
    assert geo_scope_from_countries(1, True)[0] == "Global"


def test_alert_gating_rejects_unverified_low_impact():
    assert is_critical_alert(80, "Immediate", "Moderate", "Unverified") is False
    assert is_critical_alert(70, "Immediate", "Critical", "High") is True
    assert is_critical_alert(80, "7 Days", "Critical", "High") is False
