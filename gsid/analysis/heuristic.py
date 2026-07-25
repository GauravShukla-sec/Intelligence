"""Deterministic, no-API heuristic analyzer.

This is the default analyzer. It uses transparent keyword/regex signal
detection to produce the same structured `AnalysisResult` a model-backed
analyzer would. It is intentionally conservative: it hedges language,
distinguishes claims from facts, and never invents citations.

Because it is deterministic it is also fully unit-testable, and it guarantees
the platform works with zero external dependencies or credentials.
"""

from __future__ import annotations

import re

from .base import AnalysisInput, AnalysisResult

# --------------------------------------------------------------------------
# Signal lexicons: each relevance dimension maps to weighted keyword groups.
# Matching a strong term contributes more intensity than a weak term.
# --------------------------------------------------------------------------
_LEX: dict[str, list[tuple[float, list[str]]]] = {
    "people_safety": [
        (1.0, ["killed", "casualt", "fatalit", "dead", "shooting", "gunman",
               "hostage", "kidnap", "explosion", "bombing", "stabbing",
               "evacuat", "wildfire", "earthquake", "flood", "hurricane",
               "typhoon", "outbreak", "attack on", "armed attack"]),
        (0.6, ["injur", "clash", "violence", "unrest", "riot", "protest",
               "curfew", "shelling", "airstrike", "militant", "extremist",
               "toxic", "contamination", "storm", "heatwave"]),
        (0.3, ["threat", "warning", "tension", "standoff", "demonstration"]),
    ],
    "facility_assets": [
        (1.0, ["factory", "plant", "warehouse", "refinery", "substation",
               "arson", "sabotage", "vandal", "torched", "destroyed facility"]),
        (0.6, ["office", "building", "site", "depot", "terminal", "pipeline",
               "damaged", "fire at", "break-in", "intrusion", "perimeter"]),
        (0.3, ["infrastructure", "installation", "premises"]),
    ],
    "operational": [
        (1.0, ["shutdown", "halted production", "suspended operations",
               "blackout", "power outage", "grid failure", "evacuated staff"]),
        (0.6, ["disruption", "closure", "closed", "outage", "downtime",
               "strike", "walkout", "stoppage", "delay", "grounded"]),
        (0.3, ["slowdown", "restriction", "reduced", "backlog"]),
    ],
    "supply_chain": [
        (1.0, ["port", "shipping", "container", "cargo theft", "canal",
               "strait", "blockade", "customs", "freight", "logistics",
               "supply chain", "rail freight", "trucking"]),
        (0.6, ["export", "import", "tariff", "border", "smuggl", "counterfeit",
               "seal", "vessel", "maritime", "airfreight", "warehouse"]),
        (0.3, ["trade", "supplier", "route", "corridor", "distribution"]),
    ],
    "regulatory": [
        (1.0, ["regulation", "directive", "nis2", "cer directive", "ctpat",
               "sanction", "export control", "compliance deadline",
               "enforcement action", "gdpr", "csddd", "forced labor",
               "forced labour", "aeo", "legislation", "statute"]),
        (0.6, ["law", "bill", "rule", "mandate", "fine", "penalt", "court",
               "ruling", "regulator", "customs authority", "reporting requirement"]),
        (0.3, ["policy", "guidance", "standard", "iso "]),
    ],
    "geopolitical": [
        (1.0, ["war", "invasion", "coup", "mobiliz", "missile", "nuclear",
               "military escalation", "annex", "airspace"]),
        (0.6, ["conflict", "diplomat", "treaty", "alliance", "sanction",
               "border tension", "territorial", "election dispute", "ceasefire"]),
        (0.3, ["talks", "summit", "negotiation", "relations"]),
    ],
    "cyber_physical": [
        (1.0, ["ransomware", "ics", "scada", "operational technology",
               "ot network", "industrial control", "cyberattack on",
               "control system", "gps jamming", "gps spoof"]),
        (0.6, ["cyberattack", "hack", "breach", "malware", "deepfake",
               "drone", "surveillance", "biometric", "data center outage"]),
        (0.3, ["vulnerability", "phishing", "software", "network"]),
    ],
    "reputational": [
        (1.0, ["executive", "ceo", "boycott", "scandal", "reputational"]),
        (0.6, ["brand", "protest against company", "investor", "shareholder",
               "public backlash", "misinformation campaign"]),
        (0.3, ["media", "coverage", "criticism"]),
    ],
}

_VELOCITY_CUES = {
    "Immediate": ["breaking", "unfolding", "ongoing now", "active shooter",
                  "in progress", "just", "moments ago", "erupted"],
    "Fast": ["rapidly", "escalat", "surg", "spreading", "deteriorat", "spiral"],
    "Developing": ["developing", "growing", "rising", "building", "planned"],
}

_TREND_DETERIORATE = ["escalat", "worsen", "deteriorat", "surg", "spread",
                      "intensif", "expand", "more violent", "widening"]
_TREND_IMPROVE = ["ceasefire", "de-escalat", "resolved", "reopened", "eased",
                  "restored", "agreement reached", "calm returned", "lifted"]

_LIKELIHOOD_CUES = {
    "Almost Certain": ["confirmed", "declared", "official", "in effect", "enacted"],
    "Likely": ["expected", "set to", "will", "planned", "scheduled"],
    "Possible": ["could", "may", "risk of", "potential", "warned"],
    "Unlikely": ["unlikely", "remote chance", "not expected"],
}


def _score_dimension(text: str, groups: list[tuple[float, list[str]]]) -> float:
    best = 0.0
    hits = 0
    for weight, terms in groups:
        for term in terms:
            if term in text:
                best = max(best, weight)
                hits += 1
    if best == 0.0:
        return 0.0
    # A few corroborating hits nudge intensity up but never above the group max.
    bonus = min(0.15, 0.05 * max(0, hits - 1))
    return min(1.0, best + bonus)


def _pick_from_cues(text: str, cues: dict[str, list[str]], default: str) -> str:
    for level, terms in cues.items():
        if any(t in text for t in terms):
            return level
    return default


class HeuristicAnalyzer:
    name = "heuristic"

    def analyze(self, item: AnalysisInput) -> AnalysisResult:
        text = f"{item.headline}\n{item.body}".lower()

        signals = {dim: _score_dimension(text, groups) for dim, groups in _LEX.items()}
        # Category prior: ensure the labelled category has at least some weight.
        _apply_category_prior(item.category, signals)

        velocity = _pick_from_cues(text, _VELOCITY_CUES, "Developing")
        trend = self._trend(text)
        likelihood = _pick_from_cues(text, _LIKELIHOOD_CUES, "Possible")

        result = AnalysisResult(
            signals=signals,
            velocity=velocity,
            trend=trend,
            likelihood=likelihood,
            provider="heuristic",
        )
        self._fill_narrative(item, result, signals)
        return result

    # -- narrative construction --------------------------------------------
    def _trend(self, text: str) -> str:
        det = sum(1 for t in _TREND_DETERIORATE if t in text)
        imp = sum(1 for t in _TREND_IMPROVE if t in text)
        if imp > det:
            return "Improving"
        if det >= 2:
            return "Rapidly Deteriorating"
        if det == 1:
            return "Deteriorating"
        return "Stable"

    def _fill_narrative(
        self, item: AnalysisInput, r: AnalysisResult, signals: dict[str, float]
    ) -> None:
        loc = item.location_text or "the affected area"
        top = _top_dimensions(signals)

        r.what_happened = _first_sentences(item.body, 3) or item.headline

        # Facts vs claims: attribute anything not from a primary source as a claim.
        primary = [s for s in item.sources if s.is_primary or s.tier == 1]
        if primary:
            r.verified_facts.append(
                f"Reported by a primary/authoritative source: {primary[0].name}."
            )
        for s in item.sources[:4]:
            tag = "primary source" if (s.is_primary or s.tier == 1) else f"tier-{s.tier} source"
            r.claims_uncertainties.append(
                f"Details attributed to {s.name} ({tag}); independent corroboration "
                f"{'present' if len(item.sources) > 1 else 'still limited'}."
            )
        if not item.sources:
            r.claims_uncertainties.append(
                "Insufficient verified information: no citation was attached to this item."
            )
        r.claims_uncertainties.append(
            "Casualty figures, attribution and intent (where relevant) should be "
            "treated as developing until confirmed by primary authorities."
        )

        r.background = (
            f"This development sits within the {_cat_label(item.category)} domain "
            f"affecting {loc}. Assess it against the site, supplier and travel "
            f"footprint you maintain for this geography rather than in isolation."
        )

        r.why_global = _why_global(top, loc)
        r.why_your_work = _why_your_work(top, signals)
        r.potentially_affected = _affected(item, top)
        r.risk_pathway = _risk_pathway(top, loc)
        r.indicators = _indicators(top)
        r.questions = _questions(top)
        r.actions = _actions(top, r.velocity, signals)
        r.narratives = _narratives(item)
        r.talking_points = _talking_points(top, loc, item.category)


# --------------------------------------------------------------------------
# Helper builders
# --------------------------------------------------------------------------
_DIM_LABEL = {
    "people_safety": "employee safety",
    "facility_assets": "facility and asset protection",
    "operational": "business continuity",
    "supply_chain": "supply-chain and logistics",
    "regulatory": "compliance and regulatory",
    "geopolitical": "geopolitical exposure",
    "cyber_physical": "cyber-physical risk",
    "reputational": "executive and reputational risk",
}

_CATEGORY_PRIOR = {
    "geopolitical": "geopolitical",
    "physical_corporate": "facility_assets",
    "supply_chain": "supply_chain",
    "regulatory": "regulatory",
    "cyber_physical": "cyber_physical",
    "natural_hazard": "people_safety",
    "economic_social": "operational",
    "continuity": "operational",
}


def _apply_category_prior(category: str, signals: dict[str, float]) -> None:
    key = _CATEGORY_PRIOR.get(category)
    if key and signals.get(key, 0) < 0.3:
        signals[key] = 0.3


def _cat_label(category: str) -> str:
    from ..taxonomy import CATEGORY_NAMES

    return CATEGORY_NAMES.get(category, "global security")


def _top_dimensions(signals: dict[str, float], n: int = 3) -> list[str]:
    ranked = sorted(signals.items(), key=lambda kv: kv[1], reverse=True)
    return [k for k, v in ranked if v > 0][:n] or ["operational"]


def _first_sentences(text: str, n: int) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(parts[:n]).strip()


def _why_global(top: list[str], loc: str) -> str:
    labels = ", ".join(_DIM_LABEL[t] for t in top)
    return (
        f"The event's broader significance concentrates on {labels}. Effects in "
        f"{loc} can propagate to interconnected markets, transport corridors and "
        f"regulatory regimes, so second-order impacts may exceed the immediate footprint."
    )


def _why_your_work(top: list[str], signals: dict[str, float]) -> list[str]:
    m = {
        "people_safety": "Reassess the threat rating and duty-of-care posture for any "
                         "sites, travellers or events in the affected geography.",
        "facility_assets": "Review Site Security Assessments, perimeter, access control, "
                           "CCTV coverage and intrusion detection for exposed facilities.",
        "operational": "Check Business-Impact Analysis assumptions and continuity/recovery "
                      "plans for single points of failure in the affected area.",
        "supply_chain": "Screen supplier locations, 3PL dependencies and CTPAT controls "
                       "along any transport routes that transit the region.",
        "regulatory": "Confirm whether new obligations, reporting timelines or sanctions "
                     "affect your compliance register and NIS2/CTPAT readiness.",
        "geopolitical": "Update country threat ratings and escalation triggers in the "
                       "risk register; brief executive risk owners on exposure.",
        "cyber_physical": "Coordinate with IT/OT security on convergence risk to physical "
                         "security systems and industrial control environments.",
        "reputational": "Prepare executive talking points and align with communications on "
                       "reputational and stakeholder exposure.",
    }
    out = [m[t] for t in top if t in m]
    out.append(
        "Decide whether this warrants a new risk-register entry, a corrective-action "
        "review, a KRI update, or leadership escalation."
    )
    return out


def _affected(item: AnalysisInput, top: list[str]) -> dict[str, list[str]]:
    countries = item.countries or ([item.location_text] if item.location_text else [])
    functions = sorted({
        {
            "people_safety": "Employee safety / duty of care",
            "facility_assets": "Physical security / facilities",
            "operational": "Business continuity",
            "supply_chain": "Supply chain & logistics",
            "regulatory": "Compliance / GRC",
            "geopolitical": "Enterprise risk / executive protection",
            "cyber_physical": "IT/OT security convergence",
            "reputational": "Communications / executive",
        }[t]
        for t in top
    })
    return {
        "countries": countries,
        "business_functions": functions,
        "infrastructure": _infra_for(top),
    }


def _infra_for(top: list[str]) -> list[str]:
    infra = []
    if "supply_chain" in top:
        infra += ["Ports / terminals", "Road & rail freight corridors"]
    if "facility_assets" in top:
        infra += ["Manufacturing / warehouse sites"]
    if "operational" in top:
        infra += ["Power / utilities", "Telecommunications"]
    if "cyber_physical" in top:
        infra += ["Industrial control systems", "Data centres"]
    return infra or ["To be confirmed against site register"]


def _risk_pathway(top: list[str], loc: str) -> list[str]:
    if "supply_chain" in top:
        return ["Trigger event in " + loc, "Transport / customs disruption",
                "Inbound material delay", "Production shortfall",
                "Missed commitments → financial & reputational impact"]
    if "people_safety" in top:
        return ["Security event in " + loc, "Localised danger to people",
                "Access / movement restrictions", "Staff unable to reach site",
                "Operational shortfall → duty-of-care & continuity impact"]
    if "regulatory" in top:
        return ["Regulatory change", "New obligation / deadline",
                "Control or process gap identified", "Remediation effort / cost",
                "Non-compliance exposure → penalty & reputational risk"]
    return ["Trigger event in " + loc, "Operational disruption",
            "Business-continuity strain", "Recovery cost",
            "Financial & reputational impact"]


def _indicators(top: list[str]) -> list[dict[str, str]]:
    catalogue = {
        "people_safety": [
            ("Official casualty/incident updates from authorities", "both"),
            ("Government travel-advisory level changes", "both"),
            ("Curfews, movement restrictions or evacuation orders", "deterioration"),
        ],
        "supply_chain": [
            ("Port/terminal throughput and vessel queue length", "both"),
            ("Customs clearance times and border status", "both"),
            ("Carrier surcharges or route diversions announced", "deterioration"),
        ],
        "regulatory": [
            ("Publication in the official gazette / regulator site", "both"),
            ("Effective date and transition-period confirmation", "both"),
            ("First enforcement actions or guidance issued", "deterioration"),
        ],
        "geopolitical": [
            ("Force posture / mobilisation reporting", "deterioration"),
            ("Diplomatic statements, talks or ceasefire signals", "improvement"),
            ("Airspace / border closure notices", "deterioration"),
        ],
        "operational": [
            ("Utility / grid status advisories", "both"),
            ("Duration and geographic spread of disruption", "both"),
            ("Restoration-of-service announcements", "improvement"),
        ],
        "facility_assets": [
            ("Reports of damage to industrial or commercial sites", "deterioration"),
            ("Local law-enforcement posture near facilities", "both"),
        ],
        "cyber_physical": [
            ("Vendor / CERT advisories on affected systems", "both"),
            ("Reports of OT/ICS impact or safety-system involvement", "deterioration"),
        ],
        "reputational": [
            ("Volume and tone of coverage naming the sector", "both"),
        ],
    }
    out: list[dict[str, str]] = []
    for t in top:
        for text, direction in catalogue.get(t, []):
            out.append({"text": text, "direction": direction})
    return out[:6]


def _questions(top: list[str]) -> list[str]:
    base = [
        "Do we operate sites, warehouses or supplier locations in the affected area?",
        "Are any employees currently travelling through or scheduled to visit the region?",
    ]
    extra = {
        "supply_chain": "Could this disrupt a critical inbound or outbound transport route, "
                       "and do we have alternates?",
        "regulatory": "Does this create a regulatory reporting duty or change a compliance deadline?",
        "people_safety": "Does this change the threat rating of any location, and are controls "
                        "still proportional?",
        "geopolitical": "Should executive risk owners receive an escalation, and are escalation "
                       "triggers still valid?",
        "operational": "Which single points of failure does this expose in our BIA?",
        "facility_assets": "Are physical-security controls (access, CCTV, perimeter) adequate "
                          "for the changed threat?",
        "cyber_physical": "Are any physical-security or OT systems exposed to this vector?",
        "reputational": "Do we need proactive leadership talking points?",
    }
    qs = base + [extra[t] for t in top if t in extra]
    qs.append("Do any corrective actions, due dates or mitigation owners need reprioritising?")
    return qs[:6]


def _actions(top: list[str], velocity: str, signals: dict[str, float]) -> list[dict[str, str]]:
    actions = [
        {"type": "Monitor", "text": "Track the named indicators from Tier 1/2 sources and "
                                    "update the story when material change is confirmed."},
        {"type": "Validate", "text": "Confirm exposure against the live site, supplier and "
                                     "traveller registers before acting."},
    ]
    if signals.get("people_safety", 0) >= 0.6:
        actions.append({"type": "Communicate", "text": "Prepare/di­spatch an emergency "
                        "notification to affected staff and travellers with clear guidance."})
    if signals.get("supply_chain", 0) >= 0.6:
        actions.append({"type": "Assess", "text": "Run a rapid route/supplier impact "
                        "assessment and identify alternates or buffers."})
    if signals.get("regulatory", 0) >= 0.6:
        actions.append({"type": "Assess", "text": "Map the obligation to your compliance "
                        "register; log gaps as issues with owners and due dates."})
    if velocity in {"Immediate", "Fast"} and signals.get("people_safety", 0) >= 0.6:
        actions.append({"type": "Escalate", "text": "Brief regional security leadership and "
                        "executive risk owners; consider crisis-management activation."})
    else:
        actions.append({"type": "Assess", "text": "Decide whether a risk-register entry, "
                        "corrective action or KRI update is warranted."})
    return actions


def _narratives(item: AnalysisInput) -> list[dict[str, str]]:
    """Group sources into up to two perspectives when they differ in tier/origin.

    The heuristic groups by source tier/country as a *transparent proxy* — it
    does not label outlets politically. If only one perspective is present it
    returns a single entry, avoiding false balance.
    """
    if len(item.sources) < 2:
        return []
    group_a = [s for s in item.sources if s.tier <= 2]
    group_b = [s for s in item.sources if s.tier >= 3]
    out: list[dict[str, str]] = []
    if group_a:
        out.append({
            "label": "Established international / wire reporting",
            "who": ", ".join(s.name for s in group_a[:3]),
            "claim": "Emphasis on verified, attributable detail from named sources.",
            "evidence": "Direct reporting, official statements, on-the-record attribution.",
        })
    if group_b:
        out.append({
            "label": "Specialist / local reporting",
            "who": ", ".join(s.name for s in group_b[:3]),
            "claim": "Additional local or domain-specific context and framing.",
            "evidence": "Regional access, subject-matter analysis; corroborate before relying.",
        })
    return out if len(out) >= 2 else []


def _talking_points(top: list[str], loc: str, category: str) -> list[str]:
    return [
        f"We are tracking a {_cat_label(category).lower()} development affecting {loc}; "
        f"here is our current read and confidence level.",
        f"Primary exposure areas are {', '.join(_DIM_LABEL[t] for t in top)}.",
        "We have validated (or are validating) our site, supplier and traveller exposure "
        "against the affected geography.",
        "Recommended posture is proportionate monitoring with defined escalation triggers, "
        "not blanket disruption.",
        "We will update leadership if the named indicators show material deterioration.",
    ]
