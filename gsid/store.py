"""Story assembly & persistence.

A single code path turns a `StoryDraft` (produced by demo fixtures OR the live
ingestion pipeline) into a fully analyzed, scored, persisted Story with its
Sources, Claims, Citations, Narratives, Indicators and Actions. This keeps demo
and live data structurally identical and guarantees claim→source traceability.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from . import db
from .analysis import AnalysisInput, AnalyzerProtocol
from .analysis.base import SourceRef
from .scoring import (
    derive_confidence, derive_impact, derive_urgency, geo_scope_from_countries,
    is_critical_alert, score_relevance,
)
from .taxonomy import (
    clamp_scale, LIKELIHOOD_LEVELS, TREND_LEVELS, VELOCITY_LEVELS,
    region_for_country,
)
from .ingestion.dedup import dedup_key
from .ingestion.sanitize import clean_content, is_valid_url

log = logging.getLogger("gsid.store")


@dataclass
class DraftSource:
    name: str
    url: str
    tier: int = 3
    source_type: str = "newspaper"
    country: str = ""
    language: str = "en"
    is_primary: bool = False
    title: str = ""
    published_at: str = ""
    orig_headline: str = ""
    orig_language: str = "en"
    is_circular: bool = False
    ownership: str = ""
    transparency: str = ""


@dataclass
class DraftClaim:
    text: str
    claim_type: str = "fact"
    attributed_to: str = ""
    stance: str = "supports"
    corroboration: str = "single"
    source_index: int | None = None  # index into draft.sources


@dataclass
class StoryDraft:
    headline: str
    body: str
    category: str
    location_text: str = ""
    primary_country: str = ""
    countries: list[str] = field(default_factory=list)
    lat: float | None = None
    lon: float | None = None
    event_time: str = ""
    status: str = "developing"
    sources: list[DraftSource] = field(default_factory=list)
    claims: list[DraftClaim] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    is_demo: bool = False
    story_id: str | None = None  # stable id for fixtures


def _ensure_source(conn, s: DraftSource) -> str:
    """Insert (or reuse) a source row; returns source id."""
    existing = conn.execute(
        "SELECT id FROM source WHERE name=? AND COALESCE(url,'')=?",
        (s.name, s.url or ""),
    ).fetchone()
    if existing:
        return existing["id"]
    sid = db.new_id("src_")
    conn.execute(
        "INSERT INTO source(id,name,url,tier,source_type,country,language,"
        "ownership,transparency,is_demo) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (sid, s.name, s.url, s.tier, s.source_type, s.country, s.language,
         s.ownership, s.transparency, 1 if False else 0),
    )
    return sid


def save_story(conn, draft: StoryDraft, analyzer: AnalyzerProtocol,
               actor: str = "system") -> str:
    """Analyze, score and persist a draft. Returns the story id.

    If a story with the same dedup key already exists, this updates freshness
    and appends any genuinely new citation rather than duplicating the story.
    """
    clean_body, injection_hits = clean_content(draft.body)
    if injection_hits:
        db.audit(conn, "ingestion", "sanitized_injection", "story", draft.story_id,
                 f"neutralized {injection_hits} injection pattern(s)")

    key = dedup_key(draft.headline)
    countries = _normalize_countries(draft)
    primary_country = draft.primary_country or (countries[0] if countries else "")
    primary_region = region_for_country(primary_country) if primary_country else "global"

    # -- dedup: does a matching story already exist? --
    existing = conn.execute(
        "SELECT id FROM story WHERE dedup_key=? AND is_demo=?",
        (key, 1 if draft.is_demo else 0),
    ).fetchone()
    if existing and not draft.story_id:
        return _merge_into_existing(conn, existing["id"], draft, actor)

    # -- run analyzer (provider-agnostic) --
    src_refs = [
        SourceRef(source_id=str(i), name=s.name, tier=s.tier, url=s.url,
                  title=s.title, published_at=s.published_at, country=s.country,
                  language=s.language, is_primary=s.is_primary)
        for i, s in enumerate(draft.sources)
    ]
    ai = analyzer.analyze(AnalysisInput(
        headline=draft.headline, body=clean_body, category=draft.category,
        location_text=draft.location_text, countries=countries, sources=src_refs,
    ))

    # -- scoring --
    breakdown = score_relevance(ai.signals)
    best_tier = min((s.tier for s in draft.sources), default=4)
    has_primary = any(s.is_primary or s.tier == 1 for s in draft.sources)
    confidence, conf_reason = derive_confidence(best_tier, len(draft.sources), has_primary)
    impact, impact_reason = derive_impact(breakdown.total, ai.signals)
    velocity = clamp_scale(ai.velocity, VELOCITY_LEVELS, "Developing")
    urgency, urg_reason = derive_urgency(velocity, ai.signals)
    geo_scope, geo_reason = geo_scope_from_countries(
        len(countries), primary_region == "global"
    )
    likelihood = clamp_scale(ai.likelihood, LIKELIHOOD_LEVELS, "Possible")
    trend = clamp_scale(ai.trend, TREND_LEVELS, "Stable")
    alert = is_critical_alert(breakdown.total, urgency, impact, confidence)

    scoring_json = {
        "relevance": breakdown.to_dict(),
        "ratings": {
            "impact": {"value": impact, "reason": impact_reason},
            "urgency": {"value": urgency, "reason": urg_reason},
            "geo_scope": {"value": geo_scope, "reason": geo_reason},
            "confidence": {"value": confidence, "reason": conf_reason},
            "likelihood": {"value": likelihood,
                           "reason": "Derived from certainty language in reporting."},
            "velocity": {"value": velocity,
                         "reason": "Derived from pace/escalation cues in reporting."},
            "trend": {"value": trend,
                      "reason": "Derived from escalation vs de-escalation cues."},
        },
    }

    now = db.utcnow()
    sid = draft.story_id or db.new_id("story_")
    conn.execute(
        "INSERT OR REPLACE INTO story(id,headline,summary,category,primary_region,"
        "primary_country,location_text,lat,lon,event_time,first_seen,last_updated,"
        "status,relevance_score,urgency,geo_scope,impact,likelihood,velocity,"
        "confidence,trend,is_alert,is_demo,dedup_key,analysis_json,scoring_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, draft.headline, ai.what_happened or clean_body[:400], draft.category,
         primary_region, primary_country, draft.location_text, draft.lat, draft.lon,
         draft.event_time or now, draft.event_time or now, now, draft.status,
         breakdown.total, urgency, geo_scope, impact, likelihood, velocity,
         confidence, trend, 1 if alert else 0, 1 if draft.is_demo else 0, key,
         json.dumps(ai.to_dict()), json.dumps(scoring_json)),
    )

    # countries
    conn.execute("DELETE FROM story_country WHERE story_id=?", (sid,))
    for c in countries:
        conn.execute("INSERT OR IGNORE INTO story_country(story_id,country) VALUES (?,?)",
                     (sid, c))

    # sources + citations + claims
    conn.execute("DELETE FROM citation WHERE story_id=?", (sid,))
    conn.execute("DELETE FROM claim WHERE story_id=?", (sid,))
    src_ids: list[str] = []
    for s in draft.sources:
        if s.url and not is_valid_url(s.url):
            log.warning("skipping invalid source url: %s", s.url)
            src_ids.append("")
            continue
        src_id = _ensure_source(conn, s)
        src_ids.append(src_id)
        conn.execute(
            "INSERT INTO citation(id,story_id,claim_id,source_id,title,url,"
            "published_at,accessed_at,orig_language,orig_headline,is_primary,is_circular)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (db.new_id("cit_"), sid, None, src_id, s.title or draft.headline, s.url,
             s.published_at, now, s.orig_language, s.orig_headline,
             1 if s.is_primary else 0, 1 if s.is_circular else 0),
        )

    for cl in draft.claims:
        src_id = src_ids[cl.source_index] if (
            cl.source_index is not None and cl.source_index < len(src_ids)
        ) else None
        conn.execute(
            "INSERT INTO claim(id,story_id,text,claim_type,attributed_to,stance,"
            "corroboration,source_id,confidence) VALUES (?,?,?,?,?,?,?,?,?)",
            (db.new_id("clm_"), sid, cl.text, cl.claim_type, cl.attributed_to,
             cl.stance, cl.corroboration, src_id or None, confidence),
        )

    # events
    conn.execute("DELETE FROM event WHERE story_id=?", (sid,))
    for i, ev in enumerate(draft.events):
        conn.execute(
            "INSERT INTO event(id,story_id,occurred,title,detail,ordinal) "
            "VALUES (?,?,?,?,?,?)",
            (db.new_id("evt_"), sid, ev.get("occurred", ""), ev.get("title", ""),
             ev.get("detail", ""), i),
        )

    # analysis-derived rows: narratives, indicators, actions
    _persist_analysis_rows(conn, sid, ai)

    # alert record
    conn.execute("DELETE FROM alert WHERE story_id=?", (sid,))
    if alert:
        pa = ai.potentially_affected or {}
        conn.execute(
            "INSERT INTO alert(id,story_id,people_impact,facility_impact,"
            "operational_impact,recommended_action,created_at) VALUES (?,?,?,?,?,?,?)",
            (db.new_id("alt_"), sid,
             _impact_line(ai.signals.get("people_safety", 0), "people"),
             _impact_line(ai.signals.get("facility_assets", 0), "facilities"),
             _impact_line(ai.signals.get("operational", 0), "operations"),
             (ai.actions[0]["text"] if ai.actions else "Monitor and validate exposure."),
             now),
        )

    db.reindex_story_fts(conn, sid)
    db.audit(conn, actor if ":" in actor else f"ai:{ai.provider}", "analyze_story",
             "story", sid, {"score": breakdown.total, "confidence": confidence})
    conn.commit()
    return sid


def _persist_analysis_rows(conn, sid: str, ai) -> None:
    conn.execute("DELETE FROM narrative WHERE story_id=?", (sid,))
    for i, n in enumerate(ai.narratives or []):
        conn.execute(
            "INSERT INTO narrative(id,story_id,label,who,claim,evidence,ordinal) "
            "VALUES (?,?,?,?,?,?,?)",
            (db.new_id("nar_"), sid, n.get("label", ""), n.get("who", ""),
             n.get("claim", ""), n.get("evidence", ""), i),
        )
    conn.execute("DELETE FROM indicator WHERE story_id=?", (sid,))
    for i, ind in enumerate(ai.indicators or []):
        conn.execute(
            "INSERT INTO indicator(id,story_id,text,direction,ordinal) VALUES (?,?,?,?,?)",
            (db.new_id("ind_"), sid, ind.get("text", ""), ind.get("direction", "both"), i),
        )
    conn.execute("DELETE FROM action WHERE story_id=?", (sid,))
    for i, act in enumerate(ai.actions or []):
        conn.execute(
            "INSERT INTO action(id,story_id,action_type,text,ordinal) VALUES (?,?,?,?,?)",
            (db.new_id("act_"), sid, act.get("type", "Monitor"), act.get("text", ""), i),
        )


def _merge_into_existing(conn, story_id: str, draft: StoryDraft, actor: str) -> str:
    """Freshness update path: bump last_updated, append any new citation."""
    now = db.utcnow()
    changed = False
    for s in draft.sources:
        if not s.url or not is_valid_url(s.url):
            continue
        dup = conn.execute(
            "SELECT id FROM citation WHERE story_id=? AND url=?", (story_id, s.url)
        ).fetchone()
        if dup:
            continue
        src_id = _ensure_source(conn, s)
        conn.execute(
            "INSERT INTO citation(id,story_id,claim_id,source_id,title,url,"
            "published_at,accessed_at,orig_language,orig_headline,is_primary,is_circular)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (db.new_id("cit_"), story_id, None, src_id, s.title or draft.headline,
             s.url, s.published_at, now, s.orig_language, s.orig_headline,
             1 if s.is_primary else 0, 1 if s.is_circular else 0),
        )
        changed = True
    if changed:
        conn.execute("UPDATE story SET last_updated=? WHERE id=?", (now, story_id))
        db.audit(conn, actor, "merge_citation", "story", story_id,
                 "appended new corroborating source(s)")
        conn.commit()
    return story_id


def _normalize_countries(draft: StoryDraft) -> list[str]:
    seen: list[str] = []
    for c in ([draft.primary_country] + list(draft.countries)):
        c = (c or "").strip().lower()
        if c and c not in seen:
            seen.append(c)
    return seen


def _impact_line(intensity: float, what: str) -> str:
    if intensity >= 0.67:
        return f"Elevated potential impact to {what}."
    if intensity >= 0.34:
        return f"Some potential impact to {what}; validate exposure."
    return f"No direct impact to {what} identified yet."
