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

class _FakeResponse:
    text = "hello from fake model"
    usage_metadata = None


def _fake_client(fail_models=()):
    calls = []

    class _Models:
        async def generate_content(self, *, model, contents, config):
            calls.append(model)
            if model in fail_models:
                raise RuntimeError("503 capacity")
            return _FakeResponse()

    class _Aio:
        models = _Models()

    class _Client:
        aio = _Aio()

    return _Client(), calls


async def test_generate_reply_without_langfuse(monkeypatch):
    client, calls = _fake_client()
    monkeypatch.setattr(token_server, "_get_genai_client", lambda: client)
    reply, model = await token_server._generate_reply(
        ["model-a", "model-b"], [{"role": "user", "parts": [{"text": "hi"}]}], "sys"
    )
    assert reply == "hello from fake model"
    assert model == "model-a"
    assert calls == ["model-a"]


async def test_generate_reply_falls_back_on_error(monkeypatch):
    client, calls = _fake_client(fail_models={"model-a"})
    monkeypatch.setattr(token_server, "_get_genai_client", lambda: client)
    reply, model = await token_server._generate_reply(
        ["model-a", "model-a", "model-b"], [], "sys"
    )
    assert reply == "hello from fake model"
    assert model == "model-b"
    # dict.fromkeys dedupes the chain: model-a tried once, then model-b
    assert calls == ["model-a", "model-b"]


async def test_generate_reply_all_fail(monkeypatch):
    client, _ = _fake_client(fail_models={"model-a", "model-b"})
    monkeypatch.setattr(token_server, "_get_genai_client", lambda: client)
    reply, model = await token_server._generate_reply(["model-a", "model-b"], [], "sys")
    assert reply == ""
    assert model is None


async def test_visitor_id_pseudonymous():
    a = token_server._visitor_id("203.0.113.7")
    b = token_server._visitor_id("203.0.113.7")
    c = token_server._visitor_id("203.0.113.8")
    assert a == b != c
    assert a.startswith("visitor-")
    assert "203" not in a
