"""
Langfuse observability for the voice agent + terminal chat server.

Everything here is env-gated on LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY:
without keys (or with `langfuse` not installed) every function is an inert
no-op and the agent behaves exactly as before. Never let tracing break serving.

Two distinct process contexts use this module:

- LiveKit job subprocesses (one per voice session): `setup_voice_tracing()`
  bridges LiveKit's built-in OpenTelemetry spans (agent turns, llm_node with
  full chat context, tts/stt nodes, tool calls, EOU detection) into Langfuse
  through a shared TracerProvider, following the official integration:
  https://langfuse.com/integrations/frameworks/livekit
- The main worker process (token/chat server thread): `get_langfuse()` lazily
  creates a client used for explicit generation spans around /api/chat.

Requires langfuse >= 4 (SDK rewrite; `propagate_attributes`, `base_url`).
"""

import logging
import os
import threading

logger = logging.getLogger("observability")

_client = None
_client_failed = False
_client_lock = threading.Lock()


def langfuse_enabled() -> bool:
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )


def _base_url() -> str:
    return (
        os.environ.get("LANGFUSE_BASE_URL")
        or os.environ.get("LANGFUSE_HOST")
        or "https://cloud.langfuse.com"
    )


def get_langfuse():
    """Lazy singleton Langfuse client, or None when disabled/unavailable."""
    global _client, _client_failed
    if _client is not None or _client_failed:
        return _client
    if not langfuse_enabled():
        return None
    with _client_lock:
        if _client is not None or _client_failed:
            return _client
        try:
            from langfuse import Langfuse

            _client = Langfuse(base_url=_base_url())
            logger.info("Langfuse client initialized (base_url=%s)", _base_url())
        except Exception as e:
            _client_failed = True
            logger.warning("Langfuse disabled: %s", e)
    return _client


def peek_langfuse():
    """Existing client or None — never creates one (safe during shutdown)."""
    return _client


def trace_attributes(**kwargs):
    """langfuse.propagate_attributes(...) or a null context when unavailable.

    Lets call sites write `with trace_attributes(session_id=...):` without
    caring whether Langfuse is active.
    """
    try:
        from langfuse import propagate_attributes

        return propagate_attributes(**kwargs)
    except Exception:
        import contextlib

        return contextlib.nullcontext()


def setup_voice_tracing(room_name: str):
    """Wire LiveKit's OTel spans into Langfuse for this job process.

    Call inside the rtc_session entrypoint BEFORE the AgentSession starts, so
    session/turn/llm/tts spans land under the shared provider. Each LiveKit
    job runs in its own subprocess, so the global tracer provider set here
    never leaks across concurrent sessions.

    Returns the TracerProvider (caller should force_flush it on shutdown),
    or None when tracing is disabled.
    """
    if not langfuse_enabled():
        return None
    try:
        from langfuse import Langfuse
        from livekit.agents.telemetry import set_tracer_provider
        from opentelemetry.sdk.trace import TracerProvider

        provider = TracerProvider()
        # metadata is stamped onto every LiveKit span; langfuse.session.id
        # groups the whole voice session as one Langfuse session.
        set_tracer_provider(provider, metadata={"langfuse.session.id": room_name})
        Langfuse(
            base_url=_base_url(),
            tracer_provider=provider,
            # LiveKit emits internal spans that Langfuse would drop by default.
            should_export_span=lambda span: True,
        )
        logger.info("LiveKit → Langfuse tracing enabled (room=%s)", room_name)
        return provider
    except Exception as e:
        logger.warning("Voice tracing disabled: %s", e)
        return None


# ─── Session usage & cost estimates ─────────────────────────────────
# LiveKit's usage counters are OTel *metrics*, which Langfuse does not ingest,
# so we aggregate them with UsageCollector and attach one summary span per
# session. Prices are USD estimates, overridable via env (see .env.example).

_PRICE_DEFAULTS = {
    # Fallback only: voice LLM cost normally comes from llm_voice's per-model
    # accounting (real token counts x llm_models.MODEL_PRICES_PER_M).
    "COST_LLM_INPUT_PER_1M": 0.30,
    "COST_LLM_OUTPUT_PER_1M": 1.20,
    "COST_STT_PER_MIN": 0.0077,  # deepgram nova-3 streaming
    # Cartesia sonic-3 with an instant-cloned voice: 1 credit per character.
    # Pro plan ($5/mo) includes 100k credits, then pay-as-you-go overage at
    # $65 per 1M credits (cartesia.ai/pricing, 2026-10-22). The overage rate is
    # the marginal cost once included credits run out, so it's the default.
    "COST_TTS_PER_1K_CHARS": 0.065,
}


def _price(name: str) -> float:
    try:
        return float(os.environ.get(name, _PRICE_DEFAULTS[name]))
    except ValueError:
        return _PRICE_DEFAULTS[name]


def estimate_session_costs(
    *,
    llm_prompt_tokens: int = 0,
    llm_completion_tokens: int = 0,
    stt_audio_duration: float = 0.0,
    tts_characters_count: int = 0,
    llm_usd: float | None = None,
    **_ignored,
) -> dict:
    """USD cost estimates for one voice session's usage summary. `llm_usd`, when
    known from per-model accounting, replaces the flat-rate LLM estimate."""
    if llm_usd is None:
        llm_usd = (
            llm_prompt_tokens * _price("COST_LLM_INPUT_PER_1M")
            + llm_completion_tokens * _price("COST_LLM_OUTPUT_PER_1M")
        ) / 1_000_000
    stt_usd = (stt_audio_duration / 60.0) * _price("COST_STT_PER_MIN")
    tts_usd = (tts_characters_count / 1000.0) * _price("COST_TTS_PER_1K_CHARS")
    return {
        "llm_usd": round(llm_usd, 6),
        "stt_usd": round(stt_usd, 6),
        "tts_usd": round(tts_usd, 6),
        "total_usd": round(llm_usd + stt_usd + tts_usd, 6),
    }


def attach_usage_reporter(session, ctx, room_name: str):
    """Collect per-session usage metrics; emit a summary at session end.

    Always logs the summary. When Langfuse is enabled, also records it as a
    `voice_session_usage` span so cost/usage shows up next to the trace.
    Safe to call unconditionally — failures only log.
    """
    try:
        from livekit.agents import metrics

        # `session_usage_updated` replaces the deprecated `metrics_collected`
        # event for usage tracking. Each firing carries the session's full
        # cumulative usage snapshot (ev.usage.model_usage — one entry per
        # provider/model pair), so we just keep the latest one around instead
        # of accumulating manually with UsageCollector (also deprecated).
        latest_usage: dict[str, "metrics.AgentSessionUsage | None"] = {"value": None}

        @session.on("session_usage_updated")
        def _on_usage(ev):
            latest_usage["value"] = ev.usage

        def _summarize(usage) -> dict:
            llm_prompt_tokens = 0
            llm_completion_tokens = 0
            stt_audio_duration = 0.0
            tts_characters_count = 0
            for u in (usage.model_usage if usage else []):
                if isinstance(u, metrics.LLMModelUsage):
                    llm_prompt_tokens += u.input_tokens
                    llm_completion_tokens += u.output_tokens
                elif isinstance(u, metrics.STTModelUsage):
                    stt_audio_duration += u.audio_duration
                elif isinstance(u, metrics.TTSModelUsage):
                    tts_characters_count += u.characters_count
            return {
                "llm_prompt_tokens": llm_prompt_tokens,
                "llm_completion_tokens": llm_completion_tokens,
                "stt_audio_duration": stt_audio_duration,
                "tts_characters_count": tts_characters_count,
            }

        async def _report():
            try:
                summary = _summarize(latest_usage["value"])
                llm_usd = None
                try:
                    import llm_voice

                    by_model = llm_voice.usage_summary(getattr(session, "llm", None))
                except Exception:
                    by_model = {}
                if by_model:
                    # LiveKit's own LLM counters read 0 behind the fallback
                    # adapter (first real call, 2026-10-21); ours are real.
                    summary["llm_prompt_tokens"] = sum(m["prompt_tokens"] for m in by_model.values())
                    summary["llm_cached_tokens"] = sum(m["cached_tokens"] for m in by_model.values())
                    summary["llm_completion_tokens"] = sum(m["completion_tokens"] for m in by_model.values())
                    known = [m["est_usd"] for m in by_model.values() if m["est_usd"] is not None]
                    llm_usd = sum(known) if known else None
                    summary["llm_by_model"] = {
                        k: {**v, "est_usd": round(v["est_usd"], 6) if v["est_usd"] is not None else None}
                        for k, v in by_model.items()
                    }
                costs = estimate_session_costs(**summary, llm_usd=llm_usd)
                logger.info(
                    "Session usage (room=%s): %s | est costs: %s",
                    room_name,
                    summary,
                    costs,
                )
                client = get_langfuse()
                if client is not None:
                    with client.start_as_current_observation(
                        name="voice_session_usage"
                    ) as span:
                        with trace_attributes(session_id=room_name, tags=["voice"]):
                            span.update(
                                metadata={
                                    "room": room_name,
                                    "llm_prompt_tokens": summary["llm_prompt_tokens"],
                                    "llm_completion_tokens": summary["llm_completion_tokens"],
                                    "stt_audio_seconds": round(
                                        summary["stt_audio_duration"], 2
                                    ),
                                    "tts_characters": summary["tts_characters_count"],
                                    "estimated_costs_usd": costs,
                                }
                            )
            except Exception as e:
                logger.warning("Usage report failed: %s", e)

        ctx.add_shutdown_callback(_report)
    except Exception as e:
        logger.warning("Usage reporter not attached: %s", e)


def shutdown():
    """Flush pending Langfuse events; called from server cleanup hooks."""
    client = peek_langfuse()
    if client is not None:
        try:
            client.shutdown()
        except Exception as e:
            logger.warning("Langfuse shutdown error: %s", e)
