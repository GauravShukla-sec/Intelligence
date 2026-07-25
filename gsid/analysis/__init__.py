"""Analysis subsystem: provider-agnostic story enrichment.

`get_analyzer(config)` returns an object implementing `AnalyzerProtocol`.
The heuristic analyzer requires no API keys and is the default, so the whole
platform never depends on a single model or vendor.
"""

from __future__ import annotations

from .base import AnalysisResult, AnalyzerProtocol, AnalysisInput
from .registry import get_analyzer

__all__ = [
    "AnalysisResult",
    "AnalyzerProtocol",
    "AnalysisInput",
    "get_analyzer",
]
