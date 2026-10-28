"""Tests for the LLM ladder, the shared quota breaker, and prompt layout.

The behaviours that matter most here are the spike behaviours, because they are
the ones that only show up under load and are impossible to eyeball:

  - a locked entry is skipped with ZERO network calls (so 50 concurrent visitors
    don't each rediscover the same 429)
  - a per-day lock survives a process restart (the deployment runs
    Restart=always, so an in-memory-only daily lock would evaporate on a crash
    loop and re-hit an exhausted quota)
  - an ambiguous 429 is treated as per-minute, never per-day

Run: cd agent && .venv/bin/python -m pytest tests/test_llm_ladder.py -q
"""

import sys
import time
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

import llm_models
import llm_context
import llm_ladder
from prompts import TERMINAL_PERSONA_BODY
from resume_context import get_resume_index


LADDER = (
    llm_models.parse_entry("gemini:model-a"),
    llm_models.parse_entry("openrouter:free-x:free|paid/y"),
    llm_models.parse_entry("gemini:model-b"),
)


@pytest.fixture(autouse=True)
def isolated_breaker(tmp_path, monkeypatch):
    """A fresh breaker per test, with its persistence file in tmp.

    The breaker is process-global by design, so without this a lock from one
    test leaks into the next.
    """
    monkeypatch.setattr(llm_ladder, "breaker", llm_ladder.Breaker(tmp_path / "brk.json"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_ENABLED", raising=False)
    yield


def ctx(text="hi"):
    return llm_context.BuiltContext(
        mode="full_hint", system="sys", turns=[{"role": "user", "text": text}]
    )


def fake_calls(monkeypatch, failures=None):
    """Patch call_entry; return the list of entry labels actually called.

    `failures` maps entry label → LLMError (or a callable returning one), so a
    test can make a specific rung fail without touching the network.
    """
    failures = failures or {}
    calls = []

    async def call_entry(entry, _ctx, **kwargs):
        calls.append(entry.label)
        err = failures.get(entry.label)
        if err is not None:
            raise err() if callable(err) else err
        return llm_ladder.LLMResult(
            text="ok", entry_label=entry.label, resolved_model=entry.model
        )

    monkeypatch.setattr(llm_ladder, "call_entry", call_entry)
    return calls


# ─── Ladder walk ────────────────────────────────────────────────────

async def test_first_entry_wins_and_rest_untouched(monkeypatch):
    calls = fake_calls(monkeypatch)
    result = await llm_ladder.generate(ctx(), ladder=LADDER)
    assert result.entry_label == "gemini:model-a"
    assert calls == ["gemini:model-a"]


async def test_falls_through_to_next_entry(monkeypatch):
    calls = fake_calls(monkeypatch, {
        "gemini:model-a": llm_ladder.LLMError(llm_ladder.KIND_MINUTE, "rpm"),
    })
    result = await llm_ladder.generate(ctx(), ladder=LADDER)
    assert result.entry_label == "openrouter:free-x:free"
    # model-b must NOT be touched — the second rung answered.
    assert calls == ["gemini:model-a", "openrouter:free-x:free"]


async def test_locked_entry_becomes_starter_shift(monkeypatch):
    """The spike fix: after entry 1 is locked, entry 2 becomes the starter and
    entry 3 stays last — with no network call to entry 1."""
    calls = fake_calls(monkeypatch, {
        "gemini:model-a": llm_ladder.LLMError(llm_ladder.KIND_MINUTE, "rpm"),
    })
    await llm_ladder.generate(ctx(), ladder=LADDER)
    calls.clear()

    result = await llm_ladder.generate(ctx(), ladder=LADDER)
    assert calls == ["openrouter:free-x:free"], "locked entry must cost zero calls"
    assert result.entry_label == "openrouter:free-x:free"


async def test_exhaustion_returns_none(monkeypatch):
    fake_calls(monkeypatch, {
        e.label: llm_ladder.LLMError(llm_ladder.KIND_SERVER, "boom") for e in LADDER
    })
    assert await llm_ladder.generate(ctx(), ladder=LADDER) is None


async def test_unconfigured_openrouter_is_skipped_not_locked(monkeypatch):
    """An unset key is 'not available', not 'broken'. If it were treated as a
    failure the entry would be locked for 24h as insufficient_credits."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    calls = fake_calls(monkeypatch, {
        "gemini:model-a": llm_ladder.LLMError(llm_ladder.KIND_SERVER, "boom"),
    })
    result = await llm_ladder.generate(ctx(), ladder=LADDER)
    assert calls == ["gemini:model-a", "gemini:model-b"]
    assert result.entry_label == "gemini:model-b"
    assert not llm_ladder.breaker.is_locked("openrouter:free-x:free")


async def test_on_attempt_sees_every_rung(monkeypatch):
    fake_calls(monkeypatch, {
        "gemini:model-a": llm_ladder.LLMError(llm_ladder.KIND_SERVER, "boom"),
    })
    seen = []
    await llm_ladder.generate(
        ctx(), ladder=LADDER,
        on_attempt=lambda entry, outcome: seen.append(
            (entry.label, isinstance(outcome, llm_ladder.LLMError))
        ),
    )
    assert seen == [("gemini:model-a", True), ("openrouter:free-x:free", False)]


# ─── Breaker scoping ────────────────────────────────────────────────

async def test_minute_lock_expires_at_minute_boundary(monkeypatch):
    entry = LADDER[0]
    llm_ladder.breaker.record_failure(entry, llm_ladder.LLMError(llm_ladder.KIND_MINUTE, "rpm"))
    until = llm_ladder.breaker.locked_until(entry.key)
    assert until is not None
    assert until <= time.time() + 60, "a per-minute lock must not exceed one minute"


async def test_day_lock_uses_provider_specific_reset():
    """Gemini free tier resets at Pacific midnight, OpenRouter at UTC midnight.
    Conflating them would unlock hours early or late."""
    now = time.time()
    gem = llm_ladder._daily_reset_for("gemini", now)
    orr = llm_ladder._daily_reset_for("openrouter", now)
    assert gem > now and orr > now
    assert abs(gem - orr) > 3600, "the two resets should be genuinely different instants"


async def test_ambiguous_429_is_treated_as_minute():
    """Wrongly locking an entry for a whole day is much worse than retrying in
    60s, so anything unclear must degrade to the per-minute scope."""
    err = llm_ladder._classify_openrouter(429, {"error": {"message": "Rate limit"}}, {})
    assert err.kind == llm_ladder.KIND_MINUTE

    err = llm_ladder._classify_gemini(Exception("429 Too Many Requests"))
    assert err.kind == llm_ladder.KIND_MINUTE


@pytest.mark.parametrize("message,expected", [
    ("429 quota GenerateRequestsPerDayPerProjectPerModel exceeded", llm_ladder.KIND_DAY),
    ("429 quota GenerateRequestsPerMinutePerProjectPerModel", llm_ladder.KIND_MINUTE),
    ("429 exceeded, 'retryDelay': '3600s'", llm_ladder.KIND_DAY),
    ("429 exceeded, 'retryDelay': '41s'", llm_ladder.KIND_MINUTE),
    ("404 models/gemini-9 is not found", llm_ladder.KIND_NOT_FOUND),
    ("503 Service Unavailable", llm_ladder.KIND_SERVER),
    ("403 API key not valid", llm_ladder.KIND_CREDITS),
])
async def test_gemini_classification(message, expected):
    assert llm_ladder._classify_gemini(Exception(message)).kind == expected


@pytest.mark.parametrize("status,expected", [
    (402, llm_ladder.KIND_CREDITS),
    (404, llm_ladder.KIND_NOT_FOUND),
    (503, llm_ladder.KIND_SERVER),
    (401, llm_ladder.KIND_CREDITS),
])
async def test_openrouter_classification(status, expected):
    err = llm_ladder._classify_openrouter(status, {"error": {"message": "x"}}, {})
    assert err.kind == expected


async def test_provisioning_key_401_names_the_cause():
    """A provisioning key in OPENROUTER_API_KEY 401s as 'User not found'.

    Verified against the live API: provisioning keys manage runtime keys and
    cannot do inference. The raw message is useless for diagnosis, so the
    classifier has to say what it actually means.
    """
    err = llm_ladder._classify_openrouter(
        401, {"error": {"message": "User not found.", "code": 401}}, {}
    )
    assert err.kind == llm_ladder.KIND_CREDITS  # terminal + loud, never retried
    assert "PROVISIONING" in err.message
    assert llm_ladder.KIND_CREDITS in llm_ladder.LOUD_KINDS


async def test_openrouter_reset_header_picks_day_vs_minute():
    now = time.time()
    soon = llm_ladder._classify_openrouter(
        429, {}, {"X-RateLimit-Reset": str(int((now + 30) * 1000))}
    )
    far = llm_ladder._classify_openrouter(
        429, {}, {"X-RateLimit-Reset": str(int((now + 21600) * 1000))}
    )
    assert soon.kind == llm_ladder.KIND_MINUTE
    assert far.kind == llm_ladder.KIND_DAY


async def test_quota_group_locks_every_member(tmp_path, monkeypatch):
    """If Gemini free-tier limits turn out to be a shared pool (see
    tests/probe_llm.py --quota-probe), tagging entries into a group must make one
    429 lock all of them."""
    monkeypatch.setattr(llm_ladder, "breaker", llm_ladder.Breaker(tmp_path / "b.json"))
    a = llm_models.parse_entry("gemini:model-a@google-free")
    b = llm_models.parse_entry("gemini:model-b@google-free")
    llm_ladder.breaker.record_failure(a, llm_ladder.LLMError(llm_ladder.KIND_MINUTE, "rpm"))
    assert llm_ladder.breaker.is_locked(b.key)


async def test_ungrouped_entries_lock_independently(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_ladder, "breaker", llm_ladder.Breaker(tmp_path / "b.json"))
    a, b = LADDER[0], LADDER[2]
    llm_ladder.breaker.record_failure(a, llm_ladder.LLMError(llm_ladder.KIND_MINUTE, "rpm"))
    assert not llm_ladder.breaker.is_locked(b.key)


async def test_unclassified_error_does_not_lock(tmp_path, monkeypatch):
    """An unknown one-off shouldn't take an entry out of rotation."""
    monkeypatch.setattr(llm_ladder, "breaker", llm_ladder.Breaker(tmp_path / "b.json"))
    entry = LADDER[0]
    llm_ladder.breaker.record_failure(entry, llm_ladder.LLMError(llm_ladder.KIND_OTHER, "?"))
    assert not llm_ladder.breaker.is_locked(entry.key)


# ─── Persistence across restart ─────────────────────────────────────

async def test_day_lock_survives_restart(tmp_path):
    """Restart=always means a crash loop would otherwise clear a daily lockout
    and send us straight back at an exhausted quota."""
    path = tmp_path / "brk.json"
    entry = LADDER[0]

    b1 = llm_ladder.Breaker(path)
    b1.record_failure(entry, llm_ladder.LLMError(llm_ladder.KIND_DAY, "rpd"))
    assert path.exists()

    b2 = llm_ladder.Breaker(path)  # simulated restart
    assert b2.is_locked(entry.key)


async def test_minute_lock_does_not_survive_restart(tmp_path):
    """Short locks are cheap to rediscover, and persisting them would keep an
    entry down longer than the upstream window actually lasts."""
    path = tmp_path / "brk.json"
    entry = LADDER[0]

    b1 = llm_ladder.Breaker(path)
    b1.record_failure(entry, llm_ladder.LLMError(llm_ladder.KIND_MINUTE, "rpm"))

    b2 = llm_ladder.Breaker(path)
    assert not b2.is_locked(entry.key)


async def test_expired_locks_are_dropped_on_load(tmp_path):
    path = tmp_path / "brk.json"
    path.write_text(json.dumps({
        "gemini:model-a": {"until": time.time() - 10, "kind": "rate_limit_day", "reason": "old"},
    }))
    assert not llm_ladder.Breaker(path).is_locked("gemini:model-a")


async def test_corrupt_state_file_is_survivable(tmp_path):
    """Losing persistence must degrade recovery, never break startup."""
    path = tmp_path / "brk.json"
    path.write_text("{not json")
    assert llm_ladder.Breaker(path).snapshot() == {}


# ─── Prompt layout / cacheability ───────────────────────────────────

def build(question, mode, history=None):
    return llm_context.build(
        question, history or [],
        persona_body=TERMINAL_PERSONA_BODY,
        index=get_resume_index(),
        mode=mode,
    )


@pytest.mark.parametrize("mode", llm_context.MODES)
async def test_every_mode_builds_a_well_formed_request(mode):
    c = build("What did you do at Maersk?", mode)
    messages = llm_context.to_openai_messages(c)
    assert messages[0]["role"] == "system" and messages[0]["content"]
    assert messages[-1]["role"] == "user"
    assert all(m["content"] for m in messages)

    system, contents = llm_context.to_gemini_contents(c)
    assert system == c.system
    assert contents[-1]["role"] == "user"
    assert set(x["role"] for x in contents) <= {"user", "model"}


async def test_cacheable_modes_have_identical_prefix_across_questions():
    """THE cacheability assertion. A provider can only reuse a prefix that is
    byte-identical, so this is the property caching actually depends on — more
    direct than a cached_tokens count, which can be zero for other reasons."""
    for mode in ("full_hint", "full_only"):
        a = build("What did you do at Maersk?", mode)
        b = build("Tell me about your research work.", mode)
        assert a.system_sha256 == b.system_sha256, f"{mode} prefix must not vary"
        assert a.likely_cacheable


async def test_bm25_system_mode_prefix_varies():
    """The original layout, kept as the control arm. Its prefix changes with the
    question, which is exactly why it could never cache."""
    a = build("What did you do at Maersk?", "bm25_system")
    b = build("Tell me about your research work.", "bm25_system")
    assert a.system_sha256 != b.system_sha256
    assert not a.prefix_stable


async def test_history_growth_does_not_disturb_the_prefix():
    """History must sit AFTER the system message; if it leaked into the prefix,
    caching would break on turn 2 of every conversation."""
    first = build("What did you do at Maersk?", "full_hint")
    later = build(
        "And which tools did you use?", "full_hint",
        history=[
            {"role": "user", "text": "What did you do at Maersk?"},
            {"role": "system", "text": "I built agentic AI systems."},
        ],
    )
    assert first.system_sha256 == later.system_sha256
    assert len(llm_context.to_openai_messages(later)) == 4


async def test_knowledge_goes_in_the_user_turn_not_the_prefix():
    """A blog/project snippet varies per question, so it must never touch the
    cacheable system prefix."""
    from resume_context import knowledge_block
    plain = build("what is keypsake?", "full_hint")
    c = llm_context.build(
        "what is keypsake?", [], persona_body=TERMINAL_PERSONA_BODY,
        index=get_resume_index(), mode="full_hint", knowledge=knowledge_block,
    )
    assert c.system_sha256 == plain.system_sha256
    assert "keypsake" in c.turns[-1]["text"].split("Question:", 1)[1]
    assert c.turns[-1]["text"].startswith(plain.turns[-1]["text"])


async def test_no_match_does_not_repeat_the_resume_in_the_user_turn():
    c = build("are you happy?", "full_hint")
    assert c.bm25_score == 0.0
    assert c.turns[-1]["text"] == "are you happy?"


async def test_bm25_still_runs_in_hint_mode():
    """BM25 must stay exercised — it's kept deliberately for later scaling work,
    not just as legacy."""
    c = build("What did you do at Maersk?", "full_hint")
    assert c.bm25_chars > 0
    assert c.bm25_score > 0
    assert "Most relevant resume sections" in c.turns[-1]["text"]


async def test_frontend_system_role_maps_to_assistant():
    """The terminal sends assistant turns with role 'system'; mis-mapping that
    would make the model think it said what the visitor said."""
    c = build("next question", "full_only", history=[
        {"role": "user", "text": "hello"},
        {"role": "system", "text": "Hi, I'm Paymanshu."},
    ])
    assert [t["role"] for t in c.turns] == ["user", "assistant", "user"]
    _, contents = llm_context.to_gemini_contents(c)
    assert [x["role"] for x in contents] == ["user", "model", "user"]


async def test_unknown_mode_falls_back(monkeypatch):
    monkeypatch.setenv("LLM_CONTEXT_MODE", "not-a-mode")
    assert llm_context.active_mode() == llm_context.DEFAULT_MODE


# ─── Model config parsing ───────────────────────────────────────────

@pytest.mark.parametrize("spec,provider,models", [
    ("gemini:gemini-3.5-flash", "gemini", ("gemini-3.5-flash",)),
    ("openrouter:nvidia/x:free", "openrouter", ("nvidia/x:free",)),
    ("openrouter:a:free|b/c", "openrouter", ("a:free", "b/c")),
])
async def test_parse_entry(spec, provider, models):
    e = llm_models.parse_entry(spec)
    assert e.provider == provider
    assert e.models == models


@pytest.mark.parametrize("spec", ["", "nocolon", "gemini:", "gemini:a|b", "bogus:x"])
async def test_parse_entry_rejects_malformed(spec):
    """A typo'd ladder should fail loudly at import, not at the first visitor."""
    with pytest.raises(ValueError):
        llm_models.parse_entry(spec)


async def test_latest_aliases_do_not_get_thinking_config():
    """The rolling aliases reject thinking_config with 400 INVALID_ARGUMENT."""
    assert not llm_models.gemini_supports_thinking_config("gemini-flash-lite-latest")
    assert llm_models.gemini_supports_thinking_config("gemini-3.1-flash-lite")


async def test_thinking_budget_included_for_supporting_models():
    """Without this, thinking tokens consume max_output_tokens and replies come
    back truncated mid-sentence."""
    cfg = llm_ladder._gemini_config("gemini-2.5-flash", "sys", 200, 0.6)
    assert cfg["thinking_config"] == {"thinking_budget": llm_models.GEMINI_THINKING_BUDGET}

    cfg = llm_ladder._gemini_config("gemini-3.5-flash", "sys", 200, 0.6)
    assert cfg["thinking_config"] == {"thinking_level": "minimal"}

    cfg = llm_ladder._gemini_config("gemini-3.1-flash-lite", "sys", 200, 0.6)
    assert cfg["thinking_config"] == {"thinking_level": "minimal"}

    cfg = llm_ladder._gemini_config("gemini-flash-lite-latest", "sys", 200, 0.6)
    assert "thinking_config" not in cfg


async def test_gemini_thinking_config_helper():
    assert llm_models.gemini_thinking_config("gemini-2.5-flash") == {
        "thinking_budget": llm_models.GEMINI_THINKING_BUDGET
    }
    assert llm_models.gemini_thinking_config("gemini-3.1-flash-lite") == {
        "thinking_level": "minimal"
    }
    assert llm_models.gemini_thinking_config("gemini-flash-lite-latest") is None


async def test_gemini_http_timeout_meets_google_floor():
    assert llm_models.TIMEOUT_MS["voice"] >= llm_models.GEMINI_MIN_HTTP_TIMEOUT_MS
    assert llm_models.gemini_http_timeout_ms("voice") >= 10_000


async def test_gemini_http_timeout_floor_survives_low_env(monkeypatch):
    monkeypatch.setitem(llm_models.TIMEOUT_MS, "voice", 6000)
    assert llm_models.gemini_http_timeout_ms("voice") == 10_000


async def test_openrouter_body_shape():
    entry = llm_models.parse_entry("openrouter:free-x:free|paid/y")
    body = llm_ladder._openrouter_body(
        entry, ctx(), surface="terminal", max_tokens=200,
        temperature=0.6, stream=True, session_id="sess-1",
    )
    assert body["model"] == "free-x:free"
    # Free first, paid last — escalation happens server-side in one round trip.
    assert body["models"] == ["free-x:free", "paid/y"]
    assert body["session_id"] == "sess-1"
    assert body["stream"] is True
    # provider.order would disable sticky routing and therefore cache affinity.
    assert "order" not in body["provider"]
    assert body["provider"]["quantizations"] == list(llm_models.TERMINAL_QUANTIZATIONS)


async def test_voice_provider_prefs_sort_on_latency():
    prefs = llm_models.openrouter_provider_prefs("voice")
    assert prefs["sort"] == "latency"
    assert "order" not in prefs


# ─── Cross-surface breaker (voice ↔ terminal) ───────────────────────
# The point of a process-global breaker is that one visitor's 429 protects
# everyone else — including callers on the *other* surface.

async def test_voice_guard_short_circuits_on_terminal_lock(tmp_path, monkeypatch):
    """A lock recorded by the terminal path must make the voice guard raise
    immediately, with no call to the wrapped LLM."""
    from livekit.agents import APIStatusError
    import llm_voice

    monkeypatch.setattr(llm_ladder, "breaker", llm_ladder.Breaker(tmp_path / "b.json"))
    entry = llm_models.parse_entry("gemini:model-a")

    called = []

    class _Inner:
        def chat(self, **kwargs):
            called.append(1)
            return "stream"

        async def aclose(self):
            pass

    guard = llm_voice.BreakerGuard(_Inner(), entry)

    # Healthy: delegates.
    assert guard.chat(chat_ctx=None) == "stream"
    assert called == [1]

    # Terminal discovers a 429 on this entry...
    llm_ladder.breaker.record_failure(entry, llm_ladder.LLMError(llm_ladder.KIND_MINUTE, "rpm"))

    # ...and voice now fails fast without touching the network.
    with pytest.raises(APIStatusError) as exc:
        guard.chat(chat_ctx=None)
    assert exc.value.status_code == 429
    assert called == [1], "locked entry must not reach the wrapped LLM"


async def test_voice_failure_feeds_the_shared_breaker(tmp_path, monkeypatch):
    """And the other direction: a voice-reported failure stops the terminal path
    immediately re-probing the same entry."""
    import llm_voice

    monkeypatch.setattr(llm_ladder, "breaker", llm_ladder.Breaker(tmp_path / "b.json"))
    entry = llm_models.parse_entry("gemini:model-a")

    class _Inner:
        async def aclose(self):
            pass

    llm_voice.record_voice_unavailable(llm_voice.BreakerGuard(_Inner(), entry))
    assert llm_ladder.breaker.is_locked(entry.key)


async def test_voice_openrouter_401_locks_as_credits(tmp_path, monkeypatch):
    """A provisioning key 401 must not re-probe every 20s."""
    from livekit.agents import APIStatusError
    import llm_voice

    monkeypatch.setattr(llm_ladder, "breaker", llm_ladder.Breaker(tmp_path / "b.json"))
    entry = llm_models.parse_entry("openrouter:nvidia/nemotron-3-nano-30b-a3b:free")

    class _Inner:
        async def aclose(self):
            pass

    guard = llm_voice.BreakerGuard(_Inner(), entry)
    guard._last_error = APIStatusError(
        "Error code: 401 - {'error': {'message': 'User not found.', 'code': 401}}",
        status_code=401,
        retryable=False,
    )
    llm_voice.record_voice_unavailable(guard)
    assert llm_ladder.breaker.is_locked(entry.key)
    snap = llm_ladder.breaker.snapshot()
    assert snap[entry.key]["kind"] == llm_ladder.KIND_CREDITS
    assert snap[entry.key]["seconds_left"] > 1000


async def test_voice_deadline_400_does_not_lock(tmp_path, monkeypatch):
    """Gemini's 5s-deadline 400 is a config bug, not an outage."""
    from livekit.agents import APIStatusError
    import llm_voice

    monkeypatch.setattr(llm_ladder, "breaker", llm_ladder.Breaker(tmp_path / "b.json"))
    entry = llm_models.parse_entry("gemini:gemini-3.1-flash-lite")

    class _Inner:
        async def aclose(self):
            pass

    guard = llm_voice.BreakerGuard(_Inner(), entry)
    guard._last_error = APIStatusError(
        "Manually set deadline 5s is too short. Minimum allowed deadline is 10s.",
        status_code=400,
        retryable=False,
    )
    llm_voice.record_voice_unavailable(guard)
    assert not llm_ladder.breaker.is_locked(entry.key)


async def test_record_voice_unavailable_ignores_unguarded_llm(tmp_path, monkeypatch):
    """FallbackAdapter can emit events for objects we didn't wrap; that must be a
    no-op rather than a crash mid-call."""
    import llm_voice

    monkeypatch.setattr(llm_ladder, "breaker", llm_ladder.Breaker(tmp_path / "b.json"))
    llm_voice.record_voice_unavailable(object())
    assert llm_ladder.breaker.snapshot() == {}


# ─── Per-rung timeouts ──────────────────────────────────────────────
# These are TOTAL request timeouts, not TTFT. An early draft sized them from
# TTFT figures, so a 200-token reply could never finish in time and every rung
# timed out before answering — including the fast ones.

async def test_entry_timeout_override_parses():
    e = llm_models.parse_entry("gemini:gemini-3.5-flash~15000")
    assert e.model == "gemini-3.5-flash"
    assert e.timeout_ms == 15000


async def test_entry_timeout_combines_with_quota_group():
    e = llm_models.parse_entry("gemini:m@google-free~9000")
    assert e.quota_group == "google-free"
    assert e.timeout_ms == 9000
    assert e.model == "m"


@pytest.mark.parametrize("spec", ["gemini:m~abc", "gemini:m~0", "gemini:m~-5"])
async def test_entry_timeout_rejects_nonsense(spec):
    with pytest.raises(ValueError):
        llm_models.parse_entry(spec)


async def test_slow_rung_gets_its_override(monkeypatch):
    """Regression: the quality-first terminal rung must actually get enough time
    to answer, or putting it first achieves nothing."""
    seen = {}

    async def fake_gemini(entry, _ctx, *, timeout_ms, **kw):
        seen[entry.model] = timeout_ms
        return llm_ladder.LLMResult(text="x", entry_label=entry.label)

    monkeypatch.setattr(llm_ladder, "_call_gemini", fake_gemini)

    slow = llm_models.parse_entry("gemini:slow~15000")
    fast = llm_models.parse_entry("gemini:fast")
    await llm_ladder.call_entry(slow, ctx(), surface="terminal")
    await llm_ladder.call_entry(fast, ctx(), surface="terminal")

    assert seen["slow"] == 15000, "per-rung override must win"
    assert seen["fast"] == llm_models.TIMEOUT_MS["terminal"]


async def test_terminal_timeout_covers_a_full_generation():
    """Budget must be TTFT + generation, not TTFT alone: ~200 tokens at ~50 tok/s
    is ~4s of generation before first-token latency is even counted."""
    assert llm_models.TIMEOUT_MS["terminal"] >= 6000
    for e in llm_models.LLM_LADDER:
        assert (e.timeout_ms or llm_models.TIMEOUT_MS["terminal"]) >= 6000, e.label
