#!/usr/bin/env python3
"""Development entry point for the Global Security Intelligence Desk.

    python run.py            # start the web server
    python run.py --ingest   # run one live ingestion cycle (needs live mode)
    python run.py --seed     # (re)seed demo data
    python run.py --reset    # delete the DB then seed demo data

The server binds to GSID_HOST:GSID_PORT (default 127.0.0.1:8000).
"""

from __future__ import annotations

import argparse
import logging
import sys

from gsid import db
from gsid.analysis import get_analyzer
from gsid.app import create_app
from gsid.config import load_config
from gsid.seed import seed_all

log = logging.getLogger("gsid.run")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Global Security Intelligence Desk")
    parser.add_argument("--ingest", action="store_true", help="run one ingestion cycle")
    parser.add_argument("--seed", action="store_true", help="seed demo data and exit")
    parser.add_argument("--reset", action="store_true", help="reset DB then seed demo data")
    parser.add_argument("--notify", action="store_true",
                        help="send a webhook digest of new critical alerts and exit")
    parser.add_argument("--reanalyze", action="store_true",
                        help="re-run the configured analyzer over stored stories")
    parser.add_argument("--limit", type=int, default=25,
                        help="max stories to re-analyse (default 25)")
    parser.add_argument("--only-provider", default="heuristic",
                        help="re-analyse stories whose stored analysis came from this "
                             "provider (default: heuristic); empty string for all")
    parser.add_argument("--pause", type=float, default=0.0,
                        help="seconds to wait between calls (free-tier rate limits)")
    parser.add_argument("--reclassify", action="store_true",
                        help="re-run category classification over stored stories")
    parser.add_argument("--reclassify-rollback", action="store_true",
                        help="undo the most recent reclassification pass")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --reclassify: report changes without writing")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # HTTP client libraries log one INFO line per request. With ~650 stories
    # analysed per run that buries our own diagnostics: a single WARNING about
    # a rejected API key scrolled past hundreds of "401 Unauthorized" lines,
    # which is exactly when the operator most needs to see it.
    for _noisy in ("httpx", "httpx2", "httpcore", "httpcore2", "openai", "anthropic",
                   "urllib3"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)
    config = load_config()

    if args.reset:
        if config.db_file.exists():
            config.db_file.unlink()
            log.info("removed %s", config.db_file)
        for suffix in ("-wal", "-shm"):
            p = config.db_file.with_name(config.db_file.name + suffix)
            if p.exists():
                p.unlink()

    if args.seed or args.reset:
        conn = db.connect(config.db_file)
        db.init_db(conn)
        result = seed_all(conn, config, force=True)
        conn.close()
        log.info("seed result: %s", result)
        if args.seed or args.reset:
            if not args.ingest:
                return 0

    if args.reclassify or args.reclassify_rollback:
        from gsid.reclassify import reclassify_all, rollback
        conn = db.connect(config.db_file)
        db.init_db(conn)
        if args.reclassify_rollback:
            log.info("rollback result: %s", rollback(conn))
        else:
            report = reclassify_all(conn, dry_run=args.dry_run)
            log.info("reclassify: scanned=%(scanned)d changed=%(changed)d "
                     "dry_run=%(dry_run)s", report)
            for move, n in report["moves"].items():
                log.info("  %-44s %d", move, n)
            if args.dry_run:
                log.info("dry run — nothing written. Re-run without --dry-run to apply.")
        conn.close()
        return 0

    if args.notify:
        from gsid.notify import notify_new_alerts
        conn = db.connect(config.db_file)
        db.init_db(conn)
        if not config.webhook_url:
            log.error("GSID_WEBHOOK_URL is not set — nothing to send to.")
            conn.close()
            return 1
        result = notify_new_alerts(conn, config)
        conn.close()
        log.info("notify result: %s", result)
        return 0 if result.get("sent") or result.get("reason") == "nothing new" else 1

    if args.reanalyze:
        from gsid.analysis.registry import get_analyzer
        from gsid.reanalyze import reanalyze
        conn = db.connect(config.db_file)
        db.init_db(conn)
        analyzer = get_analyzer(config)
        if analyzer.name == "heuristic" and config.ai_provider != "heuristic":
            log.error("provider %r requested but not usable (missing key?) — "
                      "refusing to re-analyse with the heuristic analyzer.",
                      config.ai_provider)
            conn.close()
            return 1
        log.info("re-analysing with %s (limit=%d)", analyzer.name, args.limit)
        result = reanalyze(conn, analyzer, limit=args.limit,
                           only_provider=(args.only_provider or None),
                           pause=args.pause, dry_run=args.dry_run)
        conn.close()
        log.info("re-analysis result: %s", result)
        return 0

    if args.ingest:
        from gsid.ingestion.pipeline import IngestionPipeline
        if config.data_mode == "demo":
            log.error("GSID_DATA_MODE=demo — set to 'live' or 'hybrid' to ingest.")
            return 1
        conn = db.connect(config.db_file)
        db.init_db(conn)
        pipeline = IngestionPipeline(conn, config, get_analyzer(config))
        result = pipeline.run()
        conn.close()
        log.info("ingestion result: %s", result)
        return 0

    app = create_app(config)
    log.info("Starting GSID on http://%s:%s (data_mode=%s, ai=%s)",
             config.host, config.port, config.data_mode, config.ai_provider)
    app.run(host=config.host, port=config.port, debug=not config.is_production,
            threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
