"""Optional in-process ingestion scheduler.

When enabled (GSID_INGEST_EVERY_HOURS > 0 and data mode is live/hybrid), a
daemon thread runs one ingestion cycle shortly after startup and then every N
hours for as long as the server process is running.

This is the self-contained "auto-refresh" path. For refreshes that must survive
reboots or run without the web server up, use an OS scheduler (cron / launchd)
calling `python run.py --ingest` instead — see docs/DATA_SOURCES.md.
"""

from __future__ import annotations

import logging
import os
import threading

from . import db
from .analysis import get_analyzer

log = logging.getLogger("gsid.scheduler")

_started = False
_lock = threading.Lock()


class IngestionScheduler:
    def __init__(self, config, analyzer=None, first_delay_seconds: float = 6.0):
        self.config = config
        self.analyzer = analyzer or get_analyzer(config)
        self.interval = max(1, config.ingest_every_hours) * 3600
        self.first_delay = first_delay_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="gsid-ingest", daemon=True)
        self._thread.start()
        log.info("ingestion scheduler started: every %d hour(s)", self.config.ingest_every_hours)

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        # Initial delay so startup isn't blocked and the reloader settles.
        if self._stop.wait(self.first_delay):
            return
        while not self._stop.is_set():
            self._cycle()
            if self._stop.wait(self.interval):
                return

    def _cycle(self) -> None:
        from .ingestion.pipeline import IngestionPipeline

        conn = None
        try:
            conn = db.connect(self.config.db_file)
            db.init_db(conn)
            result = IngestionPipeline(conn, self.config, self.analyzer).run()
            db.audit(conn, "scheduler", "scheduled_ingest", detail=result)
            conn.commit()
            log.info("scheduled ingestion complete: %s", result)
        except Exception:  # a failed cycle must never kill the thread
            log.exception("scheduled ingestion cycle failed")
        finally:
            if conn is not None:
                conn.close()


def maybe_start_scheduler(config, analyzer=None) -> IngestionScheduler | None:
    """Start the scheduler once, only if configured and appropriate."""
    global _started

    if config.ingest_every_hours <= 0:
        return None
    if config.data_mode == "demo":
        log.info("scheduler disabled: GSID_DATA_MODE=demo (no live ingestion).")
        return None
    # Under the Flask debug reloader, create_app runs in both the parent and the
    # child process; only start in the child so we don't run two schedulers.
    if not config.is_production and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return None

    with _lock:
        if _started:
            return None
        _started = True

    scheduler = IngestionScheduler(config, analyzer)
    scheduler.start()
    return scheduler
