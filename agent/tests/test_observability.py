"""Tests for observability.py — env-gating, cost estimates, and that the
chat generation pipeline is unaffected when Langfuse is disabled.

Run: cd agent && .venv/bin/python -m pytest tests/test_observability.py -q
"""

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

import observability
import token_server
import llm_context
import llm_ladder
import llm_models


@pytest.fixture(autouse=True)
def reset_observability(monkeypatch):
    """No Langfuse keys and fresh singleton state for every test."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    observability._client = None
    observability._client_failed = False
    yield
    observability._client = None
    observability._client_failed = False


@pytest.fixture(autouse=True)
def reset_breaker():
    """The breaker is process-global by design, so it must be reset between
    tests or a lock from one leaks into the next."""
    llm_ladder.breaker.clear()
    yield
    llm_ladder.breaker.clear()


# ─── Env gating ─────────────────────────────────────────────────────

async def test_disabled_without_keys():
    assert observability.langfuse_enabled() is False
    assert observability.get_langfuse() is None
    assert observability.peek_langfuse() is None
    assert observability.setup_voice_tracing("room-x") is None


async def test_enabled_flag_with_keys(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    assert observability.langfuse_enabled() is True


async def test_trace_attributes_is_always_a_context_manager():
    # Works (as a no-op) even when Langfuse is disabled/unconfigured.
    with observability.trace_attributes(session_id="s", tags=["t"]):
        pass


async def test_shutdown_never_creates_a_client():
    observability.shutdown()
    assert observability.peek_langfuse() is None


# ─── Cost estimates ─────────────────────────────────────────────────

async def test_estimate_costs_defaults():
    costs = observability.estimate_session_costs(
        llm_prompt_tokens=1_000_000,
        llm_completion_tokens=1_000_000,
        stt_audio_duration=60.0,
        tts_characters_count=1000,
    )
    assert costs["llm_usd"] == pytest.approx(0.30 + 2.50)
    assert costs["stt_usd"] == pytest.approx(0.0077)
    assert costs["tts_usd"] == pytest.approx(0.03)
    assert costs["total_usd"] == pytest.approx(2.8377)


async def test_estimate_costs_env_override(monkeypatch):
    monkeypatch.setenv("COST_TTS_PER_1K_CHARS", "0.05")
    costs = observability.estimate_session_costs(tts_characters_count=2000)
    assert costs["tts_usd"] == pytest.approx(0.10)
    assert costs["llm_usd"] == 0.0


# ─── Chat pipeline without Langfuse ─────────────────────────────────
# _generate_reply now delegates model choice and fallback to llm_ladder, so these
# fake the ladder's single call site rather than the Gemini client. The
# behaviours asserted are unchanged: first entry wins, failures fall through,
# exhaustion returns ("", None) → 503 llm_unavailable.

TEST_LADDER = (
    llm_models.parse_entry("gemini:model-a"),
    llm_models.parse_entry("gemini:model-b"),
)


def _ctx(text="hi"):
    return llm_context.BuiltContext(
        mode="full_hint", system="sys", turns=[{"role": "user", "text": text}]
    )


def _fake_ladder(monkeypatch, fail_models=()):
    """Patch llm_ladder.call_entry and return the list of models actually hit."""
    calls = []

    async def call_entry(entry, ctx, **kwargs):
        calls.append(entry.model)
        if entry.model in fail_models:
            raise llm_ladder.LLMError(llm_ladder.KIND_SERVER, "503 capacity")
        return llm_ladder.LLMResult(
            text="hello from fake model",
            entry_label=entry.label,
            resolved_model=entry.model,
            prompt_tokens=10,
            completion_tokens=5,
        )

    monkeypatch.setattr(llm_ladder, "call_entry", call_entry)
    monkeypatch.setattr(llm_models, "LLM_LADDER", TEST_LADDER)
    return calls


async def test_generate_reply_without_langfuse(monkeypatch):
    calls = _fake_ladder(monkeypatch)
    reply, model = await token_server._generate_reply(_ctx())
    assert reply == "hello from fake model"
    assert model == "model-a"
    assert calls == ["model-a"], "a healthy first entry must not touch the rest"


async def test_generate_reply_falls_back_on_error(monkeypatch):
    calls = _fake_ladder(monkeypatch, fail_models={"model-a"})
    reply, model = await token_server._generate_reply(_ctx())
    assert reply == "hello from fake model"
    assert model == "model-b"
    assert calls == ["model-a", "model-b"]


async def test_generate_reply_skips_locked_entry(monkeypatch):
    """The spike behaviour: once model-a has failed, the NEXT request must not
    pay a network call to rediscover it."""
    calls = _fake_ladder(monkeypatch, fail_models={"model-a"})
    await token_server._generate_reply(_ctx())
    calls.clear()
    reply, model = await token_server._generate_reply(_ctx())
    assert reply == "hello from fake model"
    assert calls == ["model-b"], "model-a is locked and must be skipped entirely"


async def test_generate_reply_all_fail(monkeypatch):
    _fake_ladder(monkeypatch, fail_models={"model-a", "model-b"})
    reply, model = await token_server._generate_reply(_ctx())
    assert reply == ""
    assert model is None


async def test_visitor_id_pseudonymous():
    a = token_server._visitor_id("203.0.113.7")
    b = token_server._visitor_id("203.0.113.7")
    c = token_server._visitor_id("203.0.113.8")
    assert a == b != c
    assert a.startswith("visitor-")
    assert "203" not in a
