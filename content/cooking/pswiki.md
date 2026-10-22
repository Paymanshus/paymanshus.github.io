---
title: PS-LLMWiki
summary: A personal knowledge base that compiles raw notes into a structured, browsable wiki.
date: 2026-04-11
status: early
stack: [React 19, Tailwind v4, FastAPI, LiteLLM, D3]
repo: https://github.com/Paymanshus/pswiki
---

Messy notes and Obsidian vaults go in. An LLM pipeline summarizes, cross-references and
clusters them into interlinked Markdown pages, browsable in a small React reader with a
force-directed knowledge graph and a Q&A layer that answers from the compiled pages.

Still at the skeleton stage: repo structure and schema conventions are in place, and the
compiler is next.
