"""
Central LLM model configuration — the one file to edit when changing models.

Every LLM choice in the project lives here: the terminal chat ladder, the voice
ladder, and the resume-sync ladder. Nothing else hardcodes a model name.

LADDER FORMAT
    A ladder is an ordered list of entries, tried top to bottom. Each entry is:

        provider:model[|model2|model3][@quota_group][~timeout_ms]

    - `provider` is `gemini` or `openrouter`.
    - `model` is the provider's own slug. Note OpenRouter slugs contain colons
      (`nvidia/nemotron-3-nano-30b-a3b:free`), so only the FIRST colon splits
      provider from model.
    - `|model2|...` (OpenRouter only) becomes the request's `models[]` fallback
      array — OpenRouter walks it server-side on rate-limit / context / moderation
      errors, so free→paid escalation costs one round trip instead of two.
    - `@quota_group` opts an entry into a shared breaker key, so a 429 on one
      entry locks every entry in the group. Only needed if two entries share an
      upstream quota pool — see the note under GOOGLE QUOTA below.
    - `~timeout_ms` overrides the surface's TOTAL request timeout for this rung.
      Rungs differ by an order of magnitude (6s vs 0.6s to first token), so one
      shared timeout would either strangle the slow rung or let a hung fast rung
      stall the walk.

    Example, as an env var:
        LLM_LADDER="gemini:gemini-3.5-flash~15000,openrouter:x:free|deepseek/y,gemini:gemini-3.1-flash-lite"

WHY A FLAT LIST
    Interleaving providers (gemini → deepseek → gemini-lite) is just list order,
    and "if entry 1 is rate-limited, entry 2 becomes the starter and entry 3 stays
    last" falls out of the breaker skipping entry 1. No special-casing.

GOOGLE QUOTA — UNVERIFIED, see tests/probe_llm.py
    `main.py` and readmes/deployment_options.md both assumed the Gemini models
    share one free-tier RPM pool, which is why the old three-Gemini chain was
    described as useless against 429s. Google documents free-tier limits PER
    MODEL, which would make flash → flash-lite a genuine 429 fallback. The probe
    settles it by saturating flash's RPM then immediately calling flash-lite.
      - Independent quotas  → leave quota_group unset (current default).
      - Shared pool         → tag both Gemini entries `@google-free`.

MODEL SLUGS — UNVERIFIED, see tests/probe_llm.py
    OpenRouter's free-model catalogue churns; a slug that 404s is expected
    occasionally, which is why the list is fixed and manually audited rather than
    auto-discovered. The ladder treats a 404 as "disable this entry, log loudly"
    so a stale slug degrades instead of breaking.
"""

import os
import logging
from dataclasses import dataclass

logger = logging.getLogger("llm-models")

VALID_PROVIDERS = ("gemini", "openrouter")


# ─── Ladder entries ────────────────────────────────────────────────

@dataclass(frozen=True)
class LadderEntry:
    """One rung of a fallback ladder."""

    provider: str
    models: tuple[str, ...]      # >1 only for OpenRouter `models[]` arrays
    quota_group: str | None = None
    # Per-rung TOTAL request timeout in ms, overriding the surface default.
    # Needed because rungs differ by an order of magnitude: gemini-3.5-flash
    # takes ~6s just to first token, while flash-lite answers in well under one.
    # A single shared timeout either strangles the slow rung or lets a hung fast
    # rung stall the whole walk.
    timeout_ms: int | None = None

    @property
    def model(self) -> str:
        """The primary model — what gets requested first."""
        return self.models[0]

    @property
    def key(self) -> str:
        """Breaker key. Entries in a quota_group share one key, so a 429 on any
        of them locks all of them."""
        if self.quota_group:
            return f"{self.provider}:@{self.quota_group}"
        return f"{self.provider}:{self.model}"

    @property
    def label(self) -> str:
        """Human/Langfuse-friendly name."""
        return f"{self.provider}:{self.model}"

    def __str__(self) -> str:
        return self.label


def parse_entry(spec: str) -> LadderEntry:
    """Parse one `provider:model[|model2][@quota_group]` spec.

    Raises ValueError on an unknown provider or an unparseable spec, because a
    typo'd ladder should fail at import rather than at the first visitor.
    """
    spec = spec.strip()
    if not spec:
        raise ValueError("empty ladder entry")

    # Suffixes are stripped before the models are split. OpenRouter slugs never
    # contain '@' or '~'. Order matters: '~timeout' comes last in the spec.
    timeout_ms = None
    if "~" in spec:
        spec, raw_timeout = spec.rsplit("~", 1)
        try:
            timeout_ms = int(raw_timeout.strip())
        except ValueError:
            raise ValueError(f"timeout must be an integer in ms: {raw_timeout!r}")
        if timeout_ms <= 0:
            raise ValueError(f"timeout must be positive: {timeout_ms}")

    quota_group = None
    if "@" in spec:
        spec, quota_group = spec.rsplit("@", 1)
        quota_group = quota_group.strip() or None

    # Only the first colon separates provider from model — OpenRouter's `:free`
    # suffix is part of the slug.
    if ":" not in spec:
        raise ValueError(f"ladder entry missing provider prefix: {spec!r}")
    provider, _, models_part = spec.partition(":")
    provider = provider.strip().lower()
    if provider not in VALID_PROVIDERS:
        raise ValueError(
            f"unknown provider {provider!r} in {spec!r} (expected one of {VALID_PROVIDERS})"
        )

    models = tuple(m.strip() for m in models_part.split("|") if m.strip())
    if not models:
        raise ValueError(f"ladder entry has no model: {spec!r}")
    if len(models) > 1 and provider != "openrouter":
        raise ValueError(
            f"models[] arrays are OpenRouter-only, got {len(models)} models for {provider!r}"
        )

    return LadderEntry(
        provider=provider, models=models,
        quota_group=quota_group, timeout_ms=timeout_ms,
    )


def _env_ladder(name: str, default: list[str]) -> tuple[LadderEntry, ...]:
    """Read a comma-separated ladder from the environment, else use `default`.

    A malformed env override falls back to the default rather than taking the
    agent down — a bad env var on a VPS shouldn't mean no LLM at all.
    """
    raw = os.environ.get(name, "").strip()
    specs = [s for s in raw.split(",") if s.strip()] if raw else default
    try:
        return tuple(parse_entry(s) for s in specs)
    except ValueError as e:
        if raw:
            logger.error("%s is malformed (%s) — falling back to defaults", name, e)
            return tuple(parse_entry(s) for s in default)
        raise


def _env_str_list(name: str, default: list[str]) -> tuple[str, ...]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return tuple(default)
    return tuple(s.strip() for s in raw.split(",") if s.strip())


# ─── The ladders ───────────────────────────────────────────────────
# MEASURED TTFT, 2026-07-26, streaming, median of 3, thinking disabled:
#     gemini-3.1-flash-lite      607 ms
#     gemini-flash-lite-latest   661 ms
#     gemini-3.5-flash          6321 ms   (range 2485-7014)
#     gemini-flash-latest      83787 ms   ← unusable, excluded everywhere
#
# Gemini generation note: gemini-2.5-flash and -2.5-flash-lite 404 (sunsetted
# mid-2026), so 3.x is the live generation. `gemini-flash-lite-latest` is the
# rolling alias that survives sunsets, which is why each ladder ends on it.
# `gemini-flash-latest` is NOT used: it resolves to something that took 84
# seconds to answer "say hi in four words".

# Terminal chat: quality first, latency second — a recruiter reading a written
# answer will wait, and 3.5-flash is the better model. That is a deliberate
# ~6s TTFT trade (see the table above); flip the first two entries if it starts
# feeling slow. DeepSeek V4 Flash is the spike absorber, with free-tier siblings
# ahead of it inside the same request via models[].
# `~15000` on the first rung: at ~6.3s to first token it needs roughly double
# the surface default to finish 200 tokens. Without the override it timed out on
# every single request and silently never answered, which would have quietly
# undone the whole point of putting it first.
LLM_LADDER = _env_ladder("LLM_LADDER", [
    "gemini:gemini-3.5-flash~15000",
    "openrouter:nvidia/nemotron-3-super-120b-a12b:free|deepseek/deepseek-v4-flash",
    "gemini:gemini-3.1-flash-lite",
    "gemini:gemini-flash-lite-latest",
])

# Voice: latency first, and it is not close — 3.5-flash's ~6s TTFT would be dead
# air mid-conversation, so flash-lite leads here even though it leads the terminal
# ladder only as a fallback. Spoken answers are capped at ~35 words, so the
# smaller model costs little. Nemotron Nano is the smallest free option; the probe
# confirms whether it actually wins on TTFT.
VOICE_LADDER = _env_ladder("VOICE_LADDER", [
    "gemini:gemini-3.1-flash-lite",
    "openrouter:nvidia/nemotron-3-nano-30b-a3b:free|deepseek/deepseek-v4-flash",
    "gemini:gemini-flash-lite-latest",
])

# Resume sync: FREE ONLY — an offline batch tool run a handful of times, so there
# is no reason to spend on it and no paid entry is listed. If every free entry
# fails, sync_resume exits 1 rather than falling through to something paid.
# This is the one place 3.5-flash's latency genuinely does not matter, and the
# task (emitting a structured change-set against a hand-formatted file) wants the
# most capable model available.
SYNC_LADDER = _env_ladder("SYNC_LADDER", [
    "openrouter:nvidia/nemotron-3-super-120b-a12b:free",
    "gemini:gemini-3.5-flash",
    "gemini:gemini-flash-lite-latest",
])


# ─── OpenRouter routing preferences ────────────────────────────────
# Per-surface `provider` object on the chat-completions request.
#
# Deliberately NOT set: `provider.order`. An explicit provider order disables
# OpenRouter's sticky routing, which is what keeps a caller on the provider
# holding their cached prompt prefix. Losing that costs more than any gain from
# pinning providers.

# Quantization allow-list is the real quality lever for terminal chat: without it
# you can be routed to an int4 backend of the right model and get visibly worse
# answers at the same price.
TERMINAL_QUANTIZATIONS = _env_str_list(
    "TERMINAL_QUANTIZATIONS", ["fp8", "fp16", "bf16"]
)

# Routing-layer spend guard, in USD per million tokens. Independent of (and
# secondary to) the per-key monthly limit on the OpenRouter provisioning key,
# which is the actual hard cap — see agent/RUN.md.
MAX_PRICE_PROMPT = float(os.environ.get("OPENROUTER_MAX_PRICE_PROMPT", "0.50"))
MAX_PRICE_COMPLETION = float(os.environ.get("OPENROUTER_MAX_PRICE_COMPLETION", "1.50"))


def openrouter_provider_prefs(surface: str) -> dict:
    """Build the `provider` object for a chat-completions request.

    surface: "voice" | "terminal" | "sync"
    """
    prefs: dict = {
        "max_price": {
            "prompt": MAX_PRICE_PROMPT,
            "completion": MAX_PRICE_COMPLETION,
        },
    }
    if surface == "voice":
        # Sort on observed TTFT — the only thing that matters when a human is
        # waiting mid-sentence for TTS to start.
        prefs["sort"] = "latency"
    elif surface == "terminal":
        # No `sort`: the default price-weighted selection preserves sticky
        # routing (and therefore prompt-cache affinity), and model *quality* is
        # already chosen by ladder order, not by provider sort.
        prefs["quantizations"] = list(TERMINAL_QUANTIZATIONS)
    elif surface == "sync":
        prefs["sort"] = "price"
    return prefs


# ─── Timeouts ──────────────────────────────────────────────────────
# There was previously no timeout anywhere, so a hung upstream call stalled a
# voice turn indefinitely.
#
# THESE ARE TOTAL REQUEST TIMEOUTS, NOT TTFT. Getting that wrong is easy and
# silent: an early draft used 2500ms reasoning from TTFT figures, which meant a
# 200-token reply could never finish in time and EVERY rung timed out before
# answering — including the fast ones. Budget TTFT + (max_tokens / throughput):
# at ~50 tok/s, 200 tokens is ~4s of generation on top of first-token latency.
#
# Per-rung overrides (`~ms` in the ladder spec) exist because rungs differ by an
# order of magnitude, and one shared number cannot both give the slow rung room
# and let a hung fast rung fail quickly.
TIMEOUT_MS = {
    "terminal": int(os.environ.get("LLM_TIMEOUT_MS_TERMINAL", "8000")),
    "voice": int(os.environ.get("LLM_TIMEOUT_MS_VOICE", "6000")),
    # Offline batch, emitting a structured change-set. Latency is irrelevant.
    "sync": int(os.environ.get("LLM_TIMEOUT_MS_SYNC", "60000")),
}

# Short backoff applied to an entry after a timeout or 5xx (as opposed to the
# quota-derived lockouts, which are pinned to the upstream reset window).
TRANSIENT_COOLDOWN_S = float(os.environ.get("LLM_TRANSIENT_COOLDOWN_S", "20"))


# ─── Generation config ─────────────────────────────────────────────

TERMINAL_MAX_OUTPUT_TOKENS = int(os.environ.get("TERMINAL_MAX_OUTPUT_TOKENS", "200"))
TERMINAL_TEMPERATURE = float(os.environ.get("TERMINAL_TEMPERATURE", "0.6"))

# ─── Gemini thinking budget ────────────────────────────────────────
# MEASURED 2026-07-26, and this is not a micro-optimisation — leaving thinking on
# silently truncates every answer:
#
#   gemini-3.5-flash, thinking default ON, max_output_tokens=200
#     → 190 of the 200 tokens went to thinking, 5-6 left for the reply.
#       Output was literally "At Maersk, I" — cut mid-sentence.
#       TTFT 4.7-12s.
#   gemini-3.5-flash, thinking_budget=0
#     → full 39-token replies, TTFT median 6.3s.
#   gemini-3.1-flash-lite
#     → does not think by default; TTFT median 607ms.
#
# max_output_tokens is a budget for thinking AND visible output together, so any
# thinking-capable model behind a tight cap produces truncated text rather than a
# short answer. 0 disables thinking; raise it only if a model needs reasoning,
# and raise max_output_tokens with it.
GEMINI_THINKING_BUDGET = int(os.environ.get("GEMINI_THINKING_BUDGET", "0"))

# The rolling aliases reject `thinking_config` outright with
# 400 INVALID_ARGUMENT, so it must not be sent to them. This is a starting guess,
# not the enforcement — llm_ladder also retries without the field on a 400 and
# remembers, so a model changing its mind about support self-heals.
NO_THINKING_CONFIG_SUFFIXES = ("-latest",)


def gemini_supports_thinking_config(model: str) -> bool:
    return not model.endswith(NO_THINKING_CONFIG_SUFFIXES)


def describe() -> str:
    """Render the active configuration — logged at startup and printed by probes."""
    lines = ["LLM configuration:"]
    for name, ladder in (
        ("terminal", LLM_LADDER),
        ("voice", VOICE_LADDER),
        ("sync", SYNC_LADDER),
    ):
        lines.append(f"  {name}:")
        for i, entry in enumerate(ladder, 1):
            extra = []
            if len(entry.models) > 1:
                extra.append(f"models[]={list(entry.models[1:])}")
            if entry.quota_group:
                extra.append(f"quota_group={entry.quota_group}")
            extra.append(f"timeout={entry.timeout_ms or TIMEOUT_MS.get(name, '?')}ms")
            suffix = f"  ({', '.join(extra)})" if extra else ""
            lines.append(f"    {i}. {entry.label}{suffix}")
    return "\n".join(lines)
