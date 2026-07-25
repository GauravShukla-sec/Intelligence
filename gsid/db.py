"""SQLite access layer.

Thin, dependency-free wrapper around the standard library `sqlite3`. Provides
connection management, schema initialization, UTC helpers, an audit-log helper
and a full-text-search sync helper.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .taxonomy import CATEGORY_NAMES, REGIONS, COUNTRY_REGION, COUNTRY_NAMES

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def utcnow() -> str:
    """Current time as an ISO-8601 UTC string (system stores UTC internally)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str = "") -> str:
    token = uuid.uuid4().hex[:12]
    return f"{prefix}{token}" if prefix else token


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables (idempotent) and seed reference data."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _seed_reference(conn)
    conn.commit()


def _seed_reference(conn: sqlite3.Connection) -> None:
    for r in REGIONS:
        conn.execute(
            "INSERT OR IGNORE INTO region(id, name) VALUES (?, ?)",
            (r["id"], r["name"]),
        )
    # Minimal country seed derived from the taxonomy mapping.
    for code, region_id in COUNTRY_REGION.items():
        conn.execute(
            "INSERT OR IGNORE INTO country(code, name, region_id) VALUES (?, ?, ?)",
            (code, COUNTRY_NAMES.get(code, code.upper()), region_id),
        )


# --------------------------------------------------------------------------
# Audit logging (analytical guardrail: transparent trail)
# --------------------------------------------------------------------------
def audit(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    entity: str | None = None,
    entity_id: str | None = None,
    detail: Any = None,
) -> None:
    if detail is not None and not isinstance(detail, str):
        detail = json.dumps(detail, default=str)[:4000]
    conn.execute(
        "INSERT INTO audit_log(id, ts, actor, action, entity, entity_id, detail) "
        "VALUES (?,?,?,?,?,?,?)",
        (new_id("aud_"), utcnow(), actor, action, entity, entity_id, detail),
    )


# --------------------------------------------------------------------------
# Full-text search sync
# --------------------------------------------------------------------------
def reindex_story_fts(conn: sqlite3.Connection, story_id: str) -> None:
    """Refresh the FTS row for a single story from its claims/citations."""
    row = conn.execute(
        "SELECT id, headline, summary, location_text FROM story WHERE id=?",
        (story_id,),
    ).fetchone()
    if row is None:
        return
    claims = conn.execute(
        "SELECT text FROM claim WHERE story_id=?", (story_id,)
    ).fetchall()
    body = " ".join(c["text"] for c in claims)
    conn.execute("DELETE FROM story_fts WHERE story_id=?", (story_id,))
    conn.execute(
        "INSERT INTO story_fts(story_id, headline, summary, location_text, body) "
        "VALUES (?,?,?,?,?)",
        (row["id"], row["headline"] or "", row["summary"] or "",
         row["location_text"] or "", body),
    )


def search_stories(conn: sqlite3.Connection, query: str, limit: int = 50) -> list[str]:
    """Return story ids matching an FTS query, best match first.

    Falls back to a LIKE scan if the FTS query syntax is rejected.
    """
    q = (query or "").strip()
    if not q:
        return []
    try:
        # Quote each token to avoid FTS syntax errors on punctuation.
        tokens = [t for t in _tokenize(q)]
        if not tokens:
            return []
        match = " OR ".join(f'"{t}"' for t in tokens)
        rows = conn.execute(
            "SELECT story_id FROM story_fts WHERE story_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (match, limit),
        ).fetchall()
        return [r["story_id"] for r in rows]
    except sqlite3.OperationalError:
        like = f"%{q}%"
        rows = conn.execute(
            "SELECT id FROM story WHERE headline LIKE ? OR summary LIKE ? LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [r["id"] for r in rows]


def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    for ch in text.lower():
        if ch.isalnum():
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return [t for t in out if len(t) >= 2]


# --------------------------------------------------------------------------
# Convenience row helpers
# --------------------------------------------------------------------------
def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def category_name(cat_id: str) -> str:
    return CATEGORY_NAMES.get(cat_id, cat_id)
