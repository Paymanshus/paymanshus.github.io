---
title: PS-LLMWiki
summary: My take on the LLM wiki. Years of Notion notes go in, a structured, browsable wiki comes out.
date: 2026-04-11
status: early
stack: [React 19, Tailwind v4, FastAPI, LiteLLM, D3]
repo: https://github.com/Paymanshus/pswiki
---

Karpathy's LLM wiki idea: hand a model your pile of raw notes and let it compile a proper,
interlinked wiki out of them. This is my version.

It pulls in everything I've dumped into Notion over the years and tries to make sense of it,
summarizing, cross-referencing, and clustering it into Markdown pages. If Obsidian isn't your
thing, a small web app lets you read it instead, with a knowledge graph and a Q&A layer that
answers from the compiled pages.

## Where it's headed

Curation is what makes a wiki like this worth reading, but nobody wants to hand-curate a
thousand notes. So the plan is semi-auto curation: the model surfaces what's most important and
relevant and lets the rest fade into the background, and a human makes the final call. And
eventually, a public, user-facing version.
