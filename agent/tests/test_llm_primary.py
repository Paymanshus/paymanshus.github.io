"""Tests for the 2026-10-21 primary-model work: ladders, reasoning effort, the
voice hedge, canary health, warm-up, the prompt-size guard and cost accounting.

The behaviours that matter, each pinned by a test below:
  - OpenRouter calls go out with reasoning off unless a rung says otherwise
    (default-on reasoning truncated Haiku and slowed DeepSeek in the probe)
  - the hedge never makes a visitor wait longer: a fast primary is served alone,
    a slow one is raced against rung 2 after VOICE_HEDGE_AFTER_MS, and a dead
    one hands over to rung 2 at once
  - a degraded rung (canary failed or slow) is moved to the back of the voice
    ladder before a session is built on it
  - a voice session left running can't grow the prompt toward Haiku's 100k tier

Run: cd agent && .venv/bin/python -m pytest tests/test_llm_primary.py -q
"""

import asyncio
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from livekit.agents import APIConnectionError, APIConnectOptions
from livekit.agents import llm as lk_llm
from livekit.agents.llm import ChatChunk, ChoiceDelta, CompletionUsage

import llm_context
import llm_health
import llm_ladder
import llm_models
import llm_voice


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_ladder, "breaker", llm_ladder.Breaker(tmp_path / "brk.json"))
    monkeypatch.setattr(llm_health, "HEALTH_PATH", tmp_path / "health.json")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_ENABLED", raising=False)
    yield


# ─── Ladders and reasoning effort ───────────────────────────────────

async def test_openrouter_leads_and_gemini_direct_is_last():
    assert llm_models.VOICE_LADDER[0].label == "openrouter:deepseek/deepseek-v4.1-flash-1017"
    assert llm_models.VOICE_LADDER[1].label == "openrouter:anthropic/claude-haiku-5.5"
    assert llm_models.LLM_LADDER[0].label == "openrouter:anthropic/claude-haiku-5.5"
    for ladder in (llm_models.VOICE_LADDER, llm_models.LLM_LADDER):
        assert ladder[-1].provider == "gemini"
        assert all(e.provider == "openrouter" for e in ladder[:-1])


async def test_terminal_prefs_admit_unpublished_quantization():
    """Anthropic and Google endpoints report no quantization; without `unknown`
    the terminal allow-list silently filters out Haiku entirely."""
    assert "unknown" in llm_models.openrouter_provider_prefs("terminal")["quantizations"]


@pytest.mark.parametrize("spec, effort", [
    ("openrouter:x/y", None),
    ("openrouter:x/y#none", "none"),
    ("openrouter:x/y#LOW", "low"),
    ("openrouter:x/y|z/w@grp~4000#default", "default"),
])
async def test_parse_effort_suffix(spec, effort):
    e = llm_models.parse_entry(spec)
    assert e.reasoning == effort
    assert e.model == "x/y"


@pytest.mark.parametrize("spec", ["openrouter:x/y#turbo", "gemini:g#none"])
async def test_parse_effort_rejects_nonsense(spec):
    with pytest.raises(ValueError):
        llm_models.parse_entry(spec)


async def test_reasoning_defaults_per_surface():
    plain = llm_models.parse_entry("openrouter:x/y")
    assert llm_models.openrouter_reasoning(plain, "voice") == {"effort": "none"}
    assert llm_models.openrouter_reasoning(plain, "terminal") == {"effort": "none"}
    assert llm_models.openrouter_reasoning(plain, "sync") is None
    low = llm_models.parse_entry("openrouter:openai/gpt-oss-120b#low")
    assert llm_models.openrouter_reasoning(low, "voice") == {"effort": "low"}
    mandatory = llm_models.parse_entry("openrouter:x/y#default")
    assert llm_models.openrouter_reasoning(mandatory, "voice") is None


async def test_terminal_body_turns_reasoning_off():
    ctx = llm_context.BuiltContext(mode="full_hint", system="s", turns=[{"role": "user", "text": "q"}])
    body = llm_ladder._openrouter_body(
        llm_models.parse_entry("openrouter:anthropic/claude-haiku-5.5"), ctx,
        surface="terminal", max_tokens=200, temperature=0.6, stream=False, session_id=None,
    )
    assert body["reasoning"] == {"effort": "none"}


async def test_voice_plugin_turns_reasoning_off():
    inst = llm_voice._build_one(
        llm_models.parse_entry("openrouter:deepseek/deepseek-v4.1-flash-1017"),
        max_output_tokens=140, temperature=0.6,
    )
    assert inst._opts.extra_body["reasoning"] == {"effort": "none"}
    assert inst._opts.extra_body["provider"]["sort"] == "latency"


async def test_cost_estimate():
    usd = llm_models.estimate_llm_usd("anthropic/claude-haiku-5.5", 4000, 3900, 60)
    assert usd == pytest.approx((100 * 0.10 + 3900 * 0.01 + 60 * 0.50) / 1e6)
    assert llm_models.estimate_llm_usd("unknown/model", 10, 0, 10) is None


# ─── Fake LiveKit LLMs for the hedge ────────────────────────────────

class FakeStream(lk_llm.LLMStream):
    def __init__(self, llm, *, chat_ctx, tools, conn_options, script):
        super().__init__(llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._script = script

    async def _run(self) -> None:
        for step in self._script:
            if isinstance(step, (int, float)):
                await asyncio.sleep(step)
            elif isinstance(step, BaseException):
                raise step
            else:
                self._event_ch.send_nowait(step)


def chunk(text="", usage=None):
    return ChatChunk(id="c", delta=ChoiceDelta(role="assistant", content=text) if text else None,
                     usage=usage)


class FakeLLM(lk_llm.LLM):
    def __init__(self, name, script, *, raise_on_chat=None):
        super().__init__()
        self.name, self.script, self.raise_on_chat = name, script, raise_on_chat
        self.calls = 0
        self.seen_ctx = None

    @property
    def model(self):
        return self.name

    def chat(self, *, chat_ctx, tools=None, conn_options=APIConnectOptions(), **kwargs):
        self.calls += 1
        self.seen_ctx = chat_ctx
        if self.raise_on_chat:
            raise self.raise_on_chat
        return FakeStream(self, chat_ctx=chat_ctx, tools=tools or [],
                          conn_options=conn_options, script=self.script)


async def collect(llm):
    started = time.perf_counter()
    text, first = [], None
    async with llm.chat(chat_ctx=lk_llm.ChatContext.empty(),
                        conn_options=APIConnectOptions(max_retry=0)) as s:
        async for ch in s:
            if ch.delta and ch.delta.content:
                first = first or time.perf_counter() - started
                text.append(ch.delta.content)
    return "".join(text), first


def hedged(primary, backup, after=0.1, failures=None):
    return llm_voice.HedgedLLM(
        primary, backup, hedge_after_s=after,
        on_failure=(lambda llm, err: failures.append(llm.name)) if failures is not None else None,
    )


# ─── Hedge behaviour ────────────────────────────────────────────────

async def test_fast_primary_is_served_alone():
    p = FakeLLM("p", [0.01, chunk("hello "), chunk("there")])
    b = FakeLLM("b", [chunk("backup")])
    text, _ = await collect(hedged(p, b))
    assert text == "hello there"
    assert b.calls == 0, "no hedge before the deadline"


async def test_slow_primary_is_raced_and_backup_wins():
    p = FakeLLM("p", [1.0, chunk("late")])
    b = FakeLLM("b", [0.02, chunk("quick")])
    text, first = await collect(hedged(p, b, after=0.1))
    assert text == "quick"
    assert first < 0.5, "visitor gets the backup's answer, not the primary's 1 s"


async def test_primary_can_still_win_after_hedge_starts():
    p = FakeLLM("p", [0.15, chunk("primary")])
    b = FakeLLM("b", [0.5, chunk("backup")])
    text, _ = await collect(hedged(p, b, after=0.1))
    assert text == "primary"
    assert b.calls == 1


async def test_dead_primary_hands_over_immediately():
    failures = []
    p = FakeLLM("p", [APIConnectionError("boom")])
    b = FakeLLM("b", [chunk("backup")])
    text, first = await collect(hedged(p, b, after=5.0, failures=failures))
    assert text == "backup"
    assert first < 1.0, "no waiting out the hedge deadline when rung 1 is dead"
    assert failures == ["p"], "the breaker hears about the failed rung"


async def test_primary_ending_empty_counts_as_failure():
    p = FakeLLM("p", [chunk(usage=None)])
    b = FakeLLM("b", [chunk("backup")])
    text, _ = await collect(hedged(p, b, after=5.0))
    assert text == "backup"


async def test_both_failing_raises_for_the_fallback_adapter():
    p = FakeLLM("p", [APIConnectionError("p down")])
    b = FakeLLM("b", [APIConnectionError("b down")])
    with pytest.raises(APIConnectionError):
        await collect(hedged(p, b))


async def test_locked_primary_skips_to_backup_without_relocking():
    entry = llm_models.parse_entry("openrouter:p/model")
    llm_ladder.breaker.record_failure(entry, llm_ladder.LLMError(llm_ladder.KIND_DAY, "daily"))
    until = llm_ladder.breaker.locked_until(entry.key)
    failures = []
    guard = llm_voice.BreakerGuard(FakeLLM("p", [chunk("never")]), entry)
    b = FakeLLM("b", [chunk("backup")])
    text, _ = await collect(hedged(guard, b, after=5.0, failures=failures))
    assert text == "backup"
    assert failures == [], "a locked rung isn't re-reported (would shorten a daily lock)"
    assert llm_ladder.breaker.locked_until(entry.key) == until


async def test_hedge_records_usage_and_cost():
    usage = CompletionUsage(completion_tokens=40, prompt_tokens=2400,
                            prompt_cached_tokens=2304, total_tokens=2440)
    p = FakeLLM("deepseek/deepseek-v4.1-flash-1017", [chunk("hi"), chunk(usage=usage)])
    h = hedged(p, FakeLLM("b", []))
    await collect(h)
    totals = llm_voice.usage_summary(h)["deepseek/deepseek-v4.1-flash-1017"]
    assert totals["calls"] == 1
    assert totals["prompt_tokens"] == 2400 and totals["cached_tokens"] == 2304
    assert totals["est_usd"] == pytest.approx(llm_models.estimate_llm_usd(
        "deepseek/deepseek-v4.1-flash-1017", 2400, 2304, 40))


# ─── Prompt-size guard ──────────────────────────────────────────────

async def test_guard_caps_context_and_keeps_instructions(monkeypatch):
    monkeypatch.setattr(llm_models, "VOICE_MAX_CONTEXT_ITEMS", 10)
    ctx = lk_llm.ChatContext.empty()
    ctx.add_message(role="system", content="persona")
    for i in range(30):
        ctx.add_message(role="user" if i % 2 else "assistant", content=f"turn {i}")
    inner = FakeLLM("p", [chunk("ok")])
    guard = llm_voice.BreakerGuard(inner, llm_models.parse_entry("openrouter:p/model"))
    async with guard.chat(chat_ctx=ctx, conn_options=APIConnectOptions(max_retry=0)) as s:
        async for _ in s:
            pass
    sent = inner.seen_ctx.items
    assert len(sent) <= 11
    assert sent[0].role == "system" and sent[0].text_content == "persona"
    assert sent[-1].text_content == "turn 29"
    assert len(ctx.items) == 31, "the session's own context is untouched"


# ─── Health / canary ────────────────────────────────────────────────

DS = llm_models.parse_entry("openrouter:deepseek/deepseek-v4.1-flash-1017")
HK = llm_models.parse_entry("openrouter:anthropic/claude-haiku-5.5")
GM = llm_models.parse_entry("gemini:gemini-flash-lite-latest")


async def test_degraded_means_failed_or_slow_and_recent():
    now = 1000.0
    health = {
        DS.key: {"ok": False, "ms": None, "at": now - 10},
        HK.key: {"ok": True, "ms": llm_models.LLM_CANARY_SLOW_MS + 1, "at": now - 10},
        GM.key: {"ok": True, "ms": 400, "at": now - 10},
    }
    assert llm_health.is_degraded(DS, health, now)
    assert llm_health.is_degraded(HK, health, now)
    assert not llm_health.is_degraded(GM, health, now)
    stale = {DS.key: {"ok": False, "ms": None, "at": now - llm_models.LLM_HEALTH_TTL_S - 1}}
    assert not llm_health.is_degraded(DS, stale, now), "old results expire"


async def test_order_by_health_demotes_but_keeps_degraded_rungs():
    health = {DS.key: {"ok": False, "ms": None, "at": time.time()}}
    ordered = llm_health.order_by_health((DS, HK, GM), health)
    assert [e.label for e in ordered] == [HK.label, GM.label, DS.label]


async def test_canary_records_health_and_feeds_breaker(monkeypatch):
    async def fail(entry, **kw):
        raise llm_ladder.LLMError(llm_ladder.KIND_SERVER, "503")

    monkeypatch.setattr(llm_ladder, "ping_entry", fail)
    assert await llm_health.check(DS, "voice") is False
    assert llm_health.read_health()[DS.key]["ok"] is False
    assert llm_ladder.breaker.is_locked(DS.key)

    async def slow(entry, **kw):
        return llm_models.LLM_CANARY_SLOW_MS + 500

    monkeypatch.setattr(llm_ladder, "ping_entry", slow)
    assert await llm_health.check(HK, "voice") is False
    assert llm_health.is_degraded(HK, llm_health.read_health())
    assert not llm_ladder.breaker.is_locked(HK.key), "slow isn't broken: no breaker lock"


async def test_canary_targets_cover_voice_pair_and_terminal_head():
    keys = [e.key for e, _ in llm_health.canary_targets()]
    assert keys == [DS.key, HK.key], "terminal head (Haiku) is deduplicated"


async def test_scheduler_debounces(monkeypatch):
    runs = []

    async def fake_run(**kw):
        runs.append(1)
        return {}

    monkeypatch.setattr(llm_health, "run_canaries", fake_run)
    s = llm_health.CanaryScheduler(min_gap_s=60, interval_s=0)
    t = s.kick(now=100.0)
    await t
    assert s.kick(now=130.0) is None, "within min gap"
    await s.kick(now=161.0)
    assert len(runs) == 2


async def test_build_voice_llm_hedges_the_healthiest_pair(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    llm_health.record(DS, ok=False, ms=None, error="503")
    llm = llm_voice.build_voice_llm(max_output_tokens=140, warm=False)
    head = llm._llm_instances[0]
    assert isinstance(head, llm_voice.HedgedLLM)
    assert head._primary._entry.label == HK.label, "degraded DeepSeek no longer leads"
    assert head._hedge_after_s == pytest.approx(llm_models.VOICE_HEDGE_AFTER_MS / 1000)
    assert llm_voice.primary_guard(llm)._entry.label == HK.label


# ─── Warm-up ────────────────────────────────────────────────────────

class _Completions:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("upstream 503")
        return object()


class _Client:
    def __init__(self, fail=False):
        self.chat = type("C", (), {})()
        self.chat.completions = _Completions(fail)


class _Inner:
    def __init__(self, fail=False):
        self._client = _Client(fail)

    async def aclose(self):
        pass


async def test_warm_up_sends_one_token_with_voice_settings():
    inner = _Inner()
    guard = llm_voice.BreakerGuard(inner, DS)
    ms = await llm_voice.warm_up(guard)
    assert ms is not None
    call = inner._client.chat.completions.calls[0]
    assert call["max_tokens"] == 1
    assert call["extra_body"]["reasoning"] == {"effort": "none"}


async def test_failed_warm_up_marks_rung_degraded_for_next_sessions():
    guard = llm_voice.BreakerGuard(_Inner(fail=True), DS)
    assert await llm_voice.warm_up(guard) is None
    assert llm_health.is_degraded(DS, llm_health.read_health())


async def test_warm_up_skips_locked_rung():
    llm_ladder.breaker.record_failure(DS, llm_ladder.LLMError(llm_ladder.KIND_MINUTE, "rpm"))
    inner = _Inner()
    assert await llm_voice.warm_up(llm_voice.BreakerGuard(inner, DS)) is None
    assert inner._client.chat.completions.calls == []
