"""Critical Alerts qualification + ordering.

From QA findings: the page claimed "Newest first" but interleaved old reports,
and ~11% of all stories were flagged Critical — including Level-2 travel
advisories and a feature about earthquake-resistant architecture.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from gsid import db
from gsid.repository import list_alerts
from gsid.scoring import is_critical_alert


NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def _iso(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- qualification ----------------------------------------------------------

def test_travel_advisories_never_alert():
    # "Côte d'Ivoire - Level 2: Exercise Increased Caution" was Critical/Immediate.
    assert is_critical_alert(90, "Immediate", "Critical", "Confirmed",
                             status="advisory", event_time=_iso(0), now=NOW) is False


def test_weak_evidence_never_alerts():
    for conf in ("Unverified", "Low"):
        assert is_critical_alert(90, "Immediate", "Critical", conf,
                                 event_time=_iso(0), now=NOW) is False


def test_stale_events_do_not_alert():
    """'Prompt action' is meaningless for an event from months ago."""
    assert is_critical_alert(80, "Immediate", "Critical", "High",
                             event_time=_iso(0), now=NOW) is True
    assert is_critical_alert(80, "Immediate", "Critical", "High",
                             event_time=_iso(30), now=NOW) is False


def test_unknown_event_time_still_alerts():
    # Missing/unparseable timestamps must not silently suppress a live alert.
    assert is_critical_alert(80, "Immediate", "Critical", "High",
                             event_time=None, now=NOW) is True
    assert is_critical_alert(80, "Immediate", "Critical", "High",
                             event_time="not-a-date", now=NOW) is True


def test_score_floor_scales_with_impact():
    # Critical needs 50+, High needs 65+.
    assert is_critical_alert(50, "Immediate", "Critical", "High",
                             event_time=_iso(1), now=NOW) is True
    assert is_critical_alert(49, "Immediate", "Critical", "High",
                             event_time=_iso(1), now=NOW) is False
    assert is_critical_alert(64, "Immediate", "High", "High",
                             event_time=_iso(1), now=NOW) is False
    assert is_critical_alert(65, "Immediate", "High", "High",
                             event_time=_iso(1), now=NOW) is True


def test_low_impact_or_slow_urgency_never_alerts():
    assert is_critical_alert(99, "Immediate", "Moderate", "Confirmed",
                             event_time=_iso(0), now=NOW) is False
    assert is_critical_alert(99, "7 Days", "Critical", "Confirmed",
                             event_time=_iso(0), now=NOW) is False


# ---- stored-row repair + ordering ------------------------------------------

def _story(conn, sid, headline, *, impact, urgency, conf, score, event, status=None,
           is_alert=0):
    conn.execute(
        "INSERT INTO story(id,headline,category,first_seen,last_updated,status,"
        "impact,urgency,confidence,relevance_score,event_time,is_alert,is_demo) "
        "VALUES (?,?,'geopolitical',?,?,?,?,?,?,?,?,?,0)",
        (sid, headline, event, event, status, impact, urgency, conf, score, event,
         is_alert))


def test_requalify_clears_stories_flagged_under_the_old_rule(conn):
    conn.execute("DELETE FROM story")
    # Previously flagged, must now be cleared:
    _story(conn, "s_adv", "Cote d Ivoire - Level 2", impact="Critical",
           urgency="Immediate", conf="Moderate", score=65, event=_iso(1),
           status="advisory", is_alert=1)
    _story(conn, "s_old", "Old flood report", impact="Critical", urgency="Immediate",
           conf="High", score=70, event=_iso(60), is_alert=1)
    _story(conn, "s_weak", "Single-source rumour", impact="Critical",
           urgency="Immediate", conf="Unverified", score=70, event=_iso(1), is_alert=1)
    # Genuinely alert-worthy but never flagged: must be turned ON.
    _story(conn, "s_live", "Strikes kill 10", impact="Critical", urgency="Immediate",
           conf="High", score=70, event=_iso(0), is_alert=0)
    conn.execute("DELETE FROM preference WHERE key='alert_rule_v2'")
    conn.commit()

    db._requalify_alerts(conn)

    def flagged(sid):
        return conn.execute("SELECT is_alert FROM story WHERE id=?", (sid,)).fetchone()[0]

    assert flagged("s_adv") == 0
    assert flagged("s_old") == 0
    assert flagged("s_weak") == 0
    assert flagged("s_live") == 1
    # Idempotent second pass.
    assert db._requalify_alerts(conn) == 0


def test_alerts_are_ordered_by_newest_event(conn):
    """The card shows the EVENT date, so ordering must follow it — sorting by
    last_updated made a re-verified May event lead a 'newest first' list."""
    conn.execute("DELETE FROM story")
    for sid, days in (("a_mid", 2), ("a_new", 0), ("a_old", 6)):
        _story(conn, sid, "Event " + sid, impact="Critical", urgency="Immediate",
               conf="High", score=70, event=_iso(days), is_alert=1)
    # Make the OLDEST event the most recently updated — the previous bug.
    conn.execute("UPDATE story SET last_updated=? WHERE id='a_old'", (_iso(0),))
    conn.commit()

    order = [s["id"] for s in list_alerts(conn, "live")]
    assert order == ["a_new", "a_mid", "a_old"]
