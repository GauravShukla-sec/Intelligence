"""Match developments against the desk's own watchlist.

This is deliberately a SEPARATE layer from `scoring.relevance`:

  * the 0-100 relevance model is objective and published (Transparency page
    documents every dimension and its weight). Re-weighting it per watchlist
    would make that page a lie and make two desks disagree about the same
    documented number.
  * watchlist exposure is subjective and changes whenever preferences change,
    so it is computed at READ time. Storing it at ingestion would go stale the
    moment someone edits the watchlist.

So a story has one objective score, plus an exposure view that answers a
different question: "does this touch anything *we* care about, and why?"
"""

from __future__ import annotations

import re

from .taxonomy import country_name

# Points per match kind. Small integers: this orders stories, it does not
# pretend to be a second 0-100 model.
W_COUNTRY = 4
W_SITE = 5          # a physical site is stronger evidence than a watched country
W_TRAVEL = 4
W_TOPIC = 2
W_REGULATION = 3
W_INDUSTRY = 1
MAX_TOPIC_MATCHES = 3   # stop one keyword-stuffed story dominating


def _terms(prefs: dict, key: str) -> list[str]:
    v = prefs.get(key) or []
    if isinstance(v, str):
        v = [v]
    return [str(t).strip() for t in v if str(t).strip()]


def _mentions(text: str, term: str) -> bool:
    """Word-boundary containment, so 'chip' doesn't match 'microchipped'."""
    if not term:
        return False
    return re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE) is not None


def match(story: dict, prefs: dict, countries: list[str] | None = None) -> dict:
    """Score and explain a story's overlap with the watchlist.

    Returns {"score": int, "reasons": [str], "matched": {...}} — score 0 and no
    reasons when nothing is watched or nothing matches.
    """
    text = " ".join(str(story.get(f) or "") for f in
                    ("headline", "summary", "location_text"))
    story_countries = {c.lower() for c in (countries or []) if c}
    if story.get("primary_country"):
        story_countries.add(str(story["primary_country"]).lower())

    score = 0
    reasons: list[str] = []
    matched: dict[str, list[str]] = {}

    def note(kind: str, item: str, points: int, reason: str) -> None:
        nonlocal score
        score += points
        matched.setdefault(kind, []).append(item)
        reasons.append(reason)

    watched = {c.lower() for c in _terms(prefs, "countries")}
    for iso in sorted(story_countries & watched):
        note("countries", iso, W_COUNTRY,
             f"{country_name(iso)} is on your country watchlist.")

    # Sites and travel destinations are named places; match them by name in the
    # text OR by their country code when one was configured.
    for site in _terms(prefs, "sites"):
        if _mentions(text, site):
            note("sites", site, W_SITE, f"Mentions {site}, one of your sites.")
    for dest in _terms(prefs, "travel_destinations"):
        if _mentions(text, dest):
            note("travel_destinations", dest, W_TRAVEL,
                 f"Mentions {dest}, a destination your travellers use.")

    topic_hits = 0
    for topic in _terms(prefs, "topics"):
        if topic_hits >= MAX_TOPIC_MATCHES:
            break
        if _mentions(text, topic):
            topic_hits += 1
            note("topics", topic, W_TOPIC, f"Touches a tracked topic: {topic}.")

    for reg in _terms(prefs, "regulations"):
        if _mentions(text, reg):
            note("regulations", reg, W_REGULATION,
                 f"References {reg}, which is on your compliance register.")

    for ind in _terms(prefs, "industries"):
        if _mentions(text, ind):
            note("industries", ind, W_INDUSTRY, f"Relevant to {ind}.")

    return {"score": score, "reasons": reasons, "matched": matched}


def attach(stories: list[dict], prefs: dict,
           countries_by_id: dict[str, list[str]] | None = None) -> list[dict]:
    """Annotate each story with its watchlist exposure, in place."""
    countries_by_id = countries_by_id or {}
    for s in stories:
        s["watchlist"] = match(s, prefs, countries_by_id.get(s.get("id")))
    return stories
