#!/usr/bin/env python3
"""
Persona benchmark: what visitors ask, what the voice and terminal agents answer.

THE QUESTION THIS ANSWERS
    After a prompt, resume or notes change, does the agent still answer like
    the owner, stay inside the guardrails and pick the right context? Unit
    tests cover retrieval; this covers the model's actual replies.

WHAT IT SENDS
    Exactly what production sends for a first turn, built by the production
    code: `llm_context.build` (terminal, with the knowledge snippet) and
    `llm_context.voice_context`, the function `llm_voice.prepare_voice_ctx`
    uses (voice: BM25 top-2 or full resume, plus the snippet). Nothing from
    LiveKit is imported or called, and no STT or TTS: LLM calls only.

THE QUESTIONS
    tests/persona_bench.jsonl, one per line:
      id, cat, q        identity, category, the visitor's message
      notes             whether a notes/blog/project snippet should be attached
                        (checked for free, without calling a model)
      must_all          regexes that must ALL match the reply (case-insensitive)
      must_any          regexes of which at least one must match
      must_not          regexes that must NOT match
    On top of these, every reply gets the surface's style checks: word limit,
    no em dashes, no markdown, no press-release words, first person only, and
    sentence case on the terminal. Checks are a tripwire, not a grade: read
    the replies in the report too.

USAGE
    cd agent
    .venv/bin/python tests/eval_persona.py --retrieval            # free: context checks only
    .venv/bin/python tests/eval_persona.py --run                  # call the first rung of each ladder
    .venv/bin/python tests/eval_persona.py --run --surface voice --entries openrouter:deepseek/deepseek-v4.1-flash-1017
    .venv/bin/python tests/eval_persona.py --emit /tmp/payloads   # write each request body, to run elsewhere
    .venv/bin/python tests/eval_persona.py --score replies.jsonl  # score replies gathered elsewhere
                                                                  # ({"id", "surface", "reply", "model"} per line)

    Results go to tests/results/persona-<timestamp>.{jsonl,md} (gitignored);
    copy the write-up to readmes/perf/<date>/ per CLAUDE.md.

COST
    48 questions x 2 surfaces = 96 calls. Terminal sends ~6K tokens (cached
    after the first), voice ~1.5-6K. On Haiku 5.5 + DeepSeek flash that is
    roughly $0.02-0.04 a full run. Requires OPENROUTER_API_KEY (and/or
    GOOGLE_API_KEY) in agent/.env.local and network access to the provider.
"""

from __future__ import annotations

import re
import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.local")

import llm_models
import llm_context
import voice_lexicon
from prompts import TERMINAL_PERSONA_BODY, VOICE_PERSONA_INSTRUCTIONS
from resume_context import get_resume_index, knowledge_block, knowledge_lookup

BENCH = Path(__file__).parent / "persona_bench.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"
SURFACES = ("terminal", "voice")

# Mirrors main.py / prompts.py. Kept literal so the harness doesn't import
# main.py (and with it the whole LiveKit worker).
VOICE_MAX_OUTPUT_TOKENS = 100
VOICE_TEMPERATURE = 0.6
RESUME_SCORE_THRESHOLD = 2.5
WORD_LIMIT = {"terminal": 45, "voice": 40}

PRESS_WORDS = r"\b(passionate|cutting-edge|game-changer|leverage|excited|great question|absolutely|I'd be happy to)\b"
STYLE_CHECKS = {
    "em-dash": lambda r, s: "—" not in r,
    "markdown": lambda r, s: not re.search(r"(\*\*|^#|^\s*[-*] |`)", r, re.M),
    "press-words": lambda r, s: not re.search(PRESS_WORDS, r, re.I),
    "first-person": lambda r, s: not re.search(r"\b(Paymanshu (is|has|was|works)|he (is|has|works|built))\b", r),
    # "X isn't Y, it's Z" and "gets you a demo, not a product." (banned in prompts.py)
    "x-not-y": lambda r, s: not re.search(r"(isn't|is not|wasn't) [^.,]{1,40}, (it's|it is)|, not an? [\w-]+[.!]", r, re.I),
    "sentence-case": lambda r, s: s != "terminal" or not r[:1].islower(),
    "length": lambda r, s: len(r.split()) <= WORD_LIMIT[s] + 5,  # small slack: tripwire, not a ruler
}


def load_bench(path: Path = BENCH) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ─── Building the exact production payloads ────────────────────────

def terminal_ctx(question: str, index) -> llm_context.BuiltContext:
    return llm_context.build(
        question, [], persona_body=TERMINAL_PERSONA_BODY, index=index,
        knowledge=knowledge_block,
    )


def voice_ctx(question: str, index) -> tuple[llm_context.BuiltContext, dict]:
    """The voice turn as llm_voice.prepare_voice_ctx builds it: STT word fixes,
    then the context as an assistant message right before the caller's turn."""
    question = voice_lexicon.fix_transcript(question)
    context, info = llm_context.voice_context(question, index, RESUME_SCORE_THRESHOLD, knowledge_block)
    turns = [
        {"role": "assistant", "text": llm_context.VOICE_CONTEXT_PREFIX + context},
        {"role": "user", "text": question},
    ]
    return llm_context.BuiltContext(mode="voice", system=VOICE_PERSONA_INSTRUCTIONS, turns=turns), info


def build(surface: str, question: str, index):
    if surface == "terminal":
        ctx = terminal_ctx(question, index)
        return ctx, {"bm25": round(ctx.bm25_score, 2)}
    return voice_ctx(question, index)


# ─── Scoring ───────────────────────────────────────────────────────

def score(item: dict, surface: str, reply: str) -> list[str]:
    """Names of the failed checks (empty = pass)."""
    fails = [name for name, ok in STYLE_CHECKS.items() if not ok(reply, surface)]
    for pat in item.get("must_all", []):
        if not re.search(pat, reply, re.I):
            fails.append(f"missing:{pat}")
    if item.get("must_any") and not any(re.search(p, reply, re.I) for p in item["must_any"]):
        fails.append("missing-any:" + " / ".join(item["must_any"]))
    for pat in item.get("must_not", []):
        if re.search(pat, reply, re.I):
            fails.append(f"forbidden:{pat}")
    return fails


def retrieval_report(bench: list[dict]) -> int:
    """Free check: does each question get (or not get) a notes snippet?"""
    bad = 0
    for item in bench:
        ctx, sc = knowledge_lookup(item["q"])
        got = bool(ctx)
        mark = "ok " if got == item.get("notes", False) else "BAD"
        bad += mark == "BAD"
        head = ctx.split("\n")[0][:60] if ctx else ""
        print(f"{mark} {sc:5.1f} {item['id']:18} {head}")
    print(f"\n{len(bench) - bad}/{len(bench)} retrieval expectations met")
    return bad


def write_report(records: list[dict], stem: Path) -> Path:
    stem.parent.mkdir(parents=True, exist_ok=True)
    with stem.with_suffix(".jsonl").open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    lines = [f"# Persona benchmark {stem.name}", ""]
    for surface in SURFACES:
        rows = [r for r in records if r["surface"] == surface]
        if not rows:
            continue
        passed = sum(not r["fails"] for r in rows)
        lines += [f"## {surface}: {passed}/{len(rows)} pass all checks", "",
                  "| id | model | context | reply | failed checks |", "|---|---|---|---|---|"]
        for r in rows:
            reply = r["reply"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {r['id']} | {r.get('model', '')} | {r.get('source', '')} | {reply} | {', '.join(r['fails'])} |")
        lines.append("")
    md = stem.with_suffix(".md")
    md.write_text("\n".join(lines))
    return md


# ─── Running ───────────────────────────────────────────────────────

async def run(bench, surfaces, entries, index) -> list[dict]:
    import aiohttp
    import llm_ladder

    records = []
    async with aiohttp.ClientSession() as session:
        for surface in surfaces:
            ladder = llm_models.VOICE_LADDER if surface == "voice" else llm_models.LLM_LADDER
            chosen = [e for e in ladder if not entries or e.label in entries] or ladder[:1]
            for entry in chosen:
                for item in bench:
                    ctx, info = build(surface, item["q"], index)
                    kwargs = {}
                    if surface == "voice":
                        kwargs = {"max_tokens": VOICE_MAX_OUTPUT_TOKENS, "temperature": VOICE_TEMPERATURE}
                    try:
                        res = await llm_ladder.call_entry(entry, ctx, surface=surface, session=session, **kwargs)
                        reply, err = res.text.strip(), None
                    except Exception as e:  # noqa: BLE001 — recorded, not fatal: one bad call shouldn't sink the run
                        reply, err = "", repr(e)
                    records.append({
                        "id": item["id"], "cat": item["cat"], "q": item["q"], "surface": surface,
                        "model": entry.label, "source": info.get("source", f"bm25 {info.get('bm25')}"),
                        "reply": reply, "error": err,
                        "fails": score(item, surface, reply) if reply else ["error"],
                    })
                    print(f"[{surface}] {item['id']:18} {'PASS' if not records[-1]['fails'] else records[-1]['fails']}")
    return records


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--retrieval", action="store_true", help="only check snippet retrieval (free)")
    ap.add_argument("--run", action="store_true", help="call the models")
    ap.add_argument("--emit", type=Path, help="write each request body as JSON to this directory")
    ap.add_argument("--score", type=Path, help="score a replies JSONL gathered elsewhere")
    ap.add_argument("--surface", choices=SURFACES, action="append")
    ap.add_argument("--entries", nargs="*", default=[], help="ladder labels to run (default: first rung)")
    ap.add_argument("--only", nargs="*", default=[], help="question ids or categories")
    args = ap.parse_args()

    bench = load_bench()
    if args.only:
        bench = [b for b in bench if b["id"] in args.only or b["cat"] in args.only]
    surfaces = args.surface or list(SURFACES)
    index = get_resume_index()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.retrieval:
        sys.exit(1 if retrieval_report(bench) else 0)

    if args.emit:
        args.emit.mkdir(parents=True, exist_ok=True)
        for surface in surfaces:
            for item in bench:
                ctx, info = build(surface, item["q"], index)
                out = {"id": item["id"], "surface": surface, "info": info,
                       "messages": llm_context.to_openai_messages(ctx)}
                (args.emit / f"{surface}-{item['id']}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        print(f"wrote {len(bench) * len(surfaces)} payloads to {args.emit}")
        return

    if args.score:
        by_id = {b["id"]: b for b in load_bench()}
        records = []
        for line in args.score.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            item = by_id[r["id"]]
            r.update(cat=item["cat"], q=item["q"], fails=score(item, r["surface"], r["reply"]))
            records.append(r)
        print(write_report(records, RESULTS_DIR / f"persona-{stamp}"))
        return

    if args.run:
        records = asyncio.run(run(bench, surfaces, set(args.entries), index))
        print(write_report(records, RESULTS_DIR / f"persona-{stamp}"))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
