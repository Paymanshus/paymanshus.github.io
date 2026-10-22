---
title: WatchlistXplore
summary: Browse, filter and vibe-search an IMDb watchlist.
date: 2026-06-13
status: building
stack: [React, Vite, shadcn/ui, TMDB, Multi-provider LLM, Vercel]
repo: https://github.com/Paymanshus/WatchlistXplore
live: https://watchlistxplore.vercel.app
---

Export an IMDb watchlist, enrich every title with TMDB posters, keywords and overviews, then
filter it hard: genre unions or intersections, year, runtime, rating, director, cast.

Then describe a mood, like "slow-burn psychological thriller", and an LLM picks up to five
titles from the filtered list, ranked, with its reasoning. It works with Gemini, OpenAI, Anthropic, OpenRouter or a local Ollama model.
