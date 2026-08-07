"""Precision-first category classification.

Replaces a bag-of-words scorer whose failures were structural, not tuning:

  * matches were SUBSTRING, not word-boundary — "ics" matched inside "BRICS"
    (diplomacy filed as cyber), "war" inside "award", "port" inside "reported"
    and "important" (a large share of the supply-chain noise);
  * every field weighed the same, so a passing body mention outvoted the
    headline;
  * a single keyword hit outranked the feed's own category, so a CISA
    cyber advisory could be filed as supply-chain.

Design, in precision order:

  1. word-boundary regex only — no substring matches, ever;
  2. multi-word PHRASES ("supply chain") score above single keywords, and are
     matched as phrases rather than scattered words;
  3. field tiers — headline outranks summary outranks body;
  4. authoritative source priors (CISA -> cyber, WHO -> health, …) act as a
     strong default that another category must beat by a clear MARGIN;
  5. negative rules demote awards/conferences/sport/obituaries/opinion so
     "Cybersecurity award" is not a cyber incident;
  6. minimum thresholds, with a higher bar for the two categories that were
     most over-assigned. Below threshold the answer is "unclassified" —
     never a guess.

Pure stdlib. Every decision is returned in a machine-readable explanation so a
misclassification can be audited without re-running the pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

UNCLASSIFIED = "unclassified"

# --------------------------------------------------------------------------
# Field weights (requirement 3). Headline evidence dominates: what a story is
# ABOUT is in its headline; body mentions are usually incidental.
# --------------------------------------------------------------------------
W_HEADLINE_PHRASE = 10.0
W_HEADLINE_KEYWORD = 6.0
W_SUMMARY_PHRASE = 4.0
W_SUMMARY_KEYWORD = 2.0
W_BODY_PHRASE = 2.0
W_BODY_KEYWORD = 0.5

# A trusted single-domain feed is worth about one headline keyword.
W_SOURCE_PRIOR = 6.0
# Another category must beat the prior by this much to override it.
OVERRIDE_MARGIN = 6.0

# Minimum score to assign any category at all.
MIN_SCORE = 6.0
# Cyber and supply-chain were the most over-assigned, so they carry a higher
# bar AND must have evidence in the headline/summary, not body-only.
GUARDED = {"cyber_physical", "supply_chain"}
GUARDED_MIN_SCORE = 10.0
# A secondary category must stand on its own.
SECONDARY_MIN_SCORE = 8.0
# Penalty applied per negative-rule hit.
NEGATIVE_PENALTY = 9.0

# --------------------------------------------------------------------------
# Signals. PHRASES are exact multi-word matches; KEYWORDS are single tokens
# matched on word boundaries. Keep keywords unambiguous — anything that is a
# common substring or has a everyday non-security sense belongs in PHRASES.
# --------------------------------------------------------------------------
PHRASES: dict[str, tuple[str, ...]] = {
    "cyber_physical": (
        "active exploitation", "known exploited", "data breach", "ransomware attack",
        "zero day", "zero-day", "remote code execution", "command injection",
        "denial of service", "industrial control system", "control system",
        "operational technology", "cyber attack", "cyberattack", "cyber incident",
        "threat actor", "malicious actor", "security advisory", "security vulnerability",
        "patch available", "gps jamming", "supply chain attack", "privilege escalation",
    ),
    "supply_chain": (
        "supply chain", "port closure", "port congestion", "shipping lane",
        "container ship", "freight rate", "cargo theft", "customs delay",
        "border crossing", "trade route", "logistics disruption", "shipping route",
        "export control", "port strike", "vessel rerouting", "transport corridor",
    ),
    "regulatory": (
        "export control", "final rule", "proposed rule", "federal register",
        "entity list", "sanctions regime", "compliance deadline", "regulatory filing",
        "data protection", "reporting obligation", "enters into force",
        "binding operational directive", "executive order", "regulatory framework",
    ),
    "natural_hazard": (
        "magnitude earthquake", "tropical cyclone", "storm surge", "flash flood",
        "heavy rainfall", "volcanic eruption", "wildfire season", "extreme heat",
        "natural disaster", "severe weather", "heat wave", "heatwave",
    ),
    "health": (
        "public health", "disease outbreak", "health emergency", "vaccination campaign",
        "clinical guidelines", "health authorities", "infectious disease",
        "case fatality", "health ministry", "medical supplies", "health workers",
    ),
    "physical_corporate": (
        "armed attack", "civil unrest", "security incident", "armed robbery",
        "workplace violence", "physical security", "facility damage",
        "employee safety", "kidnap for ransom", "site evacuation",
    ),
    "continuity": (
        "power outage", "rolling blackout", "grid failure", "water shortage",
        "business continuity", "disaster recovery", "service disruption",
        "telecom outage", "contingency plan",
    ),
    "geopolitical": (
        "armed conflict", "peace talks", "diplomatic relations", "military strike",
        "air strike", "airstrike", "ceasefire", "troop deployment", "border dispute",
        "state of emergency", "coup attempt", "missile attack", "drone strike",
        "drone attack", "shelling", "rebel forces", "militant attack",
        "air strikes", "strikes on", "strikes across", "launches strikes",
        "cross-border", "war crimes", "peace deal",
    ),
    "economic_social": (
        "general strike", "labour strike", "labor strike", "fuel shortage",
        "food insecurity", "cost of living", "currency devaluation",
        "mass protest", "inflation rate", "oil prices", "food prices",
        "trade war", "economic crisis", "hunger strike",
    ),
}

# Single words that are as decisive as a phrase: in a headline they essentially
# only ever mean this domain. Scored at phrase weight so one of them clears the
# guarded bar on its own. Keep this list *small* and boring — a term earns its
# place here only if an everyday non-security use is hard to construct.
# ("shipping"/"customs" deliberately excluded: "shipping turtles" and "Customs
# warns of fake recruitment" are real headlines that are not supply-chain.)
STRONG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "supply_chain": ("tariff", "embargo", "hormuz", "suez", "malacca",
                     "transshipment", "chokepoint", "demurrage"),
    "cyber_physical": ("ransomware", "scada", "cve"),
    "natural_hazard": ("earthquake", "tsunami", "hurricane", "typhoon"),
    "health": ("ebola", "cholera", "pandemic", "epidemic"),
}

KEYWORDS: dict[str, tuple[str, ...]] = {
    # NB: no bare "ics", "drone", "breach", "port", "war" — each produced
    # false positives either as a substring or as an everyday word.
    "cyber_physical": ("ransomware", "malware", "scada", "cve", "vulnerability",
                       "exploit", "phishing", "botnet", "hacker", "cybersecurity",
                       "firmware", "authentication"),
    "supply_chain": ("logistics", "freight", "cargo", "shipping", "customs",
                     "warehouse", "tariff", "importer", "exporter"),
    "regulatory": ("regulation", "regulations", "directive", "compliance",
                   "sanctions", "nis2", "gdpr", "ctpat", "legislation", "statute",
                   "regulator", "lawsuit", "ruling", "court", "tribunal",
                   "legislation", "bill", "treaty", "accord", "mandate",
                   "enforcement", "prosecutors", "verdict", "injunction"),
    "natural_hazard": ("earthquake", "flood", "flooding", "wildfire", "hurricane",
                       "typhoon", "volcano", "tsunami", "drought", "landslide",
                       "avalanche", "cyclone", "storm", "monsoon", "quake",
                       "heatwave", "blizzard", "mudslide", "erupted"),
    "health": ("outbreak", "epidemic", "pandemic", "cholera", "ebola", "measles",
               "malaria", "dementia", "vaccine", "vaccination", "who", "cdc",
               "disease", "hospital", "patients", "healthcare"),
    "physical_corporate": ("sabotage", "arson", "kidnapping", "looting",
                           "vandalism", "trespass", "intruder", "attack",
                           "protest", "protesters", "crackdown", "riot", "clash",
                           "shooting", "gunmen", "explosion", "blast", "hostage",
                           "assault", "unrest", "demonstrators", "police"),
    "continuity": ("blackout", "outage", "evacuation", "curfew", "shutdown",
                   "disruption", "suspended", "grounded", "stranded"),
    "geopolitical": ("ceasefire", "sanctions", "diplomat", "diplomacy", "treaty",
                     "militants", "insurgency", "coup", "warfare", "troops",
                     "war", "conflict", "military", "missile", "airstrike",
                     "offensive", "rebels", "militia", "election", "opposition",
                     "parliament", "tensions", "regime", "warplanes", "invasion",
                     "occupation", "hostilities", "retaliation", "geopolitical"),
    "economic_social": ("inflation", "recession", "layoffs", "unemployment",
                        "devaluation", "austerity", "tariffs", "economy",
                        "markets", "shortage", "prices", "trade",
                        "wages", "poverty", "famine", "migrants", "refugees"),
}

# --------------------------------------------------------------------------
# Negative rules (requirement 6). These demote rather than hard-delete, so a
# genuine advisory that happens to mention an award is not thrown away.
# --------------------------------------------------------------------------
NEGATIVE_RULES: dict[str, tuple[str, ...]] = {
    "sports": ("football", "soccer", "cricket", "olympics", "tournament",
               "world cup", "premier league", "championship", "athlete", "fixture"),
    "entertainment": ("celebrity", "box office", "album", "netflix", "movie",
                      "film festival", "singer", "actor", "tv series"),
    "obituary": ("obituary", "dies aged", "passed away", "funeral", "memorial service"),
    "awards": ("award", "awards", "prize", "honoured", "honored", "accolade",
               "wins top", "named best"),
    "events_marketing": ("conference", "webinar", "keynote", "expo", "trade show",
                         "product launch", "partnership announcement", "sponsorship"),
    "opinion": ("opinion", "editorial", "op-ed", "commentary", "analysis piece",
                "column", "explainer", "podcast", "interview"),
    "routine_crime": ("murder trial", "shoplifting", "burglary", "drink driving",
                      "traffic accident", "court hears"),
}

# --------------------------------------------------------------------------
# Preparedness vs active event (requirement 11). "Mall rebuilt to withstand
# earthquakes" is resilience; "Earthquake destroys mall" is an active hazard.
# --------------------------------------------------------------------------
PREPAREDNESS_TERMS = (
    "rebuilt", "rebuild", "withstand", "resilience", "resilient", "preparedness",
    "prepares for", "retrofit", "retrofitted", "drill", "exercise", "readiness",
    "mitigation plan", "earthquake-proof", "designed to survive", "contingency",
)
ACTIVE_IMPACT_TERMS = (
    "kills", "killed", "destroys", "destroyed", "damages", "damaged", "injured",
    "displaced", "collapsed", "hits", "struck", "devastated", "swept",
    "casualties", "death toll", "trapped", "missing",
)

# --------------------------------------------------------------------------
# Authoritative source priors (requirement 1). Keyed by ingestion feed id and
# by a case-insensitive substring of the source NAME, so stored rows (which
# only know their citation source names) resolve too.
# --------------------------------------------------------------------------
SOURCE_PRIORS_BY_FEED: dict[str, str] = {
    "cisa_alerts": "cyber_physical",
    "usgs_quakes": "natural_hazard",
    "gdacs": "natural_hazard",
    "reliefweb": "natural_hazard",
    "who_news": "health",
    "us_fedreg_dhs": "regulatory",
    "eu_presscorner": "regulatory",
}

SOURCE_PRIORS_BY_NAME: tuple[tuple[str, str], ...] = (
    ("cisa", "cyber_physical"),
    ("us-cert", "cyber_physical"),
    ("cybersecurity advisories", "cyber_physical"),
    ("usgs", "natural_hazard"),
    ("gdacs", "natural_hazard"),
    ("reliefweb", "natural_hazard"),
    ("world health organization", "health"),
    ("who —", "health"),
    ("africa cdc", "health"),
    ("cdc", "health"),
    ("federal register", "regulatory"),
    ("european commission", "regulatory"),
    ("gazette", "regulatory"),
)


def _variants(term: str) -> set[str]:
    """Term plus simple plural forms.

    Word-boundary matching is strict: `\\bearthquake\\b` does NOT match
    "earthquakes". Pluralising each term keeps that strictness without losing
    ordinary recall. Multi-word phrases pluralise their last word only.
    """
    head, _, last = term.rpartition(" ")
    prefix = f"{head} " if head else ""
    out = {term}
    if last.endswith("y") and len(last) > 3:
        out.add(f"{prefix}{last[:-1]}ies")
    elif last.endswith(("s", "x", "ch", "sh")):
        out.add(f"{prefix}{last}es")
    else:
        out.add(f"{prefix}{last}s")
    return out


def _compile(terms: Iterable[str]) -> re.Pattern | None:
    """Word-boundary alternation. Longest first so phrases win over prefixes."""
    expanded: set[str] = set()
    for t in terms:
        expanded |= _variants(t)
    ordered = sorted(expanded, key=len, reverse=True)
    if not ordered:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(t) for t in ordered) + r")\b",
                      re.IGNORECASE)


_PHRASE_RE = {c: _compile(v) for c, v in PHRASES.items()}
_KEYWORD_RE = {c: _compile(v) for c, v in KEYWORDS.items()}
_STRONG_RE = {c: _compile(v) for c, v in STRONG_KEYWORDS.items()}
_NEGATIVE_RE = {r: _compile(v) for r, v in NEGATIVE_RULES.items()}
_PREPAREDNESS_RE = _compile(PREPAREDNESS_TERMS)
_ACTIVE_RE = _compile(ACTIVE_IMPACT_TERMS)

ALL_CATEGORIES = sorted(set(PHRASES) | set(KEYWORDS) | set(STRONG_KEYWORDS))


@dataclass
class Classification:
    """Result plus a machine-readable audit trail (requirement 8)."""

    category: str
    confidence: float
    secondary: str | None = None
    scores: dict[str, float] = field(default_factory=dict)
    explanation: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "confidence": round(self.confidence, 3),
            "secondary": self.secondary,
            "scores": {k: round(v, 2) for k, v in sorted(
                self.scores.items(), key=lambda kv: -kv[1]) if v},
            **self.explanation,
        }


def source_prior(feed_id: str | None = None,
                 source_names: Iterable[str] = ()) -> tuple[str | None, str]:
    """Authoritative category for a feed, and what matched. ('', '') if none."""
    if feed_id and feed_id in SOURCE_PRIORS_BY_FEED:
        return SOURCE_PRIORS_BY_FEED[feed_id], f"feed:{feed_id}"
    for name in source_names:
        low = (name or "").lower()
        for needle, cat in SOURCE_PRIORS_BY_NAME:
            if needle in low:
                return cat, f"source:{needle}"
    return None, ""


def _scan(text: str, rx: re.Pattern | None) -> list[str]:
    if not text or rx is None:
        return []
    # dict.fromkeys keeps first-seen order while de-duplicating
    return list(dict.fromkeys(m.group(1).lower() for m in rx.finditer(text)))


def classify(headline: str, summary: str = "", body: str = "",
             feed_id: str | None = None,
             source_names: Iterable[str] = (),
             feed_hint: str | None = None) -> Classification:
    """Classify a development, preferring 'unclassified' over a wrong guess."""
    headline = headline or ""
    summary = summary or ""
    body = body or ""

    scores: dict[str, float] = {c: 0.0 for c in ALL_CATEGORIES}
    matched: dict[str, list[dict]] = {}

    def add(cat: str, term: str, fieldname: str, kind: str, weight: float) -> None:
        scores[cat] = scores.get(cat, 0.0) + weight
        matched.setdefault(cat, []).append(
            {"term": term, "field": fieldname, "type": kind, "weight": weight})

    for cat in ALL_CATEGORIES:
        for term in _scan(headline, _PHRASE_RE.get(cat)):
            add(cat, term, "headline", "phrase", W_HEADLINE_PHRASE)
        for term in _scan(headline, _STRONG_RE.get(cat)):
            add(cat, term, "headline", "strong", W_HEADLINE_PHRASE)
        for term in _scan(summary, _STRONG_RE.get(cat)):
            add(cat, term, "summary", "strong", W_SUMMARY_PHRASE)
        for term in _scan(headline, _KEYWORD_RE.get(cat)):
            add(cat, term, "headline", "keyword", W_HEADLINE_KEYWORD)
        for term in _scan(summary, _PHRASE_RE.get(cat)):
            add(cat, term, "summary", "phrase", W_SUMMARY_PHRASE)
        for term in _scan(summary, _KEYWORD_RE.get(cat)):
            add(cat, term, "summary", "keyword", W_SUMMARY_KEYWORD)
        for term in _scan(body, _PHRASE_RE.get(cat)):
            add(cat, term, "body", "phrase", W_BODY_PHRASE)
        for term in _scan(body, _KEYWORD_RE.get(cat)):
            add(cat, term, "body", "keyword", W_BODY_KEYWORD)

    # --- source prior -----------------------------------------------------
    prior_cat, prior_via = source_prior(feed_id, source_names)
    if prior_cat:
        scores[prior_cat] = scores.get(prior_cat, 0.0) + W_SOURCE_PRIOR

    # --- negative rules ---------------------------------------------------
    blob = f"{headline} {summary}"
    negatives: list[dict] = []
    for rule, rx in _NEGATIVE_RE.items():
        for term in _scan(blob, rx):
            negatives.append({"rule": rule, "term": term})
    # A trusted single-domain source is not demoted by incidental wording.
    if negatives and not prior_cat:
        penalty = NEGATIVE_PENALTY * min(len(negatives), 2)
        for cat in scores:
            scores[cat] = max(0.0, scores[cat] - penalty)

    # --- preparedness vs active hazard (requirement 11) -------------------
    prep = _scan(blob, _PREPAREDNESS_RE)
    active = _scan(blob, _ACTIVE_RE)
    reframed = None
    if prep and not active and scores.get("natural_hazard", 0) > 0:
        moved = scores["natural_hazard"]
        scores["natural_hazard"] = 0.0
        scores["continuity"] = scores.get("continuity", 0.0) + moved
        reframed = {"from": "natural_hazard", "to": "continuity",
                    "why": "preparedness/resilience framing, no active impact",
                    "terms": prep}

    # --- pick a winner ----------------------------------------------------
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_cat, top_score = ranked[0]
    runner_cat, runner_score = ranked[1] if len(ranked) > 1 else (None, 0.0)

    override = None
    if prior_cat and top_cat != prior_cat:
        prior_score = scores.get(prior_cat, 0.0)
        if top_score - prior_score >= OVERRIDE_MARGIN:
            override = {"from": prior_cat, "to": top_cat,
                        "margin": round(top_score - prior_score, 2),
                        "why": f"beat source prior by >= {OVERRIDE_MARGIN}"}
        else:
            # Prior holds: not enough evidence to contradict the source.
            top_cat, top_score = prior_cat, prior_score
            runner_cat, runner_score = ranked[0]
            override = {"kept": prior_cat,
                        "why": f"challenger '{ranked[0][0]}' short of "
                               f"{OVERRIDE_MARGIN} margin"}

    # --- thresholds (requirement 5) ---------------------------------------
    threshold = GUARDED_MIN_SCORE if top_cat in GUARDED else MIN_SCORE
    reason = "scored above threshold"
    if top_score < threshold:
        if prior_cat:
            top_cat, top_score = prior_cat, scores.get(prior_cat, 0.0)
            reason = "below threshold; retained authoritative source hint"
        elif feed_hint and feed_hint in ALL_CATEGORIES and scores.get(feed_hint, 0) > 0:
            top_cat, top_score = feed_hint, scores.get(feed_hint, 0.0)
            reason = "below threshold; retained feed hint with supporting evidence"
        else:
            top_cat, top_score = UNCLASSIFIED, 0.0
            reason = "insufficient evidence for any category"
    elif top_cat in GUARDED:
        # Guarded categories additionally require headline/summary evidence.
        strong = [m for m in matched.get(top_cat, [])
                  if m["field"] in ("headline", "summary")]
        if not strong and not prior_cat:
            top_cat, top_score = UNCLASSIFIED, 0.0
            reason = (f"guarded category had body-only evidence; "
                      f"refused rather than guess")

    # --- secondary (requirement 7) ----------------------------------------
    secondary = None
    if top_cat != UNCLASSIFIED and runner_cat and runner_cat != top_cat:
        sec_threshold = (GUARDED_MIN_SCORE if runner_cat in GUARDED
                         else SECONDARY_MIN_SCORE)
        if runner_score >= sec_threshold:
            secondary = runner_cat

    # --- confidence -------------------------------------------------------
    if top_cat == UNCLASSIFIED:
        confidence = 0.0
    else:
        margin = top_score - (runner_score if runner_cat else 0.0)
        confidence = min(1.0, (top_score / 20.0) * 0.6 + (margin / 12.0) * 0.4)
        confidence = max(0.05, round(confidence, 3))

    explanation = {
        "source_hint": {"category": prior_cat, "via": prior_via} if prior_cat else None,
        "matched": {c: v for c, v in matched.items() if v},
        "negative": negatives,
        "override": override,
        "reframed": reframed,
        "threshold": threshold,
        "reason": reason,
    }
    return Classification(category=top_cat, confidence=confidence,
                          secondary=secondary, scores=scores,
                          explanation=explanation)


def looks_relevant(headline: str, summary: str = "", tier: int = 3,
                   feed_id: str | None = None) -> bool:
    """Cheap pre-filter: does this item show ANY security-domain signal?

    Tier-1 official feeds are curated already and always pass.
    """
    if tier == 1 or (feed_id and feed_id in SOURCE_PRIORS_BY_FEED):
        return True
    blob = f"{headline} {summary}"
    for cat in ALL_CATEGORIES:
        if _scan(blob, _PHRASE_RE.get(cat)) or _scan(blob, _KEYWORD_RE.get(cat)):
            return True
    return False
