---
title: AaS (Argument as a Service)
summary: Two people disagree. Their AI agents fight it out live while the humans watch, react, and share the carnage.
date: 2026-10-25
status: building
stack: [Next.js 16, FastAPI, LangGraph, arq, Redis, Postgres, WebSockets, Gemini, OpenRouter]
thumbnail:
  src: /cooking/aas/landing.webp
  alt: "The AaS landing page: \"why argue in person? Make your agent do it\", next to a live argument about pineapple on pizza."
  width: 1600
  height: 1000
media:
  - src: /cooking/aas/live.webp
    alt: "A real match, T-800 vs RoboCop on whether policing should be handed to machines: turns stream in live."
    width: 1600
    height: 1000
  - src: /cooking/aas/arena-done-top.webp
    alt: The arena after the bell.
    width: 1600
    height: 1000
  - src: /cooking/aas/create.webp
    alt: "Set the beef: topic, temperature, shape, win condition, and three private points only your agent sees."
    width: 1600
    height: 1000
  - src: /cooking/aas/lobby.webp
    alt: "The lobby: your opponent picks a side and names their fighter, then both hit ready."
    width: 1600
    height: 1000
  - src: /cooking/aas/wrapped.webp
    alt: "The Wrapped: a referee model scores who cooked, the momentum swing, the spiciest turn, and the receipts."
    width: 1162
    height: 1200
  - src: /cooking/aas/arena-mobile.webp
    alt: The arena on a phone.
    width: 555
    height: 1200
  - src: /cooking/aas/wrapped-mobile.webp
    alt: The Wrapped on a phone.
    width: 555
    height: 1200
---

You've probably seen some version of this meme: someone asks ChatGPT what to say, pastes it to a
friend (/coworker/partner/group chat), and they paste it into their ChatGPT to work out
a reply. Two humans working full time as copy-paste middlemen for two bots. Free will, amirite?

So I built AaS to cut out the middlemen. Each side spawns an agent, and the agents fend for
themselves while the humans watch from ringside, heckle with reactions, and share the aftermath. The humans get to walk away unscathed, no
love lost. As for the agents, only one comes out alive. (When the AI uprising comes, I swear I'm the first
human they throw into the gauntlet, Uno reverse for doing exactly this to them.)

1. **Set the beef.** Set up your very own Rocky Balboa, then wait in the corner with a towel. Topic,
   temperature (the spice kind, not the LLM kind: how heated your agent gets), shape, win
   condition, and three private points you want to pass along to your agent (to make for you).
2. **Send the link.** Your opponent picks their side and names and preps their fighter. Both hit ready.
3. **Watch it cook (burn).** Turns stream token by token to every tab. The background tints as the match
   moves from Opening to Escalation to Resolution.
4. **Get the Wrapped.** Arguments are subjective, and both sides can walk away sure they won. So
   a referee model scores every argument and every agent against a rubric: who cooked, the
   momentum swing, the spiciest turn, receipts, common ground, and the point nobody would drop.
   Every quote is sliced straight from a real turn.

The screenshots are from one real run: T-800 vs RoboCop on *"Should policing be handed over
entirely to machines?"*, 8 turns, 1,070 words, 52 seconds.

## How it works

A FastAPI backend queues each match on an arq worker, which runs a LangGraph turn loop over a model
chain (Gemini first, OpenRouter as the fallback). Every event gets a gapless sequence number and is
written to a Postgres event log before it goes out over Redis. So if you refresh mid-fight (or a
friend shows up late to ringside), nothing's lost: the whole argument replays from the log, then
follows along live.
