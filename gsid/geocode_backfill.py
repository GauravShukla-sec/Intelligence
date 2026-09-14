"""Apply headline geocoding to stories already in the database.

Ingestion geocodes as it writes, so this exists for the stories that were
stored before that ran — without it the globe stays empty of everything except
GDACS and USGS, which is the disaster-map problem geocoding was meant to solve.

Only stories with no coordinates are touched. A feed-published coordinate is
always better evidence than a name matched out of a headline, so this never
overwrites one.
"""

from __future__ import annotations

import logging

from . import geocode

log = logging.getLogger("gsid.geocode_backfill")


def backfill(conn, dry_run: bool = False) -> dict:
    rows = conn.execute("""
        SELECT s.id, s.headline, s.location_text,
               (SELECT group_concat(sc.country) FROM story_country sc
                 WHERE sc.story_id = s.id) AS ccs
          FROM story s
         WHERE s.lat IS NULL AND s.is_demo = 0
    """).fetchall()

    placed = []
    for row in rows:
        countries = [c for c in (row["ccs"] or "").split(",") if c]
        hit = geocode.locate(row["headline"], countries)
        if hit:
            placed.append((row["id"], hit, row["location_text"]))

    if not dry_run and placed:
        conn.executemany(
            "UPDATE story SET lat = ?, lon = ?, location_text = ? WHERE id = ?",
            [(h["lat"], h["lon"], old or h["city"], sid) for sid, h, old in placed],
        )
        conn.commit()

    log.info("geocode backfill: scanned=%d placed=%d dry_run=%s",
             len(rows), len(placed), dry_run)
    return {"scanned": len(rows), "placed": len(placed), "dry_run": dry_run}
