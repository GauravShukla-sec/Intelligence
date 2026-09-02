"""Re-analysis of stored stories with the currently configured analyzer."""

from __future__ import annotations

import json

from gsid.analysis.base import AnalysisResult
from gsid.analysis.heuristic import HeuristicAnalyzer
from gsid.reanalyze import reanalyze


class _StubLLM:
    """Stands in for a model-backed analyzer."""
    name = "openai"

    def __init__(self, provider="openai"):
        self.provider = provider
        self.calls = 0

    def analyze(self, item):
        self.calls += 1
        return AnalysisResult(
            signals={"people_safety": 1.0, "operational": 0.8},
            what_happened="model summary",
            why_your_work=["Model-specific action for " + item.headline[:20]],
            risk_pathway=["a", "b"], velocity="Fast", trend="Deteriorating",
            likelihood="Likely", provider=self.provider, model="stub-model")


def _story(conn, sid, provider="heuristic", score=50):
    conn.execute(
        "INSERT INTO story(id,headline,summary,category,first_seen,last_updated,"
        "relevance_score,impact,urgency,confidence,is_demo,analysis_json) "
        "VALUES (?,?,?,'geopolitical','t','t',?,'Moderate','7 Days','Moderate',0,?)",
        (sid, f"Headline {sid}", "Body text", score,
         json.dumps({"provider": provider, "why_your_work": ["old text"]})))


def test_reanalysis_rewrites_analysis_and_derived_scores(conn):
    conn.execute("DELETE FROM story")
    _story(conn, "s1")
    conn.commit()
    llm = _StubLLM()

    res = reanalyze(conn, llm, limit=10)

    assert res["updated"] == 1 and res["failed"] == 0
    row = conn.execute("SELECT analysis_json, relevance_score, urgency FROM story "
                       "WHERE id='s1'").fetchone()
    a = json.loads(row["analysis_json"])
    assert a["provider"] == "openai"
    assert "Model-specific action" in a["why_your_work"][0]
    # Derived fields are recomputed from the new signals, not left stale.
    assert row["relevance_score"] != 50


def test_only_provider_filters_so_reruns_resume(conn):
    """Re-running must pick up where the last run stopped, not redo everything."""
    conn.execute("DELETE FROM story")
    _story(conn, "done", provider="openai")
    _story(conn, "todo", provider="heuristic")
    conn.commit()
    llm = _StubLLM()

    reanalyze(conn, llm, limit=10, only_provider="heuristic")

    assert llm.calls == 1          # only the not-yet-upgraded story
    assert json.loads(conn.execute(
        "SELECT analysis_json FROM story WHERE id='todo'").fetchone()[0])["provider"] == "openai"


def test_a_failed_provider_call_leaves_the_story_untouched(conn):
    """A fallback result must not overwrite good stored analysis."""
    conn.execute("DELETE FROM story")
    _story(conn, "s1", provider="openai", score=77)
    conn.commit()
    before = conn.execute("SELECT analysis_json FROM story WHERE id='s1'").fetchone()[0]

    # Provider failed, so the analyzer returned heuristic output.
    res = reanalyze(conn, _StubLLM(provider="heuristic"), limit=10, only_provider=None)

    assert res["failed"] == 1 and res["updated"] == 0
    assert conn.execute("SELECT analysis_json FROM story WHERE id='s1'").fetchone()[0] == before


def test_dry_run_reports_without_writing(conn):
    conn.execute("DELETE FROM story")
    _story(conn, "s1")
    conn.commit()
    before = conn.execute("SELECT analysis_json FROM story WHERE id='s1'").fetchone()[0]

    res = reanalyze(conn, _StubLLM(), limit=10, dry_run=True)

    assert res["updated"] == 1 and res["dry_run"] is True
    assert conn.execute("SELECT analysis_json FROM story WHERE id='s1'").fetchone()[0] == before


def test_limit_bounds_the_work_for_rate_limited_tiers(conn):
    conn.execute("DELETE FROM story")
    for i in range(6):
        _story(conn, f"s{i}")
    conn.commit()
    llm = _StubLLM()

    res = reanalyze(conn, llm, limit=2)

    assert res["scanned"] == 2 and llm.calls == 2


def test_heuristic_analyzer_is_allowed_to_rewrite(conn):
    """The failure guard must not block a deliberate heuristic re-run."""
    conn.execute("DELETE FROM story")
    _story(conn, "s1")
    conn.commit()
    res = reanalyze(conn, HeuristicAnalyzer(), limit=5, only_provider=None)
    assert res["updated"] == 1 and res["failed"] == 0
