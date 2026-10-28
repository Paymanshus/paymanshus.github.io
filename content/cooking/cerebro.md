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

Let's be honest: nobody forms their own opinions anymore. We borrow them from the internet hive
mind. So I built a bro to read the hive mind for me, named after Professor X's mind-reading
machine.

Everyone has their own hive mind, too. Some people trust Reddit, some trust X, most trust a mix.
Point CereBro at a target, like a GPU, a laptop or a framework, and the fields you care about. It
pulls opinions from Reddit, Hacker News, forums and the open web and clusters them into pros and
cons with an LLM. You skip the 30 open tabs and go straight to what you need to make up your mind.

## The fun part: ranking opinions

Ranking is a hard problem. Ranking opinions, which are subjective by definition, is harder.
Turning "this card is a beast" and "absolute furnace, returned it" into something you can count
is the same kind of problem recommender systems and retrieval live on, and it's a cool one to
solve.

CereBro's answer: the LLM only extracts and clusters. Scoring is deterministic, zero-LLM math
over weighted claims, and every number traces back to a source link. Exclude a source or
re-weight one and everything recomputes instantly, with no model call. An LLM writes a summary
on top, labelled as synthesized, and it never outranks the counts underneath.
