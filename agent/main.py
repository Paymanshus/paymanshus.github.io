"""
LiveKit Voice Agent — Paymanshu Portfolio

This agent joins a LiveKit room and acts as Paymanshu, answering
questions about his resume and experience via voice.

Pipeline: Deepgram STT → Gemini LLM (fallback chain) → Cartesia TTS (→ Deepgram Aura fallback)
VAD: Silero (local)
Turn detection: LiveKit Multilingual Model

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
    llm as lk_llm,
    tts as lk_tts,
)
from livekit.plugins import google, deepgram, cartesia, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from resume_context import get_resume_index
from token_server import create_token_app
from observability import setup_voice_tracing, attach_usage_reporter

load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")

# ─── Model configuration ───────────────────────────────────────────
# LLM fallback chain. Gemini free-tier models get decommissioned and
# capacity-throttled without notice (2.5-flash/2.5-flash-lite 404 as of
# July 2026; 3.5-flash intermittently 503s). The FallbackAdapter moves
# down the chain automatically. `gemini-flash-lite-latest` is Google's
# rolling alias, so the last resort keeps working across sunsets.
# Verify availability anytime with: python tests/probe_gemini.py
VOICE_LLM_MODELS = [
    m.strip()
    for m in os.environ.get(
        "VOICE_LLM_MODELS",
        "gemini-3.5-flash,gemini-3.1-flash-lite,gemini-flash-lite-latest",
    ).split(",")
    if m.strip()
]

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

server = AgentServer()


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
    # participant attributes; VoiceResume.tsx renders a status banner.
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

    # LLM: Gemini fallback chain (rate limits / sunsets handled automatically)
    llm_instances = [
        google.LLM(model=m, max_output_tokens=VOICE_MAX_OUTPUT_TOKENS, temperature=0.6)
        for m in VOICE_LLM_MODELS
    ]
    llm_model = lk_llm.FallbackAdapter(llm_instances)

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
        turn_handling=TurnHandlingOptions(
            turn_detection=MultilingualModel(),
            # Default min_delay is 0.5s; 0.4s trades a little interruption
            # risk for snap. Migrated off the deprecated top-level
            # min_endpointing_delay kwarg (removed in livekit-agents 2.0).
            endpointing={
                "min_delay": float(os.environ.get("MIN_ENDPOINTING_DELAY", "0.4")),
            },
        ),
        # Start LLM+TTS on the interim transcript while endpointing is still
        # confirming end-of-turn — hides most LLM TTFT inside the wait.
        preemptive_generation=True,
    )

    # Per-session STT/LLM/TTS usage totals + estimated cost, logged at
    # session end and (when enabled) recorded in Langfuse.
    attach_usage_reporter(session, ctx, ctx.room.name)

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
    port = int(os.environ.get("TOKEN_SERVER_PORT", "8080"))
    web.run_app(create_token_app(), port=port, handle_signals=False, print=None)


if __name__ == "__main__":
    threading.Thread(target=_run_token_server, daemon=True, name="token-server").start()
    logger.info("Token server thread started on :%s", os.environ.get("TOKEN_SERVER_PORT", "8080"))
    agents.cli.run_app(server)
