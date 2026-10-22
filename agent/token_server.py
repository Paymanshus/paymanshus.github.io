"""
HTTP server for LiveKit tokens + terminal chat LLM.

Runs inside the same Python process as the voice agent on port 8080.

Endpoints:
    GET|POST /api/token   → {serverUrl, participantToken, room} (LiveKit room token)
    POST     /api/chat    → {reply} (Gemini answer grounded in resume BM25 context)
    GET      /api/health  → {status: "ok"}
    GET      /api/voice/status → availability: 5-call cap, daily/monthly limits
                                 (see voice_availability.py)
    POST     /api/voice/notify → {email, reason}: "tell me when AI me is back"
    OPTIONS  *            → CORS preflight

Security:
    - Tokens are short-lived (10 min) and scoped to a unique per-visitor room
    - Every token embeds RoomAgentDispatch for `paymanshu-voice` — without this
      a named agent never joins the room (explicit-dispatch rule)
    - CORS restricted to known origins
    - In-memory per-IP and global rate limits on both endpoints
"""

import os
import json
import time
import asyncio
import uuid
import hashlib
import logging
from datetime import timedelta
from collections import defaultdict

from aiohttp import web
from livekit import api

from observability import get_langfuse, trace_attributes
import observability
import llm_models
import llm_context
import llm_health
import llm_ladder
from prompts import TERMINAL_PERSONA_BODY
import voice_availability

logger = logging.getLogger("token-server")

AGENT_NAME = "paymanshu-voice"
TOKEN_TTL_SECONDS = 600  # 10 minutes

ALLOWED_ORIGINS = [
    "https://paymanshus.github.io",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
]

# ─── Rate limiting (in-memory; resets on process restart) ──────────
# Per-IP sliding windows, plus GLOBAL per-minute and per-day caps.
#
# The global PER-MINUTE cap is the one that protects upstream RPM quotas during a
# concurrency spike — per-IP limits do nothing when 40 different visitors arrive
# at once. Without it, a spike saturates Gemini's free RPM in seconds.
#
# The global PER-DAY caps are cost backstops, and the chat one is deliberately
# generous now: a fully-paid day at these limits is ~$1.20 on DeepSeek-V4-Flash
# pricing, and the real hard ceiling has moved to the OpenRouter provisioning
# key's monthly `limit` (see agent/RUN.md), which — unlike these counters —
# survives a restart. The token cap stays at 300/day because it bounds Cartesia
# TTS and LiveKit minutes, which genuinely are the expensive part (~$0.10 per
# voice session vs ~$0.003 of LLM).
#
# Known limitation: per-IP limiting is weak behind CGNAT, and a lot of Indian
# mobile traffic shares egress IPs, so on a spike day several genuine visitors
# can share one IP's minute budget. The 429 is friendly and the terminal degrades
# to its keyword fallback, so this is accepted rather than solved — but don't
# tighten the per-IP numbers without weighing it.

RATE_LIMITS = {
    # endpoint: (per-ip per-minute, per-ip per-day, global per-day, global per-minute)
    "token": (6, 30, 300, 20),
    "chat": (10, 100, 3000, 60),
    "notify": (3, 10, 2000, 30),
}

_minute_hits: dict[str, list[float]] = defaultdict(list)
_day_hits: dict[str, list[float]] = defaultdict(list)
_global_day_hits: dict[str, list[float]] = defaultdict(list)
_global_minute_hits: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: web.Request) -> str:
    # fly.io / proxies set X-Forwarded-For; fall back to socket peer
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote or "unknown"


def _check_rate_limit(request: web.Request, endpoint: str) -> str | None:
    """Returns an error string if rate-limited, else None."""
    per_min, per_day, global_day, global_min = RATE_LIMITS[endpoint]
    ip = _client_ip(request)
    now = time.time()
    minute_key = f"{endpoint}:{ip}"
    day_key = f"{endpoint}:{ip}"

    _minute_hits[minute_key] = [t for t in _minute_hits[minute_key] if now - t < 60]
    _day_hits[day_key] = [t for t in _day_hits[day_key] if now - t < 86400]
    _global_day_hits[endpoint] = [t for t in _global_day_hits[endpoint] if now - t < 86400]
    _global_minute_hits[endpoint] = [t for t in _global_minute_hits[endpoint] if now - t < 60]

    if len(_global_day_hits[endpoint]) >= global_day:
        return "Daily capacity reached. Please try again tomorrow."
    if len(_day_hits[day_key]) >= per_day:
        return "Daily limit reached for your connection. Try again tomorrow."
    if len(_global_minute_hits[endpoint]) >= global_min:
        # Load shedding during a spike. Deliberately worded as "busy" rather than
        # "you did something wrong" — this visitor did nothing unusual.
        return "Busy right now — lots of visitors. Try again in a few seconds."
    if len(_minute_hits[minute_key]) >= per_min:
        return "Slow down a little — too many requests. Try again in a minute."

    _minute_hits[minute_key].append(now)
    _day_hits[day_key].append(now)
    _global_day_hits[endpoint].append(now)
    _global_minute_hits[endpoint].append(now)
    return None


# ─── CORS ───────────────────────────────────────────────────────────

def _cors_headers(request: web.Request) -> dict[str, str]:
    origin = request.headers.get("Origin", "")
    allowed = origin if origin in ALLOWED_ORIGINS else ALLOWED_ORIGINS[0]
    return {
        "Access-Control-Allow-Origin": allowed,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "3600",
        # Chrome Local Network Access: lets the public HTTPS site call this
        # server when it runs on the visitor's own machine (owner demo mode).
        # Harmless for the normal fly.io deployment.
        "Access-Control-Allow-Private-Network": "true",
    }


async def handle_cors_preflight(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=_cors_headers(request))


# ─── /api/token ─────────────────────────────────────────────────────

def _daily_token_cap_reached() -> bool:
    now = time.time()
    hits = [t for t in _global_day_hits["token"] if now - t < 86400]
    return len(hits) >= RATE_LIMITS["token"][2]


async def _voice_status() -> voice_availability.Status:
    return await voice_availability.status(daily_cap_reached=_daily_token_cap_reached())


async def generate_token(request: web.Request) -> web.Response:
    # Availability first: a 6th caller must be turned away here, because past
    # this point LiveKit's 5-session cap fails silently (the agent never joins).
    st = await _voice_status()
    if not st.available:
        return web.json_response(
            {"error": st.reason, **st.to_json()}, status=503, headers=_cors_headers(request)
        )

    if err := _check_rate_limit(request, "token"):
        return web.json_response({"error": err}, status=429, headers=_cors_headers(request))

    api_key = os.environ.get("LIVEKIT_API_KEY")
    api_secret = os.environ.get("LIVEKIT_API_SECRET")
    livekit_url = os.environ.get("LIVEKIT_URL")
    if not all([api_key, api_secret, livekit_url]):
        logger.error("Missing LiveKit credentials in environment")
        return web.json_response(
            {"error": "Server misconfigured"}, status=500, headers=_cors_headers(request)
        )

    room_name = f"voice-resume-{uuid.uuid4().hex[:8]}"
    participant_identity = f"visitor-{uuid.uuid4().hex[:6]}"

    token = (
        api.AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity(participant_identity)
        .with_name("Website Visitor")
        .with_ttl(timedelta(seconds=TOKEN_TTL_SECONDS))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
        # Named agents are never auto-dispatched: the token must request it.
        .with_room_config(
            api.RoomConfiguration(
                agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)],
            )
        )
    )
    jwt = token.to_jwt()
    voice_availability.reserve(room_name)

    logger.info(
        "Token minted: room=%s participant=%s origin=%s",
        room_name, participant_identity, request.headers.get("Origin", "unknown"),
    )
    # The voice job starts a few seconds from now; check the first rungs so the
    # session builds its ladder from fresh health (debounced; never awaited).
    llm_health.scheduler.kick()

    # Both key styles so TokenSource.endpoint() and hand-rolled fetches work
    return web.json_response(
        {
            "serverUrl": livekit_url,
            "participantToken": jwt,
            "server_url": livekit_url,
            "participant_token": jwt,
            "token": jwt,
            "url": livekit_url,
            "room": room_name,
        },
        headers=_cors_headers(request),
    )


# ─── /api/chat — terminal LLM ───────────────────────────────────────
# Model selection, fallback and the quota breaker all live in llm_ladder; the
# persona lives in prompts; the prompt layout lives in llm_context. This module
# only does HTTP, rate limiting and tracing.

MAX_MESSAGE_CHARS = 500
MAX_HISTORY_TURNS = 6


def _visitor_id(ip: str) -> str:
    """Pseudonymous visitor id — never ship raw IPs to Langfuse."""
    return "visitor-" + hashlib.sha256(ip.encode()).hexdigest()[:12]


def _record_attempt(ctx, entry, outcome) -> None:
    """Record one ladder attempt as a Langfuse generation.

    Called once per attempted entry so the whole fallback walk is visible in a
    single trace — a failed Gemini attempt followed by an OpenRouter success
    shows as two generations, the first ERROR-level.

    Kept here rather than in llm_ladder so the ladder has no Langfuse dependency
    and stays importable from scripts/.
    """
    langfuse = get_langfuse()
    if langfuse is None:
        return
    try:
        is_error = isinstance(outcome, llm_ladder.LLMError)
        gen = langfuse.start_observation(
            as_type="generation",
            name=entry.label,
            model=(entry.model if is_error else (outcome.resolved_model or entry.model)),
            input={"system": ctx.system, "turns": ctx.turns},
            model_parameters={
                "max_output_tokens": llm_models.TERMINAL_MAX_OUTPUT_TOKENS,
                "temperature": llm_models.TERMINAL_TEMPERATURE,
                "context_mode": ctx.mode,
            },
        )
        if is_error:
            gen.update(level="ERROR", status_message=f"{outcome.kind}: {outcome.message}"[:500])
        else:
            gen.update(
                output=outcome.text,
                usage_details={
                    "input": outcome.prompt_tokens,
                    "output": outcome.completion_tokens,
                    # Cached reads are billed at a fraction of the input rate, so
                    # surfacing them separately keeps Langfuse's cost estimate honest.
                    "cache_read_input_tokens": outcome.cached_tokens,
                },
                # Real cost from the provider beats our hardcoded price table,
                # which can only ever be right for direct Gemini calls.
                cost_details=({"total": outcome.cost} if outcome.cost is not None else None),
                metadata={"latency_ms": round(outcome.total_ms, 1)},
            )
        gen.end()
    except Exception as e:
        logger.warning("Langfuse generation record failed: %s", e)


async def _generate_reply(ctx, *, session_id: str | None = None,
                          on_delta=None) -> tuple[str, str | None]:
    """Walk the terminal ladder. Returns (reply, model_used); ("", None) on
    exhaustion, which the caller turns into 503 llm_unavailable. With
    `on_delta`, text is relayed as it streams (see chat_stream)."""
    extra = {"on_delta": on_delta} if on_delta is not None else {}
    result = await llm_ladder.generate(
        ctx,
        ladder=llm_models.LLM_LADDER,
        surface="terminal",
        max_tokens=llm_models.TERMINAL_MAX_OUTPUT_TOKENS,
        temperature=llm_models.TERMINAL_TEMPERATURE,
        session_id=session_id,
        on_attempt=lambda entry, outcome: _record_attempt(ctx, entry, outcome),
        **extra,
    )
    if result is None:
        return "", None
    usd = result.cost
    if usd is None:
        usd = llm_models.estimate_llm_usd(
            result.resolved_model or "", result.prompt_tokens,
            result.cached_tokens, result.completion_tokens,
        )
    logger.info(
        "terminal llm-usage served=%s total_ms=%.0f in=%d cached=%d out=%d usd=%s attempts=%s",
        result.resolved_model or result.entry_label, result.total_ms, result.prompt_tokens,
        result.cached_tokens, result.completion_tokens,
        f"{usd:.6f}" if usd is not None else "?", ",".join(result.attempts),
    )
    return result.text, (result.resolved_model or result.entry_label)


async def _parse_chat_request(request: web.Request):
    """Shared by /api/chat and /api/chat/stream: rate limit, validate, build the
    prompt. Returns (ctx, message, history, visitor, session_id) or an error
    response to send as-is."""
    if err := _check_rate_limit(request, "chat"):
        return web.json_response({"error": err}, status=429, headers=_cors_headers(request))

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400, headers=_cors_headers(request))

    message = str(body.get("message", "")).strip()[:MAX_MESSAGE_CHARS]
    if not message:
        return web.json_response({"error": "Empty message"}, status=400, headers=_cors_headers(request))

    history = body.get("history", [])
    if not isinstance(history, list):
        history = []
    history = history[-MAX_HISTORY_TURNS:]

    from resume_context import get_resume_index

    # Where the resume goes (system prefix vs user turn) is the active context
    # mode's decision — it determines whether the prompt prefix is cacheable.
    # See llm_context and tests/eval_context_modes.py.
    ctx = llm_context.build(
        message, history,
        persona_body=TERMINAL_PERSONA_BODY,
        index=get_resume_index(),
        max_chars=MAX_MESSAGE_CHARS,
    )

    visitor = _visitor_id(_client_ip(request))
    # Doubles as OpenRouter's sticky-routing key, which keeps a returning visitor
    # on the provider holding their cached prefix.
    session_id = f"terminal-{visitor}-{time.strftime('%Y%m%d')}"
    return ctx, message, history, visitor, session_id


async def chat_stream(request: web.Request) -> web.StreamResponse:
    """/api/chat streamed as Server-Sent Events: `data: {"delta": "..."}` per
    text piece, then `data: {"done": true}`, or `data: {"error": "llm_unavailable"}`
    (the frontend then uses its local fallback, same as a 503 from /api/chat).

    SSE rather than a websocket: tokens only flow one way, it's a plain POST
    the browser can read with fetch(), and Caddy passes text/event-stream
    through unbuffered. Validation errors (rate limit, bad JSON) are ordinary
    JSON responses before the stream starts.
    """
    parsed = await _parse_chat_request(request)
    if isinstance(parsed, web.StreamResponse):
        return parsed
    ctx, message, history, visitor, session_id = parsed

    resp = web.StreamResponse(headers={
        **_cors_headers(request),
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
    await resp.prepare(request)

    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        _generate_reply(ctx, session_id=session_id, on_delta=queue.put_nowait)
    )
    try:
        while True:
            get = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait({get, task}, return_when=asyncio.FIRST_COMPLETED)
            if get in done:
                await resp.write(f"data: {json.dumps({'delta': get.result()})}\n\n".encode())
                continue
            get.cancel()
            while not queue.empty():  # pieces that landed with the last chunk
                await resp.write(f"data: {json.dumps({'delta': queue.get_nowait()})}\n\n".encode())
            reply, _model = task.result()
            final = {"done": True} if reply else {"error": "llm_unavailable"}
            await resp.write(f"data: {json.dumps(final)}\n\n".encode())
            break
    except (ConnectionResetError, asyncio.CancelledError):
        # Visitor closed the tab mid-reply: stop paying for the rest of it.
        task.cancel()
        raise
    await resp.write_eof()
    return resp


async def chat(request: web.Request) -> web.Response:
    parsed = await _parse_chat_request(request)
    if isinstance(parsed, web.StreamResponse):
        return parsed
    ctx, message, history, visitor, session_id = parsed

    langfuse = get_langfuse()
    if langfuse is not None:
        # One Langfuse trace per request; the visitor is a pseudonymous hash
        # of the client IP, sessions bucket a visitor's messages by day.
        with langfuse.start_as_current_observation(name="terminal-chat") as span:
            with trace_attributes(
                user_id=visitor,
                session_id=session_id,
                tags=["terminal"],
            ):
                reply, model_used = await _generate_reply(ctx, session_id=session_id)
                span.update(
                    input={"message": message, "history_turns": len(history)},
                    output=reply or "(llm_unavailable)",
                    metadata={
                        "model_used": model_used,
                        "context_mode": ctx.mode,
                        "prefix_chars": len(ctx.system),
                        "bm25_score": round(ctx.bm25_score, 2),
                        "breaker": llm_ladder.breaker.snapshot(),
                    },
                )
    else:
        reply, model_used = await _generate_reply(ctx, session_id=session_id)

    if not reply:
        # Signal the frontend to use its local keyword fallback
        return web.json_response(
            {"error": "llm_unavailable"}, status=503, headers=_cors_headers(request)
        )

    return web.json_response({"reply": reply}, headers=_cors_headers(request))


# ─── /api/voice/status, /api/voice/notify ──────────────────────────

async def voice_status(request: web.Request) -> web.Response:
    st = await _voice_status()
    return web.json_response(st.to_json(), headers=_cors_headers(request))


async def voice_notify(request: web.Request) -> web.Response:
    if err := _check_rate_limit(request, "notify"):
        return web.json_response({"error": err}, status=429, headers=_cors_headers(request))
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400, headers=_cors_headers(request))
    reason = str(body.get("reason") or "unknown")[:32]
    if not voice_availability.add_to_waitlist(str(body.get("email") or ""), reason):
        return web.json_response({"error": "invalid_email"}, status=400, headers=_cors_headers(request))
    return web.json_response({"ok": True}, headers=_cors_headers(request))


# ─── /api/health ────────────────────────────────────────────────────

async def health_check(request: web.Request) -> web.Response:
    return web.json_response(
        {"status": "ok", "service": "voice-agent-token-server"},
        headers=_cors_headers(request),
    )


# ─── App factory ────────────────────────────────────────────────────

async def _flush_observability(app: web.Application) -> None:
    observability.shutdown()


async def _start_canaries(app: web.Application) -> None:
    logger.info(llm_models.describe())
    llm_health.scheduler.start()


async def _stop_canaries(app: web.Application) -> None:
    await llm_health.scheduler.stop()


WAITLIST_TASK = web.AppKey("waitlist_task", asyncio.Task)


async def _start_waitlist_notifier(app: web.Application) -> None:
    app[WAITLIST_TASK] = asyncio.create_task(voice_availability.notify_loop())


async def _stop_waitlist_notifier(app: web.Application) -> None:
    task = app.get(WAITLIST_TASK)
    if task:
        task.cancel()


def create_token_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(_start_canaries)
    app.on_cleanup.append(_stop_canaries)
    app.on_startup.append(_start_waitlist_notifier)
    app.on_cleanup.append(_stop_waitlist_notifier)
    app.on_cleanup.append(_flush_observability)
    app.router.add_get("/api/token", generate_token)
    app.router.add_post("/api/token", generate_token)
    app.router.add_options("/api/token", handle_cors_preflight)
    app.router.add_post("/api/chat", chat)
    app.router.add_options("/api/chat", handle_cors_preflight)
    app.router.add_post("/api/chat/stream", chat_stream)
    app.router.add_options("/api/chat/stream", handle_cors_preflight)
    app.router.add_get("/api/health", health_check)
    app.router.add_get("/api/voice/status", voice_status)
    app.router.add_post("/api/voice/notify", voice_notify)
    app.router.add_options("/api/voice/notify", handle_cors_preflight)
    logger.info(
        "Token server routes registered: /api/token, /api/chat, /api/health, "
        "/api/voice/status, /api/voice/notify"
    )
    return app


if __name__ == "__main__":
    # Standalone mode for local testing: python token_server.py
    from dotenv import load_dotenv
    load_dotenv(".env.local")
    logging.basicConfig(level=logging.INFO)
    web.run_app(create_token_app(), port=8080)
