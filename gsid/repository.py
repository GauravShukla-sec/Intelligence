"""Read-side queries: assemble full story objects, lists, filters, regulations.

Kept separate from `store.py` (write side) for clarity. All timestamps stay in
UTC here; timezone conversion is a presentation concern handled client-side.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from . import db
from .ingestion.advisory_levels import LEVEL_LABELS as ADVISORY_LEVEL_LABELS
from .ingestion.dedup import jaccard, signature
from .taxonomy import (
    CATEGORY_NAMES, REGION_NAMES, country_name, region_for_country,
)
from .ingestion.advisory_levels import LEVEL_LABELS


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
        "advisory_level": row["advisory_level"] if "advisory_level" in row.keys() else 0,
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
    if filters.get("new_today"):
        # Published (or, if unknown, first seen) within the last 24 hours.
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        add("COALESCE(event_time, first_seen) >= ?", cutoff)
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
    elif filters.get("sort") == "event":
        # Newest EVENT first. Sorting by last_updated looks jumbled wherever the
        # event date is what's displayed: an old event re-verified today would
        # jump to the top of a list labelled "newest first".
        order = "COALESCE(event_time, first_seen) DESC"
    elif filters.get("sort") == "urgency":
        order = "(urgency='Immediate') DESC, (urgency='24 Hours') DESC, relevance_score DESC"

    sql = (f"SELECT * FROM story WHERE {' AND '.join(where)} "
           f"ORDER BY {order} LIMIT ? OFFSET ?")
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    return [_story_row_to_summary(r) for r in rows]


# Near-duplicate coverage of the *same* event (collapse in lists). Tuned to
# fold near-identical headlines while leaving a developing story's distinct
# beats ("minister resigns" vs "protesters celebrate") as separate stories.
_SIM_COLLAPSE = 0.5
# Looser bar for "you might also want to read" suggestions on a story page.
_SIM_RELATED = 0.36


def group_similar_stories(stories: list[dict], threshold: float = _SIM_COLLAPSE) -> list[dict]:
    """Collapse near-duplicate coverage of the same event by headline similarity.

    Input is a pre-ordered story list (highest-ranked first). Each returned
    item is the group's lead (its highest-ranked member, i.e. the first seen)
    with a ``similar`` list of the folded-in duplicates. Non-destructive — the
    underlying stories are untouched.
    """
    groups: list[dict] = []
    for s in stories:
        sig = signature(s.get("headline", ""))
        for g in groups:
            if sig and jaccard(sig, g["sig"]) >= threshold:
                g["members"].append(s)
                g["sig"] |= sig
                break
        else:
            groups.append({"members": [s], "sig": set(sig)})
    out: list[dict] = []
    for g in groups:
        lead = dict(g["members"][0])
        lead["similar"] = [
            {"id": m["id"], "headline": m["headline"],
             "primary_country": m.get("primary_country"),
             "location_text": m.get("location_text")}
            for m in g["members"][1:]
        ]
        out.append(lead)
    return out


def list_stories_grouped(conn, filters: dict[str, Any] | None = None,
                         limit: int = 100, offset: int = 0) -> list[dict]:
    """list_stories with near-duplicate coverage collapsed into lead + similar."""
    raw = list_stories(conn, filters, limit=min(limit * 3, 300), offset=offset)
    return group_similar_stories(raw)[:limit]


def related_stories(conn, story_id: str, limit: int = 6,
                    threshold: float = _SIM_RELATED) -> list[dict]:
    """Other stories covering a similar event, ranked by headline similarity.

    Candidates are scoped by RELEVANCE (shares the category or a tagged
    country), not merely by recency: ordering the whole table by last_updated
    and taking the first N silently drops older near-duplicates once the desk
    holds more stories than the scan window.
    """
    target = conn.execute(
        "SELECT id, headline, category, is_demo FROM story WHERE id=?",
        (story_id,)).fetchone()
    if not target:
        return []
    tsig = signature(target["headline"])
    if not tsig:
        return []
    rows = conn.execute(
        "SELECT id, headline, primary_country, location_text, relevance_score "
        "FROM story WHERE id<>? AND is_demo=? "
        "AND (status IS NULL OR status!='advisory') "
        "AND (category=? OR id IN (SELECT story_id FROM story_country "
        "     WHERE country IN (SELECT country FROM story_country WHERE story_id=?))) "
        "ORDER BY last_updated DESC LIMIT 800",
        (story_id, target["is_demo"], target["category"], story_id)).fetchall()
    scored = []
    for r in rows:
        sc = jaccard(tsig, signature(r["headline"]))
        if sc >= threshold:
            scored.append((sc, r))
    scored.sort(key=lambda x: (-x[0], -(x[1]["relevance_score"] or 0)))
    return [{"id": r["id"], "headline": r["headline"],
             "primary_country": r["primary_country"],
             "location_text": r["location_text"], "similarity": round(sc, 2)}
            for sc, r in scored[:limit]]


def get_story(conn, story_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM story WHERE id=?", (story_id,)).fetchone()
    if row is None:
        return None
    story = _story_row_to_summary(row)
    story["analysis"] = json.loads(row["analysis_json"]) if row["analysis_json"] else {}
    story["scoring"] = json.loads(row["scoring_json"]) if row["scoring_json"] else {}
    story["advisory"] = (json.loads(row["advisory_json"])
                         if ("advisory_json" in row.keys() and row["advisory_json"])
                         else None)

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
    story["similar"] = related_stories(conn, story_id)
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
        "ct.orig_headline, ct.is_primary, ct.is_circular, ct.advisory_level, "
        "s.name AS source_name, "
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
    # Newest EVENT first, matching the date shown on each alert card.
    f = {"alerts_only": True, "sort": "event"}
    if data_mode:
        f["data_mode"] = data_mode
    stories = list_stories(conn, f, limit=50)
    for s in stories:
        s["alert"] = _alert(conn, s["id"])
    return stories


def list_regulations(conn, data_mode: str | None = None) -> list[dict]:
    where = ""
    if data_mode == "live":
        where = "WHERE is_demo=0"
    elif data_mode == "demo":
        where = "WHERE is_demo=1"
    rows = conn.execute(
        f"SELECT * FROM regulation {where} ORDER BY updated_at DESC").fetchall()
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


def travel_brief(conn, code: str, data_mode: str | None = None,
                 origin: str | None = None) -> dict:
    """Per-destination travel-risk brief: official advisory + relevant
    developments + a synthesized 'what to look out for' list.

    The risk picture is DESTINATION-based (that is how government advisories
    work). The optional `origin` (traveller home country / nationality) does
    not change the threat — it only decides *which* government's advisory to
    lead with and surfaces entry/visa/consular context for that traveller.
    """
    code = (code or "").strip().lower()
    origin = (origin or "").strip().lower() or None
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

    advisory_details = [_attach_advisory_detail(conn, s, origin) for s in advisories]

    # Authoritative destination risk = worst government advisory level (Layer 2),
    # not our news-impact heuristic (which over-reads for quiet destinations).
    adv_levels = [(a.get("advisory") or {}).get("consensus", 0) or 0
                  for a in advisory_details]
    advisory_consensus = max(adv_levels) if adv_levels else 0

    return {
        "country": code,
        "country_name": name,
        "region": region,
        "region_name": REGION_NAMES.get(region, region),
        "advisories": advisory_details,
        "official_links": _official_advisory_links(code, name, origin, advisory_details),
        "related": related,
        "watch_items": watch,
        "recommended_actions": actions,
        # The destination headline reflects the DESTINATION's own risk only.
        # Regional developments are shown for context but must not inflate it
        # (an unrelated crisis elsewhere in the region shouldn't make a quiet
        # country read "Critical").
        "highest_impact": _highest_impact(country_stories),
        "advisory_consensus": advisory_consensus,
        "advisory_consensus_label": LEVEL_LABELS.get(advisory_consensus, ""),
        "traveller": _traveller_context(origin, code, name),
    }


# Which ingested government advisory best matches a traveller's home country.
def _lead_authority(origin: str | None) -> str | None:
    if origin == "gb":
        return "fcdo"
    if origin == "us":
        return "state"
    return None  # other nationalities: no strong lead among the two we ingest


def _traveller_context(origin: str | None, dest_code: str, dest_name: str) -> dict:
    """Origin-dependent context: whose advisory leads + entry/visa guidance.

    We do NOT have per-nationality visa data, so we give authoritative
    guidance and links rather than fabricating specific visa rules.
    """
    if not origin:
        return {
            "origin": None,
            "note": "Showing UK FCDO and US State Department advisories. Select a "
                    "traveller nationality to lead with the matching government's "
                    "advice and see entry/consular context.",
            "lead": None,
        }
    origin_name = country_name(origin)
    lead = _lead_authority(origin)
    lead_name = {"fcdo": "UK FCDO", "state": "US State Department"}.get(lead)
    if lead_name:
        whose = f"Leading with {lead_name} advice, written for {origin_name} travellers."
    else:
        whose = (f"We track UK FCDO and US State Department advisories. {origin_name} "
                 f"may publish its own government travel advice — check it as the "
                 f"authoritative source for {origin_name} nationals.")
    return {
        "origin": origin,
        "origin_name": origin_name,
        "lead": lead,
        "note": whose,
        "entry_note": (
            f"Entry, visa and transit requirements for {dest_name} depend on the "
            f"traveller's nationality ({origin_name}) and passport, not on the threat "
            f"level. Verify against {dest_name}'s official immigration authority and "
            f"the traveller's own government travel advice before booking."
        ),
    }


def _attach_advisory_detail(conn, s: dict, origin: str | None = None) -> dict:
    full = get_story(conn, s["id"]) or s
    s = dict(s)
    s["summary"] = full.get("summary", s.get("summary"))
    s["advisory"] = full.get("advisory")  # cross-government consensus (Layer 2)
    citations = full.get("citations", [])
    lead = _lead_authority(origin)
    if lead:
        key = "fcdo" if lead == "fcdo" else "state"
        match = "FCDO" if key == "fcdo" else "State"
        citations = sorted(
            citations,
            key=lambda c: 0 if match.lower() in (c.get("source_name") or "").lower() else 1,
        )
    s["citations"] = citations
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


def _official_advisory_links(code: str, name: str, origin: str | None = None,
                             advisories: list[dict] | None = None) -> list[dict]:
    """Authoritative government advisory links for a destination.

    Every government that rates this destination gets a button. We prefer the
    exact URL we ingested (known-good, per-destination) and only fall back to a
    stable landing page — never construct a per-country URL we can't verify, so
    we don't reintroduce dead/raw links.
    """
    slug = name.lower().replace(" ", "-")
    # government ISO-2 -> (button label, stable fallback landing URL)
    GOV = {
        "gb": ("UK FCDO travel advice",
               f"https://www.gov.uk/foreign-travel-advice/{slug}"),
        "us": ("US State Dept travel advisories",
               "https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html"),
        "ca": ("Global Affairs Canada advisory",
               f"https://travel.gc.ca/destinations/{slug}"),
        "de": ("Germany Auswärtiges Amt advice",
               "https://www.auswaertiges-amt.de/en/ReiseUndSicherheit/reiseund"
               "sicherheitshinweise"),
        "au": ("Australia Smartraveller advice",
               "https://www.smartraveller.gov.au/destinations"),
    }
    # Known-good per-destination URLs we actually ingested, keyed by government.
    ingested: dict[str, str] = {}
    for a in (advisories or []):
        for c in a.get("citations", []):
            gov = (c.get("source_country") or "").lower()
            if gov in GOV and c.get("url"):
                ingested.setdefault(gov, c["url"])

    # UK + US are always offered (the baseline we track); Canada/Germany/
    # Australia appear when they actually rate this destination.
    order = ["gb", "us", "ca", "de", "au"]
    if _lead_authority(origin) == "state":
        order = ["us", "gb", "ca", "de", "au"]
    links = []
    for gov in order:
        if gov in ("gb", "us") or gov in ingested:
            label, landing = GOV[gov]
            links.append({"name": label, "url": ingested.get(gov, landing)})
    return links


def _highest_impact(stories: list[dict]) -> str:
    order = {"Low": 0, "Moderate": 1, "High": 2, "Critical": 3}
    best = "Low"
    for s in stories:
        if order.get(s.get("impact", "Low"), 0) > order.get(best, 0):
            best = s["impact"]
    return best


def advisory_changes(conn, days: int = 14, limit: int = 40,
                     include_new: bool = False) -> dict:
    """What changed in government travel advice recently.

    Reads the change-detection state written during ingestion. Three event
    kinds are distinguished:

      escalated / de-escalated — the level actually moved (the money signal)
      revised                  — same level, but the advisory text changed
      new                      — first time we tracked this destination

    First sightings are counted but kept out of the list by default: on a fresh
    database every destination is "new", which would bury the real moves.
    """
    from .ingestion.connectors import FEED_BY_ID

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(days, 0))).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute(
        "SELECT feed_id, dest_country, level, prev_level, changed_at "
        "FROM advisory_state WHERE changed_at >= ? ORDER BY changed_at DESC",
        (cutoff,),
    ).fetchall()

    # Destination -> advisory story, so each change can deep-link to the brief.
    story_by_country: dict[str, str] = {}
    for r in conn.execute(
        "SELECT sc.country AS c, s.id AS id FROM story s "
        "JOIN story_country sc ON sc.story_id = s.id WHERE s.status='advisory'"
    ).fetchall():
        story_by_country.setdefault((r["c"] or "").lower(), r["id"])

    counts = {"escalated": 0, "deescalated": 0, "revised": 0, "new": 0}
    changes: list[dict] = []
    for r in rows:
        level, prev = r["level"] or 0, r["prev_level"] or 0
        if prev <= 0:
            kind = "new"
        elif level > prev:
            kind = "escalated"
        elif level < prev:
            kind = "deescalated"
        else:
            kind = "revised"
        counts[kind] += 1
        if kind == "new" and not include_new:
            continue
        feed = FEED_BY_ID.get(r["feed_id"])
        code = (r["dest_country"] or "").lower()
        changes.append({
            "kind": kind,
            "country": code,
            "country_name": country_name(code),
            "feed_id": r["feed_id"],
            "source_name": feed.name if feed else r["feed_id"],
            "gov": feed.country if feed else "",
            "level": level,
            "prev_level": prev,
            "level_label": ADVISORY_LEVEL_LABELS.get(level, ""),
            "prev_label": ADVISORY_LEVEL_LABELS.get(prev, ""),
            "changed_at": r["changed_at"],
            "story_id": story_by_country.get(code),
        })

    # Escalations first (worst-case bias), then most recent.
    order = {"escalated": 0, "deescalated": 1, "revised": 2, "new": 3}
    changes.sort(key=lambda c: (order.get(c["kind"], 9), -c["level"],
                                c["changed_at"] or ""), reverse=False)
    return {"days": days, "since": cutoff, "counts": counts,
            "tracked": len(rows), "changes": changes[:limit]}


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


_IMPACT_RANK = {"Low": 1, "Moderate": 2, "High": 3, "Critical": 4}


def country_risk(conn, data_mode: str | None = None) -> dict[str, dict]:
    """Per-country risk for the world map choropleth, keyed by ISO-2 (lower).

    Each country gets its worst tracked impact and a development count.
    Travel advisories are excluded (they live in Travel Risk, not the map).
    """
    where = "(s.status IS NULL OR s.status != 'advisory')"
    if data_mode == "demo":
        where += " AND s.is_demo=1"
    elif data_mode == "live":
        where += " AND s.is_demo=0"
    rows = conn.execute(
        f"SELECT sc.country AS c, s.impact AS impact FROM story_country sc "
        f"JOIN story s ON sc.story_id = s.id WHERE {where}").fetchall()
    agg: dict[str, dict] = {}
    for r in rows:
        c = (r["c"] or "").strip().lower()
        if not c:
            continue
        rank = _IMPACT_RANK.get(r["impact"], 0)
        e = agg.setdefault(c, {"count": 0, "rank": 0, "impact": "Low"})
        e["count"] += 1
        if rank > e["rank"]:
            e["rank"], e["impact"] = rank, r["impact"] or "Low"
    return {c: {"impact": v["impact"], "count": v["count"]} for c, v in agg.items()}
