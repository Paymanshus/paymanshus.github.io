"""
LiveKit Voice Agent — Paymanshu Portfolio

This agent joins a LiveKit room and acts as Paymanshu, answering
questions about his resume and experience via voice.

Pipeline: Deepgram STT → Gemini LLM (fallback chain) → Cartesia TTS (→ Deepgram Aura fallback)
VAD: Silero (local)
Turn detection: LiveKit Multilingual Model locally; Silero VAD on Railway unless VOICE_TURN_DETECTOR=true

Latency design (see readmes/SPECs/TECH_SPEC.md):
- No LLM tool round-trip: resume context is injected per LLM call in
  PaymanshuAgent.llm_node (BM25 top-2; full resume below confidence threshold),
  on a copy of the chat context so preemptive generation stays valid
- preemptive_generation=True: the LLM starts on the interim transcript while
  endpointing (dynamic, 0.4-2.5 s) is still deciding the turn is over
- Fixed lines (greeting, goodbyes) play from cached audio; word fixes for STT
  and TTS live in voice_lexicon.py
- Short spoken answers enforced by persona + max_output_tokens cap

Usage:
    Development:  python main.py dev
    Production:   python main.py start
"""

import os
import time
import random
import asyncio
import threading
import logging
from dotenv import load_dotenv
from aiohttp import web
from livekit import agents
from livekit.agents import (
    AgentServer,
    AgentSession,
    Agent,
    ChatContext,
    ChatMessage,
    TurnHandlingOptions,
    tts as lk_tts,
)
from livekit.plugins import google, deepgram, cartesia, silero
from resume_context import get_resume_index
from token_server import create_token_app
from observability import setup_voice_tracing, attach_usage_reporter
import llm_models
import llm_voice
import voice_availability
import voice_greeting
import voice_lexicon
from prompts import (
    VOICE_PERSONA_INSTRUCTIONS,
    VOICE_GREETINGS,
    VOICE_GOODBYE_TIME_LIMIT,
    VOICE_IDLE_CHECK,
    VOICE_GOODBYE_IDLE,
)

load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")


def http_listen_port() -> int:
    """Port for /api/token, /api/chat, /api/health.

    On Railway the public hostname proxies to PORT, so PORT wins there even
    if TOKEN_SERVER_PORT=8080 was copied from .env.local. Elsewhere
    TOKEN_SERVER_PORT still wins (local docker -p 8080:8080).
    """
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        return int(os.environ.get("PORT") or os.environ.get("TOKEN_SERVER_PORT") or "8080")
    return int(os.environ.get("TOKEN_SERVER_PORT") or os.environ.get("PORT") or "8080")


def _env_flag(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def use_turn_detector() -> bool:
    """Whether to load LiveKit's multilingual EOU model.

    Importing that plugin registers an inference subprocess (~500MB+). On
    Railway Trial/Free that child is OOM-killed and the worker dies with
    DuplexClosed before it can register with LiveKit. Explicit
    VOICE_TURN_DETECTOR=true/false always wins; if unset, skip it when
    RAILWAY_ENVIRONMENT is set.
    """
    explicit = _env_flag("VOICE_TURN_DETECTOR")
    if explicit is not None:
        return explicit
    return not bool(os.environ.get("RAILWAY_ENVIRONMENT"))


# The turn-detector plugin must be imported here, in the main process, not
# inside the job. Importing it registers the EOU inference runner (served from
# the shared inference subprocess) and adds its model files to `download-files`,
# which the Dockerfile runs at build time. Importing it lazily inside the job
# skipped both: every voice job died with `Could not find file "languages.json"`
# and the visitor sat on "summoning the agent" forever (Oracle VM, 2026-10-21).
if use_turn_detector():
    from livekit.plugins.turn_detector.multilingual import MultilingualModel
else:
    MultilingualModel = None


def _turn_handling() -> TurnHandlingOptions:
    # "dynamic" adapts the wait to each caller's own pause pattern between the
    # min and max: quick talkers get answered sooner, people who pause mid-
    # thought get a little more room. min stays at the 0.4 s that felt right on
    # live calls; max comes down from 3.0 s so an unsure turn detector can't
    # leave anyone hanging for 3 s. See readmes/perf/2026-10-22/tests/13-*.md.
    endpointing = {
        "mode": os.environ.get("ENDPOINTING_MODE", "dynamic"),
        "min_delay": float(os.environ.get("MIN_ENDPOINTING_DELAY", "0.4")),
        "max_delay": float(os.environ.get("MAX_ENDPOINTING_DELAY", "2.5")),
    }
    # A visitor who monologues (or leaves a TV on near the mic) gets a polite
    # cut-in after ~45 s of speech instead of an ever-growing transcript; see
    # PaymanshuAgent.on_user_turn_exceeded. LiveKit >= 1.8 only.
    user_turn_limit = {"max_words": VOICE_MAX_TURN_WORDS}
    if MultilingualModel is None:
        logger.info("Turn detector off — Silero VAD endpointing only")
        return TurnHandlingOptions(endpointing=endpointing, user_turn_limit=user_turn_limit)

    return TurnHandlingOptions(
        turn_detection=MultilingualModel(),
        endpointing=endpointing,
        user_turn_limit=user_turn_limit,
    )


# ─── Model configuration ───────────────────────────────────────────
# The LLM ladder now lives in llm_models.VOICE_LADDER (env var: VOICE_LADDER),
# which replaces the old VOICE_LLM_MODELS list. It spans providers rather than
# just Gemini models, because Gemini's free-tier models used to share a chain
# that could not survive a 429 — every rung hit the same quota.
# Verify availability anytime with: python tests/probe_llm.py

# The persona caps spoken answers at 40 words (~55 tokens); this is only the
# backstop so a rambling generation can't blow up TTS time and Cartesia
# credits. Low enough to bound cost, high enough not to cut a sentence off.
VOICE_MAX_OUTPUT_TOKENS = int(os.environ.get("VOICE_MAX_OUTPUT_TOKENS", "100"))

# BM25 confidence threshold: below this, retrieval is untrustworthy and the
# full resume (~2.5K tokens) is injected instead. Calibrated in
# tests/test_resume_context.py::TestScoredSearch.
RESUME_SCORE_THRESHOLD = float(os.environ.get("RESUME_SCORE_THRESHOLD", "2.5"))

# The persona lives in prompts.py, shared with the eval harnesses.
RESUME_PERSONA_INSTRUCTIONS = VOICE_PERSONA_INSTRUCTIONS

# ─── Session limits ────────────────────────────────────────────────
# A voice call is a demo, not a phone line: every minute costs STT, LLM and TTS
# and counts against LiveKit's monthly agent minutes. Hard cap per call, a
# check-in when the visitor goes quiet, and caps on how much one user turn can
# put in front of the LLM.
VOICE_MAX_SESSION_S = float(os.environ.get("VOICE_MAX_SESSION_S", "300"))
# LiveKit marks the user "away" after this long with nobody speaking; we ask
# "Still there?" and hang up if there's still no answer VOICE_IDLE_GRACE_S later.
VOICE_USER_AWAY_S = float(os.environ.get("VOICE_USER_AWAY_S", "30"))
VOICE_IDLE_GRACE_S = float(os.environ.get("VOICE_IDLE_GRACE_S", "15"))
# ~45 s of continuous speech. Past it LiveKit fires on_user_turn_exceeded.
VOICE_MAX_TURN_WORDS = int(os.environ.get("VOICE_MAX_TURN_WORDS", "120"))
# What one user turn may send to the LLM (and BM25) is capped too: see
# llm_voice.trim_user_text (VOICE_MAX_USER_CHARS).
trim_user_text = llm_voice.trim_user_text


class PaymanshuAgent(Agent):
    """The voice agent representing Paymanshu.

    Resume context is injected per LLM call (not via an LLM tool): a tool call
    costs a full extra LLM round-trip (~600ms+) per question. Injection is
    ~0.3ms of BM25 and zero extra inference.
    """

    def __init__(self) -> None:
        super().__init__(instructions=RESUME_PERSONA_INSTRUCTIONS)

    async def llm_node(self, chat_ctx: ChatContext, tools, model_settings):
        """Every LLM call (preemptive or final) sees the session's history plus
        this turn's resume context, STT word fixes and the long-turn trim, all
        on a copy (llm_voice.prepare_voice_ctx). Nothing is added in
        on_user_turn_completed any more: that made LiveKit throw away its
        preemptive generation on every turn. History doesn't accumulate resume
        copies, since the context exists only in the per-call copy."""
        ctx, info = llm_voice.prepare_voice_ctx(chat_ctx, get_resume_index(), RESUME_SCORE_THRESHOLD)
        if info:
            logger.info(
                "context injection: score=%.2f source=%s chars=%d query=%r",
                info["score"], info["source"], info["chars"], info["query"][:80],
            )
        async for chunk in Agent.default.llm_node(self, ctx, tools, model_settings):
            yield chunk

    async def on_user_turn_exceeded(self, ev) -> None:
        """The caller has talked for ~45 s straight: cut in briefly, replying to
        the tail of what they said instead of the whole transcript."""
        logger.info("user turn limit hit: %s words", getattr(ev, "accumulated_word_count", "?"))
        await self.session.generate_reply(
            user_input=trim_user_text(getattr(ev, "transcript", "") or ""),
            instructions=(
                "The caller has been talking for a while without a pause. Cut in "
                "politely in one short sentence: respond to the gist, or ask them "
                "to put the question in a sentence or two."
            ),
            allow_interruptions=False,
            tool_choice="none",
        )


# ─── Server & Session Setup ────────────────────────────────────────

def idle_process_count() -> int:
    """Job-process pool size. LiveKit's start-mode default is 16, which OOMs
    a 0.5–1GB Railway box before any visitor connects."""
    raw = os.environ.get("AGENT_IDLE_PROCESSES")
    if raw is not None and raw.strip():
        return int(raw)
    return 0


def prewarm(proc) -> None:
    """Load the resume index and heavy LLM plugin imports before any job.

    LiveKit warns when httpcore / openai types import on first FallbackAdapter
    hop — that lands on the session loop and stalls audio. setup_fnc runs in
    the job process before the session starts. Silero stays in the session
    (its loader is loop-bound). With AGENT_IDLE_PROCESSES=0 this still runs
    per spawned job process, just not ahead of the first visitor.
    """
    get_resume_index()
    import httpcore  # noqa: F401
    from livekit.plugins import openai as _lk_openai  # noqa: F401


# Slow hosts need more than the default 10s; do not pre-spawn 16 job processes.
server = AgentServer(
    initialize_process_timeout=120.0,
    num_idle_processes=idle_process_count(),
)
server.setup_fnc = prewarm


@server.rtc_session(agent_name="paymanshu-voice")
async def voice_agent(ctx: agents.JobContext):
    """Called when a new visitor connects to a LiveKit room."""

    logger.info(f"New session in room: {ctx.room.name}")

    # Agent minutes for the monthly cap (LiveKit Build: 1,000/month). Probe
    # rooms from tests/dispatch_probe.py count too: they use real minutes.
    job_started = time.monotonic()

    async def _record_minutes() -> None:
        voice_availability.record_session_seconds(time.monotonic() - job_started)

    ctx.add_shutdown_callback(_record_minutes)

    # ─── Observability ─────────────────────────────────────────
    # Bridge LiveKit's OTel spans (turns, llm prompts, tts/stt, EOU) into
    # Langfuse. No-op without LANGFUSE_* keys. Must run before the session
    # starts so its spans land under this provider.
    trace_provider = setup_voice_tracing(ctx.room.name)
    if trace_provider is not None:
        async def _flush_traces() -> None:
            trace_provider.force_flush()

        ctx.add_shutdown_callback(_flush_traces)

    # ─── Degradation signaling ─────────────────────────────────
    # FallbackAdapter availability changes are pushed to the frontend via
    # participant attributes; VoiceResume.tsx renders LLM fallback as a mark
    # next to listening, and TTS-down as an amber banner.
    def _publish_attrs(attrs: dict[str, str]) -> None:
        async def _set() -> None:
            try:
                await ctx.room.local_participant.set_attributes(attrs)
            except Exception as e:
                logger.warning("failed to set attributes %s: %s", attrs, e)

        asyncio.create_task(_set())

    # STT: Deepgram Nova-3 (primary) or Google Chirp (fallback)
    if os.environ.get("USE_GOOGLE_STT", "false").lower() == "true":
        stt_model = google.STT(model="chirp")
        logger.info("Using Google Chirp STT (fallback)")
    else:
        # Keyterm prompting (names Deepgram should expect) is billed extra, so
        # it's opt-in: VOICE_STT_KEYTERMS=true. Free regex fixes always apply
        # (voice_lexicon.STT_FIXES, in llm_voice.prepare_voice_ctx).
        stt_kwargs = {"keyterms": voice_lexicon.STT_KEYTERMS} if voice_lexicon.USE_STT_KEYTERMS else {}
        stt_model = deepgram.STT(model="nova-3", language="en", **stt_kwargs)

    # LLM: the VOICE_LADDER from llm_models, each entry guarded by the shared
    # quota breaker (see llm_voice). Ordering is latency-first — 3.5-flash's
    # measured ~6s TTFT would be dead air mid-call, so flash-lite leads here even
    # though the terminal ladder leads with flash.
    llm_model = llm_voice.build_voice_llm(
        max_output_tokens=VOICE_MAX_OUTPUT_TOKENS, temperature=0.6
    )

    # TTS: Cartesia sonic-3 primary; Deepgram Aura as credit/rate-limit fallback.
    # (Bare "sonic" was sunsetted — see tests/probe_cartesia.sh.)
    cartesia_kwargs = {}
    if voice_lexicon.CARTESIA_PRONUNCIATION_DICT_ID:
        cartesia_kwargs["pronunciation_dict_id"] = voice_lexicon.CARTESIA_PRONUNCIATION_DICT_ID
    cartesia_tts = cartesia.TTS(
        model=os.environ.get("CARTESIA_MODEL", "sonic-3"),
        voice=os.environ.get(
            "CARTESIA_VOICE_ID",
            "79a125e8-cd45-4c13-8a67-188112f4dd22",
        ),
        **cartesia_kwargs,
    )
    deepgram_tts = deepgram.TTS()
    tts_model = lk_tts.FallbackAdapter([cartesia_tts, deepgram_tts])

    tts_down: set[str] = set()

    def _on_tts_availability(event) -> None:
        label = getattr(event.tts, "label", str(event.tts))
        if event.available:
            tts_down.discard(label)
        else:
            tts_down.add(label)
        if len(tts_down) >= 2:
            status = "down"       # every TTS provider failing
        elif tts_down:
            status = "degraded"   # primary voice failing, fallback active
        else:
            status = "ok"
        logger.warning("TTS availability changed: %s → voice.tts=%s", label, status)
        _publish_attrs({"voice.tts": status})

    def _on_llm_availability(event) -> None:
        label = getattr(event.llm, "label", str(event.llm))
        status = "fallback" if not event.available else "ok"
        logger.warning("LLM availability changed: %s → voice.llm=%s", label, status)
        _publish_attrs({"voice.llm": status})
        if not event.available:
            # Share the finding with the terminal path so it stops probing an
            # entry voice just found broken. Coarse (no quota scope available
            # here) — see llm_voice.record_voice_unavailable.
            llm_voice.record_voice_unavailable(
                event.llm, error=getattr(event, "error", None)
            )

    tts_model.on("tts_availability_changed", _on_tts_availability)
    try:
        llm_model.on("llm_availability_changed", _on_llm_availability)
    except Exception as e:
        # Event name differs across versions; degrade silently if absent.
        logger.info("llm availability event not wired: %s", e)

    vad_model = silero.VAD.load()

    session = AgentSession(
        stt=stt_model,
        llm=llm_model,
        tts=tts_model,
        vad=vad_model,
        # Default min_delay is 0.5s; 0.4s trades a little interruption
        # risk for snap. Migrated off the deprecated top-level
        # min_endpointing_delay kwarg (removed in livekit-agents 2.0).
        # Multilingual EOU is skipped on Railway unless VOICE_TURN_DETECTOR=true.
        turn_handling=_turn_handling(),
        # Start LLM+TTS on the interim transcript while endpointing is still
        # confirming end-of-turn — hides most LLM TTFT inside the wait.
        preemptive_generation=True,
        # Fires user_state_changed -> "away" after this long with nobody
        # speaking; drives the idle check-in and hang-up below.
        user_away_timeout=VOICE_USER_AWAY_S,
        # Pronunciation fixes ("resume" -> "résumé") on the text going to TTS
        # only; transcripts and history keep the real spelling. voice_lexicon.
        tts_text_transforms=voice_lexicon.tts_transforms(),
    )

    # Per-session STT/LLM/TTS usage totals + estimated cost, logged at
    # session end and (when enabled) recorded in Langfuse.
    attach_usage_reporter(session, ctx, ctx.room.name)

    # One `turn-latency` line per conversation item, from LiveKit's own
    # per-turn MetricsReport (seconds). User items carry the STT/endpointing
    # delays; assistant items carry LLM TTFT, TTS TTFB and end-to-end latency.
    # grep the container logs for `turn-latency` to profile a real call.
    @session.on("conversation_item_added")
    def _log_turn_latency(event) -> None:
        item = getattr(event, "item", None)
        metrics = getattr(item, "metrics", None) or {}
        if not metrics:
            return
        fields = " ".join(
            f"{k}={v:.3f}"
            for k, v in metrics.items()
            # *_at keys are wall-clock timestamps, not durations.
            if isinstance(v, (int, float)) and not k.endswith("_at")
        )
        logger.info(
            "turn-latency room=%s role=%s %s",
            ctx.room.name, getattr(item, "role", "?"), fields,
        )

    await session.start(
        room=ctx.room,
        agent=PaymanshuAgent(),
    )

    _publish_attrs({"voice.tts": "ok", "voice.llm": "ok"})

    # Fixed lines (greeting, goodbyes) play from pre-rendered audio: no LLM
    # call, no TTS credits after the first render, and no wait. voice_greeting
    # falls back to live TTS if the cache can't be used.
    tts_model_name = os.environ.get("CARTESIA_MODEL", "sonic-3")
    tts_voice_id = os.environ.get("CARTESIA_VOICE_ID", "79a125e8-cd45-4c13-8a67-188112f4dd22")

    def say_line(text: str, *, allow_interruptions: bool = True):
        return voice_greeting.say_cached(
            session, text, tts=cartesia_tts, model=tts_model_name, voice=tts_voice_id,
            allow_interruptions=allow_interruptions,
        )

    await say_line(random.choice(VOICE_GREETINGS))

    # ─── Session limits: hard cap and idle hang-up ─────────────
    ending = asyncio.Event()

    async def end_call(text: str, reason: str) -> None:
        """Say goodbye (not interruptible), tell the page why, then close the
        room so the visitor's client disconnects cleanly."""
        if ending.is_set():
            return
        ending.set()
        logger.info("ending voice session room=%s reason=%s", ctx.room.name, reason)
        try:
            session.interrupt()
        except Exception:
            pass
        try:
            await ctx.room.local_participant.set_attributes({"voice.end_reason": reason})
        except Exception as e:
            logger.warning("failed to set end reason: %s", e)
        try:
            handle = await say_line(text, allow_interruptions=False)
            await asyncio.wait_for(handle.wait_for_playout(), timeout=15)
        except Exception as e:
            logger.warning("goodbye playback failed: %s", e)
        await asyncio.sleep(0.5)
        try:
            await ctx.delete_room()
        except Exception as e:
            logger.warning("delete_room failed (%s), shutting down the job", e)
            ctx.shutdown(reason=reason)

    async def _time_limit() -> None:
        await asyncio.sleep(VOICE_MAX_SESSION_S)
        await end_call(VOICE_GOODBYE_TIME_LIMIT, "time_limit")

    idle_task: asyncio.Task | None = None

    async def _idle_check() -> None:
        handle = await say_line(VOICE_IDLE_CHECK)
        await handle.wait_for_playout()
        await asyncio.sleep(VOICE_IDLE_GRACE_S)
        await end_call(VOICE_GOODBYE_IDLE, "idle")

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:
        nonlocal idle_task
        if ev.new_state == "away" and not ending.is_set():
            if idle_task is None or idle_task.done():
                idle_task = asyncio.create_task(_idle_check())
        elif (ev.new_state == "speaking" and not ending.is_set()
              and idle_task is not None and not idle_task.done()):
            idle_task.cancel()  # they're back: no hang-up

    limit_task = asyncio.create_task(_time_limit())

    async def _cancel_limits() -> None:
        for task in (limit_task, idle_task):
            if task is not None and not task.done():
                task.cancel()

    ctx.add_shutdown_callback(_cancel_limits)

    logger.info("Agent session started successfully")


# ─── Main Entrypoint ───────────────────────────────────────────────

def _run_token_server() -> None:
    """Run the token/chat HTTP server in its own thread with its own event loop.

    agents.cli.run_app() owns the main thread's loop, so the aiohttp app gets
    a dedicated daemon thread. aiohttp's web.run_app creates a fresh loop when
    none exists in the thread.
    """
    port = http_listen_port()
    web.run_app(
        create_token_app(),
        host="0.0.0.0",
        port=port,
        handle_signals=False,
        print=None,
    )


if __name__ == "__main__":
    threading.Thread(target=_run_token_server, daemon=True, name="token-server").start()
    logger.info("Token server thread started on :%s", http_listen_port())
    agents.cli.run_app(server)
