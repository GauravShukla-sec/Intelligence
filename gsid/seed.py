"""Database seeding: demo stories, regulations, quiz, scenarios, preferences."""

from __future__ import annotations

import json
import logging

from . import db, fixtures
from .analysis import get_analyzer
from .store import save_story
from .taxonomy import DEFAULT_TOPICS, DEFAULT_WATCHLIST_COUNTRIES

log = logging.getLogger("gsid.seed")


def seed_all(conn, config, force: bool = False) -> dict:
    """Idempotent seed. Uses the heuristic analyzer for demo data so the demo
    is deterministic and needs no credentials, regardless of GSID_AI_PROVIDER."""
    live = (config.data_mode or "").lower() == "live"

    # Reference content is real and kept current on every startup (idempotent):
    # the regulatory tracker and the learning bank are not "demo" data.
    _seed_regulations(conn)
    _seed_quiz(conn)
    _seed_scenarios(conn)
    _seed_preferences(conn, config)

    if live:
        # A live desk shows only real developments — purge any illustrative demo
        # stories/regulations left from an earlier seed (real ingested data has
        # is_demo=0; reference regulations were just seeded as is_demo=0).
        conn.execute("DELETE FROM story WHERE is_demo=1")
        conn.execute("DELETE FROM regulation WHERE is_demo=1")
        conn.commit()
        return {"skipped": False, "demo_stories": 0, "mode": "live"}

    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM story WHERE is_demo=1").fetchone()["n"]
    if existing and not force:
        conn.commit()
        return {"skipped": True, "demo_stories": existing}

    from .analysis.heuristic import HeuristicAnalyzer
    analyzer = HeuristicAnalyzer()
    n = 0
    for draft in fixtures.demo_stories():
        save_story(conn, draft, analyzer, actor="system")
        n += 1
    db.audit(conn, "system", "seed_demo", detail={"stories": n})
    conn.commit()
    log.info("seeded %d demo stories", n)
    return {"skipped": False, "demo_stories": n}


def _seed_regulations(conn) -> None:
    """Seed the real, curated regulation reference set (is_demo=0)."""
    for r in fixtures.reference_regulations():
        conn.execute(
            "INSERT OR REPLACE INTO regulation(id,story_id,title,jurisdiction,framework,"
            "status,effective_date,affected,obligations,reporting,penalties,implications,"
            "prep_steps,source_url,updated_at,is_demo) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
            (r["id"], r.get("story_id"), r["title"], r["jurisdiction"], r.get("framework"),
             r["status"], r.get("effective_date"), r.get("affected"), r.get("obligations"),
             r.get("reporting"), r.get("penalties"), r.get("implications"),
             r.get("prep_steps"), r.get("source_url"), db.utcnow()),
        )


def _seed_quiz(conn) -> None:
    for q in fixtures.demo_quiz():
        conn.execute(
            "INSERT OR REPLACE INTO quiz_question(id,question,options_json,answer_index,"
            "explanation,difficulty,story_id,is_demo) VALUES (?,?,?,?,?,?,?,1)",
            (q["id"], q["question"], json.dumps(q["options"]), q["answer_index"],
             q.get("explanation"), q.get("difficulty", 2), q.get("story_id")),
        )


def _seed_scenarios(conn) -> None:
    for s in fixtures.demo_scenarios():
        conn.execute(
            "INSERT OR REPLACE INTO scenario(id,title,prompt,options_json,principle,"
            "story_id,is_demo) VALUES (?,?,?,?,?,?,1)",
            (s["id"], s["title"], s["prompt"], json.dumps(s["options"]),
             s.get("principle"), s.get("story_id")),
        )


def _seed_preferences(conn, config) -> None:
    defaults = {
        "countries": json.dumps(DEFAULT_WATCHLIST_COUNTRIES),
        "topics": json.dumps(DEFAULT_TOPICS),
        "sites": json.dumps([]),
        "suppliers": json.dumps([]),
        "routes": json.dumps([]),
        "travel_destinations": json.dumps([]),
        "industries": json.dumps(["manufacturing", "logistics"]),
        "regulations": json.dumps(["NIS2", "CER", "CTPAT"]),
        "risk_tolerance": "moderate",
        "timezone": config.default_timezone,
        "report_time": "07:00",
        "briefing_length": "standard",
    }
    for k, v in defaults.items():
        conn.execute("INSERT OR IGNORE INTO preference(key,value) VALUES (?,?)", (k, v))
    conn.commit()
