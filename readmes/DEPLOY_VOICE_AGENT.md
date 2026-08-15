# Deploy the Voice Agent to fly.io — Runbook

> For a future agent session + owner. Everything below is ready; the only
> blockers are owner credentials (`flyctl auth login`) and secret values.
> Once done, the live site's voice + terminal LLM work for ALL visitors,
> not just on the owner's machine.
>
> Prepared 2026-07-11. Files: `agent/Dockerfile`, `agent/fly.toml`,
> `agent/RUN.md` (created by the Sonnet packaging pass — read RUN.md first,
> it has the exact commands; this file is the end-to-end checklist around it).

## Current state (what already works)

- Static site is live at https://paymanshus.github.io (deployed 2026-07-11,
  commit `e6d1c34` in `deployed/`).
- The frontend bakes `NEXT_PUBLIC_AGENT_URL` at build time; it currently
  defaults to `http://localhost:8080`, so:
  - On the owner's machine (with `agent/main.py` running + Chrome's
    local-network permission granted): live site fully works.
  - For visitors: terminal falls back to `[OFFLINE MODE]` keyword answers,
    voice shows the connection-error view. Graceful, but not the goal.

## Step-by-step

### 1. Owner: fly.io account + CLI (interactive, owner-only)
```bash
# In WSL Ubuntu:
curl -L https://fly.io/install.sh | sh   # installs flyctl to ~/.fly
export FLYCTL_INSTALL="$HOME/.fly"; export PATH="$FLYCTL_INSTALL/bin:$PATH"
flyctl auth login                        # opens browser — OWNER does this
```

### 2. Create the app (name must match fly.toml)
```bash
cd ~/code/vibesite2k26
grep '^app' agent/fly.toml               # note the app name
flyctl apps create <that-app-name>       # or edit fly.toml to a free name
```

### 3. Set secrets from agent/.env.local
Copy the values (do NOT commit them). Required:
```bash
flyctl secrets set -a <app> \
  LIVEKIT_URL=... LIVEKIT_API_KEY=... LIVEKIT_API_SECRET=... \
  GOOGLE_API_KEY=... DEEPGRAM_API_KEY=... CARTESIA_API_KEY=... \
  CARTESIA_VOICE_ID=79a125e8-cd45-4c13-8a67-188112f4dd22
```
Optional tuning (defaults are sane): `VOICE_LLM_MODELS`, `CARTESIA_MODEL`,
`TERMINAL_LLM_MODEL`, `VOICE_MAX_OUTPUT_TOKENS`, `RESUME_SCORE_THRESHOLD`,
`MIN_ENDPOINTING_DELAY`, `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`.

### 4. Deploy (build context = repo root, NOT agent/)
```bash
cd ~/code/vibesite2k26
flyctl deploy -a <app> -c agent/fly.toml --dockerfile agent/Dockerfile
```
Gotcha: the Dockerfile copies `content/resumedump.md`, which only exists in
the repo-root context. `agent/RUN.md` documents this.

### 5. Verify the deployed agent
```bash
curl https://<app>.fly.dev/api/health          # {"status": "ok", ...}
curl -X POST https://<app>.fly.dev/api/chat \
  -H 'Content-Type: application/json' -d '{"message": "what do you do at Maersk?"}'
curl https://<app>.fly.dev/api/token | head -c 200   # JWT + serverUrl
# Check the worker registered with LiveKit Cloud:
flyctl logs -a <app> | grep "registered worker"
```

### 6. Point the live site at it
1. In `.github/workflows/deploy.yml` (BOTH the source copy and via deploy
   script), uncomment and fill:
   `NEXT_PUBLIC_AGENT_URL: https://<app>.fly.dev`
2. CORS is already correct: `token_server.py` `ALLOWED_ORIGINS` includes
   `https://paymanshus.github.io`.
3. Redeploy the site:
   `bash scripts/deploy-pages.sh -m "Point voice/terminal at fly.io agent"`
   (script builds, syncs to `deployed/`, purges private paths, commits,
   pushes; add `--no-push` first if you want to audit the commit).

### 7. Live end-to-end verification (from any device, e.g. phone)
- Terminal: ask a free-form question → grounded LLM answer (not `[OFFLINE MODE]`).
- Voice: START VOICE → mic modal (first time only) → greeting in ~2s,
  green particles while it talks, red while you talk, live transcript.
- Rate limits: hammer the terminal 11× in a minute → `[RATE LIMITED]` message.
- Check `flyctl logs` for `context injection:` lines per voice turn.

## Costs / limits to know
- fly.io free allowance covers 1 shared-cpu VM; the agent is CPU-light except
  Silero VAD + turn-detector ONNX (already baked into the image at build).
- LiveKit Cloud free tier: 1,000 agent minutes/mo. Cartesia free: 10K chars/mo
  (then Deepgram Aura fallback kicks in automatically — visitors hear a
  different voice and the UI shows the amber "fallback voice" banner).
- In-memory rate limits reset on VM restart; `auto_stop_machines` in fly.toml
  may cold-start (~seconds). If voice feels slow to connect, consider
  `min_machines_running = 1`.

## Rollback
- Site: revert the workflow env line and redeploy, or `git revert` in
  `deployed/` and push.
- Agent: `flyctl releases -a <app>` → `flyctl releases rollback`.
