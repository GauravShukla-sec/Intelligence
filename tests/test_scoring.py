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


def test_derive_impact_critical_on_life_safety():
    impact, reason = derive_impact(30, {"people_safety": 0.95})
    assert impact == "Critical"
    assert "life-safety" in reason


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
    assert is_critical_alert(60, "Immediate", "Critical", "High") is True
    assert is_critical_alert(30, "Immediate", "High", "High") is False  # below score floor
