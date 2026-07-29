#!/usr/bin/env python3
"""
Probe every ladder entry: does it resolve, does it stream, and how fast?

Replaces probe_gemini.py, which only covered Gemini. This exists because two
things about the upstream providers change without notice and silently break
production:

  1. Gemini sunsets models. 2.5-flash and 2.5-flash-lite began 404ing mid-2026.
  2. OpenRouter's free-model catalogue churns, so a `:free` slug in
     llm_models.py can stop existing.

The ladder degrades rather than breaks in both cases (a 404 disables just that
entry), but you still want to know, and this is how you find out.

WHAT IT ANSWERS
    --entries      TTFT / total / tokens for every configured entry, and whether
                   chunks actually arrive INCREMENTALLY. That last one matters
                   more than it looks: voice TTFT depends on tokens reaching
                   Cartesia as they are generated. A provider that buffers the
                   whole completion and sends it at once reports a fine "TTFT"
                   while making voice worse. `chunks=1` is the tell.
    --list-gemini  Which Gemini models the key can actually see.
    --quota-probe  Are Gemini free-tier limits PER MODEL or SHARED across models?
                   llm_models.py assumes per-model (no quota_group set). If they
                   turn out to be shared, tag the Gemini entries `@google-free`
                   so one 429 locks all of them instead of paying a doomed hop.
                   This deliberately BURNS free-tier quota — hence opt-in.

USAGE
    cd agent
    .venv/bin/python tests/probe_llm.py                  # entries + streaming
    .venv/bin/python tests/probe_llm.py --list-gemini
    .venv/bin/python tests/probe_llm.py --quota-probe    # burns quota
"""

from __future__ import annotations

import os
import sys
import time
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.local")

import aiohttp

import llm_models
import llm_context
import llm_ladder
from prompts import TERMINAL_PERSONA_BODY
from resume_context import get_resume_index

PROBE_QUESTION = "What did you work on at Maersk?"


def all_entries() -> list[llm_models.LadderEntry]:
    """Every distinct entry across all three ladders, in first-seen order."""
    seen, out = set(), []
    for ladder in (llm_models.LLM_LADDER, llm_models.VOICE_LADDER, llm_models.SYNC_LADDER):
        for entry in ladder:
            if entry.label in seen:
                continue
            seen.add(entry.label)
            out.append(entry)
    return out


# ─── Entry probe ───────────────────────────────────────────────────

async def probe_entry(entry, ctx, session, timeout_ms: int) -> dict:
    """Time one entry and detect whether it really streams.

    Streaming is judged by counting content chunks, not by timing: a short reply
    can legitimately finish within milliseconds of its first token, so a
    timing-based guess produces false "not streaming" verdicts.
    """
    try:
        result = await llm_ladder.call_entry(
            entry, ctx,
            surface="terminal",
            timeout_ms=timeout_ms,
            max_tokens=120,
            stream=True,
            session=session,
        )
    except llm_ladder.LLMError as err:
        return {
            "entry": entry.label, "ok": False,
            "kind": err.kind, "error": err.message,
        }

    gen_ms = result.total_ms - (result.ttft_ms or result.total_ms)
    return {
        "entry": entry.label,
        "ok": True,
        "resolved": result.resolved_model,
        "ttft_ms": result.ttft_ms,
        "total_ms": result.total_ms,
        "gen_ms": gen_ms,
        "in": result.prompt_tokens,
        "out": result.completion_tokens,
        "cached": result.cached_tokens,
        "cost": result.cost,
        "chunks": result.chunks,
        # One chunk means the provider buffered the whole completion and sent it
        # at once. TTFT looks fine in that case but voice suffers, because TTS
        # cannot start until generation has finished.
        "streamed": result.chunks > 1,
        "text": result.text,
    }


async def run_entries(args) -> int:
    ctx = llm_context.build(
        PROBE_QUESTION, [],
        persona_body=TERMINAL_PERSONA_BODY,
        index=get_resume_index(),
        mode="full_hint",
    )
    entries = all_entries()

    print(f"Probing {len(entries)} entr(ies). Prompt: {len(ctx.system)} chars system, "
          f"mode={ctx.mode}")
    if not llm_ladder.openrouter_enabled():
        print("NOTE: OPENROUTER_API_KEY unset — OpenRouter entries will be skipped.")
    print()
    print(f"{'entry':52} {'TTFT':>8} {'total':>8} {'in':>6} {'out':>5} {'cached':>7} {'chunks':>7} {'stream':>7}")
    print("-" * 100)

    failures = []
    async with aiohttp.ClientSession() as session:
        for entry in entries:
            if entry.provider == "openrouter" and not llm_ladder.openrouter_enabled():
                print(f"{entry.label:52} {'—':>8} {'—':>8}  (skipped: not configured)")
                continue
            r = await probe_entry(entry, ctx, session, args.timeout_ms)
            if not r["ok"]:
                print(f"{entry.label:52} FAILED [{r['kind']}] {r['error'][:60]}")
                failures.append(r)
            else:
                print(
                    f"{r['entry']:52} {r['ttft_ms'] or -1:7.0f}m {r['total_ms']:7.0f}m "
                    f"{r['in']:6} {r['out']:5} {r['cached']:7} {r['chunks']:7} "
                    f"{'yes' if r['streamed'] else 'NO':>7}"
                )
                if not r["streamed"]:
                    print(f"{'':52} ^ single chunk: provider buffered the whole "
                          f"completion — bad for voice TTFT")
                if r["resolved"] and r["resolved"] != entry.model:
                    print(f"{'':52} resolved to: {r['resolved']}")
            await asyncio.sleep(args.sleep)

    print()
    if failures:
        print(f"{len(failures)} entr(ies) failed. A `model_not_found` means the slug in "
              "llm_models.py is stale — update it.")
        return 1
    print("All configured entries resolved.")
    return 0


# ─── Gemini quota-sharing probe ────────────────────────────────────

async def run_quota_probe(args) -> int:
    """Saturate one Gemini model's RPM, then immediately call another.

    If the second call succeeds, free-tier quotas are PER MODEL and the ladder's
    default (no quota_group) is right. If it also 429s, they share a pool and
    both Gemini entries should be tagged `@google-free` so one failure locks both.
    """
    primary = llm_models.parse_entry("gemini:gemini-3.5-flash")
    secondary = llm_models.parse_entry("gemini:gemini-3.1-flash-lite")

    ctx = llm_context.build(
        "hi", [], persona_body="Reply with one word.",
        index=get_resume_index(), mode="persona_bm25_user",
    )

    print("QUOTA PROBE — this deliberately burns free-tier requests.")
    print(f"Saturating {primary.model} (up to {args.burst} rapid calls)...")

    hit_429 = False
    for i in range(1, args.burst + 1):
        try:
            await llm_ladder.call_entry(
                primary, ctx, surface="terminal", timeout_ms=20000, max_tokens=8
            )
            print(f"  {i:2}. ok")
        except llm_ladder.LLMError as err:
            print(f"  {i:2}. {err.kind}: {err.message[:70]}")
            if err.kind in (llm_ladder.KIND_MINUTE, llm_ladder.KIND_DAY):
                hit_429 = True
                break

    if not hit_429:
        print()
        print(f"Never hit a 429 in {args.burst} calls — free RPM for "
              f"{primary.model} is higher than that, or billing is attached.")
        print("Inconclusive. Re-run with a larger --burst.")
        return 0

    print()
    print(f"{primary.model} is rate-limited. Immediately calling {secondary.model}...")
    try:
        await llm_ladder.call_entry(
            secondary, ctx, surface="terminal", timeout_ms=20000, max_tokens=8
        )
        print()
        print("RESULT: PER-MODEL quotas.")
        print(f"  {secondary.model} answered while {primary.model} was limited.")
        print("  → llm_models.py is correct as-is; leave quota_group unset.")
        print("  → flash → flash-lite is a genuine 429 fallback.")
    except llm_ladder.LLMError as err:
        if err.kind in (llm_ladder.KIND_MINUTE, llm_ladder.KIND_DAY):
            print()
            print("RESULT: SHARED quota pool.")
            print(f"  {secondary.model} was limited too ({err.kind}).")
            print("  → Tag both Gemini entries `@google-free` in llm_models.py so one")
            print("    429 locks the whole group instead of paying a doomed round trip.")
        else:
            print(f"\nInconclusive — {secondary.model} failed for another reason: "
                  f"{err.kind}: {err.message[:80]}")
    return 0


# ─── Gemini catalogue ──────────────────────────────────────────────

def run_list_gemini() -> int:
    from google import genai

    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        print("GOOGLE_API_KEY not set", file=sys.stderr)
        return 1
    client = genai.Client(api_key=key)
    print("generateContent-capable models containing 'flash':")
    for m in client.models.list():
        if "generateContent" in (m.supported_actions or []) and "flash" in m.name:
            print("  ", m.name)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Probe every configured LLM ladder entry.")
    p.add_argument("--timeout-ms", type=int, default=30000,
                   help="generous, so a slow model is measured rather than timed out")
    p.add_argument("--sleep", type=float, default=2.0, help="pause between entries")
    p.add_argument("--list-gemini", action="store_true", help="list visible Gemini models")
    p.add_argument("--quota-probe", action="store_true",
                   help="determine whether Gemini free limits are per-model or shared "
                        "(BURNS QUOTA)")
    p.add_argument("--burst", type=int, default=25,
                   help="calls to fire during --quota-probe before giving up")
    args = p.parse_args()

    print(llm_models.describe())
    print()

    if args.list_gemini:
        return run_list_gemini()
    if args.quota_probe:
        return asyncio.run(run_quota_probe(args))
    return asyncio.run(run_entries(args))


if __name__ == "__main__":
    sys.exit(main())
