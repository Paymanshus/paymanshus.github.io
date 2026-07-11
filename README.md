# Paymanshu Sharma Portfolio

Next.js 15 static-export portfolio deployed to `paymanshus.github.io`, with
three ways to explore Paymanshu's experience:

- **Browse** — the standard portfolio pages and blog.
- **Terminal chat** (`ChatResume.tsx`) — a text chat backed by an LLM with
  resume content pre-loaded as context.
- **Voice** (`VoiceResume.tsx`) — a live voice conversation over LiveKit,
  backed by a Python agent (`agent/`) doing STT → LLM → TTS with resume
  context injected per-turn.

See `readmes/SPECs/TECH_SPEC.md` and `readmes/SPECs/DESIGN_SPEC.md` for the
living source of truth on implementation and design.

## Frontend — Local Development

1. Install dependencies with `npm install` (Node 22 recommended, via nvm).
2. Copy `.env.example` to `.env.local` if you want to override the
   production site URL, or point `NEXT_PUBLIC_AGENT_URL` at a locally
   running voice agent (see below).
3. Run `npm run dev`.

Checks before committing frontend changes:

```bash
npm run lint && npm run build
```

`npm run build` emits the static site to `out/`.

## Voice Agent — Local Development

The voice/terminal LLM backend lives in `agent/` (Python, LiveKit Agents).

```bash
cd agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.local   # fill in real API keys — see comments in the file
python main.py download-files   # one-time: turn-detector model
python main.py dev              # runs the LiveKit worker + token/chat HTTP server
```

`.env.local` needs keys for LiveKit Cloud, Google Gemini, Deepgram, and
Cartesia — each key's source URL is commented in `agent/.env.example`.

The same process also serves `POST /api/token` (LiveKit room tokens) and
`POST /api/chat` (the terminal chat's LLM endpoint) on `:8080`.

### Agent tests

```bash
cd agent
.venv/bin/python -m pytest tests/ -q
```

`tests/test_connections.py` is a manual smoke test (hits live third-party
APIs with real keys) and is skipped by `pytest`; run it directly with
`python tests/test_connections.py` to sanity-check API credentials.

### Packaging / deployment

`agent/Dockerfile`, `agent/fly.toml`, and `agent/RUN.md` describe how to
containerize and deploy the agent to Fly.io. No agent has deployed this —
deployment is the owner's responsibility, and `NEXT_PUBLIC_AGENT_URL` in
`.github/workflows/deploy.yml` stays commented out until a Fly.io URL exists.

## GitHub Pages Deployment (frontend)

This project is configured for:

- Next.js app router
- static export via `output: 'export'`
- GitHub Actions deployment from `.github/workflows/deploy.yml`

When this code lives inside the `paymanshus.github.io` repository, pushing to
`main` will build and deploy the exported site to GitHub Pages.

For one-command local deployment into an existing clone of
`paymanshus.github.io`, use:

```bash
./scripts/deploy-pages.sh -m "Your commit message"
```

If you only want to sync and let GitHub Actions perform the canonical build,
use:

```bash
./scripts/deploy-pages.sh -m "Your commit message" --skip-build
```

## Content

- Blog posts live in `content/blog`
- Resume content for the terminal/voice LLMs lives in `content/resumedump.md`
- SEO metadata is centralized in `lib/site.ts`
- `readmes/` is repo-only documentation and is not publicly served
