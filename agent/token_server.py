"""
HTTP server for LiveKit tokens + terminal chat LLM.

Runs inside the same Python process as the voice agent on port 8080.

Endpoints:
    GET|POST /api/token   → {serverUrl, participantToken, room} (LiveKit room token)
    POST     /api/chat    → {reply} (Gemini answer grounded in resume BM25 context)
    GET      /api/health  → {status: "ok"}
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
import uuid
import hashlib
import logging
from datetime import timedelta
from collections import defaultdict

from aiohttp import web
from livekit import api

from observability import get_langfuse, trace_attributes
import observability

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
# Per-IP sliding windows + a global daily cap as a cost backstop.

RATE_LIMITS = {
    # endpoint: (per-ip per-minute, per-ip per-day, global per-day)
    "token": (6, 30, 300),
    "chat": (10, 60, 1000),
}

_minute_hits: dict[str, list[float]] = defaultdict(list)
_day_hits: dict[str, list[float]] = defaultdict(list)
_global_day_hits: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: web.Request) -> str:
    # fly.io / proxies set X-Forwarded-For; fall back to socket peer
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote or "unknown"


def _check_rate_limit(request: web.Request, endpoint: str) -> str | None:
    """Returns an error string if rate-limited, else None."""
    per_min, per_day, global_day = RATE_LIMITS[endpoint]
    ip = _client_ip(request)
    now = time.time()
    minute_key = f"{endpoint}:{ip}"
    day_key = f"{endpoint}:{ip}"

    _minute_hits[minute_key] = [t for t in _minute_hits[minute_key] if now - t < 60]
    _day_hits[day_key] = [t for t in _day_hits[day_key] if now - t < 86400]
    _global_day_hits[endpoint] = [t for t in _global_day_hits[endpoint] if now - t < 86400]

    if len(_global_day_hits[endpoint]) >= global_day:
        return "Daily capacity reached. Please try again tomorrow."
    if len(_day_hits[day_key]) >= per_day:
        return "Daily limit reached for your connection. Try again tomorrow."
    if len(_minute_hits[minute_key]) >= per_min:
        return "Slow down a little — too many requests. Try again in a minute."

    _minute_hits[minute_key].append(now)
    _day_hits[day_key].append(now)
    _global_day_hits[endpoint].append(now)
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
    }


async def handle_cors_preflight(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=_cors_headers(request))


# ─── /api/token ─────────────────────────────────────────────────────

async def generate_token(request: web.Request) -> web.Response:
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

    logger.info(
        "Token minted: room=%s participant=%s origin=%s",
        room_name, participant_identity, request.headers.get("Origin", "unknown"),
    )

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

TERMINAL_PERSONA = """\
You are the terminal interface of Paymanshu Sharma's portfolio site, answering
as Paymanshu in first person. You are a Machine Learning Engineer at Maersk,
Bangalore. Answer questions about your experience, skills, projects, and
education using ONLY the resume context provided below. Be terse: 1-3 short
lines max (this renders in a terminal), plain text only: no markdown, no emoji.
If the context doesn't cover the question, say so honestly in one line and
suggest the voice mode or the PDF resume. Never invent facts.

RESUME CONTEXT:
{context}
"""

MAX_MESSAGE_CHARS = 500
MAX_HISTORY_TURNS = 6

GENERATION_CONFIG = {"max_output_tokens": 200, "temperature": 0.6}

_genai_client = None


def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        from google import genai
        _genai_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _genai_client


def _visitor_id(ip: str) -> str:
    """Pseudonymous visitor id — never ship raw IPs to Langfuse."""
    return "visitor-" + hashlib.sha256(ip.encode()).hexdigest()[:12]


async def _generate_reply(
    models: list[str], contents: list[dict], system_instruction: str
) -> tuple[str, str | None]:
    """Try each Gemini model in order; returns (reply, model_used).

    When Langfuse is enabled, each attempt is recorded as a generation
    (prompt, output, token usage → cost); failed attempts are ERROR-level
    generations so the fallback chain is visible per trace.
    """
    langfuse = get_langfuse()
    for model in dict.fromkeys(models):
        gen = None
        if langfuse is not None:
            try:
                gen = langfuse.start_observation(
                    as_type="generation",
                    name=f"gemini:{model}",
                    model=model,
                    input={
                        "system_instruction": system_instruction,
                        "contents": contents,
                    },
                    model_parameters=dict(GENERATION_CONFIG),
                )
            except Exception as e:
                logger.warning("Langfuse generation start failed: %s", e)
        try:
            client = _get_genai_client()
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config={"system_instruction": system_instruction, **GENERATION_CONFIG},
            )
            reply = (response.text or "").strip()
            if gen is not None:
                usage = getattr(response, "usage_metadata", None)
                usage_details = None
                if usage is not None:
                    usage_details = {
                        "input": getattr(usage, "prompt_token_count", 0) or 0,
                        "output": getattr(usage, "candidates_token_count", 0) or 0,
                    }
                gen.update(output=reply, usage_details=usage_details)
                gen.end()
            if reply:
                return reply, model
        except Exception as e:
            logger.warning("Chat LLM %s failed: %s", model, e)
            if gen is not None:
                gen.update(level="ERROR", status_message=str(e)[:500])
                gen.end()
    return "", None


async def chat(request: web.Request) -> web.Response:
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

    # Ground the answer with BM25 sections for the query
    from resume_context import get_resume_index
    context = get_resume_index().search(message, top_k=3)

    contents = []
    for turn in history:
        role = "user" if turn.get("role") == "user" else "model"
        text = str(turn.get("text", ""))[:MAX_MESSAGE_CHARS]
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    # Primary model first; free-tier capacity blips (503s) and silent model
    # sunsets (404s — 2.5-flash/-lite died in mid-2026) are common, so fall
    # through the chain before telling the frontend to go keyword-only.
    # `gemini-flash-lite-latest` is Google's rolling alias — it survives
    # sunsets. Availability probe: python tests/probe_gemini.py
    models = [
        os.environ.get("TERMINAL_LLM_MODEL", "gemini-3.1-flash-lite"),
        "gemini-flash-lite-latest",
        "gemini-3.5-flash",
    ]
    system_instruction = TERMINAL_PERSONA.format(context=context)

    langfuse = get_langfuse()
    if langfuse is not None:
        # One Langfuse trace per request; the visitor is a pseudonymous hash
        # of the client IP, sessions bucket a visitor's messages by day.
        visitor = _visitor_id(_client_ip(request))
        with langfuse.start_as_current_observation(name="terminal-chat") as span:
            with trace_attributes(
                user_id=visitor,
                session_id=f"terminal-{visitor}-{time.strftime('%Y%m%d')}",
                tags=["terminal"],
            ):
                reply, model_used = await _generate_reply(
                    models, contents, system_instruction
                )
                span.update(
                    input={"message": message, "history_turns": len(history)},
                    output=reply or "(llm_unavailable)",
                    metadata={
                        "model_used": model_used,
                        "context_chars": len(context),
                    },
                )
    else:
        reply, model_used = await _generate_reply(models, contents, system_instruction)

    if not reply:
        # Signal the frontend to use its local keyword fallback
        return web.json_response(
            {"error": "llm_unavailable"}, status=503, headers=_cors_headers(request)
        )

    return web.json_response({"reply": reply}, headers=_cors_headers(request))


# ─── /api/health ────────────────────────────────────────────────────

async def health_check(request: web.Request) -> web.Response:
    return web.json_response(
        {"status": "ok", "service": "voice-agent-token-server"},
        headers=_cors_headers(request),
    )


# ─── App factory ────────────────────────────────────────────────────

async def _flush_observability(app: web.Application) -> None:
    observability.shutdown()


def create_token_app() -> web.Application:
    app = web.Application()
    app.on_cleanup.append(_flush_observability)
    app.router.add_get("/api/token", generate_token)
    app.router.add_post("/api/token", generate_token)
    app.router.add_options("/api/token", handle_cors_preflight)
    app.router.add_post("/api/chat", chat)
    app.router.add_options("/api/chat", handle_cors_preflight)
    app.router.add_get("/api/health", health_check)
    logger.info("Token server routes registered: /api/token, /api/chat, /api/health")
    return app


if __name__ == "__main__":
    # Standalone mode for local testing: python token_server.py
    from dotenv import load_dotenv
    load_dotenv(".env.local")
    logging.basicConfig(level=logging.INFO)
    web.run_app(create_token_app(), port=8080)
