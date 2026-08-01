"""Rollback-safe reclassification of stored stories.

Re-runs the current classifier over existing rows. Every change is recorded in
`category_backup` before it is applied, so a pass can be inspected, audited, or
undone wholesale — a classifier change should never be a one-way door on live
data.

    python run.py --reclassify --dry-run     # report only, writes nothing
    python run.py --reclassify               # apply, keeping a rollback point
    python run.py --reclassify-rollback      # restore the previous categories

Stored rows don't carry their originating feed id, so the authoritative source
prior is recovered from the story's citation source names (e.g. "CISA —
Cybersecurity Advisories" -> cyber).
"""

from __future__ import annotations

import json
import logging
from collections import Counter

from . import db
from .ingestion.classify import classify

log = logging.getLogger("gsid.reclassify")


def _source_names(conn, story_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT s.name FROM citation c JOIN source s ON c.source_id = s.id "
        "WHERE c.story_id = ?", (story_id,)).fetchall()
    return [r["name"] for r in rows if r["name"]]


def reclassify_all(conn, dry_run: bool = False, include_demo: bool = False,
                   limit: int | None = None) -> dict:
    """Re-classify stored stories. Returns a report; writes only if not dry_run.

    Travel advisories are skipped — their category is structural, not inferred.
    """
    where = "(status IS NULL OR status != 'advisory')"
    if not include_demo:
        where += " AND is_demo = 0"
    sql = f"SELECT id, headline, summary, category FROM story WHERE {where}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()

    batch = db.new_id("rcls_")
    now = db.utcnow()
    changes: list[dict] = []
    moved = Counter()

    for r in rows:
        result = classify(
            headline=r["headline"] or "",
            summary=r["summary"] or "",
            source_names=_source_names(conn, r["id"]),
        )
        if result.category == r["category"]:
            continue
        changes.append({
            "story_id": r["id"],
            "headline": (r["headline"] or "")[:80],
            "old": r["category"],
            "new": result.category,
            "confidence": result.confidence,
            "reason": result.explanation.get("reason"),
        })
        moved[f'{r["category"]} -> {result.category}'] += 1

        if not dry_run:
            # Record the rollback point BEFORE mutating.
            conn.execute(
                "INSERT OR REPLACE INTO category_backup"
                "(story_id, old_category, new_category, batch, changed_at) "
                "VALUES (?,?,?,?,?)",
                (r["id"], r["category"], result.category, batch, now))
            conn.execute(
                "UPDATE story SET category=?, category_confidence=?, "
                "classification_json=? WHERE id=?",
                (result.category, result.confidence,
                 json.dumps(result.to_dict()), r["id"]))

    if not dry_run and changes:
        db.audit(conn, "system", "reclassify", "story", batch,
                 {"batch": batch, "changed": len(changes),
                  "scanned": len(rows), "moves": dict(moved)})
        conn.commit()

    return {
        "batch": None if dry_run else batch,
        "dry_run": dry_run,
        "scanned": len(rows),
        "changed": len(changes),
        "unchanged": len(rows) - len(changes),
        "moves": dict(moved.most_common()),
        "changes": changes,
    }


def rollback(conn, batch: str | None = None) -> dict:
    """Restore categories saved by a reclassification pass.

    Without `batch`, rolls back the most recent one.
    """
    if batch is None:
        row = conn.execute(
            "SELECT batch FROM category_backup ORDER BY changed_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return {"restored": 0, "batch": None}
        batch = row["batch"]

    rows = conn.execute(
        "SELECT story_id, old_category FROM category_backup WHERE batch=?",
        (batch,)).fetchall()
    for r in rows:
        conn.execute(
            "UPDATE story SET category=?, category_confidence=0, "
            "classification_json=NULL WHERE id=?",
            (r["old_category"], r["story_id"]))
    conn.execute("DELETE FROM category_backup WHERE batch=?", (batch,))
    db.audit(conn, "system", "reclassify_rollback", "story", batch,
             {"batch": batch, "restored": len(rows)})
    conn.commit()
    log.info("rolled back %d categories from batch %s", len(rows), batch)
    return {"restored": len(rows), "batch": batch}
