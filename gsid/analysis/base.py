"""Analyzer interface and structured result schema.

Every analyzer (heuristic or model-backed) returns an `AnalysisResult` with
the same shape, so downstream code (scoring, brief assembly, UI) is provider
independent. This is the abstraction layer required by the brief.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Protocol


@dataclass
class SourceRef:
    """A citation reference passed into analysis (already sanitized)."""

    source_id: str
    name: str
    tier: int
    url: str
    title: str = ""
    published_at: str = ""
    country: str = ""
    language: str = "en"
    is_primary: bool = False


@dataclass
class AnalysisInput:
    """What an analyzer receives. Text fields are treated as UNTRUSTED data."""

    headline: str
    body: str
    category: str = ""
    location_text: str = ""
    countries: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Structured, schema-stable enrichment for a story."""

    # Signal intensities in [0,1] feeding the relevance model (scoring.py keys)
    signals: dict[str, float] = field(default_factory=dict)

    # Narrative sections (story template)
    what_happened: str = ""
    verified_facts: list[str] = field(default_factory=list)
    claims_uncertainties: list[str] = field(default_factory=list)
    background: str = ""
    why_global: str = ""
    why_your_work: list[str] = field(default_factory=list)
    potentially_affected: dict[str, list[str]] = field(default_factory=dict)
    risk_pathway: list[str] = field(default_factory=list)
    indicators: list[dict[str, str]] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    actions: list[dict[str, str]] = field(default_factory=list)
    narratives: list[dict[str, str]] = field(default_factory=list)
    talking_points: list[str] = field(default_factory=list)

    # Velocity/trend hints the analyzer can express (scoring maps the rest)
    velocity: str = "Developing"
    trend: str = "Stable"
    likelihood: str = "Possible"

    provider: str = "heuristic"
    model: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AnalyzerProtocol(Protocol):
    name: str

    def analyze(self, item: AnalysisInput) -> AnalysisResult:  # pragma: no cover
        ...
