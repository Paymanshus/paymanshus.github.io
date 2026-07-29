# Paymanshu Sharma — Portfolio

Personal portfolio for Paymanshu Sharma, Machine Learning Engineer at Maersk
(Bangalore). Live at **https://paymanshus.github.io**.

The site is a statically-exported Next.js app plus a standalone Python
LiveKit voice agent that powers the interactive resume.

## Experience modes (`/experience`)

The experience page offers three ways to explore Paymanshu's resume:

1. **PDF** (`components/resume/PdfResume.tsx`) — the resume PDF, embedded.
2. **Terminal chat** (`components/resume/ChatResume.tsx`) — a text terminal
   backed by an LLM grounded in resume context (`POST /api/chat` on the
   agent server), with a keyword-matched offline fallback when the backend
   is unreachable.
3. **Voice** (`components/resume/VoiceResume.tsx`) — a live voice
   conversation over LiveKit WebRTC with a Python agent that does
   Deepgram STT → Gemini LLM → Cartesia TTS, with resume context injected
   per turn.

## Stack

- **Frontend**: Next.js (App Router, static export via `output: 'export'`)
  targeting GitHub Pages, TypeScript, Tailwind CSS v4, Framer Motion
  (`motion`) for animation.
- **Voice agent** (`agent/`): Python 3.11 + `livekit-agents`, Deepgram STT →
  Gemini LLM (with fallback chain) → Cartesia TTS, Silero VAD, LiveKit
  Multilingual turn detection. Runs as a standalone process, separate from
  the Next.js app.

## Repo layout

| Path | What's there |
| --- | --- |
| `app/` | Next.js App Router routes (`/`, `/experience`, `/thoughts`) |
| `components/` | UI components, including `components/resume/*` and `components/analytics/*` |
| `content/blog/` | Blog post Markdown source |
| `content/resumedump.md` | Flat resume text used by the agent's BM25 index and terminal LLM |
| `lib/` | Shared helpers: `site.ts` (SEO/metadata), `blog.ts` (content loading), `utils.ts` |
| `scripts/` | Build/deploy tooling — `generate-seo-files.mjs`, `sync_resume.py`, `deploy-pages.sh` |
| `agent/` | Python LiveKit voice agent + token/chat HTTP server |
| `readmes/` | Specs and plans (`SPECs/TECH_SPEC.md`, `SPECs/DESIGN_SPEC.md`, `SEOPLAN.md`) — repo-only, not published |
| `public/` | Static assets (resume PDF, generated `robots.txt`/`sitemap.xml`, etc.) |

## Frontend quickstart

```bash
npm install
```

```bash
npm run dev
```

Build the static site (runs `generate:seo` first, then `next build`):

```bash
npm run build
```

Output goes to `out/`.

## Agent quickstart

```bash
cd agent
python -m venv .venv && source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env.local
```

Fill in `.env.local` with real keys (LiveKit Cloud, Google Gemini, Deepgram,
Cartesia — each key's source URL is commented in `agent/.env.example`).
Langfuse observability keys are optional; without them tracing is a no-op.

```bash
python main.py dev
```

This starts the LiveKit worker and also runs the token/chat HTTP server
(`/api/token`, `/api/chat`, `/api/health`) on `:8080` in the same process —
no separate server to run.

## Tests

Frontend:

```bash
npm run lint
```

```bash
npm run build && npm run test:seo
```

Agent:

```bash
cd agent && .venv/bin/python -m pytest tests/ -q
```

## Deployment

`.github/workflows/deploy.yml` builds and publishes the static export to
GitHub Pages via GitHub Actions on every push to `main` (also supports
manual dispatch). `scripts/deploy-pages.sh` is also available for
one-command local deployment into an existing clone of the Pages repo.

The voice agent is deployed separately (Fly.io is the plan; see
`agent/RUN.md`) and is not part of the Pages build.

## Docs

- `readmes/SPECs/TECH_SPEC.md` — living source of truth for the shipped
  implementation.
- `readmes/SPECs/DESIGN_SPEC.md` — design system and visual spec.
- `readmes/SEOPLAN.md` — SEO, analytics, and LLM observability task board.
