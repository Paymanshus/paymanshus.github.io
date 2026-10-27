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

HEDGING (HedgedLLM)
    Rungs 1 and 2 are wrapped in one HedgedLLM: rung 1 starts alone; if it has
    produced no token after VOICE_HEDGE_AFTER_MS, rung 2 starts in parallel and
    whichever streams first is spoken, the other is cancelled. If rung 1 fails
    outright, rung 2 starts at once. No longer timeouts, no waiting: the visitor
    never waits more than they would have without it.

WARM-UP AND HEALTH
    build_voice_llm orders the ladder by the canary results the token server
    shares (llm_health) and fires a 1-token warm-up on the primary while the
    session is still connecting: measured ~50-180 ms off DeepSeek 1017's
    greeting, plus the job process's first-request import and connection cost.
"""

import asyncio
import dataclasses
import os
import re
import time
import logging

from livekit.agents import APIConnectionError, APIStatusError
from livekit.agents import llm as lk_llm
from livekit.plugins import google

import llm_health
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
        chat_ctx = kwargs.get("chat_ctx")
        limit = llm_models.VOICE_MAX_CONTEXT_ITEMS
        if chat_ctx is not None and limit > 0 and len(chat_ctx.items) > limit:
            # A session left running keeps growing its context; cap what each
            # call sends (keeps the system instructions). See llm_models.
            trimmed = chat_ctx.copy()
            trimmed.truncate(max_items=limit)
            kwargs["chat_ctx"] = trimmed
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
        reasoning = llm_models.openrouter_reasoning(entry, "voice")
        if reasoning is not None:
            # Default-on reasoning (DeepSeek `high`, Haiku `medium`) is pure
            # latency for a 35-word spoken answer. See llm_models.
            extra_body["reasoning"] = reasoning
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


# What one user turn may send to the LLM (and BM25): the last N characters.
# ~600 chars is ~100 spoken words; the end of a long ramble is where the
# question usually is, and a cap here keeps one runaway transcript (a TV near
# the mic, a visitor reading a JD aloud) from becoming a huge prompt.
VOICE_MAX_USER_CHARS = int(os.environ.get("VOICE_MAX_USER_CHARS", "600"))


def trim_user_text(text: str, limit: int | None = None) -> str:
    """Keep the last `limit` characters of a long transcript, cut at a word
    boundary and marked, so the LLM knows it's hearing the tail end."""
    limit = VOICE_MAX_USER_CHARS if limit is None else limit
    text = (text or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    if text.startswith(_TRIM_MARK) and len(text) <= limit + len(_TRIM_MARK):
        return text  # already trimmed (idempotent across repeated LLM calls)
    tail = text[-limit:]
    space = tail.find(" ")
    if 0 <= space < 40:
        tail = tail[space + 1:]
    return _TRIM_MARK + tail


_TRIM_MARK = "(earlier part trimmed) ..."


CONTEXT_PREFIX = "[Context for the next answer — internal, not spoken]\n"


def prepare_voice_ctx(chat_ctx, index, threshold: float, knowledge=None):
    """What a voice LLM call actually sends, built on a COPY of the session's
    chat context (returns (ctx, info) for logging):

      - every user message: STT word fixes (voice_lexicon) and the long-turn
        trim, so a misheard name or a ramble never reaches the model as-is;
      - resume context for the latest user message, inserted just before it:
        BM25 top-2, or the full resume when BM25 isn't confident, plus a
        blog/side-project snippet when `knowledge(query)` returns one (it
        clears a high bar, so usually nothing is added).

    Doing this per LLM call rather than in on_user_turn_completed is what keeps
    LiveKit's preemptive generation valid: it compares the chat context it
    started with against the one at end of turn, and a message added in
    on_user_turn_completed made them differ on every turn (2026-10-22 logs:
    every turn invalidated, so every turn paid for two LLM calls and waited
    for the second).
    """
    import voice_lexicon

    ctx = chat_ctx.copy()
    items = ctx.items
    last_user = None
    for i, item in enumerate(items):
        if getattr(item, "type", None) == "message" and item.role == "user":
            raw = item.text_content or ""
            clean = trim_user_text(voice_lexicon.fix_transcript(raw))
            if clean != raw:
                items[i] = item.model_copy(update={"content": [clean]})
            last_user = i
    if last_user is None:
        return ctx, {}
    query = items[last_user].text_content or ""
    context, score = index.search_scored(query, top_k=2)
    source = "bm25-top2"
    if score < threshold:
        context, source = index.full_text, "full-resume"
    if knowledge is not None and (extra := knowledge(query)):
        context += extra
        source += "+knowledge"
    items.insert(last_user, lk_llm.ChatMessage(role="assistant", content=[CONTEXT_PREFIX + context]))
    return ctx, {"score": score, "source": source, "chars": len(context), "query": query}


# Chat-template control tokens that some providers leak into the text stream
# (seen on the live site: "<end...>" / "|end|" at the start of a reply). They
# aren't spoken but they land in the transcript and the chat history.
_SPECIAL_TOKEN = re.compile(
    r"<\|[^|<>]{0,40}\|>"              # <|end|>, <|im_end|>, <|eot_id|>
    r"|<｜[^｜<>]{0,40}｜>"             # DeepSeek's <｜end▁of▁sentence｜>
    r"|</?(?:end|eos|eot|bos|s|im_start|im_end)[^<>\s]{0,30}>"  # <end_of_turn>, </s>
    r"|\|(?:end|eot|eos|im_end)[a-z_]{0,20}\|",                  # |end|
    re.IGNORECASE,
)
# A possibly unfinished token at the end of the text so far.
_TOKEN_PREFIX = re.compile(r"(?:<[|｜/]?|[|｜])[^<>\s|｜]{0,40}[|｜]?\Z")


class TokenScrubber:
    """Removes leaked special tokens from streamed text. Holds back a trailing
    fragment that could still become a token (a lone "<|end" waiting for
    "|>"), so a token split across chunks is caught too."""

    def __init__(self) -> None:
        self._held = ""

    def feed(self, text: str) -> str:
        buf = _SPECIAL_TOKEN.sub("", self._held + text)
        m = _TOKEN_PREFIX.search(buf)
        self._held = m.group() if m else ""
        return buf[: len(buf) - len(self._held)]

    def flush(self) -> str:
        out = _SPECIAL_TOKEN.sub("", self._held)
        self._held = ""
        return out


def scrub_special_tokens(text: str) -> str:
    return _SPECIAL_TOKEN.sub("", text)


_END = object()


def _has_output(chunk) -> bool:
    delta = getattr(chunk, "delta", None)
    return bool(delta and (delta.content or delta.tool_calls))


class HedgedLLM(lk_llm.LLM):
    """Rung 1 alone, then rung 1 and rung 2 racing after `hedge_after_s` with no
    output; the first to stream wins. See the module docstring."""

    def __init__(self, primary: lk_llm.LLM, backup: lk_llm.LLM, *,
                 hedge_after_s: float, on_failure=None):
        super().__init__()
        self._primary = primary
        self._backup = backup
        self._hedge_after_s = hedge_after_s
        # Called as on_failure(llm, error) for a rung that errored (not one that
        # merely lost the race), so the shared breaker learns about it.
        self._on_failure = on_failure
        # Per-model totals for this session's cost summary (observability).
        self.usage_totals: dict[str, dict] = {}

    def _record_usage(self, llm: lk_llm.LLM, usage, ttft_ms: float, hedged: bool,
                      text: str = "") -> None:
        model = llm.model
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        cached = getattr(usage, "prompt_cached_tokens", 0) or 0
        out = getattr(usage, "completion_tokens", 0) or 0
        usd = llm_models.estimate_llm_usd(model, prompt, cached, out)
        t = self.usage_totals.setdefault(
            model, {"calls": 0, "prompt_tokens": 0, "cached_tokens": 0,
                    "completion_tokens": 0, "est_usd": 0.0 if usd is not None else None})
        t["calls"] += 1
        t["prompt_tokens"] += prompt
        t["cached_tokens"] += cached
        t["completion_tokens"] += out
        if usd is not None and t["est_usd"] is not None:
            t["est_usd"] += usd
        # The reply text makes length tuning possible from the logs (words=).
        # Note a call LiveKit later discards (an invalidated preemptive
        # generation) is logged and billed here too.
        logger.info(
            "voice llm-usage model=%s ttft_ms=%.0f hedged=%s in=%d cached=%d out=%d est_usd=%s "
            "words=%d reply=%r",
            model, ttft_ms, hedged, prompt, cached, out,
            f"{usd:.6f}" if usd is not None else "?", len(text.split()), text[:240],
        )

    @property
    def model(self) -> str:
        return self._primary.model

    @property
    def provider(self) -> str:
        return self._primary.provider

    @property
    def label(self) -> str:
        return f"hedged({self._primary.label}, {self._backup.label})"

    def chat(self, *, chat_ctx, tools=None, conn_options=None, **kwargs) -> lk_llm.LLMStream:
        if conn_options is None:
            from livekit.agents import DEFAULT_API_CONNECT_OPTIONS
            conn_options = DEFAULT_API_CONNECT_OPTIONS
        return HedgedLLMStream(self, chat_ctx=chat_ctx, tools=tools or [],
                               conn_options=conn_options, chat_kwargs=kwargs)

    async def aclose(self) -> None:
        await self._primary.aclose()
        await self._backup.aclose()


class HedgedLLMStream(lk_llm.LLMStream):
    # Delegating stream, like FallbackLLMStream: the inner streams own the
    # inference spans (LiveKit 1.8 reads these; 1.6 ignores them).
    _llm_attempt_span_name = None
    _genai_operation_name = None

    def __init__(self, hedged: HedgedLLM, *, chat_ctx, tools, conn_options, chat_kwargs):
        super().__init__(hedged, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._hedged = hedged
        self._chat_kwargs = chat_kwargs

    async def _run(self) -> None:
        h = self._hedged
        inner_opts = dataclasses.replace(self._conn_options, max_retry=0)
        events: asyncio.Queue = asyncio.Queue()
        racers: dict[str, asyncio.Task] = {}
        llms = {"primary": h._primary, "backup": h._backup}
        buffers: dict[str, list] = {"primary": [], "backup": []}
        errors: dict[str, BaseException] = {}
        started = time.perf_counter()

        def start(name: str) -> None:
            async def pump() -> None:
                try:
                    async with llms[name].chat(
                        chat_ctx=self._chat_ctx, tools=self._tools,
                        conn_options=inner_opts, **self._chat_kwargs,
                    ) as stream:
                        async for chunk in stream:
                            await events.put((name, chunk))
                    await events.put((name, _END))
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    await events.put((name, e))

            racers[name] = asyncio.create_task(pump(), name=f"llm-hedge-{name}")

        def fail(name: str, err: BaseException) -> None:
            errors[name] = err
            llm = llms[name]
            entry = getattr(llm, "_entry", None)
            # A guard refusing a locked rung is the breaker talking, not news.
            if entry is not None and llm_ladder.breaker.is_locked(entry.key):
                return
            logger.warning("voice hedge: %s failed: %s", llm.label, str(err)[:160])
            if h._on_failure is not None:
                h._on_failure(llm, err)

        start("primary")
        winner = None
        try:
            while winner is None:
                timeout = None
                if "backup" not in racers:
                    timeout = max(0.0, h._hedge_after_s - (time.perf_counter() - started))
                try:
                    name, item = await asyncio.wait_for(events.get(), timeout)
                except asyncio.TimeoutError:
                    logger.info(
                        "voice hedge: no token from %s after %.0fms, starting %s",
                        h._primary.label, h._hedge_after_s * 1000, h._backup.label,
                    )
                    start("backup")
                    continue
                if item is _END or isinstance(item, BaseException):
                    err = item if item is not _END else APIConnectionError(
                        f"{llms[name].label} ended without output")
                    fail(name, err)
                    if "backup" not in racers:
                        start("backup")  # primary is down: no reason to wait
                    elif len(errors) == len(racers):
                        raise APIConnectionError(
                            f"both hedged rungs failed: {'; '.join(str(e)[:120] for e in errors.values())}"
                        )
                    continue
                buffers[name].append(item)
                if _has_output(item):
                    winner = name

            for name, task in racers.items():
                if name != winner:
                    task.cancel()
            ttft_ms = (time.perf_counter() - started) * 1000
            log = logger.info if ("backup" in racers or winner != "primary") else logger.debug
            log("voice hedge: served by %s, first token %.0fms%s", llms[winner].label, ttft_ms,
                " (hedged)" if "backup" in racers else "")
            usage = None
            scrubber = TokenScrubber()
            reply: list[str] = []

            def forward(chunk) -> None:
                delta = getattr(chunk, "delta", None)
                if delta is not None and delta.content:
                    delta.content = scrubber.feed(delta.content)
                    reply.append(delta.content)
                self._event_ch.send_nowait(chunk)

            for chunk in buffers[winner]:
                usage = getattr(chunk, "usage", None) or usage
                forward(chunk)
            while True:
                name, item = await events.get()
                if name != winner:
                    continue
                if item is _END:
                    tail = scrubber.flush()
                    if tail:
                        reply.append(tail)
                        self._event_ch.send_nowait(lk_llm.ChatChunk(
                            id="hedge-tail", delta=lk_llm.ChoiceDelta(role="assistant", content=tail)))
                    h._record_usage(llms[winner], usage, ttft_ms, "backup" in racers, "".join(reply))
                    return
                usage = getattr(item, "usage", None) or usage
                if isinstance(item, BaseException):
                    raise item if isinstance(item, APIConnectionError | APIStatusError) else \
                        APIConnectionError(f"{llms[winner].label} failed mid-stream: {item}")
                forward(item)
        finally:
            for task in racers.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*racers.values(), return_exceptions=True)


def usage_summary(llm) -> dict[str, dict]:
    """Per-model token and cost totals recorded by this session's HedgedLLM."""
    if isinstance(llm, HedgedLLM):
        return llm.usage_totals
    for inner in getattr(llm, "_llm_instances", None) or []:
        if isinstance(inner, HedgedLLM):
            return inner.usage_totals
    return {}


def primary_guard(llm) -> "BreakerGuard | None":
    """The BreakerGuard a voice LLM will try first."""
    if isinstance(llm, BreakerGuard):
        return llm
    if isinstance(llm, HedgedLLM):
        return primary_guard(llm._primary)
    instances = getattr(llm, "_llm_instances", None)  # FallbackAdapter
    return primary_guard(instances[0]) if instances else None


async def warm_up(llm, *, timeout_s: float = 3.0) -> float | None:
    """1-token request on the primary rung's own client, so its connection,
    imports and upstream routing are warm before the greeting. Returns ms, or None
    if skipped or failed (a failed warm-up is recorded as a health result, so new
    sessions demote the rung; this session's hedge covers the greeting)."""
    guard = primary_guard(llm)
    if guard is None or llm_ladder.breaker.is_locked(guard._entry.key):
        return None
    entry, inner = guard._entry, guard._inner
    client = getattr(inner, "_client", None)
    if client is None:
        return None
    started = time.perf_counter()
    try:
        if entry.provider == "openrouter":
            extra_body = {"provider": llm_models.openrouter_provider_prefs("voice")}
            reasoning = llm_models.openrouter_reasoning(entry, "voice")
            if reasoning is not None:
                extra_body["reasoning"] = reasoning
            coro = client.chat.completions.create(
                model=entry.model, messages=[{"role": "user", "content": "hi"}],
                max_tokens=1, extra_body=extra_body,
            )
        else:
            config = {"max_output_tokens": 1}
            thinking = llm_models.gemini_thinking_config(entry.model)
            if thinking is not None:
                config["thinking_config"] = thinking
            coro = client.aio.models.generate_content(model=entry.model, contents="hi", config=config)
        await asyncio.wait_for(coro, timeout_s)
    except Exception as e:
        logger.warning("voice warm-up: %s failed: %s", entry.label, str(e)[:160] or type(e).__name__)
        llm_health.record(entry, ok=False, ms=None, error=f"warm-up: {e!r}")
        return None
    ms = (time.perf_counter() - started) * 1000
    logger.info("voice warm-up: %s %.0fms", entry.label, ms)
    return ms


_background: set[asyncio.Task] = set()


def build_voice_llm(*, max_output_tokens: int, temperature: float = 0.6, warm: bool = True):
    """Build the voice LLM: VOICE_LADDER ordered by canary health, each entry
    breaker-guarded, rungs 1+2 hedged, the rest behind a FallbackAdapter.

    Entries whose provider isn't configured are dropped at build time rather than
    left in to fail — an unset OPENROUTER_API_KEY is "not available", not "broken".
    With `warm`, a warm-up request on the primary starts in the background (it
    runs while the session connects to the room, before the greeting).
    """
    instances = []
    for entry in llm_health.order_by_health(llm_models.VOICE_LADDER):
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
    chain: list[lk_llm.LLM] = list(instances)
    hedge_s = llm_models.VOICE_HEDGE_AFTER_MS / 1000.0
    if len(instances) >= 2 and hedge_s > 0:
        chain = [HedgedLLM(instances[0], instances[1], hedge_after_s=hedge_s,
                           on_failure=record_voice_unavailable)] + instances[2:]
    if len(chain) == 1:
        llm = chain[0]
    else:
        # Default attempt_timeout is 5s; Google rejects that as the HTTP deadline.
        attempt_s = llm_models.gemini_http_timeout_ms("voice") / 1000.0
        llm = lk_llm.FallbackAdapter(chain, attempt_timeout=attempt_s)

    if warm:
        try:
            task = asyncio.get_running_loop().create_task(warm_up(llm), name="voice-warm-up")
        except RuntimeError:
            pass  # no running loop (scripts, tests): nothing to warm for
        else:
            _background.add(task)
            task.add_done_callback(_background.discard)
    return llm


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
