"""Watchlist exposure — a layer ON TOP of relevance, never a replacement."""

from __future__ import annotations

from gsid import watchlist
from gsid.repository import list_stories, load_preferences

PREFS = {
    "countries": ["ke", "de"],
    "topics": ["cargo theft", "civil unrest"],
    "sites": ["Mombasa Plant"],
    "travel_destinations": ["Nairobi"],
    "regulations": ["NIS2"],
    "industries": ["logistics"],
}


def test_country_match_is_explained_by_name_not_code():
    r = watchlist.match({"headline": "Protests spread", "primary_country": "ke"}, PREFS)
    assert r["score"] == watchlist.W_COUNTRY
    assert r["matched"]["countries"] == ["ke"]
    assert "Kenya" in r["reasons"][0]        # readable, not "ke"


def test_matches_accumulate_across_kinds():
    r = watchlist.match({
        "headline": "Cargo theft ring hits Mombasa Plant",
        "summary": "NIS2 reporting may apply.",
        "primary_country": "ke",
    }, PREFS)
    kinds = set(r["matched"])
    assert {"countries", "topics", "sites", "regulations"} <= kinds
    assert r["score"] >= (watchlist.W_COUNTRY + watchlist.W_TOPIC
                          + watchlist.W_SITE + watchlist.W_REGULATION)


def test_no_watchlist_overlap_scores_zero_and_says_nothing():
    r = watchlist.match({"headline": "Snowfall closes Alpine passes",
                         "primary_country": "at"}, PREFS)
    assert r["score"] == 0 and r["reasons"] == []


def test_matching_is_word_boundary_not_substring():
    # The classifier bug in reverse: "chip" must not match "microchipped".
    prefs = {"topics": ["chip"]}
    assert watchlist.match({"headline": "Dog was microchipped"}, prefs)["score"] == 0
    assert watchlist.match({"headline": "Chip shortage hits plants"}, prefs)["score"] > 0


def test_topic_matches_are_capped():
    """One keyword-stuffed story must not dominate the ordering."""
    prefs = {"topics": [f"topic{i}" for i in range(10)]}
    text = " ".join(f"topic{i}" for i in range(10))
    r = watchlist.match({"headline": text}, prefs)
    assert len(r["matched"]["topics"]) == watchlist.MAX_TOPIC_MATCHES


def test_empty_watchlist_is_inert():
    r = watchlist.match({"headline": "Anything at all", "primary_country": "ke"}, {})
    assert r["score"] == 0 and r["reasons"] == []


# ---- integration: exposure must not disturb the published score -------------

def _add(conn, sid, headline, country, score):
    conn.execute(
        "INSERT INTO story(id,headline,category,first_seen,last_updated,"
        "primary_country,relevance_score,is_demo) VALUES (?,?,'geopolitical','t','t',?,?,0)",
        (sid, headline, country, score))
    conn.execute("INSERT INTO story_country(story_id,country) VALUES (?,?)", (sid, country))


def test_watchlist_sort_promotes_exposure_without_changing_scores(conn):
    conn.execute("DELETE FROM story")
    conn.execute("DELETE FROM story_country")
    # Low objective score but ON the watchlist; high score but irrelevant to us.
    _add(conn, "s_ours", "Unrest near our Kenyan site", "ke", 30)
    _add(conn, "s_big", "Major incident elsewhere", "au", 90)
    conn.execute("INSERT OR REPLACE INTO preference(key,value) VALUES "
                 "('countries','[\"ke\"]'),('topics','[]'),('sites','[]'),"
                 "('travel_destinations','[]'),('regulations','[]'),('industries','[]')")
    conn.commit()

    default_order = [s["id"] for s in list_stories(conn, {"data_mode": "live"})]
    assert default_order == ["s_big", "s_ours"]      # objective model unchanged

    ours = [s for s in list_stories(conn, {"sort": "watchlist", "data_mode": "live"})]
    assert [s["id"] for s in ours] == ["s_ours", "s_big"]
    # The published score is untouched — only the ordering differs.
    assert {s["id"]: s["relevance_score"] for s in ours} == {"s_ours": 30, "s_big": 90}
    assert ours[0]["watchlist"]["score"] > 0 and ours[1]["watchlist"]["score"] == 0


def test_load_preferences_decodes_json_and_scalars(conn):
    prefs = load_preferences(conn)
    assert isinstance(prefs.get("countries"), list)
    assert isinstance(prefs.get("risk_tolerance"), str)
