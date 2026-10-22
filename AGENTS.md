# Agent notes

Before exploring the codebase, read any `*_spec.md` files under `readmes/SPECs/`
(`TECH_SPEC.md`, `DESIGN_SPEC.md`). They are the fastest accurate orientation.
After completing a major feature or structural change, update `TECH_SPEC.md`
(and `DESIGN_SPEC.md` for visual changes).

## What this repo is

Static-exported Next.js portfolio at https://paymanshus.github.io, plus a
standalone Python LiveKit voice agent in `agent/` that powers the interactive
resume on `/experience`.

## Read first

| File | Why |
| --- | --- |
| `readmes/SPECs/TECH_SPEC.md` | Shipped architecture, commands, gotchas |
| `readmes/SPECs/DESIGN_SPEC.md` | Visual system — extend before inventing |
| `readmes/SPECs/BLOG_VISUALS.md` | Inline SVG figure rules for blog posts |
| `README.md` | Quickstart |
| `DEPLOY.md` | How the site and the agent deploy (CI/CD on push to `main`, plus manual). Pushing to `main` deploys. |
| `agent/RUN.md` | Local / Docker / Fly.io agent commands |
| `docs/SEO_SETUP.md` | Owner GSC / GA4 / indexing runbook |
| `readmes/SEOPLAN.md` | SEO/analytics board — Phase E is owner-only leftover |
| `readmes/DEPLOY_VOICE_AGENT.md` | Fly.io go-live checklist (not done yet) |

Do not treat `left.md`, `readmes/notes.md`, `readmes/plannerplan_voice.md`, or
`docs/voice-feature/` as source of truth. Those stay gitignored on purpose.

## Private docs (separate repo)

This repo is public. Working notes, perf write-ups and raw benchmark output,
design exports and Claude's memory notes live in the private repo
`Paymanshus/vibesite2k26-private`, with the same paths as here. Clone it next
to this checkout (`../vibesite2k26-private`) and run its `sync.sh --restore` to
put them back in place; run `sync.sh` there to save new ones. Its README has
the full new-device and cloud-session setup.

## Local secrets (not in git)

A clone is not enough to run the voice/terminal agent. The owner keeps the
secret files on Google Drive under `Claude/vibesite2k26`; copy or recreate:

1. `agent/.env.local` — real LiveKit / Gemini / Deepgram / Cartesia /
   OpenRouter / Sarvam / Langfuse keys. Start from `agent/.env.example`.
   In cloud sessions these come from the environment's variables instead.
2. Root `.env.local` — only if you need to override frontend build-time vars
   (`NEXT_PUBLIC_AGENT_URL`, `NEXT_PUBLIC_GA_ID`, …). `npm run dev` already
   talks to `http://localhost:8080` without this file.
3. Oracle VM access: `~/.ssh/oracle_agent` (SSH) and `~/.oci/` (OCI CLI API
   key). See `deploy/oracle/README.md`.
4. Recreate toolchains: `npm install`, `cd agent && python -m venv .venv &&
   pip install -r requirements.txt`, Node 22 (see `.nvmrc`).

GitHub Actions vars and Fly.io secrets live in those dashboards, not in the
working tree. `.claude/settings.local.json` is machine-specific — do not copy.
