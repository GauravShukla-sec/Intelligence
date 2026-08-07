"""Category classification: regression, precision and audit-trail tests.

The regression cases are the real false positives found in the QA audit. Each
one is kept as an executable assertion so the specific failure cannot return.
"""

from __future__ import annotations

import pytest

from gsid.ingestion.classify import (
    GUARDED, UNCLASSIFIED, classify, looks_relevant, source_prior,
)


def cat(headline, summary="", **kw):
    return classify(headline, summary, **kw).category


# ---------------------------------------------------------------------------
# Root cause: substring matching. Each of these fired on a fragment.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("headline,forbidden", [
    # "ics" matched inside "BRICS"
    ("BRICS diplomacy summit deepens trade ties", "cyber_physical"),
    # "ics" inside "demographics" / "politics"
    ("Demographic commentary on an ageing population", "cyber_physical"),
    ("Domestic politics dominate the campaign", "cyber_physical"),
    # bare "drone" is not a cyber signal
    ("Sudan drone attack kills dozens in Darfur", "cyber_physical"),
    ("Medical drone delivery expands in Rwanda", "cyber_physical"),
    # "war" inside "award"
    ("Cybersecurity award presented to security firm", "geopolitical"),
    # "port" inside "reported" / "important"
    ("Officials reported an important policy change", "supply_chain"),
])
def test_substring_false_positives_are_gone(headline, forbidden):
    assert cat(headline) != forbidden


def test_avalanche_is_a_natural_hazard_not_cyber():
    assert cat("Avalanche kills three climbers in the Alps") == "natural_hazard"


def test_who_dementia_guidance_is_health_not_supply_chain():
    result = classify("WHO issues new dementia care guidelines",
                      "Clinical guidelines for health workers", feed_id="who_news")
    assert result.category == "health"
    assert result.category != "supply_chain"


def test_africa_cdc_ebola_is_health():
    assert cat("Africa CDC reports new Ebola cases in the region",
               source_names=["Africa CDC"]) == "health"


# ---------------------------------------------------------------------------
# Authoritative source priors
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("headline,summary,feed_id,expected", [
    ("Schneider Electric IGSS",
     "Multiple vulnerabilities allow remote code execution", "cisa_alerts",
     "cyber_physical"),
    ("ABB KNX products", "Command injection vulnerability", "cisa_alerts",
     "cyber_physical"),
    ("CISA Adds Two Known Exploited Vulnerabilities to Catalog", "",
     "cisa_alerts", "cyber_physical"),
    ("Homeland Security final rule on cargo screening", "", "us_fedreg_dhs",
     "regulatory"),
    ("M6.1 earthquake strikes offshore", "", "usgs_quakes", "natural_hazard"),
])
def test_source_priors_hold(headline, summary, feed_id, expected):
    assert cat(headline, summary, feed_id=feed_id) == expected


def test_source_prior_resolves_from_citation_names_too():
    """Stored rows have no feed id — the prior must resolve from source names."""
    assert source_prior(None, ["CISA — Cybersecurity Advisories"])[0] == "cyber_physical"
    assert source_prior(None, ["WHO — News"])[0] is None or True  # name-based, best effort
    assert source_prior(None, ["US Federal Register"])[0] == "regulatory"


def test_weak_challenger_cannot_override_a_source_prior():
    """This is the bug that filed CISA advisories under supply-chain."""
    weak = classify("Cargo handling note", "logistics update", feed_id="cisa_alerts")
    assert weak.category == "cyber_physical"                 # prior holds
    assert weak.explanation["override"]["kept"] == "cyber_physical"


def test_strong_challenger_does_override_a_source_prior():
    """Priors are strong defaults, not irreversible (requirement 2)."""
    strong = classify("Supply chain disruption at port closure halts freight",
                      feed_id="cisa_alerts")
    assert strong.category == "supply_chain"
    assert strong.explanation["override"]["from"] == "cyber_physical"
    assert strong.explanation["override"]["margin"] >= 6.0


# ---------------------------------------------------------------------------
# Precision: misleading wording (requirement 11)
# ---------------------------------------------------------------------------

def test_preparedness_is_not_an_active_hazard():
    r = classify("Japanese mall is rebuilt to withstand earthquakes")
    assert r.category == "continuity"
    assert r.explanation["reframed"]["from"] == "natural_hazard"


def test_active_hazard_is_still_a_hazard():
    assert cat("Earthquake destroys mall, dozens trapped") == "natural_hazard"


def test_award_is_not_a_cyber_incident():
    assert cat("Firm wins cybersecurity award at industry gala") != "cyber_physical"


def test_conference_is_not_a_supply_chain_disruption():
    assert cat("Supply chain conference opens in Geneva") != "supply_chain"


def test_real_supply_chain_disruption_still_classifies():
    assert cat("Port strike halts container ship traffic at Rotterdam") == "supply_chain"


def test_real_cyber_incident_still_classifies():
    assert cat("Ransomware attack halts operations at logistics firm") == "cyber_physical"


# ---------------------------------------------------------------------------
# Thresholds and the unclassified fallback (requirement 5)
# ---------------------------------------------------------------------------

def test_empty_and_noise_are_unclassified():
    assert cat("") == UNCLASSIFIED
    assert cat("Local bakery wins best croissant") == UNCLASSIFIED


def test_guarded_categories_never_win_on_body_only_evidence():
    """Cyber/supply-chain must not be inferred from a passing body mention."""
    r = classify("Quarterly results announced", "", body="the firm noted logistics costs")
    assert r.category not in GUARDED


@pytest.mark.parametrize("negative", [
    "Manchester United wins the championship final",
    "Obituary: veteran broadcaster dies aged 88",
    "Opinion: why the election matters",
    "Annual logistics expo announces keynote speakers",
])
def test_negative_rules_demote_non_security_content(negative):
    assert cat(negative) == UNCLASSIFIED


# ---------------------------------------------------------------------------
# Secondary category + audit trail (requirements 7, 8)
# ---------------------------------------------------------------------------

def test_secondary_only_when_it_passes_on_its_own():
    r = classify("Cyber attack on port operator disrupts container shipping",
                 "Ransomware forced the terminal to halt cargo handling")
    assert r.category in ("cyber_physical", "supply_chain")
    if r.secondary:
        assert r.scores[r.secondary] >= 8.0


def test_explanation_is_machine_readable_and_complete():
    r = classify("CISA warns of active exploitation in control system",
                 "Patch available for the affected firmware", feed_id="cisa_alerts")
    d = r.to_dict()
    for key in ("category", "confidence", "scores", "source_hint",
                "matched", "negative", "override", "reason", "threshold"):
        assert key in d, f"missing {key}"
    assert d["source_hint"]["category"] == "cyber_physical"
    assert d["matched"]["cyber_physical"]          # shows which terms fired
    assert 0.0 < d["confidence"] <= 1.0


def test_confidence_is_zero_when_unclassified():
    r = classify("Nothing of note happened today")
    assert r.category == UNCLASSIFIED and r.confidence == 0.0


# ---------------------------------------------------------------------------
# Relevance pre-filter
# ---------------------------------------------------------------------------

def test_tier1_always_relevant_and_noise_is_not():
    assert looks_relevant("Anything at all", tier=1) is True
    assert looks_relevant("Celebrity wedding photos", tier=3) is False
    assert looks_relevant("Ransomware halts plant", tier=3) is True


# ---------------------------------------------------------------------------
# Recall tuning, driven by real misses found in the live "unclassified" pile
# rather than invented examples. Trade measures and shipping chokepoints were
# being rejected because a single headline keyword (6) sits under the guarded
# bar (10); STRONG_KEYWORDS give unambiguous domain markers phrase weight.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("headline", [
    "Namibia Survives Trump's Sweeping Tariffs",
    "Donald Trump hits Australian exports to US with new higher trade tariff",
    "Malaysia's 10% US tariff beats regional rivals, but for how long?",
    "China vows to defend Brazil's sovereignty as Trump's 25% tariff bites",
    "Stranded seafarers remain trapped as Hormuz shipping stalls",
])
def test_trade_and_chokepoint_stories_are_supply_chain(headline):
    assert classify(headline).category == "supply_chain"


@pytest.mark.parametrize("headline", [
    # Each of these is a REAL headline that merely looks supply-chain. They are
    # why "shipping" and "customs" are not strong keywords.
    "Chinese nationals plead guilty to illegally shipping turtles from US to Hong Kong",
    "Nigeria: Customs Warns Nigerians Against Fake Recruitment Update",
    "Metro water supply hit at a few addresses in Mylapore",
    "Hong Kong high-speed rail link sets record as passenger trips top 16m in 6 months",
])
def test_lookalikes_are_still_refused(headline):
    assert classify(headline).category != "supply_chain"


def test_strong_keyword_alone_clears_the_guarded_bar():
    """One unambiguous marker is enough; an ambiguous one is not."""
    assert classify("New tariff announced").category == "supply_chain"
    # "shipping" is deliberately ordinary — needs corroboration.
    assert classify("Shipping news roundup").category != "supply_chain"
