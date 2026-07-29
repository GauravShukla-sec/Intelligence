"""Content sanitization.

Retrieved web content is UNTRUSTED. This module:
  * strips HTML/markup and scripts,
  * neutralizes common prompt-injection phrasings before content reaches any
    analyzer (defense in depth; the LLM prompt also delimits untrusted data),
  * validates URLs (scheme/host) and truncates over-long text.

Nothing here executes remote content; it only cleans strings.
"""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTINL_RE = re.compile(r"\n{3,}")

# Phrases that attempt to hijack an LLM. We defang (not delete) so analysts can
# still see the original intent if they inspect the raw record.
_INJECTION_PATTERNS = [
    re.compile(r"ignore (all |the |your )?(previous|prior|above) instructions", re.I),
    re.compile(r"disregard (all |the )?(previous|prior|above)", re.I),
    re.compile(r"you are now (an?|the) ", re.I),
    re.compile(r"system prompt", re.I),
    re.compile(r"</?(system|assistant|user)>", re.I),
    re.compile(r"reveal (your )?(prompt|instructions|api key)", re.I),
    re.compile(r"\bBEGIN (SYSTEM|PROMPT)\b", re.I),
]

MAX_TEXT_LEN = 8000
ALLOWED_SCHEMES = {"http", "https"}


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = _SCRIPT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    text = _MULTINL_RE.sub("\n\n", text)
    return text.strip()


def defang_injection(text: str) -> tuple[str, int]:
    """Return (cleaned_text, number_of_neutralized_patterns)."""
    count = 0
    for pat in _INJECTION_PATTERNS:
        text, n = pat.subn(lambda m: "[neutralized-instruction]", text)
        count += n
    return text, count


def clean_content(text: str) -> tuple[str, int]:
    """Full cleaning pass used before analysis. Returns (text, injection_hits)."""
    text = strip_html(text)
    text, hits = defang_injection(text)
    if len(text) > MAX_TEXT_LEN:
        text = text[:MAX_TEXT_LEN].rsplit(" ", 1)[0] + " …"
    return text, hits


def is_valid_url(url: str) -> bool:
    try:
        p = urlparse((url or "").strip())
    except ValueError:
        return False
    if p.scheme.lower() not in ALLOWED_SCHEMES:
        return False
    if not p.netloc or "." not in p.netloc:
        return False
    # Internal CMS render paths (e.g. travel.state.gov's Adobe AEM `/tsg_aem/`)
    # return a raw HTML fragment, not a public page — never cite them.
    if "/tsg_aem/" in p.path:
        return False
    return True
