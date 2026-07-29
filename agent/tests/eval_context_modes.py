#!/usr/bin/env python3
"""
Measure the four prompt-layout modes against every ladder entry.

THE QUESTION THIS ANSWERS
    Where should the resume go — system prefix, user turn, or BM25-selected into
    the system message like the original implementation? That choice decides
    whether prompt caching can work at all, and it trades input tokens against
    cache hits against answer quality. This harness produces the numbers; the
    default in llm_context.py should follow them rather than intuition.

THE FOUR ARMS (see llm_context for the layouts)
    full_hint          persona + FULL resume in system; BM25 hint in user turn
    full_only          persona + FULL resume in system; bare question
    persona_bm25_user  persona only in system; BM25 + question in user turn
    bm25_system        persona + BM25 in system  ← the original, cache-hostile

WHY MULTI-TURN
    A single request cannot show caching. Turn 1 WRITES the cache, turns 2-3 READ
    it, and a growing history is exactly what would break prefix stability if the
    messages were ordered wrongly. So each arm runs a scripted 3-turn
    conversation, and turn 1 is reported separately from turns 2-3 rather than
    averaged in — they are structurally different events.

WHY THE PREFIX HASH
    `prefix_sha` proves byte-stability of the cacheable prefix directly. A zero
    `cached_tokens` could mean "prefix unstable" or "provider doesn't cache" or
    "under the minimum"; the hash disambiguates the first from the rest.

WHY THE REPLY TEXT IS RECORDED
    The arms show the model different amounts of context (full_only the most,
    persona_bm25_user the least), so a latency comparison alone is meaningless — a
    faster arm that answers worse is not a win. The JSONL keeps every reply so
    quality can be judged alongside the numbers.

WARM VS COLD
    Different arms have different prefixes and so never share a cache entry, but
    repeats of the SAME arm do — repeat 2 may hit a cache written by repeat 1.
    That is labelled, not hidden. `--cold` sleeps past the ~5 min provider TTL
    between repeats to measure true first-writes.

USAGE
    cd agent
    .venv/bin/python tests/eval_context_modes.py                    # default sweep
    .venv/bin/python tests/eval_context_modes.py --repeats 1 --entries gemini:gemini-3.5-flash
    .venv/bin/python tests/eval_context_modes.py --cold --sleep 4
    .venv/bin/python tests/eval_context_modes.py --report-only tests/results/<file>.jsonl

Requires GOOGLE_API_KEY and/or OPENROUTER_API_KEY in agent/.env.local.
Cost: the full sweep is ~4 arms x 3 turns x 3 repeats x N entries. At 3 entries
that is ~108 calls, well under $0.10 — but it WILL trip a 20 RPM free-tier
ceiling if fired flat out, hence --sleep.
"""

from __future__ import annotations

import os
import sys
import json
import time
import uuid
import asyncio
import argparse
import logging
import statistics
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.local")

import aiohttp

import llm_models
import llm_context
import llm_ladder
from prompts import TERMINAL_PERSONA_BODY
from resume_context import get_resume_index

RESULTS_DIR = Path(__file__).parent / "results"

# A realistic recruiter conversation: broad opener, a follow-up that depends on
# the first answer, then a comparison that spans two resume sections. The third
# question deliberately needs content BM25 might not retrieve for the earlier
# turns, which is where full-context arms should show an advantage.
QUESTIONS = [
    "What did you work on at Maersk?",
    "Which tools and frameworks did you use there?",
    "How does that compare to your research work?",
]

# Provider prompt-cache TTL is ~5 minutes almost everywhere; overshoot it.
COLD_SLEEP_S = 330


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─── One conversation ──────────────────────────────────────────────

async def run_conversation(
    entry: llm_models.LadderEntry,
    mode: str,
    *,
    repeat: int,
    turns: int,
    index,
    timeout_ms: int,
    max_tokens: int,
    sleep_s: float,
    session: aiohttp.ClientSession,
) -> list[dict]:
    """Run one scripted conversation and return one record per turn."""
    records: list[dict] = []
    history: list[dict] = []
    # Fresh session_id per conversation so OpenRouter's sticky routing behaves as
    # it would for a real visitor, and repeat N doesn't inherit repeat N-1's
    # provider affinity.
    session_id = f"eval-{mode}-{repeat}-{uuid.uuid4().hex[:8]}"

    for turn_idx in range(1, turns + 1):
        question = QUESTIONS[(turn_idx - 1) % len(QUESTIONS)]
        ctx = llm_context.build(
            question, history,
            persona_body=TERMINAL_PERSONA_BODY,
            index=index,
            mode=mode,
        )

        record = {
            "ts": _iso_now(),
            "entry": entry.label,
            "provider": entry.provider,
            "mode": mode,
            "repeat": repeat,
            "turn": turn_idx,
            "question": question,
            "history_turns": len(history),
            "prefix_sha": ctx.system_sha256[:16],
            "prefix_chars": len(ctx.system),
            "prefix_stable_by_design": ctx.prefix_stable,
            "likely_cacheable_by_design": ctx.likely_cacheable,
            "bm25_score": round(ctx.bm25_score, 3),
            "bm25_chars": ctx.bm25_chars,
        }

        try:
            # call_entry, not generate(): we are measuring a specific entry, so
            # the breaker must not reroute us to a different one mid-sweep.
            result = await llm_ladder.call_entry(
                entry, ctx,
                surface="terminal",
                timeout_ms=timeout_ms,
                max_tokens=max_tokens,
                stream=True,          # streaming is the only way to get TTFT
                session_id=session_id,
                session=session,
            )
        except llm_ladder.LLMError as err:
            record.update({"ok": False, "error_kind": err.kind, "error": err.message})
            print(f"    turn {turn_idx}: FAILED [{err.kind}] {err.message[:80]}")
            records.append(record)
            # A failure mid-conversation invalidates the rest of it (no reply to
            # append to history), so stop this conversation here.
            break

        gen_ms = (result.total_ms - result.ttft_ms) if result.ttft_ms else result.total_ms
        throughput = (
            result.completion_tokens / (gen_ms / 1000) if gen_ms > 0 and result.completion_tokens else None
        )
        record.update({
            "ok": True,
            "resolved_model": result.resolved_model,
            "ttft_ms": round(result.ttft_ms, 1) if result.ttft_ms else None,
            "total_ms": round(result.total_ms, 1),
            "throughput_tok_s": round(throughput, 1) if throughput else None,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "cached_tokens": result.cached_tokens,
            "cache_write_tokens": result.cache_write_tokens,
            "cost": result.cost,
            "reply": result.text,
        })
        records.append(record)

        cache_note = ""
        if result.prompt_tokens:
            pct = 100 * result.cached_tokens / result.prompt_tokens
            cache_note = f" cached={result.cached_tokens}/{result.prompt_tokens} ({pct:.0f}%)"
        print(
            f"    turn {turn_idx}: ttft={record['ttft_ms']}ms total={record['total_ms']}ms"
            f" in={result.prompt_tokens} out={result.completion_tokens}{cache_note}"
        )

        history.append({"role": "user", "text": question})
        # The frontend sends assistant turns with role 'system'; mirror that so
        # the harness exercises the same normalisation path as production.
        history.append({"role": "system", "text": result.text})

        if sleep_s:
            await asyncio.sleep(sleep_s)

    return records


# ─── Sweep ─────────────────────────────────────────────────────────

async def sweep(args) -> list[dict]:
    index = get_resume_index()
    entries = resolve_entries(args.entries)
    modes = args.modes

    print(f"Sweep: {len(entries)} entr(ies) x {len(modes)} arm(s) "
          f"x {args.repeats} repeat(s) x {args.turns} turn(s) "
          f"= {len(entries)*len(modes)*args.repeats*args.turns} calls")
    print(f"Entries: {[e.label for e in entries]}")
    print(f"Arms:    {list(modes)}")
    if args.cold:
        print(f"Cold mode: sleeping {COLD_SLEEP_S}s between repeats (TTL expiry)")
    print()

    all_records: list[dict] = []
    async with aiohttp.ClientSession() as session:
        for entry in entries:
            print(f"=== {entry.label} ===")
            for mode in modes:
                print(f"  arm: {mode}")
                for repeat in range(1, args.repeats + 1):
                    warm = "cold" if (args.cold or repeat == 1) else "warm"
                    print(f"   repeat {repeat}/{args.repeats} ({warm})")
                    recs = await run_conversation(
                        entry, mode,
                        repeat=repeat, turns=args.turns, index=index,
                        timeout_ms=args.timeout_ms, max_tokens=args.max_tokens,
                        sleep_s=args.sleep, session=session,
                    )
                    for r in recs:
                        r["cache_state"] = warm
                    all_records.extend(recs)
                    if args.cold and repeat < args.repeats:
                        print(f"      sleeping {COLD_SLEEP_S}s for TTL expiry...")
                        await asyncio.sleep(COLD_SLEEP_S)
    return all_records


def resolve_entries(spec: str | None) -> list[llm_models.LadderEntry]:
    """Which entries to sweep. Defaults to the terminal ladder, deduped."""
    if spec:
        return [llm_models.parse_entry(s) for s in spec.split(",") if s.strip()]
    seen, out = set(), []
    for entry in llm_models.LLM_LADDER:
        if entry.label in seen:
            continue
        seen.add(entry.label)
        out.append(entry)
    return out


# ─── Report ────────────────────────────────────────────────────────

def _med(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.median(vals), 1) if vals else None


def render_report(records: list[dict]) -> str:
    """Markdown summary. Turn 1 is separated from turns 2+ throughout, because
    turn 1 writes the cache and later turns read it."""
    lines: list[str] = []
    lines.append("# Context-mode evaluation")
    lines.append("")
    lines.append(f"Generated {_iso_now()} — {len(records)} turn records.")
    lines.append("")

    ok = [r for r in records if r.get("ok")]
    failed = [r for r in records if not r.get("ok")]

    # Prefix stability is a property of the arm, verifiable straight from data.
    lines.append("## Prefix stability (measured, not assumed)")
    lines.append("")
    lines.append("| arm | distinct prefix hashes | stable? | prefix chars |")
    lines.append("|---|---|---|---|")
    for mode in llm_context.MODES:
        rows = [r for r in records if r["mode"] == mode]
        if not rows:
            continue
        hashes = {r["prefix_sha"] for r in rows}
        chars = rows[0]["prefix_chars"]
        lines.append(f"| `{mode}` | {len(hashes)} | {'yes' if len(hashes) == 1 else 'NO'} | {chars} |")
    lines.append("")
    lines.append("A stable prefix is necessary but not sufficient for caching — it "
                 "also has to clear the provider's minimum (1,024 tokens for "
                 "OpenAI/Gemini-Flash; DeepSeek documents none).")
    lines.append("")

    lines.append("Turn 1 writes the cache and later turns read it, so they are never")
    lines.append("averaged together. `state` separates a conversation that started with a")
    lines.append("cold cache (repeat 1, or every repeat under `--cold`) from one that")
    lines.append("inherited a warm cache from an earlier repeat of the same arm.")
    lines.append("")

    for entry_label in sorted({r["entry"] for r in ok}):
        lines.append(f"## {entry_label}")
        lines.append("")
        lines.append("| arm | turn | state | n | TTFT ms | total ms | tok/s | in | out | cached | cost |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for mode in llm_context.MODES:
            for turn_label, pred in (("1", lambda t: t == 1), ("2+", lambda t: t > 1)):
                for state in ("cold", "warm"):
                    rows = [
                        r for r in ok
                        if r["entry"] == entry_label and r["mode"] == mode
                        and pred(r["turn"]) and r.get("cache_state") == state
                    ]
                    if not rows:
                        continue
                    costs = [r["cost"] for r in rows if r.get("cost") is not None]
                    lines.append(
                        f"| `{mode}` | {turn_label} | {state} | {len(rows)} "
                        f"| {_med([r['ttft_ms'] for r in rows])} "
                        f"| {_med([r['total_ms'] for r in rows])} "
                        f"| {_med([r['throughput_tok_s'] for r in rows])} "
                        f"| {_med([r['prompt_tokens'] for r in rows])} "
                        f"| {_med([r['completion_tokens'] for r in rows])} "
                        f"| {_med([r['cached_tokens'] for r in rows])} "
                        f"| {round(statistics.median(costs), 6) if costs else '-'} |"
                    )
        lines.append("")

    if failed:
        lines.append("## Failures")
        lines.append("")
        lines.append("| entry | arm | turn | kind | message |")
        lines.append("|---|---|---|---|---|")
        for r in failed:
            lines.append(
                f"| {r['entry']} | `{r['mode']}` | {r['turn']} "
                f"| {r.get('error_kind')} | {str(r.get('error'))[:80]} |"
            )
        lines.append("")

    lines.append("## Sample replies")
    lines.append("")
    lines.append("Quality has to be read, not inferred from latency — the arms show "
                 "the model different amounts of context.")
    lines.append("")
    for mode in llm_context.MODES:
        rows = [r for r in ok if r["mode"] == mode]
        if not rows:
            continue
        lines.append(f"**`{mode}`**")
        lines.append("")
        for turn in sorted({r["turn"] for r in rows}):
            sample = next((r for r in rows if r["turn"] == turn), None)
            if sample:
                lines.append(f"- *T{turn} — {sample['question']}*")
                lines.append(f"  > {sample['reply'].strip()[:400]}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--repeats", type=int, default=3, help="conversations per arm (default 3)")
    p.add_argument("--turns", type=int, default=3, help="turns per conversation (default 3)")
    p.add_argument("--sleep", type=float, default=3.0,
                   help="seconds between calls; paces against free-tier RPM (default 3.0)")
    p.add_argument("--cold", action="store_true",
                   help=f"sleep {COLD_SLEEP_S}s between repeats so caches expire")
    p.add_argument("--entries", default=None,
                   help="comma-separated provider:model specs (default: the terminal ladder)")
    p.add_argument("--modes", default=",".join(llm_context.MODES),
                   help="comma-separated arms to run")
    p.add_argument("--timeout-ms", type=int, default=30000,
                   help="generous, so a slow provider is measured rather than timed out")
    p.add_argument("--max-tokens", type=int, default=llm_models.TERMINAL_MAX_OUTPUT_TOKENS)
    p.add_argument("--out", default=None, help="JSONL output path")
    p.add_argument("--report-only", default=None,
                   help="skip the sweep; re-render the report from an existing JSONL")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.report_only:
        path = Path(args.report_only)
        records = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        report_path = path.with_suffix(".md")
        report_path.write_text(render_report(records))
        print(f"Report → {report_path}")
        return 0

    args.modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    unknown = [m for m in args.modes if m not in llm_context.MODES]
    if unknown:
        print(f"error: unknown mode(s) {unknown}; expected from {llm_context.MODES}",
              file=sys.stderr)
        return 1

    if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("OPENROUTER_API_KEY"):
        print("error: need GOOGLE_API_KEY and/or OPENROUTER_API_KEY "
              "(checked env + agent/.env.local)", file=sys.stderr)
        return 1

    started = time.time()
    records = asyncio.run(sweep(args))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) if args.out else RESULTS_DIR / f"context_modes_{stamp}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    report_path = out.with_suffix(".md")
    report_path.write_text(render_report(records))

    ok = sum(1 for r in records if r.get("ok"))
    print()
    print(f"Done in {time.time()-started:.0f}s — {ok}/{len(records)} turns succeeded")
    print(f"  raw    → {out}")
    print(f"  report → {report_path}")
    print()
    print("Next: hand the JSONL to a subagent to evaluate latency vs cache-hit vs")
    print("reply quality, and set llm_context.DEFAULT_MODE from that.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
