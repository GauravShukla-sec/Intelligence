"""Read-side queries: assemble full story objects, lists, filters, regulations.

Kept separate from `store.py` (write side) for clarity. All timestamps stay in
UTC here; timezone conversion is a presentation concern handled client-side.
"""

from __future__ import annotations

import json
from typing import Any

from . import db
from .taxonomy import (
    CATEGORY_NAMES, REGION_NAMES, country_name, region_for_country,
)


def _story_row_to_summary(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "headline": row["headline"],
        "summary": row["summary"],
        "category": row["category"],
        "category_name": CATEGORY_NAMES.get(row["category"], row["category"]),
        "primary_region": row["primary_region"],
        "region_name": REGION_NAMES.get(row["primary_region"], row["primary_region"]),
        "primary_country": row["primary_country"],
        "location_text": row["location_text"],
        "lat": row["lat"], "lon": row["lon"],
        "event_time": row["event_time"],
        "first_seen": row["first_seen"],
        "last_updated": row["last_updated"],
        "status": row["status"],
        "relevance_score": row["relevance_score"],
        "urgency": row["urgency"], "geo_scope": row["geo_scope"],
        "impact": row["impact"], "likelihood": row["likelihood"],
        "velocity": row["velocity"], "confidence": row["confidence"],
        "trend": row["trend"],
        "is_alert": bool(row["is_alert"]),
        "is_demo": bool(row["is_demo"]),
    }


def list_stories(conn, filters: dict[str, Any] | None = None,
                 limit: int = 100, offset: int = 0) -> list[dict]:
    filters = filters or {}
    where = ["1=1"]
    params: list[Any] = []

    def add(cond: str, *vals):
        where.append(cond)
        params.extend(vals)

    # Travel advisories live ONLY in the Travel Risk section. Everywhere else
    # (stories, dashboard, brief, regional, search) they are excluded unless
    # a caller explicitly opts in. (NULL-safe so untagged stories still show.)
    if not filters.get("include_advisories"):
        add("(status IS NULL OR status != 'advisory')")

    if filters.get("category"):
        add("category = ?", filters["category"])
    if filters.get("region"):
        add("primary_region = ?", filters["region"])
    if filters.get("country"):
        add("id IN (SELECT story_id FROM story_country WHERE country = ?)",
            filters["country"].lower())
    if filters.get("impact"):
        add("impact = ?", filters["impact"])
    if filters.get("urgency"):
        add("urgency = ?", filters["urgency"])
    if filters.get("confidence"):
        add("confidence = ?", filters["confidence"])
    if filters.get("trend"):
        add("trend = ?", filters["trend"])
    if filters.get("min_score") is not None:
        add("relevance_score >= ?", int(filters["min_score"]))
    if filters.get("alerts_only"):
        add("is_alert = 1")
    if filters.get("verified_only"):
        add("confidence IN ('Confirmed','High')")
    if filters.get("since"):
        add("last_updated >= ?", filters["since"])
    if filters.get("ids"):
        placeholders = ",".join("?" for _ in filters["ids"])
        add(f"id IN ({placeholders})", *filters["ids"])
    # demo/live filtering
    mode = filters.get("data_mode")
    if mode == "demo":
        add("is_demo = 1")
    elif mode == "live":
        add("is_demo = 0")

    order = "relevance_score DESC, last_updated DESC"
    if filters.get("sort") == "recent":
        order = "last_updated DESC"
    elif filters.get("sort") == "urgency":
        order = "(urgency='Immediate') DESC, (urgency='24 Hours') DESC, relevance_score DESC"

    sql = (f"SELECT * FROM story WHERE {' AND '.join(where)} "
           f"ORDER BY {order} LIMIT ? OFFSET ?")
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    return [_story_row_to_summary(r) for r in rows]


def get_story(conn, story_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM story WHERE id=?", (story_id,)).fetchone()
    if row is None:
        return None
    story = _story_row_to_summary(row)
    story["analysis"] = json.loads(row["analysis_json"]) if row["analysis_json"] else {}
    story["scoring"] = json.loads(row["scoring_json"]) if row["scoring_json"] else {}

    story["countries"] = [
        r["country"] for r in conn.execute(
            "SELECT country FROM story_country WHERE story_id=?", (story_id,)
        ).fetchall()
    ]
    story["events"] = db.rows_to_dicts(conn.execute(
        "SELECT occurred, title, detail FROM event WHERE story_id=? ORDER BY ordinal",
        (story_id,)).fetchall())
    story["claims"] = _claims(conn, story_id)
    story["citations"] = _citations(conn, story_id)
    story["narratives"] = db.rows_to_dicts(conn.execute(
        "SELECT label, who, claim, evidence FROM narrative WHERE story_id=? ORDER BY ordinal",
        (story_id,)).fetchall())
    story["indicators"] = db.rows_to_dicts(conn.execute(
        "SELECT text, direction FROM indicator WHERE story_id=? ORDER BY ordinal",
        (story_id,)).fetchall())
    story["actions"] = db.rows_to_dicts(conn.execute(
        "SELECT action_type, text FROM action WHERE story_id=? ORDER BY ordinal",
        (story_id,)).fetchall())
    story["alert"] = _alert(conn, story_id)
    story["regulation"] = _regulation_for_story(conn, story_id)
    return story


def _claims(conn, story_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT c.id, c.text, c.claim_type, c.attributed_to, c.stance, "
        "c.corroboration, c.confidence, s.name AS source_name, s.tier AS source_tier, "
        "s.url AS source_url FROM claim c LEFT JOIN source s ON c.source_id=s.id "
        "WHERE c.story_id=?", (story_id,)).fetchall()
    return db.rows_to_dicts(rows)


def _citations(conn, story_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT ct.title, ct.url, ct.published_at, ct.accessed_at, ct.orig_language, "
        "ct.orig_headline, ct.is_primary, ct.is_circular, s.name AS source_name, "
        "s.tier AS source_tier, s.source_type, s.country AS source_country, "
        "s.ownership, s.transparency FROM citation ct "
        "LEFT JOIN source s ON ct.source_id=s.id WHERE ct.story_id=? "
        "ORDER BY ct.is_primary DESC, s.tier ASC", (story_id,)).fetchall()
    out = db.rows_to_dicts(rows)
    for c in out:
        c["is_primary"] = bool(c["is_primary"])
        c["is_circular"] = bool(c["is_circular"])
    return out


def _alert(conn, story_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM alert WHERE story_id=?", (story_id,)).fetchone()
    return dict(row) if row else None


def _regulation_for_story(conn, story_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM regulation WHERE story_id=?", (story_id,)).fetchone()
    return dict(row) if row else None


def list_alerts(conn, data_mode: str | None = None) -> list[dict]:
    f = {"alerts_only": True}
    if data_mode:
        f["data_mode"] = data_mode
    stories = list_stories(conn, f, limit=50)
    for s in stories:
        s["alert"] = _alert(conn, s["id"])
    return stories


def list_regulations(conn, data_mode: str | None = None) -> list[dict]:
    rows = conn.execute("SELECT * FROM regulation ORDER BY updated_at DESC").fetchall()
    return db.rows_to_dicts(rows)


def regional_watch(conn, data_mode: str | None = None) -> list[dict]:
    """Return each region with its top stories, or a no-change flag."""
    from .taxonomy import REGIONS
    out = []
    for r in REGIONS:
        if r["id"] == "global":
            continue
        f = {"region": r["id"]}
        if data_mode:
            f["data_mode"] = data_mode
        stories = list_stories(conn, f, limit=5)
        out.append({
            "region": r["id"],
            "region_name": r["name"],
            "stories": stories,
            "no_material_change": len(stories) == 0,
        })
    return out


def travel_brief(conn, code: str, data_mode: str | None = None) -> dict:
    """Per-destination travel-risk brief: official advisory + relevant
    developments + a synthesized 'what to look out for' list."""
    code = (code or "").strip().lower()
    name = country_name(code)
    region = region_for_country(code)

    # Stories tagged to this country (advisories + incidents). This is the ONE
    # place advisories are surfaced, so opt in explicitly.
    f = {"country": code, "include_advisories": True}
    if data_mode:
        f["data_mode"] = data_mode
    country_stories = list_stories(conn, f, limit=50)

    advisories = [s for s in country_stories if s.get("status") == "advisory"]
    non_advisory = [s for s in country_stories if s.get("status") != "advisory"]

    # Broaden with regional developments if the country itself is quiet.
    regional = []
    if len(non_advisory) < 4:
        rf = {"region": region}
        if data_mode:
            rf["data_mode"] = data_mode
        seen = {s["id"] for s in country_stories}
        regional = [s for s in list_stories(conn, rf, limit=20)
                    if s["id"] not in seen and s.get("status") != "advisory"][:6]

    related = (non_advisory + regional)[:10]

    # "What to look out for" — aggregate indicators + top recommended actions.
    watch, actions = _aggregate_watch(conn, advisories + related)

    return {
        "country": code,
        "country_name": name,
        "region": region,
        "region_name": REGION_NAMES.get(region, region),
        "advisories": [_attach_advisory_detail(conn, s) for s in advisories],
        "official_links": _official_advisory_links(code, name),
        "related": related,
        "watch_items": watch,
        "recommended_actions": actions,
        "highest_impact": _highest_impact(country_stories + related),
    }


def _attach_advisory_detail(conn, s: dict) -> dict:
    full = get_story(conn, s["id"]) or s
    s = dict(s)
    s["summary"] = full.get("summary", s.get("summary"))
    s["citations"] = full.get("citations", [])
    return s


def _aggregate_watch(conn, stories: list[dict]) -> tuple[list[str], list[dict]]:
    watch: list[str] = []
    actions: list[dict] = []
    seen_w, seen_a = set(), set()
    for s in stories[:8]:
        full = get_story(conn, s["id"])
        if not full:
            continue
        for ind in (full.get("analysis", {}).get("indicators", []) or []):
            t = ind.get("text", "")
            if t and t not in seen_w:
                seen_w.add(t)
                watch.append(t)
        for act in (full.get("analysis", {}).get("actions", []) or []):
            key = (act.get("type"), act.get("text"))
            if act.get("text") and key not in seen_a:
                seen_a.add(key)
                actions.append(act)
    return watch[:8], actions[:6]


def _official_advisory_links(code: str, name: str) -> list[dict]:
    slug = name.lower().replace(" ", "-")
    return [
        {"name": "UK FCDO travel advice", "url": f"https://www.gov.uk/foreign-travel-advice/{slug}"},
        {"name": "US State Dept travel advisories", "url": "https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html"},
    ]


def _highest_impact(stories: list[dict]) -> str:
    order = {"Low": 0, "Moderate": 1, "High": 2, "Critical": 3}
    best = "Low"
    for s in stories:
        if order.get(s.get("impact", "Low"), 0) > order.get(best, 0):
            best = s["impact"]
    return best


def feed_health(conn) -> list[dict]:
    """Merge the feed registry with recorded health so every feed is listed,
    even ones never polled yet. Sorted worst-first for the Settings view."""
    from .ingestion.connectors import FEED_REGISTRY

    rows = {r["feed_id"]: dict(r) for r in
            conn.execute("SELECT * FROM feed_health").fetchall()}
    out = []
    for f in FEED_REGISTRY:
        h = rows.get(f.id, {})
        out.append({
            "feed_id": f.id, "name": f.name, "url": f.url, "tier": f.tier,
            "source_type": f.source_type, "region": f.region_hint,
            "enabled_by_default": f.enabled_by_default,
            "status": h.get("status") or "unknown",
            "last_run": h.get("last_run"),
            "last_success": h.get("last_success"),
            "last_count": h.get("last_count") or 0,
            "error": h.get("error") or "",
            "consecutive_failures": h.get("consecutive_failures") or 0,
        })
    rank = {"error": 0, "empty": 1, "unknown": 2, "ok": 3}
    out.sort(key=lambda x: (rank.get(x["status"], 9), -x["last_count"]))
    return out


def counts_by_region(conn, data_mode: str | None = None) -> dict[str, int]:
    # Exclude travel advisories from region counts (they belong to Travel Risk).
    where = "(status IS NULL OR status != 'advisory')"
    params: list[Any] = []
    if data_mode == "demo":
        where += " AND is_demo=1"
    elif data_mode == "live":
        where += " AND is_demo=0"
    rows = conn.execute(
        f"SELECT primary_region, COUNT(*) AS n FROM story WHERE {where} "
        "GROUP BY primary_region", params).fetchall()
    return {r["primary_region"]: r["n"] for r in rows}
