"""
Central LLM model configuration — the one file to edit when changing models.

Every LLM choice in the project lives here: the terminal chat ladder, the voice
ladder, and the resume-sync ladder. Nothing else hardcodes a model name.

LADDER FORMAT
    A ladder is an ordered list of entries, tried top to bottom. Each entry is:

        provider:model[|model2|model3][@quota_group][~timeout_ms][#effort]

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
    - `#effort` (OpenRouter only) sets that rung's `reasoning.effort`, overriding
      the surface default (see OPENROUTER_REASONING_EFFORT). `#default` sends no
      reasoning field at all, for models where `none` is rejected (reasoning is
      mandatory, e.g. gpt-oss-120b).

    Example, as an env var:
        LLM_LADDER="openrouter:anthropic/claude-haiku-5.5,openrouter:openai/gpt-oss-120b#low,gemini:gemini-flash-lite-latest"

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

# OpenRouter's `reasoning.effort` values, plus "default" = omit the field.
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "default")


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
    # Per-rung OpenRouter `reasoning.effort` (`#effort` in the spec). None means
    # "use the surface default"; "default" means "send no reasoning field".
    reasoning: str | None = None

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
    # contain '@', '~' or '#'. Order matters: '#effort' comes last, then '~timeout'.
    reasoning = None
    if "#" in spec:
        spec, raw_effort = spec.rsplit("#", 1)
        reasoning = raw_effort.strip().lower()
        if reasoning not in REASONING_EFFORTS:
            raise ValueError(
                f"unknown reasoning effort {raw_effort!r} (expected one of {REASONING_EFFORTS})"
            )

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
    if reasoning is not None and provider != "openrouter":
        raise ValueError(
            f"#effort is OpenRouter-only (Gemini thinking is set per model), got {provider!r}"
        )

    return LadderEntry(
        provider=provider, models=models,
        quota_group=quota_group, timeout_ms=timeout_ms, reasoning=reasoning,
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
# MEASURED 2026-10-21 from the Oracle VM (ap-hyderabad-1): voice TTFT through the
# real LiveKit plugin clients with the real voice prompt, 43 calls per finalist,
# reasoning off. Full write-up: readmes/perf/2026-10-22/ (local).
#   openrouter deepseek/deepseek-v4.1-flash-1017  p50 392  p95 1169  max 3579 ms
#                                                 greeting p50 381 / p95 531 ms
#   openrouter anthropic/claude-haiku-5.5         p50 866  p95 1197  max 1439 ms
#   openrouter google/gemini-3.1-flash-lite       p50 838  p95 1171  max 1263 ms
#   gemini (AI Studio free tier) 3.5-flash-lite   5.7 s on a warm answer; 5.2 and
#     5.9 s turns in the first real call; 3.1-flash-lite 503/504 on 5 of 9 calls.
# Terminal (full non-streamed reply): Haiku 5.5 ~1.4 s with the best answers,
# DeepSeek 1017 ~0.7 s, gemini-3.5-flash 4-16 s with no better answers.
#
# So OpenRouter leads both ladders and AI Studio direct is the last resort, kept
# because it's free and survives an OpenRouter outage. `gemini-flash-lite-latest`
# is the rolling alias that survives sunsets. `gemini-flash-latest` is NOT used:
# it once took 84 seconds to answer "say hi in four words".
#
# Rejected in the same tests: mercury-3, nemotron-3.5-super-vl and gpt-oss-120b
# each invented a fact about the owner; gpt-6-luna and qwen3.8-27b were slower
# with a 2 s+ tail; mimo-v2.6-flash had a 6 s tail; glm-5.3-flash and
# gemini-3.5-flash-lite (on OpenRouter) can't turn reasoning off.

# Terminal chat: Haiku first for answer quality (a recruiter reads it), DeepSeek
# as a fast, cheap second. Haiku's $0.10/$0.50 price holds under 100k prompt
# tokens; ours are 1-4k.
LLM_LADDER = _env_ladder("LLM_LADDER", [
    "openrouter:anthropic/claude-haiku-5.5",
    "openrouter:deepseek/deepseek-v4.1-flash-1017",
    "openrouter:google/gemini-3.1-flash-lite",
    "gemini:gemini-flash-lite-latest",
])

# Voice: latency first. DeepSeek 1017's first turn is its strongest point (greeting
# p95 0.53 s); its rare ~3.5 s outliers are cut by the hedge in llm_voice, which
# races rung 2 (Haiku, never above 1.44 s) when rung 1 has no first token after
# VOICE_HEDGE_AFTER_MS.
VOICE_LADDER = _env_ladder("VOICE_LADDER", [
    "openrouter:deepseek/deepseek-v4.1-flash-1017",
    "openrouter:anthropic/claude-haiku-5.5",
    "openrouter:google/gemini-3.1-flash-lite",
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
# `unknown` is in the list because first-party endpoints (Anthropic, Google,
# DeepSeek's own API, Together, Fireworks) don't publish a quantization; without
# it every Haiku and Google endpoint is silently filtered out of terminal chat.
TERMINAL_QUANTIZATIONS = _env_str_list(
    "TERMINAL_QUANTIZATIONS", ["fp8", "fp16", "bf16", "unknown"]
)

# Reasoning effort sent to OpenRouter per surface, unless a rung's `#effort`
# overrides it. MEASURED 2026-10-21: DeepSeek v4.1 flash defaults to effort
# `high` and Haiku 5.5 to `medium`; under a 200-token cap Haiku spent most of
# the budget thinking and truncated 4 of 6 terminal answers mid-sentence. A
# 35-word spoken answer and a short written one gain nothing from reasoning, so
# both surfaces turn it off. Sync is left at the model's default (None = omit).
OPENROUTER_REASONING_EFFORT = {
    "voice": os.environ.get("OPENROUTER_REASONING_EFFORT_VOICE", "none"),
    "terminal": os.environ.get("OPENROUTER_REASONING_EFFORT_TERMINAL", "none"),
    "sync": os.environ.get("OPENROUTER_REASONING_EFFORT_SYNC") or None,
}


def openrouter_reasoning(entry: "LadderEntry", surface: str) -> dict | None:
    """The `reasoning` object for an OpenRouter request, or None to omit it."""
    effort = entry.reasoning or OPENROUTER_REASONING_EFFORT.get(surface)
    if not effort or effort == "default":
        return None
    return {"effort": effort}

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
    # Google Gemini rejects HTTP deadlines under 10s (INVALID_ARGUMENT).
    # LiveKit's FallbackAdapter default attempt_timeout is 5s and used to leak
    # that as the request deadline — see llm_voice + livekit/agents#3723.
    "voice": int(os.environ.get("LLM_TIMEOUT_MS_VOICE", "10000")),
    # Offline batch, emitting a structured change-set. Latency is irrelevant.
    "sync": int(os.environ.get("LLM_TIMEOUT_MS_SYNC", "60000")),
}

# Short backoff applied to an entry after a timeout or 5xx (as opposed to the
# quota-derived lockouts, which are pinned to the upstream reset window).
TRANSIENT_COOLDOWN_S = float(os.environ.get("LLM_TRANSIENT_COOLDOWN_S", "20"))

# ─── Voice hedging and health ──────────────────────────────────────
# Hedge, don't wait: if voice rung 1 has produced no token after this long, rung
# 2 starts in parallel and whichever streams first is spoken. Never adds latency;
# costs one duplicate short call on the turns past it. 1200 ms sits above
# DeepSeek 1017's measured p95 (1169 ms), so it fires on ~5% of turns and
# leaves normal slower answers alone. 0 disables hedging.
VOICE_HEDGE_AFTER_MS = int(os.environ.get("VOICE_HEDGE_AFTER_MS", "1200"))

# Canary: a 1-token call to the first rungs, run by the token server when a
# visitor asks for a voice token (at most once per LLM_CANARY_MIN_GAP_S) and
# every LLM_CANARY_INTERVAL_S. A rung whose canary failed or took longer than
# LLM_CANARY_SLOW_MS counts as degraded for LLM_HEALTH_TTL_S, and new voice
# sessions start on the next healthy rung. ~$0.000002 per canary.
LLM_CANARY_INTERVAL_S = float(os.environ.get("LLM_CANARY_INTERVAL_S", "600"))
LLM_CANARY_MIN_GAP_S = float(os.environ.get("LLM_CANARY_MIN_GAP_S", "60"))
# A healthy non-streamed 1-token round trip measured 0.9-1.3 s (DeepSeek 915 ms,
# Haiku 1176 ms on the VM, 2026-10-21), so "slow" is ~2x that, not the 1.2 s
# hedge deadline, or ordinary variance would flap rungs between sessions.
LLM_CANARY_SLOW_MS = float(os.environ.get("LLM_CANARY_SLOW_MS", "2500"))
LLM_CANARY_TIMEOUT_MS = int(os.environ.get("LLM_CANARY_TIMEOUT_MS", "3000"))
LLM_HEALTH_TTL_S = float(os.environ.get("LLM_HEALTH_TTL_S", "300"))

# ─── Prompt-size guard ─────────────────────────────────────────────
# Claude Haiku 5.5 bills $0.10/$0.50 per M tokens only while the prompt is under
# 100k tokens; above that it's 5x ($0.50/$2.50). Our prompts are 1-4k, but a
# voice session left running keeps appending turns to the chat context. Every
# voice LLM call sends at most the last VOICE_MAX_CONTEXT_ITEMS items (system
# instructions are always kept): ~40 short spoken turns plus one injected resume
# is ~10-15k tokens, far from the 100k tier. Terminal history is already capped
# in token_server (6 turns x 500 chars).
VOICE_MAX_CONTEXT_ITEMS = int(os.environ.get("VOICE_MAX_CONTEXT_ITEMS", "40"))

# ─── Price table for cost logging (USD per million tokens) ─────────
# (input, cached input, output). OpenRouter prices vary by the provider it routes
# to; these are the upper end of what `sort=latency` picked on 2026-10-21, so the
# logged numbers are conservative. Gemini direct is the free tier. Unknown
# models log tokens with no dollar figure rather than a made-up one.
MODEL_PRICES_PER_M: dict[str, tuple[float, float, float]] = {
    "deepseek/deepseek-v4.1-flash-1017": (0.30, 0.006, 1.20),
    "deepseek/deepseek-v4.1-flash": (0.30, 0.006, 1.20),
    "anthropic/claude-haiku-5.5": (0.10, 0.01, 0.50),
    "google/gemini-3.1-flash-lite": (0.25, 0.025, 1.50),
    "google/gemini-2.5-flash-lite": (0.10, 0.01, 0.40),
    "gemini-flash-lite-latest": (0.0, 0.0, 0.0),
    "gemini-3.5-flash-lite": (0.0, 0.0, 0.0),
}


def estimate_llm_usd(model: str, prompt_tokens: int, cached_tokens: int,
                     completion_tokens: int) -> float | None:
    """Estimated cost of one call, or None for a model not in the table."""
    prices = MODEL_PRICES_PER_M.get(model)
    if prices is None:
        return None
    p_in, p_cached, p_out = prices
    uncached = max(0, (prompt_tokens or 0) - (cached_tokens or 0))
    return (uncached * p_in + (cached_tokens or 0) * p_cached + (completion_tokens or 0) * p_out) / 1e6


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

# Google's generateContent HTTP deadline floor. LiveKit FallbackAdapter's
# attempt_timeout default is 5s, which Gemini now rejects as 400.
GEMINI_MIN_HTTP_TIMEOUT_MS = 10_000

# The rolling aliases reject `thinking_config` outright with
# 400 INVALID_ARGUMENT, so it must not be sent to them. This is a starting guess,
# not the enforcement — llm_ladder also retries without the field on a 400 and
# remembers, so a model changing its mind about support self-heals.
NO_THINKING_CONFIG_SUFFIXES = ("-latest",)


def gemini_supports_thinking_config(model: str) -> bool:
    return not model.endswith(NO_THINKING_CONFIG_SUFFIXES)


def gemini_is_v3(model: str) -> bool:
    """Gemini 3.x wants thinking_level, not thinking_budget."""
    return "gemini-3" in model.lower()


def gemini_thinking_config(model: str) -> dict | None:
    """Per-model thinking_config, or None to omit the field.

    Gemini 3 ignores thinking_budget (plugin warning) and wants thinking_level.
    `minimal` is the fastest setting — the voice/terminal caps are too tight
    for real thinking tokens. 2.5 and earlier still take thinking_budget=0.
    Rolling `-latest` aliases reject the whole field.
    """
    if not gemini_supports_thinking_config(model):
        return None
    if gemini_is_v3(model):
        return {"thinking_level": "minimal"}
    return {"thinking_budget": GEMINI_THINKING_BUDGET}


def gemini_http_timeout_ms(surface: str = "voice") -> int:
    """HTTP deadline for google.LLM / FallbackAdapter, never under Google's 10s floor."""
    configured = TIMEOUT_MS.get(surface, GEMINI_MIN_HTTP_TIMEOUT_MS)
    return max(GEMINI_MIN_HTTP_TIMEOUT_MS, configured)


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
            if entry.provider == "openrouter":
                reasoning = openrouter_reasoning(entry, name)
                extra.append(f"reasoning={reasoning['effort'] if reasoning else 'model default'}")
            extra.append(f"timeout={entry.timeout_ms or TIMEOUT_MS.get(name, '?')}ms")
            suffix = f"  ({', '.join(extra)})" if extra else ""
            lines.append(f"    {i}. {entry.label}{suffix}")
    lines.append(
        f"  voice hedge after {VOICE_HEDGE_AFTER_MS}ms; canary every {LLM_CANARY_INTERVAL_S:.0f}s "
        f"(slow > {LLM_CANARY_SLOW_MS:.0f}ms); voice context <= {VOICE_MAX_CONTEXT_ITEMS} items"
    )
    return "\n".join(lines)
