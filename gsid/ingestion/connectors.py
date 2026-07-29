"""Modular source connectors.

The built-in connectors read public RSS/Atom feeds. The registry favours a
globally diverse mix of Tier 1 (official) and Tier 2/3 (reputable) sources and
tags each feed with a default region/category hint plus a source tier.

LEGAL/ETHICAL NOTE: only public feeds intended for syndication are included.
The fetcher sends a descriptive User-Agent, honours a timeout, and does NOT
attempt to bypass paywalls, authentication, CAPTCHAs or robots restrictions.
Operators remain responsible for confirming each feed's terms of use in their
jurisdiction. Disable or add feeds via GSID_ENABLED_FEEDS / this registry.

The connector interface is generic: implement `fetch() -> list[FeedItem]` to
add non-RSS sources (official APIs, a compliant web-search provider, etc.).
"""

from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

try:
    import feedparser  # type: ignore
    _HAS_FEEDPARSER = True
except Exception:  # pragma: no cover
    _HAS_FEEDPARSER = False

log = logging.getLogger("gsid.ingestion")

USER_AGENT = (
    "GSID-Intelligence-Desk/1.0 (+public-RSS-reader; respects-robots; no-scraping)"
)

# Some government portals (e.g. Australia's Smartraveller) sit behind bot
# protection that stalls/blocks non-browser clients. A per-feed browser-like
# User-Agent (FeedDef.user_agent) gives those feeds their best chance; the
# pipeline stays fault-tolerant if they still block.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str
    published_at: str  # UTC ISO or ""
    source_id: str
    source_name: str
    tier: int
    source_type: str
    country: str
    language: str
    region_hint: str
    category_hint: str
    is_travel_advisory: bool = False
    subject_country: str = ""   # authoritative ISO of the advisory's DESTINATION
    advisory_level: int = 0     # normalized 1..4 (0 = n/a; see advisory_levels)


@dataclass
class FeedDef:
    id: str
    name: str
    url: str
    tier: int
    source_type: str
    country: str
    language: str = "en"
    region_hint: str = "global"
    category_hint: str = "geopolitical"
    enabled_by_default: bool = True
    ownership: str = ""
    transparency: str = ""
    is_travel_advisory: bool = False  # items are per-destination government advice
    kind: str = "rss"          # connector to use: "rss" | "json_ca"
    user_agent: str = ""       # per-feed UA override (default USER_AGENT)


class Connector(Protocol):
    def fetch(self) -> list[FeedItem]:  # pragma: no cover
        ...


# --------------------------------------------------------------------------
# Feed registry — globally diverse, public feeds
# --------------------------------------------------------------------------
FEED_REGISTRY: list[FeedDef] = [
    # ---- Tier 2 international wires / broadcasters ----
    FeedDef("bbc_world", "BBC News — World", "https://feeds.bbci.co.uk/news/world/rss.xml",
            2, "broadcaster", "gb", region_hint="global", category_hint="geopolitical",
            ownership="Public broadcaster (UK licence-fee funded)",
            transparency="Published editorial guidelines"),
    FeedDef("aljazeera", "Al Jazeera English", "https://www.aljazeera.com/xml/rss/all.xml",
            2, "broadcaster", "qa", region_hint="mena", category_hint="geopolitical",
            ownership="Qatar Media Corporation (state-funded)",
            transparency="Published code of ethics"),
    FeedDef("dw_world", "Deutsche Welle — Top Stories", "https://rss.dw.com/rdf/rss-en-all",
            2, "broadcaster", "de", region_hint="europe", category_hint="geopolitical",
            ownership="German public international broadcaster"),
    FeedDef("france24", "France 24 — International", "https://www.france24.com/en/rss",
            2, "broadcaster", "fr", region_hint="europe", category_hint="geopolitical",
            ownership="France Médias Monde (state-funded)"),
    FeedDef("guardian_world", "The Guardian — World", "https://www.theguardian.com/world/rss",
            2, "newspaper", "gb", region_hint="global", category_hint="geopolitical",
            ownership="Scott Trust (independent)"),
    FeedDef("npr_world", "NPR — World", "https://feeds.npr.org/1004/rss.xml",
            2, "broadcaster", "us", region_hint="north_america", category_hint="geopolitical"),

    # ---- Regional / national outlets for source diversity ----
    FeedDef("thehindu", "The Hindu — News", "https://www.thehindu.com/news/feeder/default.rss",
            2, "newspaper", "in", region_hint="south_asia", category_hint="geopolitical"),
    FeedDef("scmp", "South China Morning Post", "https://www.scmp.com/rss/91/feed",
            2, "newspaper", "hk", region_hint="east_asia", category_hint="geopolitical"),
    FeedDef("batimes", "Buenos Aires Times", "https://www.batimes.com.ar/feed",
            3, "newspaper", "ar", region_hint="latam_caribbean", category_hint="geopolitical"),
    FeedDef("allafrica", "AllAfrica — Latest", "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
            3, "aggregator", "int", region_hint="subsaharan_africa", category_hint="geopolitical",
            ownership="AllAfrica Global Media (pan-African aggregator)"),

    # ---- Tier 1 official / international organisations ----
    FeedDef("un_news", "UN News — Global", "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
            1, "international_org", "int", region_hint="global", category_hint="geopolitical",
            ownership="United Nations", transparency="Official UN channel"),
    FeedDef("reliefweb", "ReliefWeb — Disasters", "https://reliefweb.int/updates/rss.xml",
            1, "humanitarian", "int", region_hint="global", category_hint="natural_hazard",
            ownership="UN OCHA"),
    FeedDef("who_news", "WHO — News (health emergencies & outbreaks)",
            "https://www.who.int/rss-feeds/news-english.xml",
            1, "international_org", "int", region_hint="global", category_hint="natural_hazard",
            ownership="World Health Organization",
            transparency="WHO's general English news feed; includes disease "
                         "outbreak news. Their dedicated DON RSS was retired."),
    FeedDef("usgs_quakes", "USGS — Significant Earthquakes (7d)",
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.atom",
            1, "government", "us", region_hint="global", category_hint="natural_hazard",
            ownership="US Geological Survey"),
    FeedDef("gdacs", "GDACS — Global Disaster Alerts", "https://www.gdacs.org/xml/rss.xml",
            1, "international_org", "int", region_hint="global", category_hint="natural_hazard",
            ownership="UN/EC Global Disaster Alert and Coordination System"),

    # ---- Regulatory / compliance ----
    FeedDef("cisa_alerts", "CISA — Cybersecurity Advisories",
            "https://www.cisa.gov/cybersecurity-advisories/all.xml",
            1, "government", "us", region_hint="north_america", category_hint="cyber_physical",
            ownership="US Cybersecurity & Infrastructure Security Agency"),
    FeedDef("eu_presscorner", "European Commission — Press releases",
            "https://ec.europa.eu/commission/presscorner/api/rss?language=en",
            1, "regulator", "eu", region_hint="europe", category_hint="regulatory",
            ownership="European Commission",
            transparency="EU sanctions, NIS2/CER, trade and digital-regulation announcements."),
    FeedDef("us_fedreg_dhs", "US Federal Register — Homeland Security rules",
            "https://www.federalregister.gov/api/v1/documents.rss?conditions%5Bagencies%5D%5B%5D=homeland-security-department",
            1, "government", "us", region_hint="north_america", category_hint="regulatory",
            ownership="US Government Publishing Office (Federal Register)",
            transparency="Official DHS/CBP/TSA/CISA rules and notices; CTPAT- and "
                         "customs-relevant. Sanctions rules also appear here."),

    # ---- Specialist / supply chain / travel ----
    FeedDef("gov_uk_travel", "UK FCDO — Foreign Travel Advice (updates)",
            "https://www.gov.uk/foreign-travel-advice.atom",
            1, "government", "gb", region_hint="global", category_hint="geopolitical",
            ownership="UK Foreign, Commonwealth & Development Office",
            is_travel_advisory=True),
    FeedDef("us_state_travel", "US State Dept — Travel Advisories",
            "https://travel.state.gov/_res/rss/TAsTWs.xml",
            1, "government", "us", region_hint="global", category_hint="geopolitical",
            ownership="US Department of State, Bureau of Consular Affairs",
            is_travel_advisory=True),
    FeedDef("ca_gac_travel", "Global Affairs Canada — Travel Advisories",
            "https://data.international.gc.ca/travel-voyage/index-updated.json",
            1, "government", "ca", region_hint="global", category_hint="geopolitical",
            ownership="Global Affairs Canada",
            transparency="Official open-data JSON advisory dataset; ingested at "
                         "Canada level 2 and above ('exercise a high degree of "
                         "caution' through 'avoid all travel').",
            kind="json_ca",
            is_travel_advisory=True),
    FeedDef("au_smartraveller", "Australia Smartraveller — Travel Advisories",
            "https://www.smartraveller.gov.au/countries/documents/index.rss",
            1, "government", "au", region_hint="global", category_hint="geopolitical",
            ownership="Australian Department of Foreign Affairs & Trade (DFAT)",
            transparency="Public per-destination advisory feed. Smartraveller "
                         "applies bot protection that can intermittently block "
                         "server-side fetchers even with a browser User-Agent.",
            user_agent=BROWSER_UA,
            is_travel_advisory=True),
    FeedDef("de_aa_travel", "Germany Auswärtiges Amt — Travel Warnings",
            "https://www.auswaertiges-amt.de/opendata/travelwarning",
            1, "government", "de", language="de", region_hint="global",
            category_hint="geopolitical",
            ownership="German Federal Foreign Office (Auswärtiges Amt)",
            transparency="Official OpenData travel-warning API; ingested for "
                         "destinations with an active full, partial or "
                         "situation-based travel warning.",
            kind="json_de",
            is_travel_advisory=True),
]

FEED_BY_ID = {f.id: f for f in FEED_REGISTRY}


def _to_utc_iso(struct_time) -> str:
    if not struct_time:
        return ""
    try:
        dt = datetime(*struct_time[:6], tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return ""


@dataclass
class FetchResult:
    """Outcome of a single feed fetch, for health reporting."""

    items: list["FeedItem"]
    status: str            # ok | empty | error
    error: str = ""        # short error note when status == error/empty
    http_status: int = 0

    def __iter__(self):    # allow `for it in result` convenience
        return iter(self.items)

    def __len__(self):
        return len(self.items)


class RssConnector:
    """Fetches and parses a single RSS/Atom feed with a hard timeout."""

    def __init__(self, feed: FeedDef, timeout: int = 15):
        self.feed = feed
        self.timeout = timeout

    def fetch(self) -> list[FeedItem]:
        """Backwards-compatible: return just the items."""
        return self.fetch_with_status().items

    def fetch_with_status(self) -> FetchResult:
        if not _HAS_FEEDPARSER:
            return FetchResult([], "error", "feedparser not installed")
        http_status = 0
        try:
            req = urllib.request.Request(
                self.feed.url,
                headers={"User-Agent": self.feed.user_agent or USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                http_status = getattr(resp, "status", 0) or resp.getcode() or 0
                raw = resp.read()
        except Exception as exc:  # network errors must not crash ingestion
            log.warning("fetch failed for %s: %s", self.feed.id, exc)
            return FetchResult([], "error", str(exc)[:200])

        parsed = feedparser.parse(raw)
        # Travel-advisory feeds are long alphabetical lists; keep more of them.
        cap = 300 if self.feed.is_travel_advisory else 40
        items: list[FeedItem] = []
        for entry in parsed.entries[:cap]:
            published = _to_utc_iso(
                getattr(entry, "published_parsed", None)
                or getattr(entry, "updated_parsed", None)
            )
            items.append(
                FeedItem(
                    title=getattr(entry, "title", "").strip(),
                    link=getattr(entry, "link", "").strip(),
                    summary=getattr(entry, "summary", "") or getattr(entry, "description", ""),
                    published_at=published,
                    source_id=self.feed.id,
                    source_name=self.feed.name,
                    tier=self.feed.tier,
                    source_type=self.feed.source_type,
                    country=self.feed.country,
                    language=self.feed.language,
                    region_hint=self.feed.region_hint,
                    category_hint=self.feed.category_hint,
                    is_travel_advisory=self.feed.is_travel_advisory,
                )
            )
        log.info("fetched %d items from %s", len(items), self.feed.id)
        if not items:
            note = ("no entries parsed"
                    + (f" (HTTP {http_status})" if http_status and http_status != 200 else ""))
            return FetchResult(items, "empty", note, http_status)
        return FetchResult(items, "ok", "", http_status)


def _epoch_to_utc_iso(ts) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _flag(v) -> bool:
    """Truthy for JSON booleans and stringified 'true' (APIs vary)."""
    return v is True or str(v).strip().lower() == "true"


class _JsonAdvisoryConnector:
    """Shared fetch/parse scaffold for JSON travel-advisory APIs.

    Subclasses implement ``_items(payload)`` to turn a decoded JSON body into
    FeedItems. Every emitted item should lead with the destination name and set
    ``subject_country`` to the authoritative ISO code so the pipeline geo-tags
    it to the DESTINATION and merges it with matching advisories from other
    governments for the same place.
    """

    CAP = 300

    def __init__(self, feed: FeedDef, timeout: int = 15):
        self.feed = feed
        self.timeout = timeout

    def fetch(self) -> list[FeedItem]:
        return self.fetch_with_status().items

    def fetch_with_status(self) -> FetchResult:
        http_status = 0
        try:
            req = urllib.request.Request(
                self.feed.url,
                headers={"User-Agent": self.feed.user_agent or USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                http_status = getattr(resp, "status", 0) or resp.getcode() or 0
                raw = resp.read()
        except Exception as exc:  # network errors must not crash ingestion
            log.warning("fetch failed for %s: %s", self.feed.id, exc)
            return FetchResult([], "error", str(exc)[:200])

        try:
            payload = json.loads(raw)
        except Exception as exc:
            return FetchResult([], "error", f"json parse: {str(exc)[:120]}", http_status)

        items = self._items(payload)[: self.CAP]
        log.info("fetched %d items from %s", len(items), self.feed.id)
        if not items:
            return FetchResult(items, "empty", "no elevated advisories parsed", http_status)
        return FetchResult(items, "ok", "", http_status)

    def _make_item(self, *, title, link, summary, published_at, subject_country,
                   advisory_level=0) -> FeedItem:
        return FeedItem(
            title=title, link=link, summary=summary, published_at=published_at,
            source_id=self.feed.id, source_name=self.feed.name, tier=self.feed.tier,
            source_type=self.feed.source_type, country=self.feed.country,
            language=self.feed.language, region_hint=self.feed.region_hint,
            category_hint=self.feed.category_hint, is_travel_advisory=True,
            subject_country=(subject_country or "").strip().lower(),
            advisory_level=advisory_level,
        )

    def _items(self, payload: dict) -> list[FeedItem]:  # pragma: no cover
        raise NotImplementedError


class CanadaAdvisoryConnector(_JsonAdvisoryConnector):
    """Global Affairs Canada travel advisories via the official JSON dataset.

    Lists every destination with an ``advisory-state`` (0-indexed: 0..3 map to
    Canada levels 1..4). Emits destinations at level 2 and above
    (``advisory-state >= 1``: 'high degree of caution' through 'avoid all
    travel').
    """

    MIN_STATE = 1  # Canada level 2+ ("high degree of caution" and above)

    def _items(self, payload: dict) -> list[FeedItem]:
        data = (payload or {}).get("data") or {}
        items: list[FeedItem] = []
        for entry in data.values():
            try:
                state = int(entry.get("advisory-state", -1))
            except (TypeError, ValueError):
                state = -1
            if state < self.MIN_STATE:
                continue
            eng = entry.get("eng") or {}
            name = (eng.get("name") or entry.get("country-eng") or "").strip()
            if not name:
                continue
            advisory_text = (eng.get("advisory-text") or "").strip()
            slug = (eng.get("url-slug") or "").strip()
            link = (f"https://travel.gc.ca/destinations/{slug}" if slug
                    else "https://travel.gc.ca/travelling/advisories")
            recent = (eng.get("recent-updates") or "").strip()
            if advisory_text and recent:
                summary = f"{advisory_text}. Recent update: {recent}"
            else:
                summary = advisory_text or recent
            items.append(self._make_item(
                title=f"{name} — {advisory_text}" if advisory_text else name,
                link=link,
                summary=summary,
                published_at=_epoch_to_utc_iso((entry.get("date-published") or {}).get("timestamp")),
                subject_country=entry.get("country-iso"),
                # Canada advisory-state is 0-indexed (0..3 => GSID levels 1..4).
                advisory_level=state + 1,
            ))
        return items


class GermanyAdvisoryConnector(_JsonAdvisoryConnector):
    """German Federal Foreign Office (Auswärtiges Amt) travel warnings.

    The OpenData ``/travelwarning`` endpoint returns ~200 country notices keyed
    by contentId. Each carries boolean flags; we emit destinations with any
    active warning (full 'Reisewarnung', partial, or situation-based) — the
    German analogue of an elevated advisory. Content is German (language 'de');
    the pipeline geo-tags via the authoritative 2-letter ``countryCode`` and
    renders an English destination headline.
    """

    # (flag field, English label, GSID level) in priority order, strongest first.
    _LABELS = [
        ("warning", "Travel warning (avoid travel)", 4),
        ("partialWarning", "Partial travel warning", 3),
        ("situationWarning", "Situation-based travel warning", 2),
        ("situationPartWarning", "Partial situation-based travel warning", 2),
    ]

    def _items(self, payload: dict) -> list[FeedItem]:
        resp = (payload or {}).get("response") or {}
        items: list[FeedItem] = []
        for content_id, entry in resp.items():
            if not isinstance(entry, dict) or "iso3CountryCode" not in entry:
                continue  # skips the scalar 'lastModified' and any stray keys
            match = next(((lbl, lvl) for f, lbl, lvl in self._LABELS
                          if _flag(entry.get(f))), None)
            if match is None:
                continue  # baseline safety notice, not an elevated warning
            label, level = match
            name = (entry.get("countryName") or "").strip()
            if not name:
                continue
            items.append(self._make_item(
                title=f"{name} — {label}",
                link=f"https://www.auswaertiges-amt.de/de/ReiseUndSicherheit/{content_id}",
                summary=f"{entry.get('title', name)} · {label}",
                published_at=_epoch_to_utc_iso(entry.get("lastModified") or entry.get("effective")),
                subject_country=entry.get("countryCode"),
                advisory_level=level,
            ))
        return items


_JSON_CONNECTORS = {
    "json_ca": CanadaAdvisoryConnector,
    "json_de": GermanyAdvisoryConnector,
}


def make_connector(feed: FeedDef, timeout: int = 15):
    """Return the connector appropriate for a feed's ``kind``."""
    cls = _JSON_CONNECTORS.get(feed.kind)
    if cls is not None:
        return cls(feed, timeout)
    return RssConnector(feed, timeout)


def selected_feeds(enabled_ids: list[str] | None) -> list[FeedDef]:
    if enabled_ids:
        return [FEED_BY_ID[i] for i in enabled_ids if i in FEED_BY_ID]
    return [f for f in FEED_REGISTRY if f.enabled_by_default]
