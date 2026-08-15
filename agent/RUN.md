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

## OpenRouter setup (owner-only, one-time)

OpenRouter is the second provider in the LLM ladder — it absorbs traffic spikes
when Gemini's free RPM saturates. **Everything works without it**; those rungs
are skipped and logged, not treated as failures. But without it a spike falls
back to the terminal's keyword mode once Gemini is exhausted.

1. **Deposit $10 once** at <https://openrouter.ai/credits>. This is a *lifetime
   cumulative* threshold, not a balance check: it permanently raises `:free`
   model limits from 50 to **1,000 requests/day** (20 RPM either way), and stays
   in effect even if the balance later drops to zero.

2. **Create a provisioning key** at
   <https://openrouter.ai/settings/provisioning-keys>, then use it to **mint a
   separate runtime key that carries the spend cap**. These are two different
   kinds of key and they are not interchangeable:

   | | Provisioning key | Runtime key |
   |---|---|---|
   | Purpose | creates/manages runtime keys | inference |
   | `/chat/completions` | **401 `User not found`** | works |
   | Goes in `.env.local` | ❌ never | ✅ yes |
   | Carries `limit` | no (`limit: null`) | yes |

   A provisioning key pasted into `OPENROUTER_API_KEY` fails every call with a
   401 — which the ladder classifies as terminal and logs loudly, so it degrades
   safely, but the OpenRouter rungs are dead. Mint the runtime key with:

   ```bash
   curl -s https://openrouter.ai/api/v1/keys \
     -H "Authorization: Bearer $OPENROUTER_PROVISIONING_KEY" \
     -H "Content-Type: application/json" \
     -d '{"name":"portfolio-agent","limit":5,"limit_reset":"monthly"}'
   ```

   The `key` field in the response is shown **once** — that is the value for
   `.env.local`. `limit` + `limit_reset: monthly` is the real hard spend cap:
   there is no account-wide toggle, and unlike the in-memory rate limits in
   `token_server.py` it lives outside the process, so a crash loop cannot reset
   it. When it trips you get a 402, the ladder marks that rung terminal and logs
   at ERROR, and the site degrades to its keyword fallback instead of billing
   you. Keep the provisioning key out of the agent's environment entirely — it
   can mint uncapped keys, so it is strictly more dangerous than the key it
   creates.

3. Put the **runtime** key in `agent/.env.local` as `OPENROUTER_API_KEY=...`,
   then verify:

```bash
cd agent && .venv/bin/python tests/probe_llm.py
```

Every configured rung should resolve and report `stream=yes`. A
`model_not_found` means a `:free` slug in `llm_models.py` has gone stale —
OpenRouter's free catalogue churns, which is why the list is fixed and manually
audited rather than auto-discovered. Fix it by editing `agent/llm_models.py`.

### Choosing prompt layout from data

`LLM_CONTEXT_MODE` decides whether the prompt prefix can be cached at all. To
pick it from measurements rather than reasoning:

```bash
cd agent && .venv/bin/python tests/eval_context_modes.py --repeats 3 --turns 3
```

This writes a JSONL + markdown report under `agent/tests/results/`. Read the
prefix-stability table first (it is measured, not assumed), then compare TTFT
and `cached` columns across arms — and read the sample replies, because the arms
show the model different amounts of context and a faster arm that answers worse
is not a win.

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
  OPENROUTER_API_KEY=... \
  DEEPGRAM_API_KEY=... \
  CARTESIA_API_KEY=... \
  -a paymanshu-voice-agent

# deploy — build context is the repo root, config points at agent/
flyctl deploy --config agent/fly.toml --dockerfile agent/Dockerfile -a paymanshu-voice-agent
```

After deploy, get the app URL (`https://paymanshu-voice-agent.fly.dev`) and:

1. Uncomment `NEXT_PUBLIC_AGENT_URL` in `.github/workflows/deploy.yml`
   (the line is already prepared, commented out).
2. Set the same var in the frontend's local `.env.local` if testing against
   the deployed agent from a local `npm run dev`.

## Notes

- `[http_service] min_machines_running = 0` in `fly.toml` means the agent
  scales to zero when idle — first connection after idle will have a cold
  start (Fly machine boot, ~1-3s) before LiveKit dispatch completes.
- The token/chat HTTP server and the LiveKit agent worker run in the same
  process (`agent/main.py`), so one Fly app serves both `/api/token`,
  `/api/chat`, and the voice agent's room dispatch.
