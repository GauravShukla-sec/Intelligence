"""Locate a development from its headline, using a bundled city gazetteer.

Only GDACS and USGS publish coordinates, so without this the globe plots
natural hazards and nothing else — conflict, unrest and cyber-physical stories
never appear as markers, which makes a security map look like a disaster map.

The approach is deliberately conservative, because a marker asserts a fact:

  * only place names are matched, never country centroids — a centroid would
    re-draw the choropleth as dots while implying a precision that does not
    exist;
  * a match must agree with the story's own country tags. This is the load
    bearing constraint: it stops "Paris, Texas" hijacking a story about France,
    and it means a wrong country tag cannot invent a plausible-looking place;
  * candidate names are taken from capitalised runs in the headline, so
    ordinary prose cannot match;
  * a stoplist covers city names that are also everyday English words, since
    those survive capitalisation at the start of a headline;
  * a capital used as a metonym for its government ("Damascus slams") is not
    treated as a location;
  * only the headline is read. Summaries name the places a story is *about*
    rather than where it happened, and including them geocoded a missile strike
    on a Kyiv factory to Moscow;
  * ties resolve to the largest city, which is the one a reader means.

Measured on 3,632 stored stories: 174 placed (5%). Reading summaries too would
have placed 512 (14%), but a hand audit of that set was mostly wrong, so the
coverage was bought with false markers. Precision wins here — an empty spot on
the globe claims nothing, a misplaced dot claims something untrue.

Data: GeoNames cities15000 (CC BY 4.0), filtered to population >= 100,000 or
national capital. ~6,300 places, bundled so ingestion stays offline.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("gsid.geocode")

_DATA = Path(__file__).with_name("data") / "cities.json"

# City names that are also common English words. Capitalisation cannot separate
# them (a headline may start with any of these), and the country constraint does
# not help when the story really is about that country — so they are never
# matched at all.
AMBIGUOUS = {
    "mobile", "reading", "bath", "worth", "nice", "split", "most", "bar",
    "same", "general", "santa", "union", "industrial", "victoria", "york",
    "orange", "phoenix", "jupiter", "eagle", "hope", "liberty", "independence",
    "salem", "franklin", "clinton", "jackson", "madison", "monroe", "surprise",
    "normal", "boring", "why", "point", "center", "centre", "springs", "valley",
    # Not places in a news headline: a crude-oil benchmark, an index, a brand.
    "brent", "nasdaq", "sterling", "national", "central", "federal",
}

# Capitals routinely stand in for their governments — "Washington says",
# "Moscow denies", "Damascus slams". That is an actor, not a location.
#
# This is a list of verbs rather than real parsing, so it is not exhaustive:
# "Tehran retaliates" is caught, "Seoul drops its stance on Pyongyang" is caught,
# but novel phrasings will slip through. The country anchor bounds the damage —
# a missed metonym still resolves inside a country the story is tagged with, so
# the failure is an over-precise city, not a marker on the wrong continent.
# Attack verbs ("hits", "strikes", "targets") are deliberately absent: those
# describe real events at real places, and excluding them would drop genuine
# locations like "Russia hits Kyiv".
_METONYM = re.compile(
    r"^\s*(?:has|had|have|is|are|was|were|will|would|may|could|also|now|again|"
    r"and|reportedly)?\s*(?:"
    # Speech and statecraft. A city cannot do any of these; a government can.
    r"(?:says?|said|warns?|warned|denies|denied|claims?|claimed|announces?|"
    r"announced|accuses?|accused|agrees?|agreed|signs?|signed|urges?|urged|"
    r"insists?|insisted|confirms?|confirmed|rejects?|rejected|threatens?|"
    r"threatened|backs?|backed|imposes?|imposed|orders?|ordered|vows?|vowed|"
    r"seeks?|sought|slams?|slammed|blames?|blamed|condemns?|condemned|summons|"
    r"summoned|demands?|demanded|refuses?|refused|welcomes?|welcomed|hails?|"
    r"hailed|pledges?|pledged|responds?|responded|retaliates?|retaliated|"
    r"dismisses|dismissed|downplays?|downplayed|mulls?|mulled|weighs?|weighed|"
    r"drops?|dropped|calls?|called|considers?|considered)\b"
    # Abstract nouns of policy: "citing Washington request", "Moscow pressure".
    r"|(?:request|decision|statement|demand|offer|proposal|response|warning|"
    r"pressure|refusal|stance|position|policy|denial)\b"
    # Gerunds: "contingent on Riyadh normalising relations".
    r"|(?:normalis|normaliz|refus|insist|deny|denying|agree|threaten|demand|"
    r"seek|back|push|press|urg)(?:ing|es)\b)",
    re.IGNORECASE)

# The giveaway sometimes precedes the name instead: "stance on Pyongyang",
# "talks with Beijing". These nouns take a counterparty, not a place.
_METONYM_BEFORE = re.compile(
    r"\b(?:stance|position|policy|pressure|line|view|talks|negotiations|deal|"
    r"deals|sanctions|tariffs|curbs|ties|relations|dialogue|summit|standoff|"
    r"rift|feud|row|dispute)\s+(?:on|with|toward|towards|against|between|over)"
    r"\s+$", re.IGNORECASE)

# Runs of capitalised words, e.g. "New York" or "Port-au-Prince". Allows the
# internal lowercase particles real place names contain.
_CAP_RUN = re.compile(
    r"\b([A-Z][\w'’\-]+(?:[ \-](?:of|au|aux|de|del|la|le|les|da|do|dos|van|der|el|al)?[ \-]?[A-Z][\w'’\-]+){0,2})"
)

def _is_metonym(text: str, token: str) -> bool:
    """True when every mention of `token` reads as a government, not a place.

    One locative mention is enough to keep the marker: "Moscow denies strike on
    Moscow suburb" is still a story with a location in it.
    """
    for m in re.finditer(rf"\b{re.escape(token)}\b", text):
        if not _METONYM.match(text[m.end():]) and \
           not _METONYM_BEFORE.search(text[:m.start()]):
            return False
    return True


_index: dict[str, list[tuple]] | None = None


def _load() -> dict[str, list[tuple]]:
    """Name (lowercased) -> candidate places, largest first."""
    global _index
    if _index is not None:
        return _index
    idx: dict[str, list[tuple]] = {}
    try:
        payload = json.loads(_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("city gazetteer unavailable at %s; headline geocoding disabled", _DATA)
        _index = {}
        return _index
    for name, cc, lat, lon, pop in payload.get("cities", []):
        idx.setdefault(name.lower(), []).append((name, cc, lat, lon, pop))
    for v in idx.values():                       # biggest first
        v.sort(key=lambda r: -r[4])
    _index = idx
    return _index


def candidates(headline: str) -> list[str]:
    """Capitalised runs from a headline, longest first.

    Longest first so "New York" is tried before "York", and "Port Sudan"
    before "Sudan".
    """
    if not headline:
        return []
    found = {m.group(1).strip() for m in _CAP_RUN.finditer(headline)}
    # Also consider the trailing word of a two-word run ("Port Sudan" -> "Sudan"
    # is covered by the regex separately, but "in Kyiv," style punctuation is
    # already handled by the word boundary).
    return sorted(found, key=lambda s: (-len(s), s))


def locate(headline: str, countries: list[str] | None = None) -> dict | None:
    """Best place match for a story, or None when nothing is defensible.

    `countries` are the story's ISO-2 tags. A match is only accepted when the
    place sits in one of them, so this can add precision to a story's location
    but never contradict it.

    Only the headline is read. Summaries were tried and are actively harmful:
    they name the places a story is *about* rather than where it *happened*, so
    a Russian missile strike on a Kyiv factory geocoded to Moscow and an EU
    statement to Brussels. Matching the headline alone cut coverage from 14% to
    5% and removed essentially every false positive in a 35-story audit.
    """
    allowed = {c.strip().lower() for c in (countries or []) if c and c.strip()}
    if not allowed:
        return None                              # unanchored: refuse to guess
    idx = _load()
    if not idx:
        return None

    text = headline or ""
    for token in candidates(text):
        key = token.lower()
        if key in AMBIGUOUS:
            # Never plot on one of these alone. "Mobile phones seized in raid"
            # matched Mobile, Alabama — a marker asserting a location the story
            # never claimed. Losing the genuine Mobile stories is the cheaper
            # error for a map that is supposed to be evidence.
            continue
        places = idx.get(key)
        if not places:
            continue
        if _is_metonym(text, token):
            continue
        for name, cc, lat, lon, pop in places:
            if cc not in allowed:
                continue
            return {"lat": lat, "lon": lon, "city": name, "country": cc,
                    "population": pop, "precision": "city"}
    return None
