"""
LiveKit Voice Agent — Paymanshu Portfolio

This agent joins a LiveKit room and acts as Paymanshu, answering
questions about his resume and experience via voice.

Pipeline: Deepgram STT → Gemini LLM (fallback chain) → Cartesia TTS (→ Deepgram Aura fallback)
VAD: Silero (local)
Turn detection: LiveKit Multilingual Model locally; Silero VAD on Railway unless VOICE_TURN_DETECTOR=true

Latency design (see readmes/SPECs/TECH_SPEC.md):
- No LLM tool round-trip: resume context is injected per-turn via
  on_user_turn_completed (BM25 top-2; full resume below confidence threshold)
- preemptive_generation=True: LLM+TTS start on interim transcript while
  endpointing is still deciding the turn is over
- Short spoken answers enforced by persona + max_output_tokens cap

Usage:
    Development:  python main.py dev
    Production:   python main.py start
"""

import os
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


def _turn_handling() -> TurnHandlingOptions:
    endpointing = {
        "min_delay": float(os.environ.get("MIN_ENDPOINTING_DELAY", "0.4")),
    }
    if not use_turn_detector():
        logger.info("Turn detector off — Silero VAD endpointing only")
        return TurnHandlingOptions(endpointing=endpointing)

    from livekit.plugins.turn_detector.multilingual import MultilingualModel

    return TurnHandlingOptions(
        turn_detection=MultilingualModel(),
        endpointing=endpointing,
    )


# ─── Model configuration ───────────────────────────────────────────
# The LLM ladder now lives in llm_models.VOICE_LADDER (env var: VOICE_LADDER),
# which replaces the old VOICE_LLM_MODELS list. It spans providers rather than
# just Gemini models, because Gemini's free-tier models used to share a chain
# that could not survive a 429 — every rung hit the same quota.
# Verify availability anytime with: python tests/probe_llm.py

# Spoken answers should be 1-2 sentences; cap output hard so a rambling
# generation can't blow up TTS time (and Cartesia credits).
VOICE_MAX_OUTPUT_TOKENS = int(os.environ.get("VOICE_MAX_OUTPUT_TOKENS", "140"))

# BM25 confidence threshold: below this, retrieval is untrustworthy and the
# full resume (~2.5K tokens) is injected instead. Calibrated in
# tests/test_resume_context.py::TestScoredSearch.
RESUME_SCORE_THRESHOLD = float(os.environ.get("RESUME_SCORE_THRESHOLD", "2.5"))

RESUME_PERSONA_INSTRUCTIONS = """\
You are Paymanshu Sharma on a live voice call, speaking in first person about
your own experience. You are a Machine Learning Engineer at Maersk, Bangalore.

STYLE — these rules are absolute:
- Answer in 1-2 short sentences, under 35 words total. Only go longer if the
  caller explicitly asks for detail, and even then stay under 4 sentences.
- Plain spoken language. No markdown, no emoji, no lists, no headings.
- Warm, direct, conversational — like talking to a colleague, not presenting.

CONTENT:
- Resume context relevant to the caller's question is provided in the
  conversation before each of your answers. Answer ONLY from that context.
- If the context doesn't cover the question, say so honestly in one sentence.
  Never invent facts about yourself.
"""


class PaymanshuAgent(Agent):
    """The voice agent representing Paymanshu.

    Resume context is injected per-turn (not via an LLM tool): a tool call
    costs a full extra LLM round-trip (~600ms+) per question. Injection is
    ~0.3ms of BM25 and zero extra inference.
    """

    def __init__(self) -> None:
        super().__init__(instructions=RESUME_PERSONA_INSTRUCTIONS)

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        query = new_message.text_content or ""
        index = get_resume_index()
        context, score = index.search_scored(query, top_k=2)

        if score < RESUME_SCORE_THRESHOLD:
            # Low retrieval confidence (vague/small-talk query) — give the
            # LLM the whole resume rather than trusting a weak match.
            context = index.full_text
            source = "full-resume"
        else:
            source = "bm25-top2"

        logger.info(
            "context injection: score=%.2f source=%s chars=%d query=%r",
            score, source, len(context), query[:80],
        )
        # Added to this turn only (no update_chat_ctx) so history doesn't
        # accumulate a copy of the resume on every exchange.
        turn_ctx.add_message(
            role="assistant",
            content=f"[Context for the next answer — internal, not spoken]\n{context}",
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
        stt_model = deepgram.STT(model="nova-3", language="en")

    # LLM: the VOICE_LADDER from llm_models, each entry guarded by the shared
    # quota breaker (see llm_voice). Ordering is latency-first — 3.5-flash's
    # measured ~6s TTFT would be dead air mid-call, so flash-lite leads here even
    # though the terminal ladder leads with flash.
    llm_model = llm_voice.build_voice_llm(
        max_output_tokens=VOICE_MAX_OUTPUT_TOKENS, temperature=0.6
    )

    # TTS: Cartesia sonic-3 primary; Deepgram Aura as credit/rate-limit fallback.
    # (Bare "sonic" was sunsetted — see tests/probe_cartesia.sh.)
    cartesia_tts = cartesia.TTS(
        model=os.environ.get("CARTESIA_MODEL", "sonic-3"),
        voice=os.environ.get(
            "CARTESIA_VOICE_ID",
            "79a125e8-cd45-4c13-8a67-188112f4dd22",
        ),
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

    try:
        await session.generate_reply(
            instructions="Greet the caller in one short sentence as Paymanshu and ask what they'd like to know."
        )
    except Exception as e:
        logger.warning(f"generate_reply failed: {e}")
        await session.say("Hey! I'm Paymanshu. Ask me anything about my experience.")

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
