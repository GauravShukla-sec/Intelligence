"""Analyzer selection and OpenAI-compatible endpoint support.

The point of `base_url` is that a deployment with no budget can point at a free
OpenAI-compatible tier (Groq, OpenRouter, a local model) instead of falling back
to keyword heuristics.
"""

from __future__ import annotations

import sys
import types

from gsid.analysis.heuristic import HeuristicAnalyzer
from gsid.analysis.llm import OpenAIAnalyzer
from gsid.analysis.registry import get_analyzer
from gsid.config import Config


def test_base_url_flows_from_config_to_analyzer():
    cfg = Config(ai_provider="openai", openai_api_key="k", openai_model="m",
                 openai_base_url="https://api.groq.com/openai/v1")
    a = get_analyzer(cfg)
    assert isinstance(a, OpenAIAnalyzer)
    assert a.base_url == "https://api.groq.com/openai/v1"


def test_openai_remains_the_default_when_no_base_url_is_set():
    a = get_analyzer(Config(ai_provider="openai", openai_api_key="k"))
    assert isinstance(a, OpenAIAnalyzer) and a.base_url == ""


def test_missing_key_downgrades_to_heuristic_rather_than_failing():
    # A missing credential must never hard-fail the platform.
    assert isinstance(get_analyzer(Config(ai_provider="openai")), HeuristicAnalyzer)
    assert isinstance(get_analyzer(Config(ai_provider="anthropic")), HeuristicAnalyzer)


def test_default_provider_is_heuristic():
    assert isinstance(get_analyzer(Config()), HeuristicAnalyzer)


def _fake_openai(captured: dict, text: str = '{"summary": "ok"}'):
    """Minimal stand-in for the openai SDK, recording constructor kwargs."""
    mod = types.ModuleType("openai")

    class _Client:
        def __init__(self, **kw):
            captured.update(kw)
            msg = types.SimpleNamespace(content=text)
            choice = types.SimpleNamespace(message=msg)
            resp = types.SimpleNamespace(choices=[choice])
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=lambda **_: resp))

    mod.OpenAI = _Client
    return mod


def test_base_url_is_passed_to_the_sdk_when_set(monkeypatch, sample_input):
    captured: dict = {}
    monkeypatch.setitem(sys.modules, "openai", _fake_openai(captured))
    OpenAIAnalyzer("k", "llama-3.3-70b", "https://api.groq.com/openai/v1").analyze(sample_input)
    assert captured["base_url"] == "https://api.groq.com/openai/v1"
    assert captured["api_key"] == "k"


def test_base_url_is_omitted_when_empty(monkeypatch, sample_input):
    """Passing base_url="" would break the SDK's own default endpoint."""
    captured: dict = {}
    monkeypatch.setitem(sys.modules, "openai", _fake_openai(captured))
    OpenAIAnalyzer("k", "gpt-4o-mini").analyze(sample_input)
    assert "base_url" not in captured


def test_provider_failure_falls_back_to_heuristic(monkeypatch, sample_input):
    """Free tiers rate-limit; a refused call must degrade, not crash."""
    broken = types.ModuleType("openai")

    def _boom(**kw):
        raise RuntimeError("429 rate limit exceeded")
    broken.OpenAI = _boom
    monkeypatch.setitem(sys.modules, "openai", broken)

    res = OpenAIAnalyzer("k", "m", "https://api.groq.com/openai/v1").analyze(sample_input)
    assert res is not None
    assert "heuristic" in (res.notes or "").lower()


def test_fallback_is_logged_once_not_per_story(monkeypatch, caplog, sample_input):
    """A misconfigured provider must be visible, but not 200 log lines deep.

    Without a warning, a wrong model name or rejected key looks exactly like
    never having configured a provider at all.
    """
    broken = types.ModuleType("openai")

    def _boom(**kw):
        raise RuntimeError("model_not_found: no such model")
    broken.OpenAI = _boom
    monkeypatch.setitem(sys.modules, "openai", broken)

    analyzer = OpenAIAnalyzer("k", "does-not-exist", "https://api.groq.com/openai/v1")
    with caplog.at_level("WARNING", logger="gsid.analysis"):
        for _ in range(5):
            analyzer.analyze(sample_input)

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1                      # once per run, not per story
    msg = warnings[0].getMessage()
    assert "model_not_found" in msg                # the actual cause
    assert "groq.com" in msg                       # and which endpoint
