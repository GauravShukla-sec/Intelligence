"""Global search: term handling and regulatory coverage.

From QA: searching "NIS2" returned nothing although a full NIS2 record existed
in the Regulatory Tracker, and the nonsense query "zzzz-no-match" returned
three unrelated stories.
"""

from __future__ import annotations

from gsid import db


def _story(conn, sid, headline, summary=""):
    conn.execute(
        "INSERT INTO story(id,headline,summary,category,first_seen,last_updated) "
        "VALUES (?,?,?,'geopolitical','t','t')", (sid, headline, summary))
    db.reindex_story_fts(conn, sid)


def test_all_terms_must_match(conn):
    """OR-joining terms made a nonsense query match on common words."""
    _story(conn, "s1", "Port strike halts container traffic")
    _story(conn, "s2", "No match expected here")
    conn.commit()

    # "no" and "match" each appear somewhere, but the whole phrase does not.
    assert db.search_stories(conn, "zzzz-no-match") == []
    # A genuine multi-term query still works when every term is present.
    assert "s1" in db.search_stories(conn, "port container")
    # ...and fails when only some terms are present.
    assert "s1" not in db.search_stories(conn, "port bicycle")


def test_single_term_search_still_works(conn):
    _story(conn, "s3", "Ransomware halts plant operations")
    conn.commit()
    assert "s3" in db.search_stories(conn, "ransomware")


def test_regulations_are_searchable(conn):
    """The regulatory tracker used to be invisible to global search."""
    hits = db.search_regulations(conn, "NIS2")
    assert hits, "NIS2 is seeded but search returned nothing"
    assert hits[0]["framework"] == "NIS2"       # exact framework match leads


def test_regulation_search_requires_all_terms(conn):
    assert db.search_regulations(conn, "zzzz-no-match") == []


def test_regulation_search_is_case_insensitive(conn):
    assert db.search_regulations(conn, "gdpr")
    assert db.search_regulations(conn, "GDPR")


def test_search_endpoint_returns_both_sections(client):
    res = client.get("/api/search?q=NIS2")
    assert res.status_code == 200
    body = res.get_json()
    assert "stories" in body and "regulations" in body
    assert any(r["framework"] == "NIS2" for r in body["regulations"])
