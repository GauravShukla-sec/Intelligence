"""Export generators.

Turns a persisted story into the operational artefacts a global-security
professional actually files: risk-register entries, corrective actions,
travel-security notes, Power BI-friendly CSV/JSON, and leadership summaries.

All exports are derived strictly from stored analysis — nothing is invented.
Sources are carried through so every artefact keeps its evidence trail.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from . import repository

# Map categorical scales to numeric levels for register math.
_LIKELIHOOD_NUM = {"Rare": 1, "Unlikely": 2, "Possible": 3, "Likely": 4, "Almost Certain": 5}
_IMPACT_NUM = {"Low": 1, "Moderate": 2, "High": 4, "Critical": 5}


def _sources_str(story: dict) -> str:
    return " | ".join(
        f"{c.get('source_name','?')} ({c.get('published_at','')}) {c.get('url','')}"
        for c in story.get("citations", [])
    )


def risk_register_entry(story: dict) -> dict[str, Any]:
    analysis = story.get("analysis", {})
    signals = analysis.get("signals", {})
    likelihood = story.get("likelihood", "Possible")
    impact = story.get("impact", "Moderate")
    inherent = _LIKELIHOOD_NUM.get(likelihood, 3) * _IMPACT_NUM.get(impact, 2)
    # Residual assumes proportionate monitoring/validation controls in place.
    residual = max(1, inherent - 3)

    threat = _dominant_threat(signals)
    controls = _existing_controls(signals)
    gaps = _control_gaps(signals)

    return {
        "risk_title": _strip_demo(story["headline"]),
        "description": analysis.get("what_happened") or story.get("summary", ""),
        "threat": threat,
        "vulnerability": "Exposure of sites/suppliers/travellers in the affected "
                         f"geography ({story.get('location_text') or story.get('region_name')}).",
        "potential_impact": "; ".join(analysis.get("risk_pathway", []))
                            or f"{impact} operational/safety impact.",
        "existing_controls": controls,
        "control_gaps": gaps,
        "likelihood": likelihood,
        "impact": impact,
        "inherent_risk": inherent,
        "residual_risk": residual,
        "treatment_strategy": _treatment(inherent),
        "recommended_actions": "; ".join(a["text"] for a in analysis.get("actions", [])),
        "owner": "TBD (assign regional security manager)",
        "target_date": "TBD",
        "monitoring_indicators": "; ".join(i.get("text", "") for i in analysis.get("indicators", [])),
        "sources": _sources_str(story),
        "last_reviewed": story.get("last_updated"),
        "confidence": story.get("confidence"),
        "relevance_score": story.get("relevance_score"),
    }


def corrective_action(story: dict) -> dict[str, Any]:
    analysis = story.get("analysis", {})
    return {
        "issue_title": _strip_demo(story["headline"]),
        "issue_description": analysis.get("what_happened") or story.get("summary", ""),
        "root_cause_prompt": "Assess whether an existing control gap enabled exposure "
                             "(access control, seal integrity, route security, reporting).",
        "corrective_actions": [a["text"] for a in analysis.get("actions", [])
                               if a["type"] in ("Mitigate", "Assess", "Communicate")],
        "verification": "Confirm closure via site assessment / control re-test; "
                        "update risk register and KRIs.",
        "priority": story.get("impact", "Moderate"),
        "owner": "TBD",
        "due_date": "TBD",
        "sources": _sources_str(story),
    }


def travel_security_note(story: dict) -> dict[str, Any]:
    analysis = story.get("analysis", {})
    return {
        "destination": story.get("location_text") or story.get("region_name"),
        "countries": story.get("countries", []),
        "situation": analysis.get("what_happened") or story.get("summary", ""),
        "threat_level": story.get("impact"),
        "confidence": story.get("confidence"),
        "advice": [a["text"] for a in analysis.get("actions", [])],
        "watch_indicators": [i.get("text", "") for i in analysis.get("indicators", [])],
        "sources": _sources_str(story),
        "last_updated": story.get("last_updated"),
    }


def executive_summary(story: dict) -> dict[str, Any]:
    analysis = story.get("analysis", {})
    return {
        "headline": _strip_demo(story["headline"]),
        "bottom_line": analysis.get("why_global", ""),
        "ratings": {
            "relevance_score": story.get("relevance_score"),
            "impact": story.get("impact"), "urgency": story.get("urgency"),
            "confidence": story.get("confidence"), "trend": story.get("trend"),
        },
        "talking_points": analysis.get("talking_points", []),
        "recommended_actions": [f"[{a['type']}] {a['text']}" for a in analysis.get("actions", [])],
        "sources": [c.get("url") for c in story.get("citations", [])],
    }


def email_leadership(story: dict) -> str:
    es = executive_summary(story)
    lines = [
        f"Subject: Security brief — {es['headline']}",
        "",
        f"Bottom line: {es['bottom_line']}",
        "",
        (f"Ratings: relevance {es['ratings']['relevance_score']}/100 | "
         f"impact {es['ratings']['impact']} | urgency {es['ratings']['urgency']} | "
         f"confidence {es['ratings']['confidence']} | trend {es['ratings']['trend']}"),
        "",
        "Recommended actions:",
    ]
    lines += [f"  - {a}" for a in es["recommended_actions"]]
    lines += ["", "Sources:"]
    lines += [f"  - {u}" for u in es["sources"] if u]
    lines += ["", "(Prepared by the Global Security Intelligence Desk.)"]
    return "\n".join(lines)


def stories_to_csv(stories: list[dict]) -> str:
    """Power BI-friendly flat CSV of story summaries."""
    buf = io.StringIO()
    fields = ["id", "headline", "category_name", "region_name", "primary_country",
              "location_text", "event_time", "last_updated", "status",
              "relevance_score", "urgency", "impact", "likelihood", "velocity",
              "confidence", "trend", "is_alert", "is_demo"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for s in stories:
        writer.writerow(s)
    return buf.getvalue()


def risk_register_csv(entries: list[dict]) -> str:
    buf = io.StringIO()
    if not entries:
        return ""
    fields = list(entries[0].keys())
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for e in entries:
        row = {k: (json.dumps(v) if isinstance(v, (list, dict)) else v)
               for k, v in e.items()}
        writer.writerow(row)
    return buf.getvalue()


# --------------------------------------------------------------------------
def _strip_demo(text: str) -> str:
    return text.replace("[DEMO] ", "").strip()


def _dominant_threat(signals: dict) -> str:
    if not signals:
        return "Security development with potential operational impact."
    key = max(signals, key=lambda k: signals.get(k, 0))
    return {
        "people_safety": "Threat to personnel safety in the affected area.",
        "facility_assets": "Threat to facilities / physical assets.",
        "operational": "Business-continuity disruption threat.",
        "supply_chain": "Supply-chain / transportation disruption threat.",
        "regulatory": "Compliance / regulatory exposure.",
        "geopolitical": "Geopolitical escalation exposure.",
        "cyber_physical": "Cyber-physical / OT disruption threat.",
        "reputational": "Executive / reputational exposure.",
    }.get(key, "Security development with potential operational impact.")


def _existing_controls(signals: dict) -> str:
    controls = ["Intelligence monitoring & alerting (this desk)"]
    if signals.get("facility_assets", 0) > 0.3:
        controls.append("Physical security controls (access, CCTV, perimeter, IDS)")
    if signals.get("supply_chain", 0) > 0.3:
        controls.append("CTPAT/seal procedures; carrier & 3PL vetting")
    if signals.get("people_safety", 0) > 0.3:
        controls.append("Travel-risk program & emergency notification")
    if signals.get("regulatory", 0) > 0.3:
        controls.append("Compliance register & reporting workflow")
    return "; ".join(controls)


def _control_gaps(signals: dict) -> str:
    gaps = []
    if signals.get("supply_chain", 0) > 0.5:
        gaps.append("Alternate routing/supplier redundancy may be unconfirmed")
    if signals.get("people_safety", 0) > 0.5:
        gaps.append("Traveller location awareness for the region may be incomplete")
    if signals.get("regulatory", 0) > 0.5:
        gaps.append("Reporting-timeline runbook may need validation")
    return "; ".join(gaps) or "To be determined via assessment."


def _treatment(inherent: int) -> str:
    if inherent >= 16:
        return "Reduce (prioritized mitigation) + Escalate for decision"
    if inherent >= 9:
        return "Reduce (targeted controls) / consider Transfer where applicable"
    if inherent >= 4:
        return "Monitor & accept with periodic review"
    return "Accept with routine monitoring"


# Dispatch table used by the API.
EXPORTERS = {
    "risk_register": risk_register_entry,
    "corrective_action": corrective_action,
    "travel_note": travel_security_note,
    "executive_summary": executive_summary,
    "email_leadership": email_leadership,
}


def export_story(story: dict, kind: str):
    fn = EXPORTERS.get(kind)
    if fn is None:
        raise ValueError(f"unknown export kind: {kind}")
    return fn(story)
