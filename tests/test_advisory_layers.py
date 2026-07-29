"""Travel-advisory normalization (L1), consensus/divergence (L2),
change-detection (L3)."""

from __future__ import annotations

import json

from gsid.analysis.heuristic import HeuristicAnalyzer
from gsid.ingestion.advisory_levels import level_from_text
from gsid.repository import get_story
from gsid.store import DraftClaim, DraftSource, StoryDraft, save_story


# ---- Layer 1: normalization -------------------------------------------------

def test_level_from_text_per_government():
    L = level_from_text
    assert L("us_state_travel", "Mexico - Level 3: Reconsider Travel") == 3
    assert L("us_state_travel", "Japan - Level 1: Exercise Normal Precautions") == 1
    assert L("gov_uk_travel", "Ruritania", "FCDO advises against all travel to X") == 4
    assert L("gov_uk_travel", "Ruritania",
             "advises against all but essential travel to X") == 3
    assert L("au_smartraveller", "X", "Do not travel to this destination") == 4
    assert L("au_smartraveller", "X", "Exercise a high degree of caution") == 2
    assert L("gov_uk_travel", "X", "General information updated, no level given") == 0


# ---- helpers ----------------------------------------------------------------

def _advisory(gov_name, feed_id, country_code, level, url, title):
    """One government's advisory for a destination (merges by headline)."""
    return StoryDraft(
        headline="Travel advisory: Ruritania",  # shared dedup key across govts
        body=f"{title}",
        category="geopolitical",
        location_text="Ruritania",
        primary_country=country_code,
        countries=[country_code],
        status="advisory",
        sources=[DraftSource(name=gov_name, url=url, tier=1, source_type="government",
                             country=gov_country(gov_name),
                             title=title, advisory_level=level, feed_id=feed_id,
                             is_primary=True)],
        claims=[DraftClaim(text=title, claim_type="official_claim", source_index=0)],
    )


def gov_country(name):
    return {"US State Dept": "us", "Global Affairs Canada": "ca",
            "German FFO": "de"}.get(name, "us")


def _advisory_row(conn, story_id):
    row = conn.execute("SELECT advisory_level, advisory_json FROM story WHERE id=?",
                       (story_id,)).fetchone()
    return row["advisory_level"], json.loads(row["advisory_json"])


# ---- Layer 2: consensus + divergence ---------------------------------------

def test_consensus_is_worst_case_and_merges_governments(conn):
    a = HeuristicAnalyzer()
    sid = save_story(conn, _advisory("US State Dept", "us_state_travel", "ru", 4,
                                     "https://travel.state.gov/ruritania", "Do not travel"), a)
    # Canada, same destination, milder — must merge into the same story.
    sid2 = save_story(conn, _advisory("Global Affairs Canada", "ca_gac_travel", "ru", 3,
                                      "https://travel.gc.ca/destinations/ruritania",
                                      "Avoid non-essential travel"), a)
    assert sid2 == sid  # merged, not duplicated

    level, adv = _advisory_row(conn, sid)
    assert level == 4 and adv["consensus"] == 4        # worst case wins
    assert adv["lowest"] == 3 and adv["spread"] == 1
    assert adv["diverges"] is False
    govs = {s["gov"]: s["level"] for s in adv["sources"]}
    assert govs == {"us": 4, "ca": 3}


def test_divergence_flag_when_governments_disagree(conn):
    a = HeuristicAnalyzer()
    sid = save_story(conn, _advisory("US State Dept", "us_state_travel", "ru", 4,
                                     "https://travel.state.gov/ruritania", "Do not travel"), a)
    save_story(conn, _advisory("German FFO", "de_aa_travel", "ru", 2,
                               "https://auswaertiges-amt.de/ruritania",
                               "Increased caution"), a)
    _, adv = _advisory_row(conn, sid)
    assert adv["consensus"] == 4 and adv["lowest"] == 2
    assert adv["spread"] == 2 and adv["diverges"] is True
    # Exposed through the read API too.
    assert get_story(conn, sid)["advisory"]["diverges"] is True


# ---- Layer 3: change-detection ---------------------------------------------

def _state(conn, feed_id, dest="ru"):
    return conn.execute(
        "SELECT level, prev_level, changed_at, last_seen FROM advisory_state "
        "WHERE feed_id=? AND dest_country=?", (feed_id, dest)).fetchone()


def test_no_op_reingest_does_not_bump(conn):
    a = HeuristicAnalyzer()
    d = _advisory("US State Dept", "us_state_travel", "ru", 4,
                  "https://travel.state.gov/ruritania", "Do not travel")
    sid = save_story(conn, d, a)
    before = conn.execute("SELECT last_updated FROM story WHERE id=?", (sid,)).fetchone()[0]
    st_before = _state(conn, "us_state_travel")["changed_at"]

    save_story(conn, d, a)  # identical re-ingest
    after = conn.execute("SELECT last_updated FROM story WHERE id=?", (sid,)).fetchone()[0]
    st_after = _state(conn, "us_state_travel")["changed_at"]
    assert after == before          # no material change -> no freshness bump
    assert st_after == st_before    # changed_at unchanged


def test_level_change_on_stable_url_is_detected(conn):
    a = HeuristicAnalyzer()
    url = "https://travel.state.gov/ruritania"
    sid = save_story(conn, _advisory("US State Dept", "us_state_travel", "ru", 4, url,
                                     "Do not travel"), a)
    # Same URL, escalation reversed to level 3 — invisible to a URL-only check.
    save_story(conn, _advisory("US State Dept", "us_state_travel", "ru", 3, url,
                               "Reconsider travel"), a)

    cit = conn.execute("SELECT advisory_level FROM citation WHERE url=?", (url,)).fetchone()
    assert cit["advisory_level"] == 3          # citation updated in place
    st = _state(conn, "us_state_travel")
    assert st["level"] == 3 and st["prev_level"] == 4   # delta captured
    assert _advisory_row(conn, sid)[0] == 3    # consensus recomputed


# ---- stale internal-URL cleanup --------------------------------------------

def test_cleanup_dedupes_or_rewrites_tsg_aem_citations(conn):
    from gsid import db
    AEM = "https://travel.state.gov/content/tsg_aem/us/en/home/x.ita.html"
    GOOD = "https://travel.state.gov/content/travel/en/traveladvisories/x-travel-advisory.html"
    PUBLIC = "https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html"
    # Story A: has both a good citation and a stale AEM one -> AEM dropped.
    # Story B: AEM is its only citation -> rewritten to the public index.
    conn.execute("INSERT INTO story(id,headline,category,first_seen,last_updated) "
                 "VALUES ('sA','A','geopolitical','t','t'),('sB','B','geopolitical','t','t')")
    for cid, story, u in [("cA1", "sA", GOOD), ("cA2", "sA", AEM), ("cB1", "sB", AEM)]:
        conn.execute("INSERT INTO citation(id,story_id,url) VALUES (?,?,?)", (cid, story, u))
    conn.commit()

    db._cleanup_stale_citations(conn)

    assert conn.execute("SELECT COUNT(*) FROM citation WHERE url LIKE '%/tsg_aem/%'").fetchone()[0] == 0
    a_urls = {r["url"] for r in conn.execute("SELECT url FROM citation WHERE story_id='sA'")}
    assert a_urls == {GOOD}                                    # stale dropped, good kept
    b_urls = {r["url"] for r in conn.execute("SELECT url FROM citation WHERE story_id='sB'")}
    assert b_urls == {PUBLIC}                                  # orphan rewritten, not deleted


# ---- official links ---------------------------------------------------------

def test_official_links_cover_all_rating_governments():
    from gsid.repository import _official_advisory_links
    us_url = ("https://travel.state.gov/content/travel/en/traveladvisories/"
              "traveladvisories/italy-travel-advisory.html")
    advisories = [{"citations": [
        {"source_country": "ca", "url": "https://travel.gc.ca/destinations/italy"},
        {"source_country": "us", "url": us_url},
    ]}]
    links = _official_advisory_links("it", "Italy", None, advisories)
    names = " ".join(l["name"] for l in links)
    assert "UK FCDO" in names and "US State" in names   # baseline always present
    assert "Canada" in names                            # rating govt added
    assert "Germany" not in names and "Australia" not in names  # not rating Italy
    # US link uses the known-good ingested per-country URL, not a guess.
    us = next(l for l in links if "US State" in l["name"])
    assert us["url"] == us_url
