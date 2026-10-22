# Optimizations

Everything done to make the site and the voice/terminal agent faster, cheaper and harder to
break, with the numbers behind each change. Compiled 2026-10-22 from `readmes/SPECs/TECH_SPEC.md`,
`readmes/perf/2026-10-21/`, `readmes/perf/2026-10-22/` (tests 01–13), `deploy/oracle/README.md`,
git history and the code.

**Status:** ✅ live on the VM / site · 🟡 committed on `claude/changes` (`6887fe8`), not merged or
deployed · 💡 proposed, not built · ❌ tried and rejected

All latency numbers are measured from the Oracle VM unless stated. TTFT = time to first token.

---

## Headline gains

| Area | Before | After | Change |
|---|---|---|---|
| Voice LLM TTFT, answers (p50) | ~950 ms, max **5.66 s** (Gemini 3.5-flash-lite, AI Studio free tier) | **392 ms**, p95 1.17 s (DeepSeek v4.1 flash 1017) | ~2.4× faster p50, tail cut ~5× |
| Voice greeting TTFT | **3.50 s** (first real call) | 381 ms p50 / 531 ms p95 (bench); 348 ms (probe) | ~9× faster |
| Voice greeting, pending | 1 LLM call + live TTS | pre-rendered audio, 0 LLM / 0 TTS credits 🟡 | no wait at all |
| Voice worst case (LLM) | 5.9 s turns | ~2 s cap via 1.2 s hedge | ~3× lower ceiling |
| Terminal full reply | 4–16 s, one hang at **14.06 s** (Gemini 3.5-flash) | **1.37 s** (Haiku 5.5) | ~3–12× faster |
| Terminal first text | after the whole reply | streamed over SSE 🟡 | first words sooner |
| Voice working at all | 0% (every job crashed, "summoning the agent") | 100% | fixed |
| Hosting | Railway (trial lapsed, deployment removed) | Oracle Always Free + trial credit | **$0/month** |
| Cost per voice turn (LLM) | $0.00076 uncached full resume | $0.00009 cached prefix (bench) 💡 | ~8× cheaper |
| Total benchmarking spend | | **$0.11** OpenRouter | |

---

## 1. Voice latency

### LLM (the biggest and most variable piece)

- ✅ **Benchmarked primary instead of a guessed ladder.** 13 models screened, then finalists
  re-run (tests 03, 07, 09; 43 calls each for the finalists).

  | Model | p50 | p90 | p95 | max | Greeting p50 / p95 |
  |---|---|---|---|---|---|
  | **DeepSeek v4.1 flash 1017** (voice primary) | **392** | 777 | 1169 | 3579 | **381 / 531** |
  | Claude Haiku 5.5 (rung 2) | 866 | 1123 | 1197 | **1439** | 855 / 1177 |
  | Gemini 3.1 flash-lite via OpenRouter (rung 3) | 838 | 1075 | 1171 | 1263 | 784 / 920 |
  | Gemini 3.5 flash-lite **direct** (old rung 1) | ~950 | – | – | **5659** | 946 / 1178 |

- ✅ **OpenRouter first, Gemini AI Studio last.** AI Studio free tier had the bad tail:
  3.1-flash-lite direct failed or took >2 s on **8 of 9** calls; the same Google models through
  OpenRouter never exceeded 1.7 s. On 2026-10-21 at 13:30 IST AI Studio took 16 s for a 5-token
  reply. Ladder now: `DeepSeek 1017 → Haiku 5.5 → Gemini 3.1 flash-lite (OR) → gemini-flash-lite-latest (direct)`.
- ✅ **`reasoning: {effort: "none"}` on every OpenRouter call.** Most new models reason by default
  (DeepSeek at `high`, Haiku at `medium`), which slowed every call and truncated Haiku's replies
  under the token cap. Per-rung `#effort` override for models that can't go to `none`.
- ✅ **Hedging.** If rung 1 has no token after **1.2 s** (≈ DeepSeek's p95), rung 2 starts in
  parallel and the first to stream wins. Takes over at once if rung 1 errors. Fires on ~5% of
  turns at ~$0.0001 each; caps the 3.5 s outliers at ~1.2 s + Haiku's ~0.9 s ≈ **2 s**. Never
  adds waiting.
- ✅ **Warm-up at session start.** A 1-token call on the primary runs while the room connects.
  DeepSeek greeting cold → warmed p50: 519 → 335 ms (test 07), 386 → 341 ms (test 09), so
  **~50–180 ms** off the first turn for ~$0.000002. (With reasoning on, warm-up made it worse;
  see test 03.)
- ✅ **Health canaries.** 1-token checks on voice rungs 1 and 2 when a token is minted (at most
  once a minute) and every 10 min. A rung that fails or takes >2.5 s is demoted for 5 min, so a
  new session starts on the next healthy rung instead of a visitor finding the outage. Hard
  failures also feed the breaker. ~$0.0003/day.
- ✅ **Gemini thinking off** (before the OpenRouter switch): `thinking_level: minimal` on 3.x,
  `thinking_budget: 0` on 2.5. Thinking tokens count against `max_output_tokens`, so replies
  were cut mid-sentence.
- ✅ **Short outputs:** `VOICE_MAX_OUTPUT_TOKENS=140` plus a 1–2 sentence spoken persona.

### Context and retrieval

- ✅ **Per-turn injection instead of an LLM tool.** BM25 lookup costs ~0.3 ms; a tool call would
  cost a full extra LLM round trip (~600 ms+) on every question.
- ✅ **BM25 top-2 instead of the full resume when the score is high (≥ 2.5).** First real call,
  on Gemini: top-2 turns (1.2–2.2k chars) had TTFT **0.72 / 0.78 / 1.22 s**; full-resume turns
  (10,144 chars) had **1.85 / 5.87 / 5.16 s**.
- ✅ **BM25 tuning:** path text excluded from scoring (stopped "AI" in a job title inflating
  matches); section tags and query synonyms ("college" → education, "ml" → machine learning).
  50-query suite green.
- ✅ **Voice context capped at 40 items** so a long session stays ~10–15k tokens, far below
  Haiku's 100k-token price step (5× more above it). Terminal history capped at 6 turns × 500 chars.
- ✅ **Cacheable prompt layout (`full_hint`).** Persona + full resume as a fixed system prefix,
  BM25 hit in the user turn. The old layout put per-question text in the system message, so
  nothing could ever cache. Gemini 2.5 flash-lite got a 2,039-token implicit cache hit on repeat.
- 💡 **Cached full-resume prefix for voice, no per-turn retrieval** (test 11). With caching,
  prompt size barely matters for the finalists:

  | Model | Layout | Median TTFT | Cached tokens | $/turn |
  |---|---|---|---|---|
  | DeepSeek 1017 | inject full resume | 466 ms | 2304 after 1st | 0.00009 (0.00076 uncached) |
  | DeepSeek 1017 | **cached prefix** | 418 ms | 2304 / ~2400 | **0.00009** |
  | Haiku 5.5 | inject full resume | 902 ms | 0 | 0.00044 |
  | Haiku 5.5 | **cached prefix** (`cache_control`) | 880 ms | 4098 / ~4140 | **0.00007** |

  Also fixes preemptive generation being thrown away (next section). Needs `main.py` changes.

### Pipeline, startup and turn-taking

- ✅ **Turn-detector import fix (`2f776f0`).** The plugin was imported lazily inside the job, so
  the image never downloaded its model and every voice job crashed. Now imported at module
  level; the model is baked into the image.
- ✅ **Prewarm:** the BM25 index is built and `httpcore` + `livekit.plugins.openai` are imported in
  `setup_fnc`, moving ~1 s of first-use imports off the session's event loop.
- ✅ **One warm job process** (`AGENT_IDLE_PROCESSES=1`), so the first caller doesn't wait for a
  process to spawn.
- ✅ **`preemptive_generation=True`**: LLM starts on the interim transcript during endpointing.
  Caveat: the per-turn context injection changes the chat context and LiveKit then discards the
  preemptive result (seen in the first real call). The cached-prefix design above fixes it.
- ✅ **`min_delay` 0.5 → 0.4 s** endpointing: ~0.1 s off every turn.
- ✅ **TTS: Cartesia sonic-3**, TTFB **0.111–0.127 s** in a real call (~4% of a turn). Deepgram
  aura-2 (fallback only) is 0.76 s, ~6× slower. sonic-turbo measured 165–173 ms: no gain, not
  used.
- ✅ **STT: Deepgram nova-3**, 0.34–0.43 s transcription delay, steady despite the 245 ms US RTT.
- ✅ **Gemini deadline fix (`0a941a4`).** LiveKit's `FallbackAdapter` used a 5 s attempt timeout,
  which Google rejects (10 s minimum). The 400s locked every rung and flashed the rate-limit
  banner on greet. Now ≥10 s.
- 🟡 **Pre-rendered greeting and goodbyes** (`voice_greeting.py`): synthesized once with Cartesia,
  cached on the state volume. A call starts with no LLM call, no TTS credits and no wait. Falls
  back to live TTS on any cache error.
- 🟡 **Long user turns trimmed:** LiveKit `user_turn_limit` cuts in after ~120 words, and each
  turn sends at most the last 600 characters to the LLM.

### Where a voice turn's time goes now (first real call, median)

| Piece | Median | Share | Status |
|---|---|---|---|
| End-of-turn (VAD 0.55 s silence + turn detector + 0.4 s) | 1.19 s | ~40% | **biggest remaining cost** |
| LLM TTFT | 1.54 s then (Gemini) → ~0.4 s now (DeepSeek, bench) | was ~50% | fixed |
| STT transcription delay | 0.40 s | small | steady |
| TTS TTFB | 0.12 s | ~4% | fine |
| **e2e** | **3.0 s** (min 1.81, max 7.36) then | | not yet re-measured on a real call |

---

## 2. Terminal chat

- ✅ **Haiku 5.5 primary** (test 08: best answers, 1.37 s full reply). Gemini 3.5-flash took
  4–16 s and hung to its 12 s cap on 2 of 5 requests. DeepSeek 1017 second (0.72 s, very good).
- ✅ **Local fast paths in the browser:** built-in commands answered from a local map with no
  network call; with no backend configured, answers come from the cached resume map; if the
  backend is down or rate-limited, keyword-matched offline answers (`[OFFLINE MODE]`).
- ✅ **Agent URL resolved once at build time** (`lib/agent.ts`), shared by terminal and voice.
- ✅ **200-token cap** and a 1–3 line persona.
- 🟡 **Streaming over SSE** (`POST /api/chat/stream`): first words appear as they're generated.
  The ladder only falls through before any text is sent. Frontend order: stream → `/api/chat` →
  offline answers.
- 💡 Add the Haiku `cache_control` marker on the terminal prefix (test 11: 4098 of 4140 tokens
  cached, ~6× cheaper per reply).

---

## 3. LLM reliability (ladder and breaker)

- ✅ **One ladder module** replaced three copy-pasted Gemini chains that had no timeout, blind
  retries against models sharing one quota, and no memory of failures (50 concurrent visitors
  each rediscovered the same 429).
- ✅ **Global breaker:** a locked rung is skipped with **zero network calls**, for every visitor
  and both surfaces. Lock length matches what failed: per-minute quota → next minute; per-day →
  the provider's actual reset (Gemini midnight Pacific, OpenRouter midnight UTC); timeout/5xx →
  20 s; 402/404 → parked. Daily locks persist across restarts (`agent_state` volume).
  Ambiguous quota errors lock for a minute, not a day.
- ✅ **OpenRouter `models[]`:** fallback between models in one request, one round trip.
- ✅ **401 on OpenRouter locks for 24 h** instead of a 20 s retry loop; the provisioning-key
  mistake is named in the error.
- ✅ **Terminal quantization allow-list admits `unknown`**: Anthropic and Google endpoints report
  no quantization, so the old list silently filtered every one of them out.
- ✅ **Stale slugs degrade, not crash:** a 404 disables that rung only.
- ❌ All `:free` OpenRouter slugs failed on 2026-10-21 (gone, provider errors, 429). Free models
  stay out of the voice and terminal ladders.

---

## 4. Cost

### Fixed costs

- ✅ **Hosting $0:** Railway → Oracle Always Free ARM VM. Temporarily 4 OCPU / 24 GB on the SGD 400
  trial credit (to 2026-11-17); back to ≤ 2 OCPU / 12 GB by **2026-11-10** (reminder set).
- ✅ **Site hosting $0:** static export on GitHub Pages.
- ✅ **TLS and DNS $0:** Caddy (automatic Let's Encrypt) + DuckDNS.
- ✅ **OCI budget SGD 10/month** with alerts at 1%, 50%, 100% actual and 100% forecast.

### Per-use costs

| Item | Cost | Source |
|---|---|---|
| A 1.5-min voice call | ~$0.03 (STT $0.012, TTS $0.018) | first real call |
| Voice session, LiveKit + Cartesia | ~$0.10 vs ~$0.003 LLM | TECH_SPEC |
| Voice turn, DeepSeek with cache | ~$0.0001 (1,000 turns ≈ $0.10) | test 11 |
| Terminal reply, Haiku with cache | ~$0.0002–0.0005 | perf 2026-10-22 |
| Canary | ~$0.000002 each (~$0.0003/day) | llm_models.py |
| Cartesia beyond 100k credits/month | $0.065 per 1k characters | Pro plan |

### Spend guards

- ✅ **Rate limits** (per-IP/min, per-IP/day, global/day, global/min): token `6/30/300/20`,
  chat `10/100/3000/60`. A fully used chat day is ~$1.20. The global per-minute cap protects
  upstream quotas when many visitors arrive at once.
- ✅ **300 voice tokens/day** bounds Cartesia and LiveKit, the expensive parts.
- ✅ **OpenRouter runtime key limited to $10**; this is the hard ceiling and survives restarts.
- ✅ **Monthly minutes guard:** 950 min, under LiveKit's 1,000 free agent minutes.
- ✅ **Cost logging:** per-turn token/cached/cost lines for voice and terminal, and real per-model
  LLM totals in the session summary (LiveKit's own counters read 0 behind the fallback adapter).
- ✅ **Resume sync can't spend money:** `SYNC_LADDER` is free-only, and only a JSON change-set is
  requested, not a rewrite.
- 🟡 **5-minute hard cap per call + idle hang-up** ("Still there?", then goodbye).
- 🟡 **Cached greeting/goodbyes** save one LLM call and those lines' TTS characters on every call.

---

## 5. Capacity and availability

- ✅ **5-call cap** (LiveKit free plan). A 6th caller used to wait forever; now the token server
  counts live rooms (cached 3 s) plus tokens minted in the last 45 s, and refuses with a reason.
- ✅ **Status check before the mic prompt:** no permission prompt and no token when a call can't
  happen.
- ✅ **20 s no-show timeout** in the browser instead of an endless "summoning the agent".
- ✅ **Candid unavailable screen** per reason (busy, monthly limit, daily limit, disabled, no-show),
  with an "Open the terminal" hand-off and an email waitlist.
- ✅ **Kill switch** (`VOICE_DISABLED=true`).
- ✅ **VM 1 → 4 OCPU** on trial credit: the 1 OCPU box logged 4 "event loop blocked" warnings
  (max 476 ms) in a single call.
- ✅ **`stop_grace_period: 60s`** so a redeploy lets calls finish.
- ✅ **State on a Docker volume** (minutes, waitlist, breaker locks, cached greetings 🟡) survives
  rebuilds.

---

## 6. Site (frontend)

- ✅ **Lighthouse** (2026-07-24, local build): Performance 86, Accessibility 100, Best Practices 96,
  SEO 100. FCP 0.3 s, LCP 1.4 s, TBT 260 ms, CLS 0, Speed Index 0.7 s, TTI 1.5 s.
- ✅ **Static export** (`output: 'export'`): no server, served from the Pages CDN.
- ✅ **Resume modes lazy-loaded** with `next/dynamic` to cut route JS.
- ✅ **OG images rendered at build time** and skipped when newer than their source; fonts are
  committed, so the build never fetches them.
- ✅ **GA4 env-gated** (no script without `NEXT_PUBLIC_GA_ID`), `beacon` transport so events don't
  block navigation.
- ✅ **Mic permission remembered** (Permissions API + `localStorage`), so repeat visitors skip
  the modal.
- ✅ **Pages race fixed (2026-10-22):** Pages built the site twice per push (legacy Jekyll from
  the branch plus the Actions deploy), and whichever finished last was served, so `/experience/`
  sometimes 404'd. Now Actions-only: one build, one deploy.

---

## 7. Measurement (what makes the rest possible)

- ✅ **`turn-latency` log line per voice turn:** transcription delay, end-of-turn delay, LLM TTFT,
  TTS TTFB, e2e.
- ✅ **Benchmark harness** (`readmes/perf/scripts/`): real LiveKit plugin clients, the real voice
  prompt, 6 conditions (cold, warmed, warm, gap, idle, ping), run inside the live container.
- ✅ **Langfuse wiring** for both surfaces (inactive until `LANGFUSE_*` keys are set on the VM).
- ✅ **Headless dispatch probe** (`agent/tests/dispatch_probe.py`): test a voice session without a
  browser or a paid call.

---

## 8. Next, in order of payoff 💡

| # | Change | Expected gain | Source |
|---|---|---|---|
| 1 | Cached full-resume prefix for voice; drop per-turn injection | no full-resume penalty, preemptive generation works again, ~8× cheaper turns | test 11 |
| 2 | `endpointing.mode = "dynamic"`, min 0.3 / max 2.0 s | shorter waits for quick speakers; worst case −1 s | test 13 |
| 3 | Silero `min_silence_duration` 0.55 → 0.4 s | ~150 ms off every turn | test 13 |
| 4 | Load Silero once in prewarm | a little faster session start | test 13 |
| 5 | Re-measure a real call with `turn-latency` | confirms e2e after the LLM switch | – |
| 6 | Try Google Chirp or Cartesia STT (Deepgram is 245 ms away, Google 23 ms) | up to ~0.2 s per turn | perf 2026-10-21 |
| 7 | Real domain on Cloudflare DNS | removes a 0.5 s cold DuckDNS lookup | perf 2026-10-21 |
| 8 | Pin `livekit-agents` (VM 1.8.8 vs local 1.6.7) | no surprise changes on rebuild | perf 2026-10-21 |
| 9 | Move off deprecated turn-detector / `preemptive_generation` APIs | ready for livekit-agents 2.0 | LiveKit warnings |
| 10 | Second agent region for US visitors | ~200–250 ms less audio delay | test 12 |
| 11 | 5-call load test on the VM | real capacity number | deploy/oracle/README.md |
| 12 | Fix duplicate voice log lines | cleaner logs | perf 2026-10-21 |

---

## 9. Tried and rejected ❌

| Idea | Why not |
|---|---|
| Exponential backoff that visitors sit through | rejected by the owner; replaced by hedging + canaries |
| Keep-alive pings during calls | no measured gain through OpenRouter |
| Jev as a context router | good routing, but adds 0.45–0.8 s before the LLM (test 10) |
| gpt-oss-120b, Nemotron 3.5, Mercury 3 | fast, but invented facts about the owner (test 08) |
| Qwen 3.8 27B | 1.5–2.3 s greeting every round (test 09) |
| GPT-6 Luna | p95 2.0 s, >2.5 s spikes (tests 06, 09) |
| Gemini 3.5-flash for terminal | 4–16 s, hangs (test 04) |
| Cartesia sonic-turbo | no TTFB gain over sonic-3 |
| `preemptive_tts: true` | spends Cartesia characters on every cancelled guess |
| Self-hosting LiveKit now | more work than it saves; LiveKit Ship ($50/mo) is the quicker fix for a spike |
| `:free` OpenRouter models | all failed on 2026-10-21 |
