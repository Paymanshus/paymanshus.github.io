"""
Prompt assembly for the terminal chat — and the four layouts the eval harness
compares.

WHY THIS MODULE EXISTS
    Prompt caching matches a *prefix*. Everything that varies per request must
    therefore come after everything that is stable. The original implementation
    interpolated per-question BM25 results into the SYSTEM message, so the prefix
    differed on every single request and no provider could ever cache it.

    Moving the varying part into the user turn fixes that — but only if what is
    left in the system message is big enough to be cacheable at all. Documented
    minimums are 1,024 tokens for OpenAI and Gemini-Flash (4,096 for Gemini Pro);
    DeepSeek and Groq document none. The persona alone is ~200 tokens, so the
    stable prefix needs the full resume (~2.5K) in it to clear the bar reliably.

THE FOUR MODES
    Selected by LLM_CONTEXT_MODE. `tests/eval_context_modes.py` measures all four
    and the default here should follow that data, not intuition.

    full_hint           system: persona + FULL resume     user: BM25 hint + question
                        Cacheable. BM25 still runs, as a relevance hint over full
                        context rather than as the only context.

    full_only           system: persona + FULL resume     user: question
                        Cacheable. Isolates what BM25 actually contributes.

    persona_bm25_user   system: persona                   user: BM25 + question
                        Fewest tokens sent. Prefix is probably under the 1,024
                        minimum, so caching likely misses — but DeepSeek documents
                        no minimum, so it may cache anyway. Worth measuring.

    bm25_system         system: persona + BM25            user: question
                        The original behaviour. Cache-hostile by construction —
                        kept as the control arm for BM25 scaling experiments.

INVARIANT
    For `full_hint` and `full_only`, `system_sha256` MUST be identical across
    different questions and across turns. That is the property caching depends on,
    and it is asserted directly in tests rather than inferred from a cache-hit
    count (which can be zero for unrelated reasons).
"""

import os
import hashlib
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("llm-context")

MODES = ("full_hint", "full_only", "persona_bm25_user", "bm25_system")
DEFAULT_MODE = "full_hint"

# Attached to the stable prefix. Kept as its own constant so every mode that
# includes the resume formats it identically — a stray whitespace difference
# between call sites would silently break cache hits.
RESUME_BLOCK = "\n\nRESUME CONTEXT:\n{context}\n"

# Wraps the per-question BM25 result in the user turn. Phrased as a hint rather
# than as the authoritative context, because in `full_hint` the model can also see
# the whole resume in the system message.
HINT_BLOCK = (
    "Most relevant resume sections for this question:\n{context}\n\n"
    "Question: {question}"
)


def active_mode() -> str:
    """The configured mode, falling back to the default on an unknown value."""
    mode = os.environ.get("LLM_CONTEXT_MODE", DEFAULT_MODE).strip()
    if mode not in MODES:
        logger.warning(
            "LLM_CONTEXT_MODE=%r is not one of %s — using %s", mode, MODES, DEFAULT_MODE
        )
        return DEFAULT_MODE
    return mode


@dataclass
class BuiltContext:
    """An assembled prompt, provider-agnostic.

    `turns` is normalised to [{"role": "user"|"assistant", "text": str}, ...] and
    always ends with the current user turn.
    """

    mode: str
    system: str
    turns: list[dict] = field(default_factory=list)
    bm25_score: float = 0.0
    bm25_chars: int = 0

    @property
    def system_sha256(self) -> str:
        """Fingerprint of the cacheable prefix. Stable across questions iff the
        mode is a cacheable one — that is the whole point."""
        return hashlib.sha256(self.system.encode("utf-8")).hexdigest()

    @property
    def prefix_stable(self) -> bool:
        """Whether the system prefix is byte-identical across questions.

        True for every mode except `bm25_system`. Necessary for caching but NOT
        sufficient — see `likely_cacheable`.
        """
        return self.mode != "bm25_system"

    @property
    def likely_cacheable(self) -> bool:
        """Whether the prefix is both stable AND plausibly over the provider
        minimum (1,024 tokens for OpenAI/Gemini-Flash; DeepSeek documents none).

        `persona_bm25_user` is stable but only ~200 tokens, so it is excluded
        here — whether it caches anyway on a no-minimum provider is exactly what
        tests/eval_context_modes.py is for. Says nothing about whether a given
        provider actually cached; read `cached_tokens` off the response for that.
        """
        return self.mode in ("full_hint", "full_only")


def _normalise_history(history: list, max_chars: int) -> list[dict]:
    """Coerce the frontend's history into user/assistant turns.

    The terminal sends assistant turns with role 'system' (see
    components/resume/ChatResume.tsx), so anything that isn't 'user' is treated
    as an assistant turn — matching the original server behaviour.
    """
    turns: list[dict] = []
    for turn in history or []:
        if not isinstance(turn, dict):
            continue
        role = "user" if turn.get("role") == "user" else "assistant"
        text = str(turn.get("text", ""))[:max_chars]
        if text:
            turns.append({"role": role, "text": text})
    return turns


def build(
    question: str,
    history: list,
    *,
    persona_body: str,
    index,
    mode: str | None = None,
    top_k: int = 3,
    max_chars: int = 500,
    knowledge=None,
) -> BuiltContext:
    """Assemble the prompt for one request.

    Args:
        question:     The current user message (already length-capped upstream).
        history:      Prior turns, as sent by the frontend.
        persona_body: The persona instructions, WITHOUT any resume block — this
                      module owns where the resume goes, so that placement is
                      identical across call sites.
        index:        A resume_context.ContentIndex.
        mode:         One of MODES; defaults to `active_mode()`.
        top_k:        BM25 sections to retrieve.
        max_chars:    Per-turn text cap.
        knowledge:    Optional callable(question) -> str, e.g.
                      resume_context.knowledge_block. Its text (blog posts,
                      side projects; usually "") is appended to the user turn,
                      never the system prefix, so caching is unaffected.
    """
    mode = mode or active_mode()
    if mode not in MODES:
        raise ValueError(f"unknown context mode {mode!r} (expected one of {MODES})")

    # BM25 runs for every mode except full_only, so the retrieval path stays
    # exercised and measurable even where its output isn't used.
    bm25_text, bm25_score = "", 0.0
    if mode != "full_only":
        bm25_text, bm25_score = index.search_scored(question, top_k=top_k)

    if mode in ("full_hint", "full_only"):
        system = persona_body + RESUME_BLOCK.format(context=index.full_text)
    elif mode == "persona_bm25_user":
        system = persona_body
    else:  # bm25_system
        system = persona_body + RESUME_BLOCK.format(context=bm25_text)

    # A zero score means BM25 matched nothing and handed back the full resume
    # as its fallback; in full_hint the system prompt already carries it, so
    # repeating it in the user turn would double the request for no gain.
    if mode == "full_hint" and bm25_score == 0.0:
        user_text = question
    elif mode in ("full_hint", "persona_bm25_user"):
        user_text = HINT_BLOCK.format(context=bm25_text, question=question)
    else:
        user_text = question
    if knowledge is not None:
        user_text += knowledge(question)

    turns = _normalise_history(history, max_chars)
    turns.append({"role": "user", "text": user_text})

    return BuiltContext(
        mode=mode,
        system=system,
        turns=turns,
        bm25_score=bm25_score,
        bm25_chars=len(bm25_text),
    )


# ─── Provider shapes ───────────────────────────────────────────────
# History goes AFTER the system message in both shapes, so a growing
# conversation never perturbs the cacheable prefix.

def to_openai_messages(ctx: BuiltContext) -> list[dict]:
    """OpenAI / OpenRouter chat-completions `messages`."""
    messages = [{"role": "system", "content": ctx.system}]
    for turn in ctx.turns:
        messages.append({"role": turn["role"], "content": turn["text"]})
    return messages


def to_gemini_contents(ctx: BuiltContext) -> tuple[str, list[dict]]:
    """Gemini `(system_instruction, contents)`.

    Gemini uses 'model' where OpenAI uses 'assistant', and wraps text in `parts`.
    """
    contents = [
        {
            "role": "user" if turn["role"] == "user" else "model",
            "parts": [{"text": turn["text"]}],
        }
        for turn in ctx.turns
    ]
    return ctx.system, contents
