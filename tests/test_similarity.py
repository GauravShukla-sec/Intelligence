"""Read-time near-duplicate collapse + related-story suggestions."""

from __future__ import annotations

from gsid.repository import group_similar_stories, related_stories


def _s(sid, headline, score=10):
    return {"id": sid, "headline": headline, "relevance_score": score,
            "primary_country": "xx", "location_text": ""}


def test_group_collapses_near_duplicates_keeps_distinct():
    stories = [
        _s("a", "Thousands flee wildfires in France and Spain as temperatures rise", 40),
        _s("b", "Thousands flee wildfires in France as temperatures reach record", 30),
        _s("c", "Cyberattack disrupts port operations in Rotterdam", 25),
    ]
    grouped = group_similar_stories(stories)
    assert len(grouped) == 2                       # a+b collapsed, c distinct
    lead = next(g for g in grouped if g["id"] == "a")
    assert [x["id"] for x in lead["similar"]] == ["b"]
    assert lead["relevance_score"] == 40           # highest-ranked stays the lead
    assert next(g for g in grouped if g["id"] == "c")["similar"] == []


def test_group_lead_is_first_in_order():
    # Input is pre-ordered; the first member of a group leads.
    stories = [
        _s("hi", "Port strike halts Rotterdam container operations", 50),
        _s("lo", "Rotterdam container operations halted by port strike", 20),
    ]
    grouped = group_similar_stories(stories)
    assert len(grouped) == 1 and grouped[0]["id"] == "hi"
    assert grouped[0]["similar"][0]["id"] == "lo"


def test_related_stories_ranks_by_headline_similarity(conn):
    from gsid.analysis.heuristic import HeuristicAnalyzer
    from gsid.store import DraftClaim, DraftSource, StoryDraft, save_story
    a = HeuristicAnalyzer()

    def mk(sid, headline):
        return save_story(conn, StoryDraft(
            story_id=sid, headline=headline, body=headline, category="geopolitical",
            primary_country="ir", countries=["ir"],
            sources=[DraftSource(name="Wire", url="https://ex.org/" + sid, tier=2)],
            claims=[DraftClaim(text=headline, source_index=0)]), a)

    target = mk("t", "US launches new strikes on Iran nuclear sites")
    mk("r1", "US strikes on Iran nuclear infrastructure widen the conflict")
    mk("r2", "Wildfires spread across southern Europe amid heatwave")

    rel = related_stories(conn, target)
    ids = [r["id"] for r in rel]
    assert "r1" in ids and "r2" not in ids         # topical match only
    assert target not in ids                        # never returns itself
    assert all(0 <= r["similarity"] <= 1 for r in rel)
