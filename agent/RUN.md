# Running / Deploying the Voice Agent

This is a reference for the owner. **No deployment has been performed by any
agent** — these are just the commands to run manually once Fly.io
credentials are set up.

## Local development

```bash
cd agent
python -m venv .venv && source .venv/bin/activate   # if not already set up
pip install -r requirements.txt
cp .env.example .env.local   # fill in real API keys
python main.py download-files   # turn-detector model (one-time)
python main.py dev
```

## Docker build (build context MUST be repo root)

The Dockerfile copies `content/resumedump.md`, which lives outside `agent/`,
so it has to build with the repo root as context:

```bash
docker build -f agent/Dockerfile -t paymanshu-voice-agent .
docker run --rm -p 8080:8080 --env-file agent/.env.local paymanshu-voice-agent
```

## Fly.io deploy (NOT yet done — owner-only)

```bash
# one-time app setup
flyctl launch --no-deploy --config agent/fly.toml --dockerfile agent/Dockerfile

# secrets (mirror agent/.env.local — do not commit real values)
flyctl secrets set \
  LIVEKIT_URL=... \
  LIVEKIT_API_KEY=... \
  LIVEKIT_API_SECRET=... \
  GOOGLE_API_KEY=... \
  DEEPGRAM_API_KEY=... \
  CARTESIA_API_KEY=... \
  -a paymanshu-voice-agent

# deploy — build context is the repo root, config points at agent/
flyctl deploy --config agent/fly.toml --dockerfile agent/Dockerfile -a paymanshu-voice-agent
```

After deploy, get the app URL (`https://paymanshu-voice-agent.fly.dev`) and:

1. Uncomment `NEXT_PUBLIC_AGENT_URL` in `.github/workflows/deploy.yml`
   (see item 8 in `left.md` — the line is already prepared, commented out).
2. Set the same var in the frontend's local `.env.local` if testing against
   the deployed agent from a local `npm run dev`.

## Notes

- `[http_service] min_machines_running = 0` in `fly.toml` means the agent
  scales to zero when idle — first connection after idle will have a cold
  start (Fly machine boot, ~1-3s) before LiveKit dispatch completes.
- The token/chat HTTP server and the LiveKit agent worker run in the same
  process (`agent/main.py`), so one Fly app serves both `/api/token`,
  `/api/chat`, and the voice agent's room dispatch.
