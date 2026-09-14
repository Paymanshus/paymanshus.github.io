"""
Voice-side LLM wiring: build the FallbackAdapter from VOICE_LADDER, and share the
terminal's quota breaker with it.

WHY A PROXY
    LiveKit's FallbackAdapter already tracks per-instance availability and does
    background recovery, which is good — but it only learns from failures IT has
    seen. That means a voice caller would happily probe a Gemini model that the
    terminal path discovered was rate-limited thirty seconds ago, pay the doomed
    round trip, and only then fall back.

    `BreakerGuard` fixes that by consulting the shared llm_ladder.breaker before
    the call. If the entry is locked, it raises immediately — no network, no
    retries — and FallbackAdapter moves to the next entry. FallbackAdapter
    evaluates `llm.chat(...)` inside its own try block, so a synchronous raise
    there is caught and handled exactly like a real upstream failure.

DIRECTION OF INFORMATION
    Consuming shared state (terminal 429 → voice skips) is exact.
    Contributing it (voice failure → terminal skips) is coarse: LiveKit surfaces
    "this LLM became unavailable" without the upstream quota metric, so we record
    a short transient lock rather than inventing a per-minute/per-day scope we
    cannot actually observe. Precise scoping still happens on the terminal path,
    which carries most of the request volume. Deliberate trade — wrapping
    LLMStream to classify voice errors precisely costs a lot of fragile code for
    a small gain.
"""

import os
import time
import logging

from livekit.agents import APIStatusError
from livekit.agents import llm as lk_llm
from livekit.plugins import google

import llm_models
import llm_ladder

logger = logging.getLogger("llm-voice")


class BreakerGuard(lk_llm.LLM):
    """Delegates to `inner`, but short-circuits when the shared breaker says the
    entry is locked."""

    def __init__(self, inner: lk_llm.LLM, entry: llm_models.LadderEntry):
        super().__init__()
        self._inner = inner
        self._entry = entry
        # Last exception from the wrapped stream, if any. FallbackAdapter's
        # availability event does not carry the upstream body, so we remember
        # it here for record_voice_unavailable to classify 401 vs 5xx.
        self._last_error: BaseException | None = None

    @property
    def model(self) -> str:
        return self._entry.model

    @property
    def provider(self) -> str:
        return self._entry.provider

    @property
    def label(self) -> str:
        return f"guarded({self._entry.label})"

    def chat(self, **kwargs) -> lk_llm.LLMStream:
        locked_until = llm_ladder.breaker.locked_until(self._entry.key)
        if locked_until is not None:
            # 429 with retryable=False: this is a known-dead entry, so the
            # adapter should move on rather than burn its retry budget here.
            raise APIStatusError(
                f"{self._entry.label} locked by shared breaker for "
                f"{locked_until - time.time():.0f}s",
                status_code=429,
                retryable=False,
            )
        stream = self._inner.chat(**kwargs)
        orig_run = getattr(stream, "_run", None)
        if orig_run is None:
            return stream

        async def _run_and_remember(_orig=orig_run, _guard=self):
            try:
                return await _orig()
            except Exception as e:
                _guard._last_error = e
                raise

        stream._run = _run_and_remember
        return stream

    async def aclose(self) -> None:
        await self._inner.aclose()


def _gemini_http_options():
    """Pin Google's HTTP deadline ≥10s so FallbackAdapter's 5s attempt_timeout
    cannot leak through as `Manually set deadline 5s is too short`."""
    timeout_ms = llm_models.gemini_http_timeout_ms("voice")
    try:
        from google.genai import types as genai_types

        return genai_types.HttpOptions(timeout=timeout_ms)
    except Exception:
        return {"timeout": timeout_ms}


def _build_one(entry: llm_models.LadderEntry, *, max_output_tokens: int, temperature: float):
    """Construct the concrete plugin LLM for a ladder entry."""
    if entry.provider == "gemini":
        kwargs = {
            "model": entry.model,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
            "http_options": _gemini_http_options(),
        }
        # Thinking tokens are charged against the output budget, so leaving it on
        # under a ~140-token cap truncates spoken replies mid-sentence. Gemini 3
        # wants thinking_level; 2.5 wants thinking_budget. Rolling `-latest`
        # aliases reject the field entirely.
        thinking = llm_models.gemini_thinking_config(entry.model)
        if thinking is not None:
            kwargs["thinking_config"] = thinking
        try:
            return google.LLM(**kwargs)
        except TypeError:
            kwargs.pop("http_options", None)
            try:
                return google.LLM(**kwargs)
            except TypeError:
                kwargs.pop("thinking_config", None)
                return google.LLM(**kwargs)

    if entry.provider == "openrouter":
        from livekit.plugins import openai as lk_openai

        extra_body: dict = {
            "provider": llm_models.openrouter_provider_prefs("voice"),
        }
        if len(entry.models) > 1:
            # Server-side free→paid escalation in a single round trip.
            extra_body["models"] = list(entry.models)
        return lk_openai.LLM(
            model=entry.model,
            base_url=llm_ladder.OPENROUTER_BASE_URL,
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            max_completion_tokens=max_output_tokens,
            temperature=temperature,
            extra_body=extra_body,
            extra_headers={
                "HTTP-Referer": llm_ladder.OPENROUTER_REFERER,
                "X-Title": llm_ladder.OPENROUTER_TITLE,
            },
        )

    raise ValueError(f"unknown provider {entry.provider!r}")


def build_voice_llm(*, max_output_tokens: int, temperature: float = 0.6):
    """Build the voice LLM: VOICE_LADDER, each entry breaker-guarded, wrapped in
    a FallbackAdapter.

    Entries whose provider isn't configured are dropped at build time rather than
    left in to fail — an unset OPENROUTER_API_KEY is "not available", not "broken".
    """
    instances = []
    for entry in llm_models.VOICE_LADDER:
        if entry.provider == "openrouter" and not llm_ladder.openrouter_enabled():
            logger.info("voice ladder: skipping %s (not configured)", entry.label)
            continue
        try:
            inner = _build_one(
                entry, max_output_tokens=max_output_tokens, temperature=temperature
            )
        except Exception as e:
            logger.error("voice ladder: could not build %s: %s", entry.label, e)
            continue
        instances.append(BreakerGuard(inner, entry))

    if not instances:
        raise RuntimeError(
            "voice ladder is empty — check GOOGLE_API_KEY / OPENROUTER_API_KEY "
            f"and VOICE_LADDER ({[e.label for e in llm_models.VOICE_LADDER]})"
        )

    logger.info(
        "voice ladder: %s", " → ".join(g._entry.label for g in instances)
    )
    if len(instances) == 1:
        return instances[0]
    # Default attempt_timeout is 5s; Google rejects that as the HTTP deadline.
    attempt_s = llm_models.gemini_http_timeout_ms("voice") / 1000.0
    return lk_llm.FallbackAdapter(instances, attempt_timeout=attempt_s)


def classify_voice_failure(entry: llm_models.LadderEntry, error=None) -> llm_ladder.LLMError | None:
    """Map a LiveKit voice failure onto a breaker error, or None to not lock.

    FallbackAdapter only tells us "this LLM became unavailable". When we have
    the upstream exception (BreakerGuard._last_error, or event.error), classify
    it the same way the terminal path does: 401/403 is a dead key, a Gemini
    deadline-too-short 400 is a config bug and must not look like a 5xx.
    """
    text = str(error or "")
    low = text.lower()
    status = getattr(error, "status_code", None)
    if status is None:
        # livekit.agents.APIStatusError and openai.BadRequestError both expose this.
        status = getattr(error, "status", None)
        if isinstance(status, str) and status.isdigit():
            status = int(status)

    if "deadline" in low and "too short" in low:
        return None
    if status == 400 and "deadline" in low:
        return None

    if entry.provider == "openrouter" or "openrouter" in low:
        if (
            status in (401, 403)
            or "401" in text
            or "403" in text
            or "user not found" in low
        ):
            return llm_ladder.LLMError(
                llm_ladder.KIND_CREDITS,
                "openrouter auth failure: 'User not found' usually means "
                "OPENROUTER_API_KEY holds a PROVISIONING key; it must be a "
                "runtime key (see agent/RUN.md)",
            )

    if status == 400:
        # Other client errors (wrong thinking_config, etc.) are not outages.
        return None

    return llm_ladder.LLMError(
        llm_ladder.KIND_SERVER, f"voice reported {entry.label} unavailable"
    )


def record_voice_unavailable(llm_instance, error=None) -> None:
    """Feed a LiveKit availability-change back into the shared breaker.

    Uses BreakerGuard._last_error when the availability event has no body, so
    an OpenRouter 401 locks as KIND_CREDITS (24h) instead of hammering every 20s.
    """
    entry = getattr(llm_instance, "_entry", None)
    if entry is None:
        return
    if error is None:
        error = getattr(llm_instance, "_last_error", None)
    classified = classify_voice_failure(entry, error)
    if classified is None:
        logger.warning(
            "voice: not locking %s after client error: %s",
            entry.label,
            str(error)[:160] if error else "(no body)",
        )
        return
    llm_ladder.breaker.record_failure(entry, classified)
