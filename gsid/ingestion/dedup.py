"""Deduplication and topic clustering.

Uses a normalized token-shingle signature per item and a Jaccard-similarity
comparison to cluster near-duplicate / syndicated coverage. This lets the
platform distinguish a *new development* from *recycled reporting*, and flag
circular reporting (many items tracing to the same wire origin).

Deliberately dependency-free (no numpy/sklearn) so it runs anywhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "for", "with",
    "as", "by", "from", "is", "are", "was", "were", "be", "been", "has", "have",
    "had", "it", "its", "that", "this", "after", "over", "amid", "says", "said",
    "new", "report", "reports", "update", "breaking", "latest",
}


def normalize_tokens(text: str) -> list[str]:
    text = (text or "").lower()
    words = re.findall(r"[a-z0-9]+", text)
    return [w for w in words if w not in _STOP and len(w) > 2]


def signature(text: str) -> set[str]:
    """Bag of significant tokens used for similarity comparison."""
    return set(normalize_tokens(text))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def dedup_key(headline: str) -> str:
    """Stable clustering key: sorted top significant tokens from the headline."""
    toks = sorted(set(normalize_tokens(headline)))
    return "-".join(toks[:8])


@dataclass
class Cluster:
    key: str
    signature: set[str] = field(default_factory=set)
    members: list[int] = field(default_factory=list)  # indices into items list


def cluster_items(
    texts: list[str], threshold: float = 0.5
) -> list[list[int]]:
    """Greedy single-pass clustering by Jaccard similarity.

    Returns a list of clusters, each a list of item indices. Order-stable.
    """
    clusters: list[Cluster] = []
    for idx, text in enumerate(texts):
        sig = signature(text)
        placed = False
        for c in clusters:
            if jaccard(sig, c.signature) >= threshold:
                c.members.append(idx)
                c.signature |= sig  # widen the cluster signature
                placed = True
                break
        if not placed:
            clusters.append(Cluster(key=str(idx), signature=sig, members=[idx]))
    return [c.members for c in clusters]


def detect_circular(sources_per_item: list[str]) -> bool:
    """Flag likely circular reporting: >=3 items but <=1 distinct origin.

    `sources_per_item` is the origin/wire attribution for each clustered item.
    """
    origins = {s for s in sources_per_item if s}
    return len(sources_per_item) >= 3 and len(origins) <= 1

# --------------------------------------------------------------------------
# Cross-run event matching
# --------------------------------------------------------------------------
# `cluster_items` only ever sees one ingestion batch. With a five-minute poll
# interval, coverage of the same event by different outlets almost never lands
# in the same batch, so each arrival became its own story: the Leipzig airport
# drone attack was stored four times (BBC, DW, Guardian, SCMP) at pairwise
# similarity 0.75-0.88, and the corpus ran 90% single-source as a result.
#
# That is not cosmetic. Corroboration is what `derive_confidence` reads, and an
# evidence gate requiring two independent Tier-1/2 sources is unreachable while
# every story has one. So matching has to run against stored events too.

# How far back to look for the same event. Wire coverage of one incident spreads
# over hours, and follow-ups over a day or two; beyond that a similar headline is
# more likely a distinct recurrence than the same event.
MATCH_WINDOW_HOURS = 72

# Two observed positions this far apart are different events whatever the
# wording. This is the Mozambique rule: a fire in Mozambique and a fire in
# Namibia share GDACS boilerplate almost exactly.
MAX_MATCH_KM = 75.0


def _km_apart(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance. Plain haversine; no dependency worth adding."""
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def find_matching_story(conn, headline: str, *, is_demo: bool = False,
                        lat=None, lon=None, threshold: float = 0.5,
                        window_hours: int = MATCH_WINDOW_HOURS) -> str | None:
    """Best stored event this text is the same event as, or None.

    Compares HEADLINES, exactly as the in-batch clusterer does, so an item
    merges identically whether its sibling arrived in the same run or an earlier
    one. Including the body collapses similarity — see the pipeline for the
    measurement.

    Travel advisories are excluded: their boilerplate is near-identical across
    destinations, and they are keyed by destination at save time instead.
    """
    sig = signature(headline)
    if not sig:
        return None
    # No row cap: a 72-hour window already holds ~470 stories at current volume,
    # so a LIMIT silently drops candidates and the match becomes a function of
    # ingestion order rather than similarity. The window is the bound.
    rows = conn.execute(
        "SELECT id, headline, lat, lon FROM story "
        " WHERE is_demo = ? AND COALESCE(status,'') != 'advisory' "
        "   AND last_updated >= datetime('now', ?)",
        (1 if is_demo else 0, f"-{int(window_hours)} hours"),
    ).fetchall()

    best, best_sim = None, 0.0
    for r in rows:
        if lat is not None and r["lat"] is not None:
            if _km_apart(lat, lon, r["lat"], r["lon"]) > MAX_MATCH_KM:
                continue
        sim = jaccard(sig, _story_signature(r["id"], r["headline"]))
        if sim >= threshold and sim > best_sim:
            best, best_sim = r["id"], sim
    return best


# Signatures are recomputed for every candidate on every save, which is O(saves
# x window) tokenisations per run. Headline and summary never change once
# stored, so cache by id.
_SIG_CACHE: dict[str, set[str]] = {}


def _story_signature(story_id: str, headline: str) -> set[str]:
    hit = _SIG_CACHE.get(story_id)
    if hit is None:
        hit = signature(headline)
        if len(_SIG_CACHE) > 5000:      # bounded; this is a per-process cache
            _SIG_CACHE.clear()
        _SIG_CACHE[story_id] = hit
    return hit
