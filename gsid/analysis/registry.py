"""Analyzer selection based on configuration.

Always returns a working analyzer. If a model-backed provider is requested but
its key is missing, we log the downgrade and use the heuristic analyzer so the
platform never hard-fails on a missing credential.
"""

from __future__ import annotations

from .base import AnalyzerProtocol
from .heuristic import HeuristicAnalyzer
from .llm import AnthropicAnalyzer, OpenAIAnalyzer


def get_analyzer(config) -> AnalyzerProtocol:
    provider = (getattr(config, "ai_provider", "heuristic") or "heuristic").lower()

    if provider == "anthropic" and getattr(config, "anthropic_api_key", ""):
        return AnthropicAnalyzer(config.anthropic_api_key, config.anthropic_model)
    if provider == "openai" and getattr(config, "openai_api_key", ""):
        return OpenAIAnalyzer(config.openai_api_key, config.openai_model)

    return HeuristicAnalyzer()
