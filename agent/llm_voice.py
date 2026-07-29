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
        return self._inner.chat(**kwargs)

    async def aclose(self) -> None:
        await self._inner.aclose()


def _build_one(entry: llm_models.LadderEntry, *, max_output_tokens: int, temperature: float):
    """Construct the concrete plugin LLM for a ladder entry."""
    if entry.provider == "gemini":
        kwargs = {
            "model": entry.model,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
        }
        # Thinking tokens are charged against the output budget, so leaving it on
        # under a ~140-token cap truncates spoken replies mid-sentence. Same
        # reasoning as llm_models.GEMINI_THINKING_BUDGET; the `-latest` aliases
        # reject the field entirely, hence the guard.
        if llm_models.gemini_supports_thinking_config(entry.model):
            kwargs["thinking_config"] = {
                "thinking_budget": llm_models.GEMINI_THINKING_BUDGET
            }
        try:
            return google.LLM(**kwargs)
        except TypeError:
            # Older plugin versions don't accept thinking_config.
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
    return lk_llm.FallbackAdapter(instances)


def record_voice_unavailable(llm_instance) -> None:
    """Feed a LiveKit availability-change back into the shared breaker.

    Coarse by necessity — see the module docstring. A short transient lock is
    enough to stop the terminal path immediately re-probing an entry that voice
    just found broken.
    """
    entry = getattr(llm_instance, "_entry", None)
    if entry is None:
        return
    llm_ladder.breaker.record_failure(
        entry,
        llm_ladder.LLMError(
            llm_ladder.KIND_SERVER, f"voice reported {entry.label} unavailable"
        ),
    )
