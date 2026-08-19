# SEOPLAN.md — SEO, Analytics & LLM Observability Plan

Created 2026-07-10 by Fable. This is the execution plan for maximizing findability of
`https://paymanshus.github.io`, adding visit/engagement analytics, and adding LLM
observability (Langfuse) to the voice/terminal agent.

**How to use this file:** each task below is tagged with the model tier that should
execute it (`FABLE` / `OPUS` / `SONNET` / `HAIKU`) plus `OWNER` for things only the
human can do. Tasks are self-contained: an agent should be able to open this file,
read its task, and complete it without other context. Fable-tier tasks were executed
in the planning session itself — they are marked DONE with what shipped.

**Ground rules for every agent picking up a task:**
- Work only in `~/code/vibesite2k26`. NEVER touch `~/code/deployed`.
- Frontend verification: `npm run lint && npm run build` (Node 22 via nvm, inside WSL).
- Agent (Python) verification: `cd agent && .venv/bin/python -m pytest tests/test_token_server.py tests/test_resume_context.py -q`.
- After finishing a feature, update `readmes/SPECs/TECH_SPEC.md` (and `DESIGN_SPEC.md`
  for visual changes) and end with a test (simple is fine).
- The site is a **static export** (`output: 'export'` in `next.config.ts`) deployed to
  GitHub Pages. There is **no server at runtime**: no API routes, no middleware, no
  dynamic OG image routes. Anything dynamic must happen at build time or client-side.
- Identity facts (single source of truth = `content/resumedump.md`):
  - Name: **Paymanshu Sharma**. Role: **Machine Learning Engineer at Maersk**,
    Bangalore, India (Apr 2025–present).
  - Education: B.Tech Data Science, MPSTME NMIMS Mumbai (2018–2022).
  - Links: github.com/Paymanshus, **linkedin.com/in/paymanshus** (note trailing `s`),
    huggingface.co/paymanshus. Email: paymanshus@gmail.com.

---

## Strategy summary (why these tasks)

"Paymanshu" is a globally unique token — ranking #1 for the name is already true.
The goal is therefore **not** ranking, it is (a) making the result *rich* (knowledge-
panel-grade entity data, sitelinks, article results, good snippets/previews when the
link is shared), (b) making every page independently findable (blog posts ranking for
their topics, not just the name), (c) being legible to AI assistants (increasingly how
recruiters "search" people), and (d) measuring who comes and what they engage with.

Architecture decisions (made, do not re-litigate):
1. **Entity graph**: one canonical `Person` node with a stable `@id`
   (`https://paymanshus.github.io/#person`), referenced by `@id` from every page's
   JSON-LD instead of re-declaring divergent Person copies. Shipped in Phase A.
2. **Analytics: GA4** (gtag.js, client-side). Rationale: free, custom events, engagement
   time, works on static hosting. Rejected: Plausible (paid), Umami (needs a host),
   GoatCounter (weak custom-event model). Custom instrumentation (below) covers
   time-per-section, which GA4 alone can't see inside a page.
3. **OG images generated at build time** (satori → PNG per route) since there's no
   server. Until that lands, a single static default OG image is acceptable.
4. **RSS + JSON Feed** generated in the existing `scripts/generate-seo-files.mjs` step.
5. **LLM observability: Langfuse** via OTel export from LiveKit Agents + explicit
   instrumentation of the terminal `/api/chat` endpoint. See Phase L (researched and
   implemented in the Fable session; read that section before touching `agent/`).

---

## Phase A — FABLE (DONE in planning session, 2026-07-10)

### A1. This plan. DONE.

### A2. Entity graph & identity overhaul. DONE.
What shipped (for later agents' awareness — don't redo):
- `lib/site.ts`: corrected LinkedIn URL (`/in/paymanshus`), location → Bangalore,
  role → Machine Learning Engineer at Maersk; added `PERSON_ID`/`WEBSITE_ID` and
  `personJsonLd()` / `websiteJsonLd()` builders (Person with `worksFor`, `alumniOf`,
  `knowsAbout`, `sameAs`); rewrote default title/description/keywords to be
  identity-rich instead of design-jargon ("Austere Neon…" was a bad meta description).
- `app/page.tsx`: home now emits `WebSite` (publisher → `@id`), `ProfilePage`
  (mainEntity → `@id`), and the full `Person` node.
- `app/experience/page.tsx`, `app/thoughts/[slug]/page.tsx`: Person re-declarations
  replaced with `@id` references (author/publisher/mainEntity).
- `app/layout.tsx`: keywords/description aligned with `siteConfig`.

### A3. SEO output regression test. DONE.
`tests/seo/check-static-output.mjs` + `npm run test:seo` — validates the built `out/`
HTML: canonical tags, exactly-one-h1, Person `@id` graph on home, `BlogPosting` with
`@id` author on articles, robots.txt/sitemap.xml presence and URL agreement. Run it
after any SEO-touching change: `npm run build && npm run test:seo`.

---

## Execution status (updated 2026-07-25 by Opus)

| Phase | Tasks | Status |
| --- | --- | --- |
| A (Fable) | A1–A3 | ✅ done 2026-07-10 |
| L (Fable) | Langfuse observability | ✅ done 2026-07-10 — owner keys pending (E5) |
| B (Opus) | B1 analytics, B2 OG images, B3 crawlability | ✅ done 2026-07-25 |
| C (Sonnet) | C1–C6 | ✅ done 2026-07-25 |
| D (Haiku) | D1–D4 | ✅ done 2026-07-25 — see `readmes/seo-verify-report.md` |
| E (Owner) | E1–E5 | ⏳ E1 verification files shipped 2026-08-19; owner still must click Verify, submit sitemap, create GA4 |

Final audit (local build, headless): **SEO 100, Accessibility 100, Best practices 96,
Performance 86**. Verification commands, all green:
`npm run lint`, `npm run build`, `npm run test:unit`, `npm run test:seo`,
and `cd agent && .venv/bin/python -m pytest tests/ -q --ignore=tests/test_connections.py` (75 passed).

**Bug found and fixed during D4** (unrelated to SEO, but severe): `components/RippleGrid.tsx`
called `new Renderer()` from `ogl` unguarded. Where WebGL is unavailable — GPU
blocklists, hardware acceleration disabled, some privacy/enterprise setups, older
devices, and any headless browser — the constructor threw and **crashed React
hydration on the home page**, leaving a blank/broken document. That is also what
made Lighthouse report a missing `lang` attribute and missing `main` landmark
(accessibility 73) on a page whose source plainly has both. Renderer creation is
now wrapped in try/catch with a null check on `renderer.gl`; the background is
decorative, so it degrades to rendering nothing. Accessibility went 73 → 100.

Implementation notes for anyone picking this up later are folded into
`readmes/SPECs/TECH_SPEC.md` (SEO, Open Graph images, Feeds, Analytics,
Observability sections) and `DESIGN_SPEC.md` (Footer). The per-task detail below
is kept as the original brief — where shipped reality differs, the SPECs win.

Deviations from the original brief, and why:
- **B1**: the plan put section timing behind `useSectionView` everywhere. Full-page
  sections (article body, thoughts index, hero) are server components, so they use
  a `PageEngagement` client component instead — mount/unmount is a more accurate
  signal than intersection for a whole page. `useSectionView` is still used for the
  partial-page `experience` section. Timer flush also happens on route change, not
  just `pagehide`, so SPA navigation doesn't lose dwell time.
- **B2**: satori cannot parse the Space Grotesk *variable* font (`fvar` table
  crash in its opentype.js fork), so committed fonts are static instances
  produced with `fonttools varLib.instancer`. Also added `absoluteAssetUrl()` —
  the existing `absoluteUrl()` appends a trailing slash, which silently corrupts
  image/feed URLs (`/og/default.png/`).
- **B3**: the footer renders on every route *except* home (the hero is
  `h-screen overflow-hidden`; a footer there is clipped). Home's identity links
  are carried by the Person JSON-LD `sameAs` instead.
- **C1**: also added `atom:self` link, `<category>` per tag, and per-item `image`
  pointing at the generated OG card.

---

## Phase B — OPUS tasks

### B1 (OPUS). GA4 + engagement analytics engine
Goal: page views per route, plus **time spent per surface**: home vs experience vs
each blog article vs terminal vs voice.

Build exactly this:
1. `lib/analytics.ts`:
   - `export function trackEvent(name: string, params?: Record<string, string | number | boolean>)`
     — safe no-op if `window.gtag` is undefined.
   - `export function createSectionTimer(nowFn = () => performance.now())` — a **pure,
     testable** accumulator: `start(section)`, `stop(section)`, `pauseAll()`,
     `resumeAll()`, `flush(): Array<{section: string, ms: number}>` (flush resets).
     All GA/browser wiring stays out of this function so it can be unit-tested.
2. `components/analytics/Analytics.tsx` (client component, rendered once in
   `app/layout.tsx` body):
   - Injects gtag.js with `NEXT_PUBLIC_GA_ID` (skip entirely when env var is unset —
     dev builds stay clean). Configure with `send_page_view: false`.
   - Sends `page_view` manually on every `usePathname()` change (App Router SPA nav).
   - Hosts the section-timer: listens to `visibilitychange` (pause/resume) and
     `pagehide` (final flush). Flush sends one `section_time` event per section:
     `trackEvent('section_time', { section, seconds, page_path })`. GA4 events are
     dropped on unload unless transported reliably — set
     `gtag('config', ..., { transport_type: 'beacon' })`.
3. `hooks/useSectionView.ts`: `useSectionView(sectionId: string)` returns a ref;
   IntersectionObserver at ≥50% visibility calls timer `start/stop` and fires a
   one-time `section_view` event per page load. Attach to: hero (`home_hero`),
   thoughts list (`thoughts_index`), article body (`article:<slug>`), experience
   shell (`experience`).
4. Experience-mode + agent events (these are the interesting ones):
   - `components/resume/*` tab switch → `resume_mode_change { mode: 'pdf'|'terminal'|'voice' }`
     and route timer sections `resume:pdf`, `resume:terminal`, `resume:voice`.
   - `ChatResume.tsx`: `terminal_command { command }` for built-in commands (help,
     clear…), `terminal_chat { llm: true|false }` for free-text messages. **Never send
     the message text itself** (privacy; also keeps GA cardinality sane).
   - `VoiceResume.tsx`: `voice_session_start`, `voice_session_end { duration_seconds }`,
     `voice_error { stage }`.
5. Scroll depth for articles: fire `scroll_depth { percent: 25|50|75|100, page_path }`
   once per threshold per page view (GA4's enhanced measurement only gives 90%).
6. Wire `NEXT_PUBLIC_GA_ID` into `.env.example` and add a **commented** line in
   `.github/workflows/deploy.yml` env block (owner uncomments after E1).
7. Tests: node test for `createSectionTimer` (fake `nowFn`; assert accumulation,
   pause, flush-resets). Add as `tests/seo/section-timer.test.mjs`, runnable with
   `node --test tests/seo/`.
Acceptance: `npm run build` passes with and without `NEXT_PUBLIC_GA_ID`; no gtag
request happens when env unset; events visible in GA4 DebugView when
`NEXT_PUBLIC_GA_DEBUG=true` adds `debug_mode: true` to all events.

### B2 (OPUS). Build-time OG image pipeline
1. Add devDeps: `satori`, `@resvg/resvg-js`. Commit one TTF (Space Grotesk regular +
   bold) under `scripts/assets/fonts/` (never fetch fonts at build).
2. `scripts/generate-og-images.mjs`: renders 1200×630 dark cards (bg `#040404`, red
   accent `#ef4444`-ish per site palette): default card (name + "Machine Learning
   Engineer · Maersk" + URL) → `public/og/default.png`; per post (title, date,
   "Paymanshu Sharma — Thoughts") → `public/og/thoughts/<slug>.png`. Read posts the
   same way `scripts/generate-seo-files.mjs` does (gray-matter over `content/blog`,
   skip `_`-prefixed / `published: false`).
3. Hook into build: `"generate:seo": "node ./scripts/generate-seo-files.mjs && node ./scripts/generate-og-images.mjs"`.
   Skip regeneration if output newer than source (build speed).
4. `lib/site.ts` `createMetadata()`: add `openGraph.images = [absoluteUrl(ogImage ?? '/og/default.png')]`
   (new optional `ogImage` input) and matching `twitter.images`; blog page passes
   `/og/thoughts/<slug>.png`.
5. Extend `tests/seo/check-static-output.mjs`: assert `og:image` present on home +
   one article and the PNG files exist in `out/`.

### B3 (OPUS). Crawlability & internal-linking pass
1. Every route exactly one `<h1>`: home has it; `/thoughts` has it; article has it;
   `/experience` currently tops out at `<h2>Experience</h2>` in
   `components/ExperienceSection.tsx` — promote to `<h1>` (keep visual size via classes).
2. `components/SiteShell.tsx` / `SiteHeader.tsx`: ensure `<nav>` landmark with
   `aria-current="page"` on active link; add a real `<footer>` (rendered on all pages)
   with: name, one-line role blurb, links to GitHub/LinkedIn/HuggingFace
   (`rel="me"` on each), email, and internal links to /experience and /thoughts.
   Match existing austere design — check `readmes/SPECs/DESIGN_SPEC.md` first.
3. Article pages: previous/next post links (chronological) at the bottom + a
   `BreadcrumbList` JSON-LD (Home → Thoughts → title). Use `@id` person conventions
   from `lib/site.ts`.
4. `ThoughtPost.tsx`: ensure external links in markdown get `rel="noopener"`; images
   (if any ever) require alt from markdown.
5. Test: extend `tests/seo/check-static-output.mjs` — one-h1 rule for `/experience/`,
   footer link presence, BreadcrumbList on an article.

---

## Phase C — SONNET tasks (follow literally; no design decisions needed)

### C1 (SONNET). RSS + JSON Feed
In `scripts/generate-seo-files.mjs` (patterns for reading posts already exist there):
1. Add `writeRssFile()` → `public/feed.xml`, RSS 2.0: channel title
   `Thoughts — Paymanshu Sharma`, link `${SITE_URL}/thoughts/`, description
   `Essays on machine learning, agents, and engineering by Paymanshu Sharma.`,
   `<language>en-us</language>`; one `<item>` per published post: title, absolute
   link, `<guid isPermaLink="true">` = link, pubDate (`new Date(date).toUTCString()`),
   description = excerpt (XML-escaped with the existing `escapeXml`).
2. Add `writeJsonFeedFile()` → `public/feed.json` per JSON Feed 1.1
   (`https://jsonfeed.org/version/1.1`): `title`, `home_page_url`, `feed_url`,
   `authors: [{ name: 'Paymanshu Sharma', url: SITE_URL }]`, items with `id`=url,
   `url`, `title`, `summary`, `date_published` (ISO).
3. Call both in the main block at the bottom, next to `writeSitemapFile()`.
4. `app/layout.tsx` metadata: add
   `alternates.types = { 'application/rss+xml': absoluteUrl('/feed.xml') }` — note
   `alternates.canonical` already exists there; merge, don't replace.
5. Extend `tests/seo/check-static-output.mjs`: `out/feed.xml` exists and contains
   one known slug; `out/feed.json` parses via `JSON.parse` and has ≥1 item.
6. Run `npm run build && npm run test:seo && npm run lint`.

### C2 (SONNET). Search-engine verification hooks + setup doc
1. `app/layout.tsx` metadata: add
   `verification: { google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION }`
   (Next skips the tag when undefined). Add the var (empty) to `.env.example` with a
   comment, and a commented line in `.github/workflows/deploy.yml` env block.
2. Create `docs/SEO_SETUP.md`: click-by-click owner instructions for
   (a) Google Search Console URL-prefix property for `https://paymanshus.github.io/`,
   HTML-tag verification (paste content value into the env var, redeploy, verify),
   then submit `https://paymanshus.github.io/sitemap.xml`;
   (b) Bing Webmaster Tools "Import from GSC";
   (c) GA4 property + web data stream creation, copy `G-XXXX` id into
   `NEXT_PUBLIC_GA_ID`;
   (d) how to check indexing (`site:paymanshus.github.io`) and request indexing for
   new posts.
3. No test needed beyond `npm run build`.

### C3 (SONNET). Meta copy polish (exact strings)
1. `app/experience/page.tsx` description →
   `Interactive resume of Paymanshu Sharma, Machine Learning Engineer at Maersk — read the PDF, ask the terminal, or talk to a voice agent trained on his experience.`
2. `app/thoughts/page.tsx` description →
   `Essays and technical notes by Paymanshu Sharma on machine learning, LLM agents, voice AI, and engineering craft.`
3. For each file in `content/blog/*.md` (skip `_template.md`): ensure frontmatter has
   3–6 `tags` and an `excerpt` of 120–155 chars that summarizes the actual content
   (read the post body first). Keep tone factual, no keyword stuffing.
4. `npm run build && npm run test:seo`.

### C4 (SONNET). llms.txt
1. Create `public/llms.txt` (plain markdown, served at `/llms.txt`):
   H1 `# Paymanshu Sharma`, blockquote one-liner (ML Engineer at Maersk, Bangalore;
   builds agentic AI, voice agents), then sections: `## Site` (bullet list of the
   main routes with absolute URLs + one-line description each, including each
   published blog post), `## Elsewhere` (GitHub/LinkedIn/HuggingFace URLs),
   `## Contact` (email). Regenerate the blog-post list by hand — 3 posts today.
2. Mention `/llms.txt` in `docs/SEO_SETUP.md` if it exists.
3. `npm run build` and confirm `out/llms.txt` exists.

### C5 (SONNET). 404 page
1. Create `app/not-found.tsx`: server component, austere style (reuse `SiteShell` if it
   doesn't require props beyond children), `<h1>404</h1>`, one-liner, links to `/`,
   `/thoughts/`, `/experience/`. Export
   `metadata = { title: 'Not found', robots: { index: false } }`.
2. `npm run build` — confirm `out/404.html` renders the content (GitHub Pages picks up
   `404.html` automatically).

### C6 (SONNET). Docs refresh (folds in left.md items 4 & 9)
1. Rewrite root `README.md`: what the site is, three resume modes, quickstart for
   frontend (`npm i && npm run dev`) + agent (`cd agent && python main.py dev`, env
   from `agent/.env.example`), test commands, deploy note (GitHub Actions → Pages).
2. Update `readmes/WORKING_ON.md` to point at the current surface (agent/, resume
   components, analytics once B1 lands).
3. No code; no test beyond `npm run lint`.

---

## Phase D — HAIKU tasks (verification & reporting; read-only + one report file)

### D1 (HAIKU). Post-build tag sweep
Run `npm run build`, then verify in `out/`: for each of `index.html`,
`experience/index.html`, `thoughts/index.html`, `thoughts/<each-slug>/index.html`,
`404.html`: grep for `rel="canonical"`, `og:title`, `og:image`, `application/ld+json`,
`<h1`. Record a pass/fail table in `readmes/seo-verify-report.md`. Also run
`npm run test:seo` and paste the output.

### D2 (HAIKU). External validator checklist
Append to `readmes/seo-verify-report.md` a checklist of URLs for the owner to paste
into: Google Rich Results Test, validator.schema.org, opengraph.xyz (one per route
type). Do not attempt to browse; just produce the exact URLs and what to look for
(Person entity on home, Article on posts, no errors).

### D3 (HAIKU). Alt/anchor audit
Grep `components/` and `content/blog/` for `<img`, `Image`, and markdown images;
list any missing alt text, plus any `<a>` with anchor text like "click here". Append
findings to `readmes/seo-verify-report.md`. Read-only.

### D4 (HAIKU). Lighthouse
From WSL: `npx lighthouse https://paymanshus.github.io --only-categories=seo,performance --preset=desktop --output=json --output-path=./readmes/lighthouse.json --chrome-flags="--headless"`
(after next deploy). Record SEO + perf scores and the top 3 opportunities in
`readmes/seo-verify-report.md`. If Chrome isn't available in WSL, note that and skip.

---

## Phase E — OWNER tasks (no agent can do these)

### Search Console verification methods (updated 2026-08-19)

Google offered five ways to verify `https://paymanshus.github.io/`. What is
possible on this host:

| Method | Can you do it today? | Can an agent do it? | Status |
| --- | --- | --- | --- |
| **HTML file** (`google51d43957481c87ef.html` at site root) | Yes — after this deploy is live | Yes | **Shipped** in `public/google51d43957481c87ef.html`. Wait for Pages, then click **Verify**. Do not delete the file. |
| **HTML meta tag** (`google-site-verification`) | Yes — after this deploy is live | Yes | **Shipped** in `app/layout.tsx` / `lib/site.ts` (`0o-VrKZb3IemUzf8qmVFsl_dRpOwOPaZU1azIjFYnkw`). Same: wait for Pages, then Verify. |
| **Google Analytics** (gtag.js on the homepage) | Yes — live after this deploy | Yes | **Shipped** (`G-5LV14G6B05` via `NEXT_PUBLIC_GA_ID`). Check GA4 → Reports → Realtime. |
| **Google Tag Manager** | Only if you first create a GTM container | Not worth adding just to verify | **Skip.** The site does not use GTM. Meta tag + HTML file already cover ownership. |
| **DNS TXT** (`google-site-verification=CnlXj14HVM8sSgvtriztuQ6nKfE3wIS3oddj0lRDz_Y` on `paymanshus.github.io`) | **No** | **No** | **Impossible.** `github.io` DNS is owned by GitHub. You cannot add TXT records for this hostname. Only viable after a custom domain (E4). |

After the Pages deploy finishes, confirm then verify:

```bash
curl -s https://paymanshus.github.io/ | grep google-site-verification
curl -sI https://paymanshus.github.io/google51d43957481c87ef.html
```

Then in Search Console: **Verify** (HTML file or HTML tag — either is enough), then
**Sitemaps → submit `sitemap.xml`**.

- **E1 (remaining)**:
  1. Click **Verify** in Search Console once the meta tag / HTML file is live.
  2. Submit `https://paymanshus.github.io/sitemap.xml`.
  3. Create a GA4 property + Web stream for `https://paymanshus.github.io`, copy the
     Measurement ID (`G-XXXXXXXXXX`), add GitHub Actions repo variable
     `NEXT_PUBLIC_GA_ID`, and tell an agent (or uncomment
     `NEXT_PUBLIC_GA_ID: ${{ vars.NEXT_PUBLIC_GA_ID }}` in
     `.github/workflows/deploy.yml` yourself). Until that id exists, **visitor
     counts are not collected**.
  4. Optional: Bing Webmaster Tools → Import from Google Search Console.
- **E2 (highest-leverage SEO action available)**: put `https://paymanshus.github.io`
  in the website field of: GitHub profile, LinkedIn (both contact-info website AND
  featured section), HuggingFace profile, Kaggle, X/Twitter if any. Consistent
  identity links are what turn a unique name into a knowledge panel.
- **E3**: The 3 blog posts are AI-generated placeholders (flagged in left.md #5).
  Replace or rewrite with real writing — content quality is the only durable ranking
  factor for the topic queries. Decide `published: false` for any you don't stand by.
- **E4**: Consider a custom domain later (e.g. paymanshu.dev). If ever, do it soon —
  the cost of moving grows with backlink count; github.io is perfectly fine otherwise.
  **Full research + migration runbook: `readmes/DOMAIN_PORTING.md`** (options,
  free vs paid, the repo's CORS/build-time landmines, and the automatic 301 from
  github.io). Note the SEO gain is ~zero: github.io and every free-subdomain
  alternative are all on the Public Suffix List, so none of them share authority.
- **E5**: Langfuse project + keys (see Phase L): set `LANGFUSE_PUBLIC_KEY`,
  `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` in `agent/.env.local` and on the fly.io app
  when deployed. Optionally register the Langfuse MCP server for querying traces:
  `claude mcp add --transport http langfuse https://cloud.langfuse.com/api/public/mcp --header "Authorization: Basic <base64 pk:sk>"`.

---

## Phase L — Langfuse / agent observability (FABLE — DONE 2026-07-10)

**Decision: Langfuse, not abort.** LiveKit Agents already *instruments* the whole
pipeline (OTel spans with full LLM chat context, tool calls, TTS/STT nodes, turn
latencies, plus usage counters), but (a) its first-party dashboard is LiveKit-Cloud-
deployment oriented while this agent is a self-hosted fly.io worker with BYO
Deepgram/Google/Cartesia keys, and (b) the terminal `/api/chat` path never touches
LiveKit — no LiveKit product can ever observe it. Langfuse is LiveKit's officially
supported OTel export target and covers both surfaces in one project. SDK: langfuse
v4 (4.13.2; the v4 rewrite landed March 2026 — do not use v3 code patterns like
`update_current_trace`; v4 uses `propagate_attributes`).

Shipped (see TECH_SPEC "Observability (Langfuse)" for the full wiring):
- `agent/observability.py` — env-gated module: `setup_voice_tracing()` (shared
  TracerProvider → LiveKit `set_tracer_provider` + Langfuse exporter, session id =
  room name), `attach_usage_reporter()` (UsageCollector → `voice_session_usage` span
  with token/char/second totals + USD estimates, `COST_*` env-overridable),
  `get_langfuse()`/`trace_attributes()`/`shutdown()` helpers.
- `agent/main.py` — tracing + usage reporter wired into the rtc_session entrypoint,
  spans force-flushed via shutdown callback.
- `agent/token_server.py` — `/api/chat` refactored into `_generate_reply()`: one
  `terminal-chat` trace per request (pseudonymous sha256(IP) user, visitor+day
  session, `terminal` tag), one Langfuse generation per Gemini fallback attempt with
  prompt/output/token usage; ERROR-level generations on failed attempts. aiohttp
  cleanup flushes the client.
- `agent/requirements.txt` (+ `langfuse>=4,<5`), `agent/.env.example` (LANGFUSE_* +
  COST_* docs), `agent/tests/test_observability.py` (10 tests; suite 75 green).
- Verified: no dependency conflicts with livekit-agents OTel pins (`pip check`
  clean); smoke-tested provider wiring + span creation against a dead endpoint
  (export failure is retried in background and never blocks serving).

Remaining (OWNER — see E5): create the Langfuse project, set `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` in `agent/.env.local` (and on fly.io at
deploy time). In Langfuse, models named `gemini-*` get costs computed automatically
from the recorded token usage. Optionally register the Langfuse MCP server to query
traces from Claude Code (command in E5).
