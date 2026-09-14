"""
Ordered multi-provider LLM ladder with a shared, quota-scope-aware breaker.

WHAT THIS REPLACES
    Three duplicated Gemini model chains (token_server, main, sync_resume) that
    each had the same three defects:
      1. No timeout — a hung upstream call stalled a voice turn indefinitely.
      2. `except Exception: continue` — a 429 was retried against models sharing
         the same quota, burning two more doomed ~200ms round trips.
      3. No memory — 50 concurrent visitors each rediscovered the same 429.

THE BREAKER IS THE POINT
    State is module-level, so a lockout is global across every user, every
    session, and (via llm_voice.breaker_guard) both the terminal and voice
    surfaces. One visitor's 429 immediately stops everyone else probing the dead
    entry. Locked entries are skipped with ZERO network calls.

    Lock duration is scoped to what actually failed:
      per-minute quota → next minute boundary (or the upstream reset hint)
      per-day quota    → the upstream reset instant. NOTE these differ by
                         provider: Gemini free tier resets midnight America/
                         Los_Angeles, OpenRouter midnight UTC.
      timeout / 5xx    → short backoff (llm_models.TRANSIENT_COOLDOWN_S)
      402 no credits   → locked until cleared; this is the spend cap firing
      404 model gone   → locked until restart; a stale slug to audit

    Distinguishing per-minute from per-day has no clean documented field, so it
    is an explicit heuristic (see `_classify_gemini` / `_classify_openrouter`).
    When ambiguous we assume PER-MINUTE: wrongly locking an entry for a whole day
    is far worse than retrying in 60 seconds.

    Daily locks are persisted to LLM_BREAKER_STATE_PATH and reloaded on boot,
    because the deployment runs under `Restart=always` — an in-memory-only daily
    lock would evaporate on every crash and we would re-hit an exhausted quota.
"""

import os
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp

import llm_models
from llm_models import LadderEntry
import llm_context

logger = logging.getLogger("llm-ladder")

OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)
BREAKER_STATE_PATH = Path(
    os.environ.get("LLM_BREAKER_STATE_PATH", Path(__file__).parent / ".llm_breaker.json")
)

# Optional attribution headers; harmless if unset.
OPENROUTER_REFERER = os.environ.get("OPENROUTER_REFERER", "https://paymanshus.github.io")
OPENROUTER_TITLE = os.environ.get("OPENROUTER_TITLE", "paymanshu-portfolio")


def openrouter_enabled() -> bool:
    """OpenRouter needs both a key and an explicit opt-out check.

    Read at call time, not import time, so tests can toggle it.
    """
    if os.environ.get("OPENROUTER_ENABLED", "true").lower() in ("false", "0", "no"):
        return False
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


# ─── Errors ────────────────────────────────────────────────────────

# Kinds that mean "this entry is dead for a while", mapped to lock scope.
KIND_MINUTE = "rate_limit_minute"
KIND_DAY = "rate_limit_day"
KIND_TIMEOUT = "timeout"
KIND_SERVER = "server_error"
KIND_CREDITS = "insufficient_credits"
KIND_NOT_FOUND = "model_not_found"
KIND_OTHER = "other"

# These get logged at ERROR because they need a human: either the spend cap has
# fired or the model list has gone stale.
LOUD_KINDS = (KIND_CREDITS, KIND_NOT_FOUND)


class LLMError(Exception):
    """A classified upstream failure."""

    def __init__(self, kind: str, message: str, *, until: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        # Absolute epoch seconds the entry should stay locked until. None means
        # "use the default for this kind".
        self.until = until


@dataclass
class LLMResult:
    """One successful generation, with whatever accounting the provider gave us."""

    text: str
    entry_label: str
    resolved_model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    cost: float | None = None
    ttft_ms: float | None = None
    total_ms: float = 0.0
    # Number of streamed content chunks. 1 means the provider buffered the whole
    # completion and sent it at once — which reports a fine TTFT while being bad
    # for voice, since TTS can't start early. 0 for non-streaming calls.
    chunks: int = 0
    attempts: list[str] = field(default_factory=list)


# ─── Quota reset windows ───────────────────────────────────────────

def _next_minute_boundary(now: float | None = None) -> float:
    """Top of the next wall-clock minute. Upstream per-minute windows are
    fixed-window, not sliding, so this is when quota actually frees up."""
    now = now if now is not None else time.time()
    return (int(now) // 60 + 1) * 60


def _next_midnight(tz: timezone | str, now: float | None = None) -> float:
    """Epoch seconds of the next midnight in `tz`."""
    if isinstance(tz, str):
        try:
            from zoneinfo import ZoneInfo

            tzinfo = ZoneInfo(tz)
        except Exception:  # pragma: no cover - tzdata missing
            logger.warning("timezone %s unavailable, using UTC for quota reset", tz)
            tzinfo = timezone.utc
    else:
        tzinfo = tz
    dt = datetime.fromtimestamp(now if now is not None else time.time(), tz=tzinfo)
    tomorrow = (dt + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return tomorrow.timestamp()


def _daily_reset_for(provider: str, now: float | None = None) -> float:
    # Gemini free tier resets on Pacific midnight; OpenRouter on UTC midnight.
    if provider == "gemini":
        return _next_midnight("America/Los_Angeles", now)
    return _next_midnight(timezone.utc, now)


# ─── Breaker ───────────────────────────────────────────────────────

@dataclass
class Lock:
    until: float
    kind: str
    reason: str

    @property
    def persistent(self) -> bool:
        """Daily quota and credit locks outlive a restart; short backoffs don't."""
        return self.kind in (KIND_DAY, KIND_CREDITS, KIND_NOT_FOUND)


class Breaker:
    """Process-global entry availability. Not per-user, deliberately."""

    def __init__(self, state_path: Path | None = None):
        self._locks: dict[str, Lock] = {}
        self._state_path = state_path if state_path is not None else BREAKER_STATE_PATH
        self._load()

    # -- queries --

    def locked_until(self, key: str, now: float | None = None) -> float | None:
        now = now if now is not None else time.time()
        lock = self._locks.get(key)
        if lock is None:
            return None
        if lock.until <= now:
            del self._locks[key]
            return None
        return lock.until

    def is_locked(self, key: str, now: float | None = None) -> bool:
        return self.locked_until(key, now) is not None

    def snapshot(self, now: float | None = None) -> dict[str, dict]:
        now = now if now is not None else time.time()
        return {
            key: {
                "kind": lock.kind,
                "seconds_left": round(lock.until - now, 1),
                "reason": lock.reason,
            }
            for key, lock in self._locks.items()
            if lock.until > now
        }

    # -- mutations --

    def record_failure(
        self,
        entry: LadderEntry,
        err: LLMError,
        *,
        now: float | None = None,
    ) -> None:
        """Lock `entry` for a duration derived from what went wrong."""
        now = now if now is not None else time.time()

        if err.until is not None:
            until = err.until
        elif err.kind == KIND_MINUTE:
            until = _next_minute_boundary(now)
        elif err.kind == KIND_DAY:
            until = _daily_reset_for(entry.provider, now)
        elif err.kind in (KIND_CREDITS, KIND_NOT_FOUND):
            # No automatic recovery — these need a human. Park it far out rather
            # than inventing a fake reset time.
            until = now + 86400
        elif err.kind in (KIND_TIMEOUT, KIND_SERVER):
            until = now + llm_models.TRANSIENT_COOLDOWN_S
        else:
            # Unclassified: don't lock at all. An unknown one-off shouldn't take
            # an entry out of rotation.
            return

        self._locks[entry.key] = Lock(until=until, kind=err.kind, reason=err.message[:200])
        log = logger.error if err.kind in LOUD_KINDS else logger.warning
        log(
            "breaker: locked %s for %.0fs (%s) — %s",
            entry.key, until - now, err.kind, err.message[:160],
        )
        self._save()

    def clear(self, key: str | None = None) -> None:
        if key is None:
            self._locks.clear()
        else:
            self._locks.pop(key, None)
        self._save()

    # -- persistence --

    def _load(self) -> None:
        try:
            if not self._state_path.exists():
                return
            raw = json.loads(self._state_path.read_text())
        except Exception as e:
            logger.warning("breaker state unreadable (%s) — starting clean", e)
            return
        now = time.time()
        for key, item in (raw or {}).items():
            try:
                until = float(item["until"])
            except (KeyError, TypeError, ValueError):
                continue
            if until > now:
                self._locks[key] = Lock(
                    until=until,
                    kind=str(item.get("kind", KIND_OTHER)),
                    reason=str(item.get("reason", "restored")),
                )
        if self._locks:
            logger.warning(
                "breaker: restored %d lock(s) from %s: %s",
                len(self._locks), self._state_path, list(self._locks),
            )

    def _save(self) -> None:
        persistent = {
            key: {"until": lock.until, "kind": lock.kind, "reason": lock.reason}
            for key, lock in self._locks.items()
            if lock.persistent
        }
        try:
            if not persistent:
                self._state_path.unlink(missing_ok=True)
                return
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(persistent, indent=2))
            tmp.replace(self._state_path)
        except Exception as e:
            # Losing persistence degrades recovery behaviour but must never break
            # a request.
            logger.warning("could not persist breaker state: %s", e)


breaker = Breaker()


# ─── Error classification ──────────────────────────────────────────

def _classify_gemini(exc: Exception) -> LLMError:
    """Map a google-genai exception onto a lock scope.

    The 429 body names the violated quota metric and may carry a RetryInfo
    retryDelay. There is no dedicated field saying "this was the daily quota", so
    we look for PerDay/PerMinute in the metric name and fall back to the retry
    delay: anything asking us to wait more than two minutes is a daily window.
    """
    text = str(exc)
    low = text.lower()
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)

    if "429" in text or "resource_exhausted" in low or "quota" in low:
        retry_s = None
        # RetryInfo surfaces as e.g. "retryDelay': '41s'" in the message.
        import re

        m = re.search(r"retry[_ ]?delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", low)
        if m:
            retry_s = float(m.group(1))

        per_day = "perday" in low.replace(" ", "") or "per day" in low
        per_min = "perminute" in low.replace(" ", "") or "per minute" in low
        if per_day and not per_min:
            return LLMError(KIND_DAY, f"gemini daily quota: {text[:200]}")
        if retry_s is not None and retry_s > 120:
            return LLMError(
                KIND_DAY, f"gemini quota, retryDelay={retry_s}s: {text[:160]}"
            )
        until = time.time() + retry_s if retry_s else None
        return LLMError(KIND_MINUTE, f"gemini rate limit: {text[:200]}", until=until)

    if "404" in text or "not found" in low or "is not supported" in low:
        return LLMError(KIND_NOT_FOUND, f"gemini model unavailable: {text[:200]}")
    if status in (500, 502, 503, 504) or "503" in text or "unavailable" in low:
        return LLMError(KIND_SERVER, f"gemini server error: {text[:200]}")
    if "api key" in low or "permission" in low or "401" in text or "403" in text:
        # Misconfiguration, not transient. Treat like credits: needs a human.
        return LLMError(KIND_CREDITS, f"gemini auth failure: {text[:200]}")
    return LLMError(KIND_OTHER, f"gemini error: {text[:200]}")


def _classify_openrouter(status: int, body: dict, headers) -> LLMError:
    """Map an OpenRouter error response onto a lock scope.

    `X-RateLimit-Reset` is epoch milliseconds. A reset more than five minutes out
    is a daily window; anything sooner is the per-minute one.
    """
    err = (body or {}).get("error") or {}
    message = str(err.get("message") or body or f"HTTP {status}")[:200]

    if status == 429:
        reset_ms = headers.get("X-RateLimit-Reset") if headers else None
        until = None
        if reset_ms:
            try:
                until = float(reset_ms) / 1000.0
            except (TypeError, ValueError):
                until = None
        if until is not None:
            horizon = until - time.time()
            kind = KIND_DAY if horizon > 300 else KIND_MINUTE
            return LLMError(kind, f"openrouter 429 ({int(horizon)}s): {message}", until=until)
        low = message.lower()
        if "per day" in low or "daily" in low:
            return LLMError(KIND_DAY, f"openrouter daily limit: {message}")
        # Ambiguous — assume the cheaper mistake.
        return LLMError(KIND_MINUTE, f"openrouter rate limit: {message}")

    if status == 402:
        return LLMError(KIND_CREDITS, f"openrouter out of credits: {message}")
    if status == 404:
        return LLMError(KIND_NOT_FOUND, f"openrouter model not found: {message}")
    if status in (500, 502, 503, 504):
        return LLMError(KIND_SERVER, f"openrouter {status}: {message}")
    if status in (401, 403):
        # A provisioning key in OPENROUTER_API_KEY fails exactly this way. It is
        # a management key — it mints runtime keys but cannot do inference — and
        # the bare message gives no hint, so name the likely cause. See RUN.md.
        if "user not found" in message.lower():
            return LLMError(
                KIND_CREDITS,
                "openrouter auth failure: 'User not found' usually means "
                "OPENROUTER_API_KEY holds a PROVISIONING key; it must be a "
                "runtime key (see agent/RUN.md)",
            )
        return LLMError(KIND_CREDITS, f"openrouter auth failure: {message}")
    return LLMError(KIND_OTHER, f"openrouter {status}: {message}")


# ─── Providers ─────────────────────────────────────────────────────

_genai_client = None


def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        from google import genai

        _genai_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _genai_client


# Models observed to reject `thinking_config` at runtime. Seeded from
# llm_models.gemini_supports_thinking_config and extended on a live 400 so a
# model that starts or stops supporting the field doesn't need a code change.
_no_thinking_config: set[str] = set()


def _gemini_config(
    model: str, system_instruction: str, max_tokens: int, temperature: float
) -> dict:
    config = {
        "system_instruction": system_instruction,
        "max_output_tokens": max_tokens,
        "temperature": temperature,
    }
    if (
        model not in _no_thinking_config
        and llm_models.gemini_supports_thinking_config(model)
    ):
        # Gemini 3 wants thinking_level; 2.5 wants thinking_budget=0 so
        # thinking tokens cannot eat max_output_tokens. See
        # llm_models.gemini_thinking_config.
        thinking = llm_models.gemini_thinking_config(model)
        if thinking is not None:
            config["thinking_config"] = thinking
    return config


def _is_invalid_argument(exc: Exception) -> bool:
    text = str(exc)
    return "INVALID_ARGUMENT" in text or ("400" in text and "invalid argument" in text.lower())


async def _call_gemini(
    entry: LadderEntry,
    ctx: llm_context.BuiltContext,
    *,
    timeout_ms: int,
    max_tokens: int,
    temperature: float,
    stream: bool,
) -> LLMResult:
    system_instruction, contents = llm_context.to_gemini_contents(ctx)
    config = _gemini_config(entry.model, system_instruction, max_tokens, temperature)
    client = _get_genai_client()
    started = time.perf_counter()
    ttft = None
    chunk_count = 0

    async def _run():
        nonlocal ttft
        nonlocal chunk_count
        if stream:
            text_parts = []
            usage = None
            it = await client.aio.models.generate_content_stream(
                model=entry.model, contents=contents, config=config
            )
            async for chunk in it:
                if chunk.text:
                    if ttft is None:
                        ttft = (time.perf_counter() - started) * 1000
                    chunk_count += 1
                    text_parts.append(chunk.text)
                if getattr(chunk, "usage_metadata", None):
                    usage = chunk.usage_metadata
            return "".join(text_parts), usage
        resp = await client.aio.models.generate_content(
            model=entry.model, contents=contents, config=config
        )
        return (resp.text or ""), getattr(resp, "usage_metadata", None)

    try:
        text, usage = await asyncio.wait_for(_run(), timeout=timeout_ms / 1000)
    except asyncio.TimeoutError:
        raise LLMError(KIND_TIMEOUT, f"gemini timed out after {timeout_ms}ms")
    except LLMError:
        raise
    except Exception as exc:
        # Some models (the rolling `-latest` aliases at time of writing) reject
        # thinking_config with 400 INVALID_ARGUMENT. Retry once without it and
        # remember, so the model list stays declarative and this self-heals.
        if "thinking_config" in config and _is_invalid_argument(exc):
            logger.warning(
                "%s rejected thinking_config — retrying without it", entry.model
            )
            _no_thinking_config.add(entry.model)
            config = {k: v for k, v in config.items() if k != "thinking_config"}
            try:
                text, usage = await asyncio.wait_for(_run(), timeout=timeout_ms / 1000)
            except asyncio.TimeoutError:
                raise LLMError(KIND_TIMEOUT, f"gemini timed out after {timeout_ms}ms")
            except Exception as exc2:
                raise _classify_gemini(exc2)
        else:
            raise _classify_gemini(exc)

    total_ms = (time.perf_counter() - started) * 1000
    text = (text or "").strip()
    if not text:
        # A 200 with no content is a failure for our purposes — matches the
        # original "empty reply falls through the chain" behaviour.
        raise LLMError(KIND_SERVER, "gemini returned an empty reply")

    return LLMResult(
        text=text,
        entry_label=entry.label,
        resolved_model=entry.model,
        prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
        completion_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        cached_tokens=getattr(usage, "cached_content_token_count", 0) or 0,
        ttft_ms=ttft,
        total_ms=total_ms,
        chunks=chunk_count,
    )


def _openrouter_body(
    entry: LadderEntry,
    ctx: llm_context.BuiltContext,
    *,
    surface: str,
    max_tokens: int,
    temperature: float,
    stream: bool,
    session_id: str | None,
) -> dict:
    body: dict = {
        "model": entry.model,
        "messages": llm_context.to_openai_messages(ctx),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "provider": llm_models.openrouter_provider_prefs(surface),
    }
    if len(entry.models) > 1:
        # Server-side fallback: OpenRouter walks this on rate-limit, context and
        # moderation errors, so free→paid escalation costs one round trip.
        body["models"] = list(entry.models)
    if stream:
        body["stream"] = True
    if session_id:
        # Sticky routing keeps a caller on the provider holding their cached
        # prefix. Only works because we never set provider.order.
        body["session_id"] = session_id
    return body


def _usage_from_openrouter(usage: dict | None) -> dict:
    usage = usage or {}
    details = usage.get("prompt_tokens_details") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens") or 0,
        "completion_tokens": usage.get("completion_tokens") or 0,
        "cached_tokens": details.get("cached_tokens") or 0,
        "cache_write_tokens": details.get("cache_write_tokens") or 0,
        "cost": usage.get("cost"),
    }


async def _call_openrouter(
    entry: LadderEntry,
    ctx: llm_context.BuiltContext,
    *,
    surface: str,
    timeout_ms: int,
    max_tokens: int,
    temperature: float,
    stream: bool,
    session_id: str | None,
    session: aiohttp.ClientSession | None = None,
) -> LLMResult:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise LLMError(KIND_CREDITS, "OPENROUTER_API_KEY is not set")

    body = _openrouter_body(
        entry, ctx,
        surface=surface, max_tokens=max_tokens, temperature=temperature,
        stream=stream, session_id=session_id,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": OPENROUTER_TITLE,
    }
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)

    own_session = session is None
    session = session or aiohttp.ClientSession()
    started = time.perf_counter()
    ttft = None
    chunk_count = 0
    try:
        async with session.post(url, json=body, headers=headers, timeout=timeout) as resp:
            if resp.status >= 400:
                try:
                    payload = await resp.json()
                except Exception:
                    payload = {"error": {"message": (await resp.text())[:200]}}
                raise _classify_openrouter(resp.status, payload, resp.headers)

            if not stream:
                payload = await resp.json()
                text = ""
                choices = payload.get("choices") or []
                if choices:
                    text = (choices[0].get("message") or {}).get("content") or ""
                usage = _usage_from_openrouter(payload.get("usage"))
                resolved = payload.get("model")
            else:
                text_parts: list[str] = []
                usage_raw = None
                resolved = None
                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8", "replace").strip()
                    # OpenRouter emits ": OPENROUTER PROCESSING" keepalive
                    # comments. SSE comment lines start with ':' and are not JSON.
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    resolved = chunk.get("model") or resolved
                    if chunk.get("usage"):
                        usage_raw = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        piece = (choice.get("delta") or {}).get("content")
                        if piece:
                            if ttft is None:
                                ttft = (time.perf_counter() - started) * 1000
                            chunk_count += 1
                            text_parts.append(piece)
                text = "".join(text_parts)
                usage = _usage_from_openrouter(usage_raw)
    except asyncio.TimeoutError:
        raise LLMError(KIND_TIMEOUT, f"openrouter timed out after {timeout_ms}ms")
    except aiohttp.ClientError as exc:
        raise LLMError(KIND_SERVER, f"openrouter transport error: {exc}")
    finally:
        if own_session:
            await session.close()

    total_ms = (time.perf_counter() - started) * 1000
    text = (text or "").strip()
    if not text:
        raise LLMError(KIND_SERVER, "openrouter returned an empty reply")

    return LLMResult(
        text=text,
        entry_label=entry.label,
        resolved_model=resolved or entry.model,
        ttft_ms=ttft,
        total_ms=total_ms,
        chunks=chunk_count,
        **usage,
    )


async def call_entry(
    entry: LadderEntry,
    ctx: llm_context.BuiltContext,
    *,
    surface: str = "terminal",
    timeout_ms: int | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    stream: bool = False,
    session_id: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> LLMResult:
    """Call one ladder entry. Raises LLMError; does not touch the breaker.

    Exposed separately so probes and the eval harness can exercise a single entry
    without ladder semantics.
    """
    # Precedence: explicit argument → the rung's own `~ms` override → the
    # surface default. Rungs vary by an order of magnitude in latency, so a
    # single shared timeout would either strangle the slow ones or let a hung
    # fast one stall the walk.
    timeout_ms = timeout_ms or entry.timeout_ms or llm_models.TIMEOUT_MS.get(surface, 8000)
    max_tokens = max_tokens if max_tokens is not None else llm_models.TERMINAL_MAX_OUTPUT_TOKENS
    temperature = temperature if temperature is not None else llm_models.TERMINAL_TEMPERATURE

    if entry.provider == "gemini":
        return await _call_gemini(
            entry, ctx,
            timeout_ms=timeout_ms, max_tokens=max_tokens,
            temperature=temperature, stream=stream,
        )
    if entry.provider == "openrouter":
        if not openrouter_enabled():
            raise LLMError(KIND_CREDITS, "openrouter disabled or unconfigured")
        return await _call_openrouter(
            entry, ctx,
            surface=surface, timeout_ms=timeout_ms, max_tokens=max_tokens,
            temperature=temperature, stream=stream, session_id=session_id,
            session=session,
        )
    raise LLMError(KIND_OTHER, f"unknown provider {entry.provider!r}")


# ─── The walk ──────────────────────────────────────────────────────

async def generate(
    ctx: llm_context.BuiltContext,
    *,
    ladder: "tuple[LadderEntry, ...] | None" = None,
    surface: str = "terminal",
    max_tokens: int | None = None,
    temperature: float | None = None,
    session_id: str | None = None,
    stream: bool = False,
    on_attempt=None,
) -> LLMResult | None:
    """Walk the ladder top to bottom; return the first success, else None.

    Locked entries are skipped without a network call — that is what turns a
    spike from "50 visitors each pay a doomed round trip" into "50 visitors go
    straight to the entry that works".

    `on_attempt(entry, result_or_error)` is called once per attempted entry, so
    callers can record a Langfuse generation per attempt without this module
    depending on Langfuse.
    """
    ladder = ladder if ladder is not None else llm_models.LLM_LADDER
    attempts: list[str] = []

    for entry in ladder:
        # "Not configured" is not "failed". Without this an unset
        # OPENROUTER_API_KEY would raise insufficient_credits and lock the entry
        # for 24h, which is nonsense for a key that was simply never set — and it
        # is the normal state before the account exists.
        if entry.provider == "openrouter" and not openrouter_enabled():
            attempts.append(f"{entry.label}=unconfigured")
            continue

        locked_until = breaker.locked_until(entry.key)
        if locked_until is not None:
            attempts.append(f"{entry.label}=skipped")
            logger.info(
                "ladder: skipping %s, locked for another %.0fs",
                entry.label, locked_until - time.time(),
            )
            continue

        try:
            result = await call_entry(
                entry, ctx,
                surface=surface, max_tokens=max_tokens, temperature=temperature,
                stream=stream, session_id=session_id,
            )
        except LLMError as err:
            breaker.record_failure(entry, err)
            attempts.append(f"{entry.label}={err.kind}")
            if on_attempt:
                on_attempt(entry, err)
            continue

        result.attempts = attempts + [f"{entry.label}=ok"]
        if on_attempt:
            on_attempt(entry, result)
        return result

    logger.error("ladder exhausted: %s", attempts or "(no entries)")
    return None
