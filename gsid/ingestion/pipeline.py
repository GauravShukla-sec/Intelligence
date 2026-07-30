"""Live ingestion pipeline.

Flow: fetch feeds -> sanitize -> relevance pre-filter -> cluster near-duplicates
-> build one StoryDraft per cluster (multiple citations, circular-reporting
flag) -> persist via the shared store (analyze + score). Every stage is
fault-tolerant: a failing feed is skipped, never fatal.
"""

from __future__ import annotations

import logging

from .advisory_levels import level_from_text
from .connectors import make_connector, selected_feeds, FeedItem
from .dedup import cluster_items, detect_circular
from .sanitize import clean_content, is_valid_url
from ..store import DraftClaim, DraftSource, StoryDraft, save_story
from ..taxonomy import (
    CATEGORY_IDS, advisory_destination, country_name, subject_countries,
)
from ..db import utcnow

log = logging.getLogger("gsid.pipeline")

# Keyword hints to refine the category beyond the feed's default hint.
_CATEGORY_KEYWORDS = {
    "regulatory": ["regulation", "directive", "sanction", "law", "compliance",
                   "customs", "tariff", "nis2", "ctpat", "gdpr", "ruling", "court"],
    "supply_chain": ["port", "shipping", "cargo", "freight", "logistics", "canal",
                     "container", "customs", "border", "supply chain"],
    "cyber_physical": ["ransomware", "cyberattack", "ics", "scada", "malware",
                       "breach", "gps jamming", "drone"],
    "natural_hazard": ["earthquake", "flood", "wildfire", "hurricane", "typhoon",
                       "volcano", "tsunami", "storm", "outbreak", "drought"],
    "physical_corporate": ["factory", "warehouse", "office", "sabotage", "theft",
                           "kidnap", "attack", "arson", "protest", "workplace"],
    "continuity": ["blackout", "outage", "power", "water shortage", "telecom",
                   "grid", "evacuation", "curfew"],
    "economic_social": ["inflation", "strike", "layoff", "currency", "fuel shortage",
                        "unrest", "food insecurity"],
    "geopolitical": ["war", "military", "border", "coup", "election", "diplomat",
                     "sanction", "treaty", "missile", "conflict"],
}

# Items with none of these signals are unlikely to be security-relevant.
_RELEVANCE_HINTS = set()
for _terms in _CATEGORY_KEYWORDS.values():
    _RELEVANCE_HINTS.update(_terms)


class IngestionPipeline:
    def __init__(self, conn, config, analyzer):
        self.conn = conn
        self.config = config
        self.analyzer = analyzer

    def run(self) -> dict:
        feeds = selected_feeds(self.config.enabled_feeds or None)
        all_items: list[FeedItem] = []
        feed_status: dict[str, int] = {}
        for feed in feeds:
            result = make_connector(feed, self.config.fetch_timeout_seconds).fetch_with_status()
            feed_status[feed.id] = len(result.items)
            all_items.extend(result.items)
            self._record_health(feed, result)

        # Pre-filter for security relevance (keeps the desk focused).
        relevant = [it for it in all_items if _looks_relevant(it)]

        # News is clustered by text similarity to fuse near-duplicate coverage.
        # Travel advisories are NOT: their boilerplate wording is near-identical
        # across destinations, so text clustering would wrongly fuse unrelated
        # countries. Each advisory stands alone and is grouped by DESTINATION at
        # save time (dedup_key = "Travel advisory: <country>"), which is how one
        # story ends up with one citation per government.
        news = [it for it in relevant if not it.is_travel_advisory]
        advisories = [it for it in relevant if it.is_travel_advisory]
        news_texts = [f"{it.title} {it.summary}" for it in news]
        clusters = cluster_items(news_texts, threshold=0.5) if news_texts else []
        member_groups = [[news[i] for i in idx] for idx in clusters]
        member_groups += [[it] for it in advisories]

        saved = 0
        for members in member_groups:
            draft = self._build_draft(members)
            if draft is None:
                continue
            try:
                save_story(self.conn, draft, self.analyzer, actor="ingestion")
                saved += 1
            except Exception as exc:  # one bad item shouldn't stop the run
                log.exception("failed to persist cluster: %s", exc)

        result = {
            "feeds_polled": len(feeds),
            "items_fetched": len(all_items),
            "items_relevant": len(relevant),
            "clusters": len(member_groups),
            "stories_saved": saved,
            "feed_status": feed_status,
        }
        log.info("ingestion run: %s", result)
        return result

    def _record_health(self, feed, result) -> None:
        """Persist per-feed outcome for the Settings feed-health indicator."""
        now = utcnow()
        ok = result.status == "ok"
        row = self.conn.execute(
            "SELECT consecutive_failures FROM feed_health WHERE feed_id=?",
            (feed.id,),
        ).fetchone()
        prev_fail = row["consecutive_failures"] if row else 0
        fails = 0 if ok else prev_fail + 1
        self.conn.execute(
            "INSERT INTO feed_health(feed_id, name, url, tier, last_run, last_success, "
            "last_count, status, error, consecutive_failures) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(feed_id) DO UPDATE SET name=excluded.name, url=excluded.url, "
            "tier=excluded.tier, last_run=excluded.last_run, "
            "last_success=COALESCE(excluded.last_success, feed_health.last_success), "
            "last_count=excluded.last_count, status=excluded.status, "
            "error=excluded.error, consecutive_failures=excluded.consecutive_failures",
            (feed.id, feed.name, feed.url, feed.tier, now,
             now if ok else None, len(result.items), result.status,
             result.error, fails),
        )

    def _build_draft(self, members: list[FeedItem]) -> StoryDraft | None:
        lead = max(members, key=lambda m: (m.tier == 1, m.tier == 2, len(m.summary)))
        body, _ = clean_content(lead.summary or lead.title)
        if not lead.title or not is_valid_url(lead.link):
            return None

        category = _refine_category(lead.title + " " + body, lead.category_hint)
        origins = [m.source_name for m in members]
        circular = detect_circular(origins)

        # Travel advisories are per-DESTINATION: geo-tag to the destination
        # country (from the item title / URL slug), not the publishing govt.
        travel = any(m.is_travel_advisory for m in members)
        dest_code = None
        location_text = ""
        if travel:
            dest_code = advisory_destination(
                lead.title, lead.link, getattr(lead, "subject_country", ""))
            if dest_code:
                location_text = country_name(dest_code)

        sources: list[DraftSource] = []
        for m in members:
            if not is_valid_url(m.link):
                continue
            # Normalize this government's advisory to the shared 1..4 scale:
            # JSON connectors set it directly; free-text feeds are parsed here.
            level = m.advisory_level or (
                level_from_text(m.source_id, m.title, m.summary)
                if m.is_travel_advisory else 0
            )
            sources.append(DraftSource(
                name=m.source_name, url=m.link, tier=m.tier,
                source_type=m.source_type, country=m.country, language=m.language,
                is_primary=(m.tier == 1), title=m.title, published_at=m.published_at,
                orig_headline=m.title if m.language != "en" else "",
                orig_language=m.language, is_circular=circular,
                advisory_level=level, feed_id=m.source_id,
            ))
        if not sources:
            return None

        claims = [DraftClaim(
            text=lead.title,
            claim_type="official_claim" if lead.tier == 1 else "fact",
            attributed_to=lead.source_name,
            corroboration="multiple" if len(members) > 1 else "single",
            source_index=0,
        )]

        if travel:
            # An advisory belongs to its DESTINATION only. If the destination
            # can't be resolved we leave it untagged: guessing from the body
            # would tag it to the issuing government (US State advisories say
            # "U.S. citizens…"), piling every unresolved advisory onto that
            # government's own Travel Risk page.
            headline = (f"Travel advisory: {country_name(dest_code)}" if dest_code
                        else lead.title)
            countries = [dest_code] if dest_code else []
            primary_country = dest_code or ""
        else:
            headline = lead.title
            # Geo-tag to the countries the story is ABOUT (headline first, so a
            # roundup's passing body mentions don't leak), not to its publisher —
            # so the map and country filters reflect where events happen.
            countries = subject_countries(lead.title, body)
            primary_country = countries[0] if countries else ""

        return StoryDraft(
            headline=headline,
            body=body,
            category=category,
            location_text=location_text,
            primary_country=primary_country,
            countries=countries,
            event_time=lead.published_at,
            status="advisory" if travel else "developing",
            sources=sources,
            claims=claims,
            is_demo=False,
        )


def _looks_relevant(item: FeedItem) -> bool:
    text = f"{item.title} {item.summary}".lower()
    if item.tier == 1:
        return True  # official feeds are curated already
    return any(term in text for term in _RELEVANCE_HINTS)


def _refine_category(text: str, default_hint: str) -> str:
    text = text.lower()
    best = default_hint if default_hint in CATEGORY_IDS else "geopolitical"
    best_score = 0
    for cat, terms in _CATEGORY_KEYWORDS.items():
        score = sum(1 for t in terms if t in text)
        if score > best_score:
            best_score = score
            best = cat
    return best
