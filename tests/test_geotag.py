"""Country-mention geo-tagging (extractor + backfill)."""

from __future__ import annotations

from gsid import db
from gsid.taxonomy import mentioned_countries, subject_countries


def test_extracts_subject_countries():
    codes = mentioned_countries("Yemen's Houthis attack Saudi tanker as US launches Iran strikes")
    assert codes == ["us", "ye", "sa", "ir"]  # US first (abbr), then by mention order


def test_word_boundaries_avoid_false_matches():
    # 'Niger' must not swallow 'Nigeria' (and vice-versa); both are present here.
    assert set(mentioned_countries("Niger coup; Nigeria sanctions")) == {"ne", "ng"}
    # 'Mali'/'Oman' not matched inside 'Somalia'/'Romania'
    assert mentioned_countries("Somalia drought") == ["so"]
    assert mentioned_countries("Romania election") == ["ro"]


def test_us_uk_case_sensitive_not_pronoun():
    assert mentioned_countries("Please contact us about the deal") == []
    assert "us" in mentioned_countries("US and UK issue joint statement")
    assert "gb" in mentioned_countries("US and UK issue joint statement")


def test_empty_and_none():
    assert mentioned_countries("") == []
    assert mentioned_countries(None) == []


def test_subject_countries_prefers_headline_over_roundup_body():
    # A roundup about India that name-drops Iran/Spain in the body must NOT be
    # tagged to Iran — the headline decides aboutness.
    head = "Monday briefing: How the Cockroach protests exposed cracks in India's government"
    body = "Elsewhere: strikes near Iran; markets in Spain; France reacts."
    assert subject_countries(head, body) == ["in"]
    # When the headline names no country, fall back to the body.
    assert set(subject_countries("Middle East crisis deepens", "Iran and Israel trade fire")) == {"ir", "il"}


def test_backfill_retags_and_is_idempotent(conn):
    # A story mis-tagged to its publisher (gb) but clearly about Iran/Yemen.
    conn.execute(
        "INSERT INTO story(id,headline,summary,category,primary_country,primary_region,"
        "first_seen,last_updated,status) VALUES "
        "('s_ir','US strikes Iran as Yemen conflict widens','Escalation across the region.',"
        "'geopolitical','gb','europe','t','t','developing')")
    conn.execute("INSERT INTO story_country(story_id,country) VALUES ('s_ir','gb')")
    # Clear the one-shot marker so the backfill runs on this test DB.
    conn.execute("DELETE FROM preference WHERE key='country_retag_v2'")
    conn.commit()

    db._backfill_country_tags(conn)

    tagged = {r["country"] for r in conn.execute(
        "SELECT country FROM story_country WHERE story_id='s_ir'")}
    assert "ir" in tagged and "ye" in tagged and "us" in tagged
    assert "gb" not in tagged  # publisher tag rebuilt away
    prim = conn.execute("SELECT primary_country FROM story WHERE id='s_ir'").fetchone()[0]
    assert prim == "us"  # lead subject

    # Idempotent: marker set, a second run is a no-op.
    assert conn.execute("SELECT 1 FROM preference WHERE key='country_retag_v2'").fetchone()
    db._backfill_country_tags(conn)
    assert {r["country"] for r in conn.execute(
        "SELECT country FROM story_country WHERE story_id='s_ir'")} == tagged


def test_advisory_stories_left_untouched(conn):
    conn.execute(
        "INSERT INTO story(id,headline,summary,category,primary_country,first_seen,"
        "last_updated,status) VALUES "
        "('s_adv','Travel advisory: France','FCDO advises against travel to Iran regions.',"
        "'geopolitical','fr','t','t','advisory')")
    conn.execute("INSERT INTO story_country(story_id,country) VALUES ('s_adv','fr')")
    conn.execute("DELETE FROM preference WHERE key='country_retag_v2'")
    conn.commit()

    db._backfill_country_tags(conn)

    # Advisory keeps its destination tag; not re-tagged from the text mention.
    assert {r["country"] for r in conn.execute(
        "SELECT country FROM story_country WHERE story_id='s_adv'")} == {"fr"}
