# Technical Specification

> Living source of truth for the shipped implementation. Update this file whenever architecture, runtime behavior, deployment, or content-loading behavior changes.

## Current Product Shape

This repo is a static-exported Next.js 15 portfolio intended for `paymanshus.github.io`.

Current public routes:

- `/`: fullscreen landing / hero
- `/experience/`: resume surface with `pdf`, `chat`, and `voice` modes
- `/thoughts/`: blog index
- `/thoughts/[slug]/`: static article pages generated from local Markdown

The home route is a no-scroll hero state. The experience and thoughts routes are normal scroll pages inside the shared site shell.

## Stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Framework | Next.js 15 App Router | Static export build target |
| Language | TypeScript | All first-party code is TS/TSX |
| Styling | Tailwind CSS v4 | Theme tokens live in `app/globals.css` |
| Animation | `motion` | Used for hero, nav, and section transitions |
| WebGL | `ogl` | Drives the landing `RippleGrid` |
| Content parsing | `gray-matter`, `remark`, `remark-gfm`, `remark-html` | Blog frontmatter + Markdown to HTML |
| Icons | `lucide-react` | Navigation and resume mode controls |

## Runtime Architecture

### Shell and routing

- `app/layout.tsx`
  Loads global fonts, metadata, and the outer width-constrained shell.
- `components/SiteShell.tsx`
  Wraps routes with the shared header and main content area.
- `components/SiteHeader.tsx`
  Top navigation with route-aware active state from `usePathname()`.

### Home route

- `app/page.tsx`
  Renders the landing page and structured data for the website/person.
- `components/HeroSection.tsx`
  Renders the two-line hero title, descriptor line, CTAs, and fixed background layers.
- `components/RippleGrid.tsx`
  Uses `ogl` to render a shader grid, then maps pointer movement into shader uniforms while the floor perspective is applied in CSS.

### Experience route

- `app/experience/page.tsx`
  Static route wrapper with SEO metadata and structured data.
- `components/ExperienceSection.tsx`
  Owns the resume mode toggle.
  Current default mode is `chat`.
  Mode panels are lazy-loaded with `next/dynamic` to reduce route JS.
- `components/resume/PdfResume.tsx`
  Loads the PDF iframe after mount to avoid competing with initial route transition.
- `components/resume/ChatResume.tsx`
  Terminal interface with boot sequence, local command map fast-path, and LLM
  backend for free-form questions (`POST {NEXT_PUBLIC_AGENT_URL}/api/chat`).
  Falls back to keyword-matched canned answers when the backend is
  unreachable or rate-limited (`[OFFLINE MODE]` prefix). LLM output is
  HTML-escaped before rendering (history lines use `dangerouslySetInnerHTML`).
- `components/resume/VoiceResume.tsx`
  Live LiveKit WebRTC voice session (see Voice Agent Server below).
  State machine: `idle → permission → connecting → connected → error`.
  Uses `LiveKitRoom` + `useVoiceAssistant` + `useTranscriptions` +
  `RoomAudioRenderer` from `@livekit/components-react`. The particle canvas is
  amplitude-driven via Web Audio `AnalyserNode` on both the agent audio track
  and the local mic track; accent color crossfades red (user speaking) ↔
  green (agent speaking) ↔ amber (thinking).
  UX behaviors:
  - Transcript coalescing: consecutive STT segments from the same speaker are
    merged into one flowing line; new lines only on speaker change, so chunk
    boundaries are invisible.
  - Mic permission is a one-time experience: Permissions API check +
    `localStorage['ps-voice-mic-granted']` fallback skip the modal on
    subsequent visits.
  - Thinking indicator: rotating verb from `THINKING_WORDS` (Claude-Code-style)
    shown while agent state is `thinking`.
  - Degradation: reads agent participant attributes `voice.tts` / `voice.llm`.
    LLM fallback and TTS degraded show a 6px amber square next to the
    listening indicator (`title` = fallback model/voice). TTS down still uses
    the amber top-center banner — output is actually gone.

### Thoughts route

- `app/thoughts/page.tsx`
  Blog index route with collection-page structured data.
- `app/thoughts/[slug]/page.tsx`
  Static article route with `generateStaticParams()`, metadata per post, and `BlogPosting` structured data.
- `components/ThoughtsSection.tsx`
  Lists available posts from the local content directory.
- `components/ThoughtPost.tsx`
  Renders the article header, reading view, and progress bar.
- `components/ReadingProgressBar.tsx`
  Client-side top progress bar using `useScroll()`.

## Content System

Blog content lives in `content/blog/`.

Supported source files:

- `.md`
- `.mdx`

Current behavior in `lib/blog.ts`:

- Reads frontmatter with `gray-matter`
- Filters unpublished content via `published: false`
- Computes reading time locally
- Sorts posts by descending date
- Converts Markdown to HTML with `remark + gfm + html`

Frontmatter currently expected:

- `title`
- `excerpt`
- `date`
- optional `updatedAt`
- optional `tags`
- optional `published`

### Current posts

Live posts are authored content imported from the author's Notion workspace
(originally written December 2024). Both open with an italic editorial note
marking their age, since the surrounding tooling has moved on:

- `on-device-llms-on-android.md` — on-device LLMs, ONNX Runtime, RAG demo app
- `llm-optimization-memory-gpu-cpu.md` — quantization, precision formats, KV cache

The three original scaffold posts (`austere-neon-designing-for-focus`,
`building-audio-reactive-particle-systems`, `the-cli-as-a-first-class-interface`)
were placeholder copy. They are retained on disk as formatting references but
carry `published: false`, so they are excluded from the index, from
`getAllBlogSlugs()`, and return 404 on direct access.

Blog content is covered by `tests/blog/blog-content.test.mjs`.

## Typography Implementation

Loaded in `app/layout.tsx`:

- `Space_Grotesk`
- `Instrument_Serif`
- `Lora`
- `JetBrains_Mono`

Current font roles:

- `Space Grotesk`: display/UI sans
- `Instrument Serif`: editorial accent serif, mostly for excerpts and selected supporting text
- `Lora`: long-form reading serif for article body copy
- `JetBrains Mono`: navigation, metadata, terminal, and system labels

## Theme Tokens

Theme tokens live in `app/globals.css`.

Current named tokens:

- `--color-bg`
- `--color-surface`
- `--color-border`
- `--color-text-primary`
- `--color-text-secondary`
- `--color-brand-red`
- `--color-glow`
- `--color-tron-glow`
- `--font-sans`
- `--font-serif`
- `--font-reading`
- `--font-mono`

## SEO and Discoverability

SEO is already wired for a static site. The full roadmap and per-agent task
assignments live in `readmes/SEOPLAN.md` (source of truth for what's shipped vs
pending in this area).

Current pieces:

- `lib/site.ts`
  Central canonical URL, metadata helpers, display-date helpers, identity fields,
  and the JSON-LD **entity graph**: `PERSON_ID`/`WEBSITE_ID` stable `@id`s plus
  `personJsonLd()` / `websiteJsonLd()` / `personRef()` builders. Every page
  references the same Person `@id` (full node on home; stub nodes elsewhere) so
  crawlers reconcile one entity. Identity facts (ML Engineer at Maersk, Bangalore,
  LinkedIn `/in/paymanshus`) mirror `content/resumedump.md`. Document title is
  `Paymanshu Sharma | AI Product Engineer`. GSC HTML-tag token lives here as
  `GOOGLE_SITE_VERIFICATION` (env override, committed fallback). The HTML-file
  method is `public/google51d43957481c87ef.html` at the site root.
- Route metadata in `app/layout.tsx`, `app/experience/page.tsx`, `app/thoughts/page.tsx`, and `app/thoughts/[slug]/page.tsx`
- JSON-LD via `components/StructuredData.tsx` (home: WebSite + Person + ProfilePage;
  articles: BlogPosting with `@id` author/publisher)
- `scripts/generate-seo-files.mjs` writes `public/robots.txt` + `public/sitemap.xml`
  during `npm run build` (there are no `app/robots.ts` / `app/sitemap.ts` routes)

Important current behavior:

- Canonicals are generated from `NEXT_PUBLIC_SITE_URL`
- Blog post routes emit article metadata and structured data
- Static sitemap includes home, experience, thoughts, and each blog post
- `npm run test:seo` (after a build) runs `tests/seo/check-static-output.mjs`,
  a regression check over `out/`: canonicals, single-h1, Person `@id` graph,
  BlogPosting authorship + BreadcrumbList, per-post `og:image`, footer `rel="me"`
  identity links, feeds, llms.txt, 404 noindex, robots/sitemap agreement. Run it
  after any SEO change.
- `npm run test:unit` runs `node --test tests/seo/*.test.mjs` (section-timer logic).

### Open Graph images

There is no server, so cards cannot be rendered on request. `scripts/generate-og-images.mjs`
(run from `npm run generate:seo`, i.e. every build) renders 1200×630 PNGs with
satori + resvg into `public/og/`: `default.png` for the site and one card per
published post at `public/og/thoughts/<slug>.png`. Outputs are skipped when newer
than their sources (`OG_FORCE=true` overrides).

Fonts are committed at `scripts/assets/fonts/` — never fetched at build time.
They are **static instances** of Space Grotesk; satori's opentype.js fork cannot
parse the variable font's `fvar` table. Regenerate with:
`fonttools varLib.instancer "SpaceGrotesk[wght].ttf" wght=400 -o SpaceGrotesk-Regular.ttf`

`lib/site.ts` exposes `absoluteAssetUrl()` for file URLs — `absoluteUrl()` appends
a trailing slash (correct for routes, corrupting for `.png`/`.xml` paths).

### Feeds

`scripts/generate-seo-files.mjs` also writes `public/feed.xml` (RSS 2.0, with an
`atom:self` link) and `public/feed.json` (JSON Feed 1.1), newest-first, both
advertised from `alternates.types` in the root layout. `public/llms.txt` is a
hand-maintained plain-markdown site summary for LLM consumers.

## Analytics

GA4 via `gtag.js`, entirely client-side and **env-gated on `NEXT_PUBLIC_GA_ID`** —
with the variable unset, no script loads and every call is a no-op, so dev builds
stay clean. `NEXT_PUBLIC_GA_DEBUG=true` stamps `debug_mode` for GA4 DebugView.

- `lib/analytics.ts` — `trackEvent`, `trackPageView`, and `createSectionTimer()`:
  a pure, clock-injectable dwell-time accumulator (start/stop/pauseAll/resumeAll/
  flush) with no browser or GA dependency, unit-tested in
  `tests/seo/section-timer.test.mjs`. A shared `sectionTimer` singleton is
  exported for the components to share.
- `components/analytics/Analytics.tsx` — mounted once in the root layout body.
  Loads gtag with `send_page_view: false` + `transport_type: 'beacon'`, sends
  `page_view` on every `usePathname()` change (App Router SPA nav never fires
  a real page load), pauses/resumes the timer on `visibilitychange`, and flushes
  on `pagehide` and route change.
- `components/analytics/PageEngagement.tsx` — drop-in for server-rendered pages;
  accumulates dwell for a named section and optionally emits `scroll_depth`
  milestones (25/50/75/100). Used for `home_hero`, `thoughts_index`, and
  `article:<slug>` (with scroll depth).
- `hooks/useSectionView.ts` — IntersectionObserver (≥50%) variant for sections
  that occupy part of a page; used for `experience`.

Events: `page_view`, `section_view`, `section_time {section, seconds, page_path}`,
`scroll_depth {percent, page_path}`, `resume_mode_change {mode}`,
`terminal_command {command}`, `terminal_chat {llm}`, `voice_session_start`,
`voice_session_end {duration_seconds}`, `voice_error {stage}`.

Privacy: terminal message text is never sent — only built-in command names and a
boolean for whether the LLM answered. Time in each resume mode is tracked as
separate timer sections (`resume:pdf` / `resume:chat` / `resume:voice`), which is
how "time in voice vs terminal" is answered. Owner setup: `docs/SEO_SETUP.md`.

## Static Export and GitHub Pages

### Current setup

This repo is already configured for GitHub Pages deployment.

Relevant files:

- `next.config.ts`
  Uses `output: 'export'`
  Uses `trailingSlash: true`
  Uses `images.unoptimized = true`
- `public/.nojekyll`
  Prevents GitHub Pages from treating `_next/` as Jekyll content
- `.github/workflows/deploy.yml`
  Builds and deploys the exported `out/` directory through GitHub Actions

Workflow behavior:

- Triggers on push to `main`
- Also supports manual dispatch
- Sets `NEXT_PUBLIC_SITE_URL=https://paymanshus.github.io`
- Runs `npm ci`
- Runs `npm run build`
- Uploads `./out`
- Deploys via `actions/deploy-pages`

GitHub Pages should be configured to use:

- Source: GitHub Actions

### Repo replacement plan

For migration into the existing `paymanshus.github.io` repository:

1. Clone the existing GitHub Pages repo separately.
2. Keep its git history intact for rollback.
3. Replace the old site source with this Next.js app source.
4. Preserve `.github/workflows/deploy.yml`, `public/.nojekyll`, `content/blog`, and the PDF asset.
5. Push to `main` so GitHub Actions rebuilds and deploys the static export.

This keeps rollback simple because the old history remains in the same repository.

## Voice Agent Server

A standalone Python service in `agent/` that handles the real-time voice pipeline for the `/experience` voice mode. It runs separately from the Next.js app and communicates only through LiveKit's WebRTC infrastructure.

**Hosting: Oracle Cloud Always Free ARM VM (1 OCPU / 6 GB, `ap-hyderabad-1`) behind Caddy at `https://ps-agent.duckdns.org`; runbook in `deploy/oracle/README.md`. The static site is pointed at that URL via `NEXT_PUBLIC_AGENT_URL` in `.github/workflows/deploy.yml`. The turn detector runs there (it is only skipped by default when `RAILWAY_ENVIRONMENT` is set). Railway (`railway.toml`) is retired; its trial lapsed on 2026-10-13.**

Note for any hosting work: the agent worker registers with LiveKit Cloud over an **outbound** WebSocket and needs no public inbound ports. Only the `token_server.py` HTTP endpoints (:8080) require a public URL.

### Stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Runtime | Python 3.11 + asyncio | Isolated venv at `agent/.venv/` |
| Agent framework | `livekit-agents` 1.5.1 | Worker + session lifecycle |
| STT | Deepgram Nova-3 | Primary; Google Chirp as fallback via `USE_GOOGLE_STT=true` |
| LLM | Multi-provider ladder (`llm_ladder.py`) — OpenRouter first, Gemini direct last, shared quota breaker | Voice: `deepseek-v4.1-flash-1017 → claude-haiku-5.5 → gemini-3.1-flash-lite (OpenRouter) → gemini-flash-lite-latest (AI Studio)`, rungs 1+2 hedged after 1.2 s. Terminal: Haiku 5.5 first. Reasoning off on OpenRouter calls. Canary health checks (`llm_health.py`). Measurements: `readmes/perf/2026-10-22/` (local) |
| TTS | Cartesia `sonic-3` → Deepgram Aura via `tts.FallbackAdapter` | Bare `sonic` was sunsetted by Cartesia (400). Model via `CARTESIA_MODEL`, voice via `CARTESIA_VOICE_ID`. Verified with `tests/probe_cartesia.sh` |
| VAD | Silero (local) | `livekit-plugins-silero`; no API call, no cost |
| Turn detection | LiveKit Multilingual Model (local default) | Skipped on Railway unless `VOICE_TURN_DETECTOR=true` — the EOU inference child is ~500MB and OOM-kills Trial/Free. Silero VAD endpointing is the fallback. |

### Directory structure

```
agent/
├── main.py                # Agent entrypoint — worker registration + session wiring
│                          # + token server started in a daemon thread
├── token_server.py        # HTTP server on :8080 — /api/token, /api/chat(/stream), /api/health
├── prompts.py             # Persona (shared core + terminal/voice registers), fixed voice lines
├── voice_greeting.py      # Render-once, cache-on-disk audio for fixed voice lines
├── llm_voice.py           # Voice LLM: breaker guard, hedging, warm-up, prompt-size caps
├── llm_health.py          # Canary health checks shared with voice sessions
├── resume_context.py      # ContentIndex (BM25) + get_resume_index() singleton
├── requirements.txt       # Python dependencies (+ pytest-asyncio for tests)
├── .env.example           # Credential template (committed)
├── .env.local             # Real credentials (gitignored)
├── .venv/                 # Python virtualenv (gitignored)
├── tests/
│   ├── test_connections.py      # API key + component smoke tests (script-style)
│   ├── test_resume_context.py   # ContentIndex unit tests (55 tests incl. scored search)
│   ├── test_token_server.py     # Token minting/CORS/rate-limit tests
│   ├── test_llm_ladder.py       # Ladder walk, quota breaker, prompt layout
│   ├── probe_cartesia.sh        # Cartesia TTS model availability probe
│   ├── probe_llm.py             # Per-rung availability + TTFT + streaming probe
│   ├── eval_context_modes.py    # Prompt-layout / caching comparison harness
│   ├── dispatch_probe.py        # Headless agent dispatch (test sessions without a browser)
│   └── bisect_run.sh            # Restart agent + headless session smoke test
└── eval/                  # (Feature 03) Retrieval evaluation harness — stub for now
```

### Token & chat HTTP server (`token_server.py`)

Runs in a daemon thread inside the same process as the agent (port via
`TOKEN_SERVER_PORT`, default 8080).

- `GET|POST /api/token` — mints a LiveKit JWT: unique room
  (`voice-resume-<hex>`), unique visitor identity, 10-minute TTL, audio-only
  grants. **Critically**, the token embeds
  `RoomConfiguration(agents=[RoomAgentDispatch(agent_name="paymanshu-voice")])` —
  named agents are never auto-dispatched, so without this the agent never
  joins the room. Response carries both `serverUrl`/`participantToken` and
  `url`/`token` key styles.
- `POST /api/chat` — terminal LLM endpoint. Body `{message, history?}`.
  Builds the prompt via `llm_context` (layout set by `LLM_CONTEXT_MODE`), then
  walks `LLM_LADDER` through `llm_ladder.generate()`. Max 200 output tokens,
  1-3 line persona. Returns `{reply}`; `503 {"error": "llm_unavailable"}`
  tells the frontend to use its keyword fallback. Request/response shapes are
  unchanged from the original Gemini-only implementation, so the frontend needed
  no change.
- `POST /api/chat/stream` — same request and validation, answered as
  Server-Sent Events: `data: {"delta": "..."}` per piece, then `{"done": true}`
  or `{"error": "llm_unavailable"}`. SSE over fetch, not a websocket: one-way
  tokens, no connection management, and Caddy passes `text/event-stream`
  through. The ladder only falls through to the next model before any text has
  been sent. `ChatResume.tsx` (`lib/chatStream.ts`) streams first and falls back
  to `/api/chat`, then to the offline keyword answers.
- CORS restricted to `paymanshus.github.io` + localhost dev origins.
- In-memory rate limits (per-IP/minute, per-IP/day, global/day, **global/minute**):
  token `6/30/300/20`, chat `10/100/3000/60`. 429 responses carry a
  human-readable message that the terminal renders.
  - The **global per-minute** cap is what protects upstream RPM quotas during a
    concurrency spike — per-IP limits do nothing when 40 distinct visitors
    arrive at once.
  - Chat daily caps are deliberately generous: a fully-paid day at these limits
    is ~$1.20 at DeepSeek-V4-Flash pricing, and the real hard ceiling is the
    OpenRouter provisioning key's monthly `limit`, which survives a restart.
    The token cap stays at 300/day because it bounds Cartesia and LiveKit, which
    are the genuinely expensive parts (~$0.10/session vs ~$0.003 of LLM).

### LLM ladder (`llm_ladder.py`, `llm_models.py`, `llm_context.py`)

Replaced three duplicated Gemini model chains (token_server, main, sync_resume)
that shared three defects: no per-request timeout, blind `except Exception`
retry against models sharing one quota, and no memory of failure — so 50
concurrent visitors each rediscovered the same 429.

- **Ladder** — one ordered list of `provider:model[|model2][@quota_group]`
  entries per surface, in `llm_models.py`. Providers can interleave freely; a
  locked rung simply drops out and the next becomes the starter, with no
  special-casing. `|model2` becomes OpenRouter's `models[]` array, so free→paid
  escalation happens server-side in a single round trip.
- **Breaker** — module-level, therefore global across all users, all sessions,
  and both surfaces (`llm_voice.BreakerGuard` consults the same state). Locked
  rungs are skipped with **zero network calls**. Lock duration is scoped to what
  failed: per-minute quota → next minute boundary; per-day → the upstream reset
  (Gemini midnight *Pacific*, OpenRouter midnight *UTC* — different instants);
  timeout/5xx → 20s; 402/404 → parked and logged at ERROR. Per-day locks persist
  to `LLM_BREAKER_STATE_PATH` because the deployment runs `Restart=always`.
  RPM-vs-RPD has no clean documented field, so it is an explicit heuristic and
  **ambiguous cases degrade to per-minute** — wrongly locking a rung for a day is
  far worse than retrying in 60s.
- **Prompt layout** — `LLM_CONTEXT_MODE` selects one of four layouts. Caching
  matches a *prefix*, and the original implementation interpolated per-question
  BM25 output into the system message, so the prefix changed every request and
  nothing could ever cache. Default `full_hint` puts persona + full resume in a
  stable system prefix and the BM25 result in the user turn, keeping BM25
  exercised while making the prefix cacheable. Compare layouts with
  `tests/eval_context_modes.py`.
- **Gemini thinking** — thinking tokens are charged against `max_output_tokens`,
  so a tight cap with thinking on truncates spoken/written replies mid-sentence.
  Gemini 3 models (`gemini-3.*`) get `thinking_level: "minimal"`; 2.5 and
  earlier get `thinking_budget: 0`. Rolling `-latest` aliases reject the field
  with 400, so it is withheld from them (and the ladder retries without it on a
  400).
- **Gemini HTTP deadline** — Google rejects deadlines under 10s
  (`Manually set deadline 5s is too short`). LiveKit's `FallbackAdapter`
  defaults `attempt_timeout=5.0`, which used to leak through as the request
  deadline. Voice now passes `http_options.timeout ≥ 10000` on `google.LLM` and
  constructs the adapter with `attempt_timeout` matching
  `LLM_TIMEOUT_MS_VOICE` (default 10000, floored at 10s).

### Runtime architecture

```
Browser ←—WebRTC—→ LiveKit Cloud SFU ←—WebRTC—→ agent/main.py
                                                  ├── Silero VAD (local)
                                                  ├── Deepgram STT (API)
                                                  ├── Gemini LLM (API)
                                                  └── Cartesia TTS (API)
```

`main.py` key components:
- `PaymanshuAgent` — `Agent` subclass. Resume context is injected **per turn**
  via `on_user_turn_completed` (NOT an LLM tool — a tool call costs a full
  extra LLM round-trip ~600ms+ per question; injection is ~0.3ms of BM25 and
  zero extra inference). Routing: BM25 top-2 when `search_scored()` top score
  ≥ `RESUME_SCORE_THRESHOLD` (2.5), otherwise the full resume (~2.5K tokens)
  is injected. Context is added to the turn only, so history doesn't
  accumulate resume copies.
- `voice_agent()` — `@server.rtc_session` handler; constructs models and `AgentSession` per visitor connection
- **Latency design**: `preemptive_generation=True` (LLM+TTS start on interim
  transcript during endpointing), `min_delay=0.4s` (env `MIN_ENDPOINTING_DELAY`)
  set via `turn_handling=TurnHandlingOptions(turn_detection=..., endpointing={"min_delay": ...})`
  (migrated 2026-07-10 off the deprecated top-level `min_endpointing_delay`
  kwarg, removed in livekit-agents 2.0), `VOICE_MAX_OUTPUT_TOKENS=140` cap +
  1-2 sentence persona for short spoken replies.
- **Degradation signaling**: `FallbackAdapter` `*_availability_changed` events
  publish participant attributes (`voice.tts`: ok/degraded/down, `voice.llm`:
  ok/fallback). `VoiceResume.tsx` shows a 6px amber square next to the
  listening indicator for LLM fallback / TTS degraded; TTS `down` still gets
  the amber banner. OpenRouter 401s lock as `KIND_CREDITS` (24h) rather than a
  20s `server_error` retry loop. Gemini deadline-too-short 400s are not locked.
- **Persona**: `prompts.py` holds one shared core voice plus a texting register
  (terminal) and a spoken register (voice), with short in-voice examples.
- **Fixed lines from cached audio** (`voice_greeting.py`): the greeting (random
  from `prompts.VOICE_GREETINGS`) and the goodbye/idle lines are synthesized once
  with Cartesia, cached as WAV under `VOICE_AUDIO_CACHE_DIR` (the state volume on
  the VM), and played with `session.say(audio=...)`: no LLM call and no TTS
  credits after the first render. Falls back to live TTS on any cache error.
- **Session limits**: hard cap `VOICE_MAX_SESSION_S` (300 s) and an idle
  hang-up (user "away" after `VOICE_USER_AWAY_S`, then "Still there?", then
  goodbye after `VOICE_IDLE_GRACE_S`). Before closing the room the agent sets
  participant attribute `voice.end_reason` (`time_limit` / `idle`), which
  `VoiceResume.tsx` shows. Long user turns: LiveKit `user_turn_limit`
  (`VOICE_MAX_TURN_WORDS`, ~45 s of speech) cuts in politely, and each turn sends
  at most the last `VOICE_MAX_USER_CHARS` (600) characters to the LLM; the voice
  context is capped at `VOICE_MAX_CONTEXT_ITEMS` (40).
- **Prewarm** (`server.setup_fnc`): builds the resume BM25 index and imports
  `httpcore` + `livekit.plugins.openai` so those ~1s first-use imports do not
  block the session event loop. Silero still loads in the session.

`resume_context.py` key components:
- `ContentIndex` — generic BM25 index; accepts optional `section_tags` and `query_synonyms` params (doc-agnostic; resume config passed in, not hardcoded); each `Section` records `source_file` for future multi-source routing
- Scoring tokens: `content + heading` only — `path_str` excluded to prevent heading-token inflation (e.g. `"AI"` from `"Awarathon — AI Intern"` path no longer distorts ranking)
- `RESUME_SECTION_TAGS` — injected at index time; anchors conversational vocab to sections (`"college"` → Education, `"current"/"recent"` → Maersk)
- `RESUME_QUERY_SYNONYMS` — expanded at query time; bridges abbreviation gaps (`"college"` → `["education", "university"]`, `"ml"` → `["machine", "learning"]`)
- `get_resume_index()` — singleton over `content/resumedump.md` with resume-specific config. Path candidates (first existing wins): `RESUME_CONTENT_PATH`, `<agent-dir>/content/resumedump.md` (Docker `/app/content/...`), `<repo>/content/resumedump.md` (local). The Docker image copies agent files into `/app`, so `__file__.parent.parent` is `/` and must not be the only lookup.
- Future expansion: `ContentIndex("content/blog/", label="blog")` with its own optional config; no class changes needed

**BM25 empirical findings** (50-test suite with realistic voice queries):
- Works well for keyword-rich queries, technical terms, proper nouns, skill names
- Previously known limitations now fixed: `"AI"` collision (path_str removal), `"college"` synonym gap (section tags + query synonyms), `"current role"` vague queries (Maersk section tags)
- Remaining limitation: pure stop-word queries (e.g. "what have you been doing") fall back to full resume text — correct behavior, BM25 IDF already handles de-weighting
- See `docs/voice-feature/02-resume-context-system.md` for full analysis

### Required environment variables

Set in `agent/.env.local` (copy from `agent/.env.example`):

| Variable | Source |
| --- | --- |
| `LIVEKIT_URL` | LiveKit Cloud → Settings → Keys |
| `LIVEKIT_API_KEY` | LiveKit Cloud → Settings → Keys |
| `LIVEKIT_API_SECRET` | LiveKit Cloud → Settings → Keys |
| `GOOGLE_API_KEY` | aistudio.google.com → Get API key |
| `DEEPGRAM_API_KEY` | console.deepgram.com → API Keys |
| `CARTESIA_API_KEY` | play.cartesia.ai → API Keys |
| `CARTESIA_VOICE_ID` | play.cartesia.ai → voice UUID (default: `79a125e8-cd45-4c13-8a67-188112f4dd22`) |

### Running locally

```bash
cd agent
source .venv/bin/activate

# One-time: download turn-detector ONNX model (~30MB)
python main.py download-files

# Smoke test all API keys + components
python tests/test_connections.py

# Start agent (connects to LiveKit Cloud and waits for room joins)
python main.py dev
```

Test via LiveKit Cloud → your project → **Sandbox → Web Voice Agent → Launch**.

### Content

`content/resumedump.md` — flat Markdown dump of Paymanshu's resume. Used by the `lookup_resume` tool (Feature 02). Previously lived at `readmes/resumedump.md`.

**Source-of-truth sync (`scripts/sync_resume.py`)** — the owner maintains ONE
resume: the PDF in `public/assets/`. This script keeps `content/resumedump.md`
in sync so there is no second hand-maintained copy. Pipeline:
1. sha256 the PDF; cache in `content/.resume_pdf_hash`. No change → exit 0
   quietly (safe as a dev-server-start / predeploy hook).
2. Extract text with PyMuPDF (`fitz`, added to `agent/.venv`).
3. Ask for a JSON **change-set** (not a rewrite) via `SYNC_LADDER`, which is
   free-only so the script cannot spend money; Python applies the changes against
   exact heading anchors, so the owner's formatting is owned by code and cannot
   drift. Unmatched anchors are rejected, never guessed. `--rewrite` keeps the
   old full-document regeneration for a genuine restructure.
   prompted to preserve every fact verbatim and re-emit into the exact heading
   skeleton of the current `resumedump.md` (passed as a formatting example).
4. Writes `resumedump.md.new` + prints a unified diff. **Default run is a dry
   run**; only `--apply` overwrites, and only then is the hash cache updated.
   Never auto-apply in CI.
5. After `--apply`, runs `tests/test_resume_context.py` — if the section
   structure drifted, those tests fail and signal the prompt needs tightening.
Run inside the venv: `agent/.venv/bin/python scripts/sync_resume.py [--apply|--force|--pdf PATH]`.
Helper-level tests: `scripts/test_sync_resume.py`. Note: PDF extraction carries
no bold markup, so applied output must be reviewed via the diff before commit.

### Observability (Langfuse)

`agent/observability.py` — env-gated on `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`
(plus `LANGFUSE_BASE_URL`, default cloud.langfuse.com). Without keys, or with
`langfuse` missing, every entry point is an inert no-op; tracing must never
break serving. Uses the Langfuse **v4** Python SDK (`langfuse>=4,<5`).

Decision record (2026-07-10): LiveKit Agents natively instruments everything
(OTel spans with full chat context/prompts, tool calls, per-turn latencies;
usage counters for tokens/TTS chars/STT seconds), but its first-party dashboard
targets LiveKit Cloud deployments, and the terminal `/api/chat` path never
touches LiveKit at all. Langfuse is the officially supported OTel export target
(https://langfuse.com/integrations/frameworks/livekit) and covers both surfaces
in one project, so it was chosen over LiveKit-Cloud-only insights.

Wiring:

- **Voice sessions** (`main.py` entrypoint): `setup_voice_tracing(room)` creates
  a shared `TracerProvider`, hands it to LiveKit via
  `livekit.agents.telemetry.set_tracer_provider(provider, metadata={"langfuse.session.id": room})`
  and to `Langfuse(tracer_provider=..., should_export_span=lambda s: True)`.
  Each LiveKit job runs in its own subprocess, so the global provider is
  per-session. Shutdown callback force-flushes spans.
- **Usage/cost summary** (`attach_usage_reporter`): listens to the
  `session_usage_updated` event (migrated 2026-07-10 off the deprecated
  `metrics_collected`), which fires the session's full cumulative
  `AgentSessionUsage.model_usage` (per provider/model) on every metrics
  update — the handler keeps the latest snapshot and sums it by type at
  shutdown; a `voice_session_usage` span
  records token/char/second totals plus USD estimates from
  `estimate_session_costs()` (env-overridable `COST_*` rates — Langfuse can't
  ingest OTel metrics, so this bridges usage into the trace).
- **Terminal chat** (`token_server.py`): each `/api/chat` request becomes a
  `terminal-chat` trace (user = sha256-hashed IP, session = visitor+day,
  tag `terminal`); every rung attempted in the ladder is a
  Langfuse generation with prompt/output/token usage, cached-token counts, and —
  for OpenRouter — the provider's real per-request cost in preference to the
  local estimate (Langfuse computes LLM
  cost), failed attempts logged at ERROR level so fallbacks are visible.
  aiohttp `on_cleanup` flushes the client.

Tests: `agent/tests/test_observability.py` (env gating, cost math, fallback
chain behavior with a fake genai client, pseudonymous visitor ids).

---

## Remaining Backend Plan

The voice agent server (`agent/`) is the first backend service and is now scaffolded locally. Remaining work:

- **Feature 02**: ✅ `agent/resume_context.py` — `ContentIndex` with section-aware BM25; `RESUME_SECTION_TAGS` + `RESUME_QUERY_SYNONYMS` fix known routing gaps; exposed as `@function_tool() lookup_resume`; 50-test suite green
- **Feature 03**: `agent/eval/` — evaluation harness comparing BM25 vs vector vs hybrid retrieval (still pending)
- **Feature 04**: ✅ `agent/token_server.py` — token + chat HTTP server on `:8080`, embedded in the agent process; includes agent dispatch in tokens, CORS, and rate limiting; 10 tests green
- **Feature 05**: ✅ Frontend wiring — `VoiceResume.tsx` uses real LiveKit WebRTC (`@livekit/components-react` 2.9.x: `LiveKitRoom` + `useVoiceAssistant` + `useTranscriptions`); verified end-to-end in browser (agent greets, live transcript streams, states transition)
- **Feature 06**: ✅ Amplitude-reactive particle visualizer — Web Audio `AnalyserNode` on agent + local mic tracks; red accent while user speaks, green while agent speaks, amber while thinking; smooth accent crossfade
- **Terminal LLM**: ✅ `POST /api/chat` + `ChatResume.tsx` wiring with rate limiting and offline keyword fallback
- **LLM ladder**: ✅ `agent/llm_ladder.py` + `llm_models.py` + `llm_context.py` +
  `llm_voice.py` — Gemini + OpenRouter with a shared quota-scoped breaker,
  per-request timeouts, cacheable prompt prefixes, and a global per-minute rate
  limit; 51 ladder tests + 29 sync_resume tests green. **Pending**: OpenRouter
  rungs are inert until `OPENROUTER_API_KEY` holds a valid *runtime* key. A
  provisioning key does not work there — it manages runtime keys and 401s on
  inference (`"User not found."`), which the classifier now names explicitly;
  mint a runtime key with a monthly `limit` per `agent/RUN.md`, and note the $10
  lifetime deposit is what raises `:free` from 50 to 1,000 RPD. Also
  `tests/eval_context_modes.py` still needs a full run to pick the
  `LLM_CONTEXT_MODE` default from data rather than reasoning.
- **Feature 07**: Deployment — Oracle Always Free ARM VM running `deploy/oracle/compose.yaml` (agent built from `agent/Dockerfile` with repo-root context, plus Caddy for HTTPS). Public URL is `https://ps-agent.duckdns.org`. Pages gets it from `NEXT_PUBLIC_AGENT_URL` in `.github/workflows/deploy.yml`. Worker must stay always-on. Previously on Railway (`railway.toml`), where `VOICE_TURN_DETECTOR` defaulted off so the EOU subprocess would not OOM.

Integration rules going forward:

- Keep the blog fully static and independent of the backend.
- Use environment-based API origin configuration in the frontend.
- Restrict backend CORS to the Pages domain and local dev origin.
- Treat PDF/blog/SEO generation as build-time concerns, not backend concerns.
- The token endpoint lives in the Python agent server, not a Next.js API route (static export constraint).

## Public vs Repo-Only Content

Publicly shipped:

- `app/`
- `components/`
- `content/blog/`
- `public/`
- generated `out/`

Repo-only documentation:

- `readmes/`

That means the spec files in `readmes/` do not get published to GitHub Pages unless they are copied into public-facing routes explicitly.

## Verification

Minimum checks after UI or content-system changes:

- `npm run lint`
- `npm run build`

For deployment changes, also verify:

- `out/` is produced successfully
- blog routes are emitted
- `sitemap.xml` and `robots.txt` are generated

