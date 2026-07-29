"""Normalize each government's travel-advisory scale to one GSID scale.

Every issuing government uses a different vocabulary — US State runs Levels
1–4, the UK FCDO writes free text ("advises against all but essential
travel"), Australia uses four tiers, Canada 0–3, Germany warning flags. To
compare them (and to never let a "do not travel" hide behind a mild label) we
map every source onto a single ordinal scale:

    1  Take normal precautions      (baseline)
    2  Exercise increased caution
    3  Reconsider / avoid non-essential travel
    4  Do not travel                (most severe)
    0  Unknown — not an advisory, or no level could be read (excluded from
       consensus so it never dilutes the worst-case reading)

JSON connectors set the level directly from their structured field (they know
their own scale). Free-text RSS advisories (US/UK/Australia) are normalized
here from their wording via ``level_from_text``.
"""

from __future__ import annotations

import re

LEVEL_LABELS = {
    0: "—",
    1: "Take normal precautions",
    2: "Exercise increased caution",
    3: "Reconsider / avoid non-essential travel",
    4: "Do not travel",
}

# Government-agnostic phrase → level, strongest first (first match wins).
_PHRASE_LEVELS: list[tuple[int, tuple[str, ...]]] = [
    (4, ("do not travel", "avoid all travel", "against all travel")),
    (3, ("reconsider your need to travel", "reconsider travel",
         "avoid non-essential travel", "all but essential travel",
         "avoid non essential travel")),
    (2, ("high degree of caution", "exercise increased caution",
         "increased caution", "exercise a high degree of caution")),
    (1, ("exercise normal", "take normal", "normal security precautions",
         "normal safety precautions")),
]

_US_LEVEL_RE = re.compile(r"level\s*([1-4])", re.IGNORECASE)


def level_from_phrases(text: str) -> int:
    """Best-effort level from advisory wording; 0 when nothing matches."""
    t = (text or "").lower()
    for level, phrases in _PHRASE_LEVELS:
        if any(p in t for p in phrases):
            return level
    return 0


def level_from_text(feed_id: str, title: str = "", summary: str = "") -> int:
    """Normalize a free-text advisory item to the 1..4 scale (0 = unknown).

    US State titles carry an explicit ``Level N`` (same 1..4 semantics); every
    other text source falls back to phrase matching.
    """
    blob = f"{title} {summary}"
    if feed_id == "us_state_travel":
        m = _US_LEVEL_RE.search(blob)
        if m:
            return int(m.group(1))
    return level_from_phrases(blob)


def clamp_level(value) -> int:
    """Coerce any input to a valid 0..4 level."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return 0 if n < 0 else 4 if n > 4 else n
