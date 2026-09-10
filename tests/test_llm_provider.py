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
    """A refused call must degrade, not crash."""
    broken = types.ModuleType("openai")

    def _boom(**kw):
        raise RuntimeError("400 bad request")
    broken.OpenAI = _boom
    monkeypatch.setitem(sys.modules, "openai", broken)

    res = OpenAIAnalyzer("k", "m", "https://api.groq.com/openai/v1").analyze(sample_input)
    assert res is not None
    assert "heuristic" in (res.notes or "").lower()


# ---- rate limiting: wait and resend, don't discard the story ---------------

def _rate_limited_then(results, captured_sleeps):
    """openai stand-in that raises 429 until `results` yields a success."""
    mod = types.ModuleType("openai")
    state = {"calls": 0}

    class _Client:
        def __init__(self, **kw):
            state["calls"] += 1
            if state["calls"] <= results:
                raise RuntimeError("Error code: 429 - rate limit reached")
            msg = types.SimpleNamespace(content='{"what_happened": "model output"}')
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(
                create=lambda **_: types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=msg)])))

    mod.OpenAI = _Client
    return mod, state


def test_rate_limit_is_waited_out_and_the_story_succeeds(monkeypatch, sample_input):
    """The whole point of B: a 429 costs time, not the story."""
    sleeps: list[float] = []
    monkeypatch.setattr("gsid.analysis.llm.time.sleep", lambda s: sleeps.append(s))
    mod, state = _rate_limited_then(2, sleeps)
    monkeypatch.setitem(sys.modules, "openai", mod)

    res = OpenAIAnalyzer("k", "m", "https://api.groq.com/openai/v1").analyze(sample_input)

    assert res.provider == "openai"          # not a heuristic fallback
    assert state["calls"] == 3               # two refusals, then success
    assert len(sleeps) == 2 and all(s > 0 for s in sleeps)


def test_backoff_grows_between_attempts(monkeypatch, sample_input):
    sleeps: list[float] = []
    monkeypatch.setattr("gsid.analysis.llm.time.sleep", lambda s: sleeps.append(s))
    mod, _ = _rate_limited_then(3, sleeps)
    monkeypatch.setitem(sys.modules, "openai", mod)
    OpenAIAnalyzer("k", "m", "https://api.groq.com/openai/v1").analyze(sample_input)
    assert sleeps == sorted(sleeps) and sleeps[-1] > sleeps[0]


def test_rate_limit_eventually_gives_up_and_falls_back(monkeypatch, sample_input):
    sleeps: list[float] = []
    monkeypatch.setattr("gsid.analysis.llm.time.sleep", lambda s: sleeps.append(s))
    mod, state = _rate_limited_then(99, sleeps)      # never recovers
    monkeypatch.setitem(sys.modules, "openai", mod)

    a = OpenAIAnalyzer("k", "m", "https://api.groq.com/openai/v1", rate_limit_retries=3)
    res = a.analyze(sample_input)

    assert "heuristic" in (res.notes or "").lower()
    assert state["calls"] == 4                       # initial + 3 retries
    assert len(sleeps) == 3                          # bounded, not infinite


def test_non_rate_limit_errors_are_not_retried(monkeypatch, sample_input):
    """Retrying a bad model name would only burn the clock."""
    sleeps: list[float] = []
    monkeypatch.setattr("gsid.analysis.llm.time.sleep", lambda s: sleeps.append(s))
    broken = types.ModuleType("openai")
    state = {"calls": 0}

    def _boom(**kw):
        state["calls"] += 1
        raise RuntimeError("model_not_found: no such model")
    broken.OpenAI = _boom
    monkeypatch.setitem(sys.modules, "openai", broken)

    OpenAIAnalyzer("k", "nope", "https://api.groq.com/openai/v1").analyze(sample_input)

    assert state["calls"] == 1 and sleeps == []


def test_server_suggested_wait_is_honoured(monkeypatch, sample_input):
    """A hint LONGER than our backoff floor is obeyed exactly."""
    sleeps: list[float] = []
    monkeypatch.setattr("gsid.analysis.llm.time.sleep", lambda s: sleeps.append(s))
    mod = types.ModuleType("openai")
    state = {"calls": 0}

    class _Client:
        def __init__(self, **kw):
            state["calls"] += 1
            if state["calls"] == 1:
                exc = RuntimeError("429 too many requests")
                exc.response = types.SimpleNamespace(headers={"retry-after": "45"})
                raise exc
            msg = types.SimpleNamespace(content='{"what_happened": "ok"}')
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(
                create=lambda **_: types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=msg)])))

    mod.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", mod)

    OpenAIAnalyzer("k", "m", "https://api.groq.com/openai/v1").analyze(sample_input)
    assert sleeps == [45.0]


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


# ---- duration parsing: Groq sends Go-style durations, not bare seconds -----

import pytest
from gsid.analysis.llm import _parse_duration, RATE_LIMIT_MAX_WAIT


@pytest.mark.parametrize("raw,expected", [
    ("33.787s", 33.787),      # seconds
    ("577ms", 0.577),         # milliseconds — the case that broke
    ("8m38.4s", 518.4),       # minutes + seconds
    ("36m0s", 2160.0),
    ("1h2m3s", 3723.0),
    ("30", 30.0),             # bare HTTP retry-after
    ("", None),
    (None, None),
    ("garbage", None),
])
def test_duration_formats_all_parse(raw, expected):
    got = _parse_duration(raw)
    if expected is None:
        assert got is None
    else:
        assert got == pytest.approx(expected)


def test_short_token_window_is_waited_not_capped(monkeypatch, sample_input):
    """A sub-second reset must not become a 90s stall (the original bug)."""
    sleeps: list[float] = []
    monkeypatch.setattr("gsid.analysis.llm.time.sleep", lambda s: sleeps.append(s))
    mod = types.ModuleType("openai")
    state = {"calls": 0}

    class _Client:
        def __init__(self, **kw):
            state["calls"] += 1
            if state["calls"] == 1:
                exc = RuntimeError("429 rate limit")
                exc.response = types.SimpleNamespace(
                    headers={"x-ratelimit-reset-tokens": "577ms",
                             "x-ratelimit-reset-requests": "36m0s"})
                raise exc
            msg = types.SimpleNamespace(content='{"what_happened": "ok"}')
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(
                create=lambda **_: types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=msg)])))

    mod.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", mod)

    res = OpenAIAnalyzer("k", "m", "https://api.groq.com/openai/v1").analyze(sample_input)

    assert res.provider == "openai"
    # The 36-minute request window is ignored, and the sub-second token hint is
    # raised to the backoff floor: too short a wait cannot refill the bucket.
    assert len(sleeps) == 1
    assert 0.577 < sleeps[0] <= RATE_LIMIT_MAX_WAIT


def test_long_wait_stops_instead_of_stalling(monkeypatch, sample_input):
    """An hourly/daily quota must end the run, not sleep through it."""
    sleeps: list[float] = []
    monkeypatch.setattr("gsid.analysis.llm.time.sleep", lambda s: sleeps.append(s))
    mod = types.ModuleType("openai")

    class _Client:
        def __init__(self, **kw):
            exc = RuntimeError("429 rate limit")
            exc.response = types.SimpleNamespace(
                headers={"x-ratelimit-reset-tokens": "36m0s"})
            raise exc

    mod.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", mod)

    a = OpenAIAnalyzer("k", "m", "https://api.groq.com/openai/v1")
    res = a.analyze(sample_input)

    assert a.quota_exhausted is True
    assert sleeps == []                      # no stalling
    assert "quota exhausted" in (res.notes or "").lower()


def test_waits_are_capped(monkeypatch, sample_input):
    """Without a server hint, backoff must never exceed the cap."""
    sleeps: list[float] = []
    monkeypatch.setattr("gsid.analysis.llm.time.sleep", lambda s: sleeps.append(s))
    mod, _ = _rate_limited_then(99, sleeps)
    monkeypatch.setitem(sys.modules, "openai", mod)
    OpenAIAnalyzer("k", "m", "https://api.groq.com/openai/v1",
                   rate_limit_retries=20).analyze(sample_input)
    assert max(sleeps) <= RATE_LIMIT_MAX_WAIT
