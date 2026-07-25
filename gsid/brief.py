"""Daily Global Security Brief assembly.

Builds the 12-section brief from persisted stories/regulations. Purely a
read/compose step — no fabrication. Sections that have no qualifying content
say so explicitly rather than padding.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import db, repository
from .taxonomy import REGIONS, REGION_NAMES


def _risk_direction(trend: str) -> str:
    return {
        "Improving": "↓ improving",
        "Stable": "→ stable",
        "Deteriorating": "↑ deteriorating",
        "Rapidly Deteriorating": "⇈ rapidly deteriorating",
    }.get(trend, "→ stable")


def build_brief(conn, data_mode: str | None = None) -> dict:
    stories = repository.list_stories(
        conn, {"data_mode": data_mode} if data_mode else {}, limit=200
    )
    top = stories[:5]

    # ---- 1. Executive snapshot ----
    snapshot = [{
        "id": s["id"], "headline": s["headline"],
        "why": _why_line(s),
        "direction": _risk_direction(s["trend"]),
        "immediate_action": s["urgency"] in ("Immediate", "24 Hours"),
        "score": s.get("relevance_score"),
        "impact": s.get("impact"),
        "urgency": s.get("urgency"),
        "confidence": s.get("confidence"),
        "trend": s.get("trend"),
        "category_name": s.get("category_name"),
        "region_name": s.get("region_name"),
    } for s in top]

    # ---- 2. Global risk pulse ----
    deteriorating = [s for s in stories if s["trend"] in
                     ("Deteriorating", "Rapidly Deteriorating")]
    improving = [s for s in stories if s["trend"] == "Improving"]
    regions_det = _region_names({s["primary_region"] for s in deteriorating})
    regions_imp = _region_names({s["primary_region"] for s in improving})

    posture = _overall_posture(stories)
    pulse = {
        "posture": posture,
        "regions_deteriorating": regions_det,
        "regions_improving": regions_imp,
        "emerging_hotspots": [s["region_name"] for s in stories[:3]],
        "top_regulatory": _top_of_category(stories, "regulatory"),
        "top_supply_chain": _top_of_category(stories, "supply_chain"),
        "top_employee_safety": _top_by_signal(conn, stories, "people_safety"),
        "watch_next": _watch_next(stories),
    }

    # ---- 3. Critical alerts ----
    alerts = repository.list_alerts(conn, data_mode)

    # ---- 4. Regional watch ----
    regional = repository.regional_watch(conn, data_mode)

    # ---- 5. Laws & regulations ----
    regs = repository.list_regulations(conn, data_mode)

    # ---- 6. Supply-chain watch ----
    supply = [s for s in stories if s["category"] == "supply_chain"][:6]

    # ---- 7. Cyber-physical watch ----
    cyber = [s for s in stories if s["category"] == "cyber_physical"][:6]

    # ---- 8. 30/60/90 outlook ----
    outlook = _outlook(regs)

    # ---- 9. Security lesson ----
    lesson = _todays_lesson(stories)

    # ---- 10 & 11 handled by scenario/quiz endpoints; include references ----
    scenario_ids = [r["id"] for r in conn.execute(
        "SELECT id FROM scenario ORDER BY is_demo DESC LIMIT 1").fetchall()]

    # ---- 12. Executive talking points ----
    talking_points = _exec_talking_points(conn, top)

    brief = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_mode": data_mode or "all",
        "story_count": len(stories),
        "executive_snapshot": snapshot,
        "global_risk_pulse": pulse,
        "critical_alerts": alerts,
        "regional_watch": regional,
        "regulations": regs,
        "supply_chain_watch": supply,
        "cyber_physical_watch": cyber,
        "outlook": outlook,
        "todays_lesson": lesson,
        "scenario_id": scenario_ids[0] if scenario_ids else None,
        "executive_talking_points": talking_points,
    }
    return brief


def persist_brief(conn, brief: dict) -> str:
    bid = db.new_id("brief_")
    conn.execute(
        "INSERT INTO daily_brief(id,brief_date,payload_json,created_at) VALUES (?,?,?,?)",
        (bid, brief["generated_at"][:10], json.dumps(brief), db.utcnow()),
    )
    conn.commit()
    return bid


# --------------------------------------------------------------------------
def _why_line(s: dict) -> str:
    return (f"{s['category_name']} in {s['region_name']}; impact {s['impact']}, "
            f"urgency {s['urgency']}, confidence {s['confidence']}.")


def _region_names(region_ids) -> list[str]:
    return sorted({REGION_NAMES.get(r, r) for r in region_ids if r and r != "global"})


def _overall_posture(stories: list[dict]) -> dict:
    if not stories:
        return {"level": "Baseline", "reason": "No qualifying developments loaded."}
    crit = sum(1 for s in stories if s["impact"] == "Critical")
    high = sum(1 for s in stories if s["impact"] == "High")
    rapid = sum(1 for s in stories if s["trend"] == "Rapidly Deteriorating")
    if crit >= 1 or rapid >= 2:
        level = "Elevated"
    elif high >= 2:
        level = "Guarded"
    else:
        level = "Baseline"
    return {
        "level": level,
        "reason": f"{crit} critical- and {high} high-impact developments tracked; "
                  f"{rapid} rapidly deteriorating.",
    }


def _top_of_category(stories: list[dict], category: str) -> dict | None:
    for s in stories:
        if s["category"] == category:
            return {"id": s["id"], "headline": s["headline"]}
    return None


def _top_by_signal(conn, stories: list[dict], signal_key: str) -> dict | None:
    best = None
    best_val = 0.0
    for s in stories[:50]:
        row = conn.execute("SELECT analysis_json FROM story WHERE id=?", (s["id"],)).fetchone()
        if not row or not row["analysis_json"]:
            continue
        val = (json.loads(row["analysis_json"]).get("signals", {}) or {}).get(signal_key, 0)
        if val > best_val:
            best_val = val
            best = {"id": s["id"], "headline": s["headline"], "intensity": round(val, 2)}
    return best


def _watch_next(stories: list[dict]) -> list[dict]:
    fast = [s for s in stories if s["velocity"] in ("Fast", "Immediate")]
    fast = fast or stories
    return [{"id": s["id"], "headline": s["headline"]} for s in fast[:3]]


def _outlook(regs: list[dict]) -> dict:
    confirmed, foreseeable, speculative = [], [], []
    for r in regs:
        entry = {"title": r["title"], "when": r.get("effective_date") or "TBD",
                 "framework": r.get("framework")}
        status = (r.get("status") or "").lower()
        if status in ("effective", "enforced", "enacted"):
            confirmed.append(entry)
        elif status in ("draft", "proposal"):
            foreseeable.append(entry)
        else:
            speculative.append(entry)
    return {
        "confirmed": confirmed,
        "foreseeable": foreseeable,
        "speculative": speculative,
        "note": "Populate additional confirmed dates (elections, court decisions, "
                "military exercises, seasonal weather, labor/sanctions deadlines) via "
                "the regulation tracker and calendar connectors.",
    }


def _todays_lesson(stories: list[dict]) -> dict:
    # Rotate lessons; connect to a current story where possible.
    example = next((s for s in stories if s["confidence"] in ("Unverified", "Low")),
                   stories[0] if stories else None)
    return {
        "concept": "Intelligence confidence vs. source strength",
        "plain_language": (
            "Confidence is not the same as how alarming a report sounds. It reflects "
            "the strength and independence of the evidence. A dramatic single-source "
            "social clip is 'Unverified'; a claim backed by a primary authority and "
            "multiple reputable outlets can be 'Confirmed'. Treat weak-evidence items "
            "as alerting signals that trigger validation — not as facts to act on."),
        "connected_story": ({"id": example["id"], "headline": example["headline"]}
                            if example else None),
        "why_it_helps": "Prevents both under-reaction (dismissing early warnings) and "
                        "over-reaction (acting on rumor). Ties directly to proportionate "
                        "recommended actions.",
    }


def _exec_talking_points(conn, top: list[dict]) -> list[str]:
    if not top:
        return ["No material developments to brief at this time."]
    points = [
        f"Top watch item: {top[0]['headline']} — {top[0]['impact']} impact, "
        f"{top[0]['confidence']} confidence; recommended posture is proportionate.",
    ]
    for s in top[1:4]:
        points.append(f"{s['region_name']}: {s['headline']} ({s['category_name']}, "
                      f"{s['urgency']}).")
    points.append("We are validating site/supplier/traveller exposure against each item "
                  "and will escalate only on confirmed deterioration.")
    return points[:5]
