---
title: CereBro
summary: Structured, auditable, weighted opinion mining over the messy subjective web.
date: 2026-07-07
status: building
stack: [Next.js, React 19, Tailwind v4, Drizzle, Supabase, LLM layer, Vitest]
repo: https://github.com/Paymanshus/CereBro
thumbnail:
  src: /cooking/cerebro/thumb.webp
  alt: "41 opinions about the RTX 5070 Ti wired into a ledger of 23 pros and 18 cons, with one r/nvidia opinion traced in red to the unit it became."
  width: 1600
  height: 900
# The graphic stays as the detail-view hero once a real screenshot replaces the card thumbnail.
hero:
  src: /cooking/cerebro/thumb.webp
  alt: "41 opinions about the RTX 5070 Ti wired into a ledger of 23 pros and 18 cons, with one r/nvidia opinion traced in red to the unit it became."
  width: 1600
  height: 900
---

Point it at a target, like a GPU, a laptop or a framework, and the fields you care about. CereBro pulls
opinions from Reddit, Hacker News, forums and the open web, clusters them into pros and cons with
an LLM, then scores everything with deterministic, zero-LLM math.

Every number traces back to weighted claims with a source link, so excluding a source or
re-weighting one recomputes instantly with no model call. The LLM-written summary sits on top,
labelled as synthesized, and is never allowed to outrank the counts underneath it.
