"""Regression tests for advisory -> destination matching.

Every case here comes from a QA finding: selecting United States in Travel Risk
showed "Level 4 — Do not travel" built from ~20 advisories about *other*
destinations, because an advisory whose destination couldn't be parsed was
tagged to the issuing government instead.
"""

from __future__ import annotations

from gsid import db
from gsid.taxonomy import advisory_country_text, advisory_destination


# ---- destination parsing ----------------------------------------------------

def test_us_state_naming_variants_resolve():
    cases = {
        "Turks and Caicos Islands - Level 2: Exercise Increased Caution": "tc",
        "Burma - Level 4: Do Not Travel": "mm",
        "The Kyrgyz Republic - Level 1: Exercise Normal Precautions": "kg",
        "Sao Tome and Principe - Level 2: Exercise Increased Caution": "st",
        "French Guiana Travel Advisory": "gf",
        "Cabo Verde - Level 1": "cv",
        "Mainland China, Hong Kong & Macau - See Summaries - Level 2": "cn",
    }
    for title, expected in cases.items():
        assert advisory_destination(title) == expected, title


def test_us_abbreviation_does_not_hijack_destination():
    # "U.S. Virgin Islands" must be the Virgin Islands, not the United States.
    assert advisory_destination("U.S. Virgin Islands - Level 2: Exercise Increased Caution") == "vi"


def test_normalized_headline_keeps_its_destination():
    # Our own stored form. Splitting on ':' from the left yields the LABEL and
    # would wipe the destination off ~200 advisories.
    assert advisory_country_text("Travel advisory: Thailand") == "Thailand"
    assert advisory_destination("Travel advisory: Thailand") == "th"
    assert advisory_destination("Travel advisory: United States") == "us"


def test_non_country_advisories_resolve_to_nothing():
    # Better untagged than wrongly tagged: these must not land on any country.
    assert advisory_destination("Worldwide Caution") is None
    assert advisory_destination("") is None
    assert advisory_destination(None) is None


# ---- repair backfill --------------------------------------------------------

def _advisory(conn, sid, headline, tags):
    conn.execute(
        "INSERT INTO story(id,headline,category,first_seen,last_updated,status) "
        "VALUES (?,?,'geopolitical','t','t','advisory')", (sid, headline))
    for c in tags:
        conn.execute("INSERT INTO story_country(story_id,country) VALUES (?,?)", (sid, c))


def test_retag_moves_advisories_off_the_publisher(conn):
    # Exactly the reported corruption: a US State advisory about Burma tagged 'us'.
    _advisory(conn, "a_burma", "Burma - Level 4: Do Not Travel", ["us"])
    # A correctly stored advisory must be left intact, not wiped.
    _advisory(conn, "a_thai", "Travel advisory: Thailand", ["th"])
    # Unresolvable destination: the wrong tag is cleared rather than kept.
    _advisory(conn, "a_world", "Worldwide Caution", ["us"])
    conn.execute("DELETE FROM preference WHERE key='advisory_retag_v1'")
    conn.commit()

    db._retag_advisories(conn)

    def tags(sid):
        return {r["country"] for r in conn.execute(
            "SELECT country FROM story_country WHERE story_id=?", (sid,))}

    assert tags("a_burma") == {"mm"}   # re-pointed to the destination
    assert tags("a_thai") == {"th"}    # untouched
    assert tags("a_world") == set()    # cleared, not left on the publisher

    # Idempotent: the marker stops a second pass.
    assert conn.execute(
        "SELECT 1 FROM preference WHERE key='advisory_retag_v1'").fetchone()


def test_us_brief_is_not_built_from_other_destinations(conn):
    """The end-to-end symptom: US must not inherit a Level 4 from elsewhere."""
    from gsid.repository import travel_brief
    _advisory(conn, "a_burma2", "Burma - Level 4: Do Not Travel", ["us"])
    conn.execute("UPDATE story SET advisory_level=4 WHERE id='a_burma2'")
    conn.execute("DELETE FROM preference WHERE key='advisory_retag_v1'")
    conn.commit()

    db._retag_advisories(conn)
    conn.commit()

    us = travel_brief(conn, "us")
    assert all("Burma" not in a["headline"] for a in us["advisories"])
    assert us.get("advisory_consensus", 0) != 4
