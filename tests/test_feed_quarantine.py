"""A persistently dead feed must stop costing a fetch timeout every run."""

from __future__ import annotations

from gsid.ingestion.pipeline import IngestionPipeline


class _Cfg:
    enabled_feeds: list[str] = []
    fetch_timeout_seconds = 5
    data_mode = "live"
    ai_provider = "heuristic"


class _Feed:
    def __init__(self, fid="dead"):
        self.id = fid
        self.name = "Dead Feed"
        self.url = "https://example.invalid/rss"
        self.tier = 1


def _pipeline(conn):
    return IngestionPipeline(conn, _Cfg(), None)


def _set_fails(conn, feed_id, n):
    conn.execute(
        "INSERT INTO feed_health(feed_id,name,url,tier,last_run,consecutive_failures) "
        "VALUES (?,?,?,1,'t',?) ON CONFLICT(feed_id) DO UPDATE SET "
        "consecutive_failures=excluded.consecutive_failures",
        (feed_id, "Dead Feed", "https://example.invalid/rss", n))
    conn.commit()


def test_healthy_feed_is_never_skipped(conn):
    _set_fails(conn, "dead", 0)
    assert _pipeline(conn)._is_quarantined(_Feed()) is False


def test_feed_below_the_threshold_still_gets_tried(conn):
    _set_fails(conn, "dead", IngestionPipeline.QUARANTINE_AFTER - 1)
    assert _pipeline(conn)._is_quarantined(_Feed()) is False


def test_persistently_dead_feed_is_skipped(conn):
    _set_fails(conn, "dead", 9)          # past threshold, not a re-probe run
    assert _pipeline(conn)._is_quarantined(_Feed()) is True


def test_skipping_advances_the_reprobe_clock(conn):
    """Without this the feed would be skipped forever and never recover."""
    _set_fails(conn, "dead", 9)
    p = _pipeline(conn)
    p._is_quarantined(_Feed())
    after = conn.execute(
        "SELECT consecutive_failures FROM feed_health WHERE feed_id='dead'").fetchone()[0]
    assert after == 10


def test_a_quarantined_feed_is_reprobed_periodically(conn):
    """Recovery must be automatic — nobody should have to edit the registry."""
    at = IngestionPipeline.QUARANTINE_AFTER
    every = IngestionPipeline.QUARANTINE_REPROBE_EVERY
    _set_fails(conn, "dead", at + every)     # lands exactly on a re-probe
    assert _pipeline(conn)._is_quarantined(_Feed()) is False


def test_unknown_feed_is_not_quarantined(conn):
    """A feed with no health row yet has never failed."""
    assert _pipeline(conn)._is_quarantined(_Feed("brand_new")) is False


def test_disabled_dead_feed_is_not_selected():
    """ReliefWeb: RSS permanently 202s and v2 needs an approved appname."""
    from gsid.ingestion.connectors import FEED_REGISTRY, selected_feeds
    assert any(f.id == "reliefweb" for f in FEED_REGISTRY)      # record kept
    assert not any(f.id == "reliefweb" for f in selected_feeds(None))


def test_cli_ingest_branch_can_resolve_the_analyzer():
    """Regression: a function-level `import get_analyzer` inside the
    --reanalyze branch made the name local to main() for its whole body, so
    the --ingest branch raised UnboundLocalError. Guard against re-shadowing.
    """
    import ast
    import pathlib

    src = pathlib.Path("run.py").read_text()
    tree = ast.parse(src)
    main = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    shadowed = [
        alias.asname or alias.name
        for node in ast.walk(main)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
        if (alias.asname or alias.name) == "get_analyzer"
    ]
    assert not shadowed, (
        "get_analyzer is imported at module level; importing it inside main() "
        "shadows it for every branch and breaks --ingest")
