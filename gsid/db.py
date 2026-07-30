"""SQLite access layer.

Thin, dependency-free wrapper around the standard library `sqlite3`. Provides
connection management, schema initialization, UTC helpers, an audit-log helper
and a full-text-search sync helper.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .taxonomy import CATEGORY_NAMES, REGIONS, COUNTRY_REGION, COUNTRY_NAMES

log = logging.getLogger("gsid.db")

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
    _migrate(conn)
    _cleanup_stale_citations(conn)
    _backfill_country_tags(conn)
    _retag_advisories(conn)
    _seed_reference(conn)
    conn.commit()


def _backfill_country_tags(conn: sqlite3.Connection) -> None:
    """One-time re-tag of existing developments to the countries they mention.

    Early ingestion tagged stories to their publisher's country, so the map and
    country filters missed obvious subjects (e.g. Iran). This rebuilds
    story_country from the headline/summary text and repoints primary_country /
    region to the lead subject. Advisories are left untouched (their country IS
    the destination). Idempotent: guarded by a one-shot preference marker.
    """
    from .taxonomy import region_for_country, subject_countries

    # v2: headline-first tagging (v1 over-tagged roundups from passing body
    # mentions). Bumping the marker re-runs the corrected pass on deployments
    # that already applied v1.
    marker = conn.execute(
        "SELECT 1 FROM preference WHERE key='country_retag_v2'").fetchone()
    if marker:
        return
    rows = conn.execute(
        "SELECT id, headline, summary FROM story "
        "WHERE (status IS NULL OR status != 'advisory')").fetchall()
    for r in rows:
        codes = subject_countries(r["headline"] or "", r["summary"] or "")
        if not codes:
            continue  # leave stories with no detectable subject as-is
        conn.execute("DELETE FROM story_country WHERE story_id=?", (r["id"],))
        for c in codes:
            conn.execute(
                "INSERT OR IGNORE INTO story_country(story_id, country) VALUES (?,?)",
                (r["id"], c))
        conn.execute(
            "UPDATE story SET primary_country=?, primary_region=? WHERE id=?",
            (codes[0], region_for_country(codes[0]), r["id"]))
    conn.execute(
        "INSERT OR REPLACE INTO preference(key, value) VALUES ('country_retag_v2','done')")


def _retag_advisories(conn: sqlite3.Connection) -> int:
    """Re-point travel advisories at their DESTINATION, not their publisher.

    Advisories whose destination couldn't be parsed were previously tagged to
    the issuing government, so e.g. every unresolved US State advisory landed on
    the United States' own Travel Risk page — producing a bogus "Level 4 — do
    not travel" consensus for the US built from advisories about other places.

    Re-resolves each advisory from its headline. Where the destination still
    can't be determined the tags are CLEARED: no tag is far better than a wrong
    one, which actively corrupts the destination brief. Returns rows changed.
    """
    from .taxonomy import advisory_destination, country_name, region_for_country

    marker = conn.execute(
        "SELECT 1 FROM preference WHERE key='advisory_retag_v1'").fetchone()
    if marker:
        return 0
    rows = conn.execute(
        "SELECT id, headline FROM story WHERE status='advisory'").fetchall()
    changed = 0
    for r in rows:
        dest = advisory_destination(r["headline"] or "")
        current = {x["country"] for x in conn.execute(
            "SELECT country FROM story_country WHERE story_id=?", (r["id"],))}
        want = {dest} if dest else set()
        if current == want:
            continue
        conn.execute("DELETE FROM story_country WHERE story_id=?", (r["id"],))
        if dest:
            conn.execute(
                "INSERT OR IGNORE INTO story_country(story_id, country) VALUES (?,?)",
                (r["id"], dest))
            conn.execute(
                "UPDATE story SET primary_country=?, primary_region=?, "
                "location_text=? WHERE id=?",
                (dest, region_for_country(dest), country_name(dest), r["id"]))
        else:
            conn.execute(
                "UPDATE story SET primary_country='', primary_region=NULL WHERE id=?",
                (r["id"],))
        changed += 1
    conn.execute(
        "INSERT OR REPLACE INTO preference(key, value) VALUES ('advisory_retag_v1','done')")
    if changed:
        log.info("re-tagged %d travel advisories to their destination", changed)
    return changed


def _cleanup_stale_citations(conn: sqlite3.Connection) -> None:
    """Remove internal Adobe AEM (`/tsg_aem/`) travel.state.gov citations left
    by an earlier ingestion — they open a raw HTML fragment, not a public page.

    Idempotent: drop the stale citation where the story already has a good one
    (deduping); for the rare story whose only citation is a tsg_aem link,
    rewrite it to the public advisories index so the link still works.
    """
    PUBLIC = ("https://travel.state.gov/content/travel/en/"
              "traveladvisories/traveladvisories.html")
    rows = conn.execute(
        "SELECT id, story_id FROM citation WHERE url LIKE '%/tsg_aem/%'"
    ).fetchall()
    for r in rows:
        has_good = conn.execute(
            "SELECT 1 FROM citation WHERE story_id=? AND id<>? "
            "AND url NOT LIKE '%/tsg_aem/%' LIMIT 1",
            (r["story_id"], r["id"]),
        ).fetchone()
        if has_good:
            conn.execute("DELETE FROM citation WHERE id=?", (r["id"],))
        else:
            conn.execute("UPDATE citation SET url=? WHERE id=?", (PUBLIC, r["id"]))


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive column migrations to pre-existing tables.

    `CREATE TABLE IF NOT EXISTS` never alters an existing table, so columns
    added to schema.sql after a DB was first created must be back-filled here.
    Each ADD COLUMN is idempotent (guarded by a PRAGMA table_info check).
    """
    additions = {
        "story": [
            ("advisory_level", "INTEGER NOT NULL DEFAULT 0"),
            ("advisory_json", "TEXT"),
        ],
        "citation": [
            ("advisory_level", "INTEGER NOT NULL DEFAULT 0"),
        ],
    }
    for table, cols in additions.items():
        existing = {r["name"] for r in
                    conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, decl in cols:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


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
