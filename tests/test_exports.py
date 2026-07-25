"""Export generator tests."""

from __future__ import annotations

import csv
import io

from gsid import exports, repository


def test_risk_register_entry_fields(conn):
    s = repository.get_story(conn, "demo_redsea_transit")
    entry = exports.risk_register_entry(s)
    for field in ["risk_title", "threat", "vulnerability", "likelihood", "impact",
                  "inherent_risk", "residual_risk", "treatment_strategy",
                  "monitoring_indicators", "sources", "last_reviewed"]:
        assert field in entry
    assert isinstance(entry["inherent_risk"], int)
    assert entry["residual_risk"] <= entry["inherent_risk"]
    assert "[DEMO]" not in entry["risk_title"]  # cleaned


def test_email_leadership_is_text(conn):
    s = repository.get_story(conn, "demo_redsea_transit")
    txt = exports.email_leadership(s)
    assert "Subject:" in txt and "Recommended actions:" in txt


def test_stories_csv_parseable(conn):
    rows = repository.list_stories(conn, {}, limit=20)
    out = exports.stories_to_csv(rows)
    parsed = list(csv.DictReader(io.StringIO(out)))
    assert len(parsed) == len(rows)
    assert "relevance_score" in parsed[0]


def test_risk_register_csv(conn):
    s = repository.get_story(conn, "demo_redsea_transit")
    out = exports.risk_register_csv([exports.risk_register_entry(s)])
    assert "risk_title" in out.splitlines()[0]


def test_unknown_export_raises(conn):
    s = repository.get_story(conn, "demo_redsea_transit")
    try:
        exports.export_story(s, "nope")
        assert False, "should raise"
    except ValueError:
        pass
