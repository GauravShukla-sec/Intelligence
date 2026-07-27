"""Tests for the daily-brief 'today's top' selection logic."""

from datetime import datetime, timedelta, timezone

from gsid.brief import todays_top

_NOW = datetime.now(timezone.utc)


def _iso(hours_ago: float) -> str:
    return (_NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _story(sid, score, hours_ago):
    return {"id": sid, "relevance_score": score, "event_time": _iso(hours_ago)}


def test_todays_top_prefers_fresh_over_stale_high_score():
    stories = [
        _story("old_critical", 95, 240),   # very high score but 10 days old
        _story("fresh_mid", 55, 3),         # fresh, medium score
    ]
    top = todays_top(stories, n=2)
    assert top[0]["id"] == "fresh_mid"      # recency wins over stale high score


def test_todays_top_excludes_alert_ids():
    stories = [_story("alert1", 90, 5), _story("normal", 60, 5)]
    top = todays_top(stories, n=5, exclude_ids={"alert1"})
    assert [s["id"] for s in top] == ["normal"]


def test_todays_top_falls_back_when_all_excluded():
    stories = [_story("a", 80, 5), _story("b", 70, 5)]
    # Excluding everything must not return an empty snapshot.
    top = todays_top(stories, n=3, exclude_ids={"a", "b"})
    assert len(top) == 2


def test_todays_top_handles_missing_timestamps():
    stories = [{"id": "x", "relevance_score": 50}]  # no event_time
    top = todays_top(stories, n=1)
    assert top[0]["id"] == "x"
