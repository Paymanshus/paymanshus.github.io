"""Tests for the persona prompts, cached voice lines, long-turn trimming and the
streamed terminal endpoint.

  - prompts: one shared core, voice and terminal differ only in register, and
    nothing in them reads badly aloud (no em dashes) or is too long to greet with
  - voice_greeting: a line is rendered with TTS exactly once, then played from
    disk; a cache problem falls back to live TTS instead of losing the line
  - trim_user_text: a runaway transcript keeps its tail, marked as trimmed
  - /api/chat/stream: SSE deltas then done; llm_unavailable as an event; and
    the ladder never falls through to a second model after part of a reply has
    already been streamed

Run: cd agent && .venv/bin/python -m pytest tests/test_voice_and_stream.py -q
"""

import json
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

pytestmark = pytest.mark.asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

import llm_context
import llm_ladder
import llm_models
import llm_voice
import prompts
import token_server
import voice_greeting


# ─── Prompts ────────────────────────────────────────────────────────

async def test_voice_and_terminal_share_one_core():
    core = prompts._CORE
    assert prompts.TERMINAL_PERSONA_BODY.startswith(core)
    assert prompts.VOICE_PERSONA_INSTRUCTIONS.startswith(core)
    assert prompts.TERMINAL_PERSONA_BODY != prompts.VOICE_PERSONA_INSTRUCTIONS


async def test_spoken_lines_read_well_aloud():
    spoken = list(prompts.VOICE_GREETINGS) + [
        prompts.VOICE_GOODBYE_TIME_LIMIT, prompts.VOICE_IDLE_CHECK, prompts.VOICE_GOODBYE_IDLE,
    ]
    for line in spoken:
        assert "—" not in line and "(" not in line, line
    for g in prompts.VOICE_GREETINGS:
        assert len(g) <= 120, "greetings stay short: they are the first thing a visitor hears"


async def test_prompts_ban_em_dashes_in_output_instructions():
    for prompt in (prompts.TERMINAL_PERSONA_BODY, prompts.VOICE_PERSONA_INSTRUCTIONS):
        assert "em dashes" in " ".join(prompt.split())


# ─── Cached voice lines ─────────────────────────────────────────────

class _Frame:
    def __init__(self, n):
        self.sample_rate, self.num_channels = 24000, 1
        self.data = b"\x01\x00" * n


class _Ev:
    def __init__(self, n):
        self.frame = _Frame(n)


class FakeTTS:
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def synthesize(self, text):
        self.calls += 1
        tts = self

        class _Stream:
            async def __aenter__(self):
                if tts.fail:
                    raise RuntimeError("cartesia down")
                return self

            async def __aexit__(self, *a):
                return False

            def __aiter__(self):
                async def gen():
                    for n in (480, 480, 100):
                        yield _Ev(n)
                return gen()

        return _Stream()


class FakeSession:
    def __init__(self):
        self.said = []

    def say(self, text, *, audio=None, allow_interruptions=True):
        self.said.append((text, audio is not None))
        return "handle"


async def test_line_is_rendered_once_then_played_from_disk(tmp_path):
    tts, session = FakeTTS(), FakeSession()
    kw = dict(tts=tts, model="sonic-3", voice="v1", cache_dir=tmp_path)
    assert await voice_greeting.say_cached(session, "Hi there", **kw) == "handle"
    await voice_greeting.say_cached(session, "Hi there", **kw)
    assert tts.calls == 1, "second play comes from the cache: no TTS credits"
    assert session.said == [("Hi there", True), ("Hi there", True)]
    pcm, sr, ch = voice_greeting.load_pcm(
        voice_greeting.cache_key("Hi there", model="sonic-3", voice="v1"), tmp_path)
    assert sr == 24000 and ch == 1 and len(pcm) == 2 * (480 + 480 + 100)


async def test_changing_voice_or_text_renders_again(tmp_path):
    k1 = voice_greeting.cache_key("Hi", model="sonic-3", voice="a")
    assert k1 != voice_greeting.cache_key("Hi", model="sonic-3", voice="b")
    assert k1 != voice_greeting.cache_key("Hi!", model="sonic-3", voice="a")


async def test_cache_failure_falls_back_to_live_tts(tmp_path):
    session = FakeSession()
    await voice_greeting.say_cached(session, "Hi", tts=FakeTTS(fail=True), model="m",
                                    voice="v", cache_dir=tmp_path)
    assert session.said == [("Hi", False)], "the visitor still hears the line"


async def test_frames_are_20ms():
    frames = list(voice_greeting.to_frames(b"\x00\x00" * 24000, 24000, 1))
    assert len(frames) == 50
    assert frames[0].samples_per_channel == 480


# ─── Long user turns ────────────────────────────────────────────────

async def test_trim_keeps_short_text():
    assert llm_voice.trim_user_text("what do you do?", 600) == "what do you do?"


async def test_trim_keeps_the_tail_marked():
    text = "blah " * 300 + "so what did you build at Hike?"
    out = llm_voice.trim_user_text(text, 100)
    assert out.startswith("(earlier part trimmed) ...")
    assert out.endswith("so what did you build at Hike?")
    assert len(out) <= 100 + len("(earlier part trimmed) ...")
    assert not out.split("...", 1)[1].startswith("lah"), "cut at a word boundary"


# ─── Streaming ladder ───────────────────────────────────────────────

@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_ladder, "breaker", llm_ladder.Breaker(tmp_path / "b.json"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def _ctx():
    return llm_context.BuiltContext(mode="full_hint", system="s", turns=[{"role": "user", "text": "q"}])


async def test_failure_before_any_text_falls_through(isolated, monkeypatch):
    seen = []

    async def fake_call(entry, ctx, **kw):
        if entry.model == "a":
            raise llm_ladder.LLMError(llm_ladder.KIND_SERVER, "503")
        kw["on_delta"]("hello")
        return llm_ladder.LLMResult(text="hello", entry_label=entry.label)

    monkeypatch.setattr(llm_ladder, "call_entry", fake_call)
    ladder = (llm_models.parse_entry("openrouter:a"), llm_models.parse_entry("openrouter:b"))
    result = await llm_ladder.generate(_ctx(), ladder=ladder, on_delta=seen.append)
    assert result.text == "hello" and seen == ["hello"]


async def test_failure_after_text_does_not_append_a_second_answer(isolated, monkeypatch):
    seen, called = [], []

    async def fake_call(entry, ctx, **kw):
        called.append(entry.model)
        kw["on_delta"]("half an ans")
        raise llm_ladder.LLMError(llm_ladder.KIND_TIMEOUT, "cut")

    monkeypatch.setattr(llm_ladder, "call_entry", fake_call)
    ladder = (llm_models.parse_entry("openrouter:a"), llm_models.parse_entry("openrouter:b"))
    assert await llm_ladder.generate(_ctx(), ladder=ladder, on_delta=seen.append) is None
    assert called == ["a"], "no second model after part of a reply was sent"


# ─── /api/chat/stream ───────────────────────────────────────────────

class _NoCanary:
    def kick(self, now=None):
        pass

    def start(self):
        pass

    async def stop(self):
        pass


@pytest_asyncio.fixture
async def client(monkeypatch):
    for d in (token_server._minute_hits, token_server._day_hits,
              token_server._global_day_hits, token_server._global_minute_hits):
        d.clear()
    monkeypatch.setattr(token_server.llm_health, "scheduler", _NoCanary())
    async with TestClient(TestServer(token_server.create_token_app())) as c:
        yield c


def _events(raw: str) -> list[dict]:
    return [json.loads(line[5:]) for line in raw.split("\n") if line.startswith("data:")]


async def test_stream_sends_deltas_then_done(client, monkeypatch):
    async def fake_reply(ctx, *, session_id=None, on_delta=None):
        for piece in ("building ", "Shipment ", "CoCaptain"):
            on_delta(piece)
        return "building Shipment CoCaptain", "m"

    monkeypatch.setattr(token_server, "_generate_reply", fake_reply)
    resp = await client.post("/api/chat/stream", json={"message": "what do you do?"})
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("text/event-stream")
    events = _events(await resp.text())
    assert "".join(e["delta"] for e in events if "delta" in e) == "building Shipment CoCaptain"
    assert events[-1] == {"done": True}


async def test_stream_reports_llm_unavailable(client, monkeypatch):
    async def fake_reply(ctx, *, session_id=None, on_delta=None):
        return "", None

    monkeypatch.setattr(token_server, "_generate_reply", fake_reply)
    resp = await client.post("/api/chat/stream", json={"message": "hi"})
    assert _events(await resp.text()) == [{"error": "llm_unavailable"}]


async def test_stream_validates_before_streaming(client):
    resp = await client.post("/api/chat/stream", json={"message": "   "})
    assert resp.status == 400
