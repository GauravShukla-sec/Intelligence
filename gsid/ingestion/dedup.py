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
