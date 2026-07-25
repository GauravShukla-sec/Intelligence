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
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
