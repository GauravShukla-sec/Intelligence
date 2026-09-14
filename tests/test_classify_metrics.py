"""Labeled evaluation set + precision/recall gate.

Holds the classifier to measurable quality rather than anecdote. The set is
deliberately precision-weighted: it contains the audit's false positives, the
misleading-wording cases, and ordinary security news that must still classify.

`None` as the label means "must NOT be confidently classified" — the correct
answer is `unclassified`. A tuple of categories marks a genuinely ambiguous
item where more than one domain is defensible (e.g. an armed attack is both
geopolitical and physical security); any member counts as correct, and the
first is used as the canonical label for per-category accounting. Ambiguity is
only allowed where the *safety* requirement still holds unambiguously — these
items must still never land in a guarded category.
"""

from __future__ import annotations

from collections import defaultdict

import pytest

from gsid.ingestion.classify import UNCLASSIFIED, classify

# (headline, summary, feed_id, source_names, expected_category_or_None)
Label = "str | tuple[str, ...] | None"
DATASET: list[tuple] = [
    # ---- cyber / OT (must classify) ----
    ("Schneider Electric IGSS", "Multiple vulnerabilities allow remote code execution",
     "cisa_alerts", (), "cyber_physical"),
    ("ABB KNX products", "Command injection vulnerability in the web interface",
     "cisa_alerts", (), "cyber_physical"),
    ("CISA Adds Two Known Exploited Vulnerabilities to Catalog", "",
     "cisa_alerts", (), "cyber_physical"),
    ("Ransomware attack halts operations at logistics firm", "", None, (),
     "cyber_physical"),
    ("Threat actor exploits zero-day in control system", "", None, (),
     "cyber_physical"),
    ("Data breach exposes customer records", "", None, (), "cyber_physical"),

    # ---- cyber false positives (must NOT be cyber) ----
    # Both defensible; the hard requirement is only that neither is cyber.
    ("BRICS diplomacy summit deepens trade ties", "", None, (),
     ("geopolitical", "economic_social")),
    ("Sudan drone attack kills dozens in Darfur", "", None, (),
     ("geopolitical", "physical_corporate")),
    ("Medical drone delivery expands in Rwanda", "", None, (), None),
    ("Avalanche kills three climbers in the Alps", "", None, (), "natural_hazard"),
    ("Demographic commentary on an ageing population", "", None, (), None),
    ("Firm wins cybersecurity award at industry gala", "", None, (), None),

    # ---- supply chain (must classify) ----
    ("Port strike halts container ship traffic at Rotterdam", "", None, (),
     "supply_chain"),
    ("Supply chain disruption after port closure", "", None, (), "supply_chain"),
    ("Cargo theft ring targets freight depots", "", None, (), "supply_chain"),

    # ---- supply chain false positives ----
    ("Supply chain conference opens in Geneva", "", None, (), None),
    ("Officials reported an important policy change", "", None, (), None),
    ("WHO issues new dementia care guidelines", "Clinical guidelines for health workers",
     "who_news", (), "health"),

    # ---- health ----
    ("Africa CDC reports new Ebola cases", "", None, ("Africa CDC",), "health"),
    ("Cholera outbreak spreads in the capital", "", None, (), "health"),
    ("Measles vaccination campaign launched", "", None, (), "health"),

    # ---- regulatory ----
    ("Homeland Security final rule on cargo screening", "", "us_fedreg_dhs", (),
     "regulatory"),
    ("New data protection regulation enters into force", "", None, (), "regulatory"),
    ("Federal Register notice on export control", "", None, ("US Federal Register",),
     "regulatory"),

    # ---- natural hazard vs preparedness ----
    ("Earthquake destroys mall, dozens trapped", "", None, (), "natural_hazard"),
    ("Japanese mall is rebuilt to withstand earthquakes", "", None, (), "continuity"),
    ("Floods displace thousands in Pakistan", "", None, (), "natural_hazard"),
    ("Tropical cyclone makes landfall", "", None, (), "natural_hazard"),

    # ---- geopolitical ----
    ("Air strikes reported across the border region", "", None, (), "geopolitical"),
    ("Ceasefire talks resume between the two states", "", None, (), "geopolitical"),

    # ---- physical / corporate ----
    ("Police crackdown on protesters in the capital", "", None, (),
     "physical_corporate"),
    ("Armed robbery at a distribution warehouse", "", None, (), "physical_corporate"),

    # ---- economic / social ----
    ("Oil prices hit $100 for the first time since May", "", None, (),
     "economic_social"),
    ("Workers begin general strike over pay", "", None, (), "economic_social"),

    # ---- must be unclassified (noise) ----
    ("Manchester United wins the championship final", "", None, (), None),
    ("Obituary: veteran broadcaster dies aged 88", "", None, (), None),
    ("Opinion: why the election matters", "", None, (), None),
    ("Local bakery wins best croissant", "", None, (), None),
    ("Annual logistics expo announces keynote speakers", "", None, (), None),
]


def _accepted(expected) -> tuple[str, ...]:
    if expected is None:
        return (UNCLASSIFIED,)
    if isinstance(expected, tuple):
        return expected
    return (expected,)


def _run() -> list[tuple[tuple[str, ...], str, str]]:
    """Returns (accepted_categories, predicted, headline) for every row."""
    out = []
    for headline, summary, feed_id, names, expected in DATASET:
        got = classify(headline, summary, feed_id=feed_id, source_names=names).category
        out.append((_accepted(expected), got, headline))
    return out


def compute_metrics() -> tuple[dict, float]:
    """Per-category precision/recall/F1 plus overall accuracy."""
    results = _run()
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    correct = 0
    for accepted, got, _ in results:
        if got in accepted:
            correct += 1
            tp[got] += 1
        else:
            fp[got] += 1
            fn[accepted[0]] += 1
    metrics = {}
    for c in sorted(set(list(tp) + list(fp) + list(fn))):
        p = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0
        r = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        metrics[c] = {"precision": round(p, 3), "recall": round(r, 3),
                      "f1": round(f1, 3), "support": tp[c] + fn[c]}
    return metrics, correct / len(results)


def test_no_regression_on_known_false_positives():
    """Every audit false positive must be fixed — this list may not grow."""
    failures = [(h, a, g) for a, g, h in _run() if g not in a]
    assert not failures, "misclassified:\n" + "\n".join(
        f"  {h[:60]!r}: expected {'|'.join(a)}, got {g}" for h, a, g in failures)


def test_guarded_categories_have_perfect_precision():
    """Cyber and supply-chain must never be asserted wrongly (requirement 5)."""
    metrics, _ = compute_metrics()
    for c in ("cyber_physical", "supply_chain"):
        if c in metrics:
            assert metrics[c]["precision"] == 1.0, (
                f"{c} precision {metrics[c]['precision']} — a wrong confident "
                f"assertion is worse than 'unclassified'")


def test_overall_accuracy_gate():
    _, accuracy = compute_metrics()
    assert accuracy >= 0.90, f"accuracy {accuracy:.2f} below gate"


if __name__ == "__main__":  # pragma: no cover - manual report
    metrics, accuracy = compute_metrics()
    print(f"{'category':<20} {'prec':>6} {'recall':>7} {'f1':>6} {'n':>4}")
    for c, m in metrics.items():
        print(f"{c:<20} {m['precision']:>6.2f} {m['recall']:>7.2f} "
              f"{m['f1']:>6.2f} {m['support']:>4}")
    print(f"\noverall accuracy: {accuracy:.1%} on {len(DATASET)} labeled items")


# --------------------------------------------------------------------------
# Lexicon matching: the analyzer used plain `term in text`, so any word that
# merely contained a keyword scored full marks for that dimension.
# --------------------------------------------------------------------------
class TestLexiconWordBoundaries:
    """Substring matching inflated nearly every score in the corpus.

    "reported" contains "port", so every story that reported anything scored
    15/15 for supply-chain disruption — 32% of stories hit full marks on that
    dimension. Fixing it dropped that to 7%.
    """

    @pytest.mark.parametrize("word, dimension", [
        ("reported", "supply_chain"),     # port
        ("important", "supply_chain"),    # import, port
        ("support", "supply_chain"),      # port
        ("transport", "supply_chain"),    # port
        ("deadline", "people_safety"),    # dead
        ("politics", "cyber_physical"),   # ics
        ("economics", "cyber_physical"),  # ics
        ("couple", "geopolitical"),       # coup
        ("toward", "geopolitical"),       # war
        ("billion", "regulatory"),        # bill
        ("lawyer", "regulatory"),         # law
        ("website", "facility_assets"),   # site
    ])
    def test_innocent_word_does_not_fire(self, word, dimension):
        from gsid.analysis.heuristic import _LEX_RE, _score_dimension
        assert _score_dimension(word, _LEX_RE[dimension]) == 0.0

    @pytest.mark.parametrize("text, dimension", [
        ("ports closed after storm", "supply_chain"),
        ("imports halted at the border", "supply_chain"),
        ("casualties confirmed", "people_safety"),
        ("dozens injured in clashes", "people_safety"),
        ("a coup attempt", "geopolitical"),
        ("ransomware hit the control system", "cyber_physical"),
    ])
    def test_real_terms_still_fire(self, text, dimension):
        from gsid.analysis.heuristic import _LEX_RE, _score_dimension
        assert _score_dimension(text, _LEX_RE[dimension]) > 0.0

    def test_stems_still_match_inflections(self):
        """A trailing '*' marks a deliberate stem and must keep matching."""
        from gsid.analysis.heuristic import _LEX_RE, _score_dimension
        for word in ("casualty", "casualties", "fatalities", "evacuated"):
            assert _score_dimension(word, _LEX_RE["people_safety"]) > 0.0


class TestFactCheckDamping:
    def test_debunk_scores_far_below_the_real_event(self):
        """A fact-check quotes the event it debunks, so it lights the same terms."""
        from gsid.analysis.base import AnalysisInput
        from gsid.analysis.heuristic import HeuristicAnalyzer
        from gsid.scoring import score_relevance

        analyzer = HeuristicAnalyzer()

        def score(headline):
            r = analyzer.analyze(AnalysisInput(
                headline=headline, body="", category="",
                location_text="", sources=[]))
            return score_relevance(r.signals).total

        real = score("Drone attack on ships in Egypt kills three")
        fake = score("No, this video does not show a drone attack on ships in Egypt")
        assert fake < real

    def test_real_story_about_deepfakes_is_not_damped(self):
        """"AI-generated" was tried as a cue and dropped — it caught arrests."""
        from gsid.analysis.heuristic import _DEBUNK
        assert not _DEBUNK.search(
            "Police nab scammer who circulated AI-generated deep fakes")


class TestFigurativeUsage:
    """The strongest people-safety terms are meaningless used figuratively."""

    @pytest.mark.parametrize("text", [
        "RSL says the slur was an attack on every veteran's service",
        "Russians on the Goethe-Institut: hostage to politics",
        "The ruling is an attack on democracy",
        "An attack on the freedom of the press",
    ])
    def test_figurative_does_not_fire(self, text):
        from gsid.analysis.heuristic import _LEX_RE, _score_dimension
        assert _score_dimension(text.lower(), _LEX_RE["people_safety"]) == 0.0

    @pytest.mark.parametrize("text", [
        "attack on a police station",
        "attack on rail services in Kyiv",
        "gunman took three hostages",
        "hostages released after standoff",
    ])
    def test_literal_still_fires(self, text):
        from gsid.analysis.heuristic import _LEX_RE, _score_dimension
        assert _score_dimension(text.lower(), _LEX_RE["people_safety"]) > 0.0
