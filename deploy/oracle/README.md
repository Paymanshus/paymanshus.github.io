# Voice agent on Oracle Cloud

The agent (`agent/main.py start`: token/chat HTTP server plus LiveKit worker)
runs on one Oracle Cloud ARM VM behind Caddy, which handles HTTPS.

| | |
|---|---|
| Public URL | `https://ps-agent.duckdns.org` (DuckDNS → VM public IP `129.225.126.59`, ephemeral) |
| VM | `instance-20261021-1242`, `VM.Standard.A1.Flex`, Ubuntu 24.04 aarch64, `ap-hyderabad-1` (home region, single AD) |
| Size | **4 OCPU / 24 GB until 2026-11-10** (launch window, paid from trial credit), then back to ≤ 2 OCPU / 12 GB (Always Free) |
| Boot volume | 50 GB, 10 VPU |
| SSH | `ssh -i ~/.ssh/oracle_agent ubuntu@129.225.126.59` (key only in WSL) |
| OCI CLI | `~/.local/bin/oci` in WSL, API key in `~/.oci/` (admin user) |
| Code on VM | `/opt/agent/src` (git clone of this repo) |
| Secrets on VM | `/opt/agent/agent.env` (copy of `agent/.env.local`, mode 600, never committed) |
| Persistent state | Docker volume `ps-agent_agent_state` → `/app/state` (voice minutes, waitlist, LLM breaker locks) |
| Perf logs | `/opt/agent/perf/` on the VM; copies + write-ups in `readmes/perf/` (local, gitignored) |

## Account and money

- Oracle account (tenancy `paymanshus`, home region Hyderabad) is **Pay As You
  Go** and bills in **SGD** (fixed at signup; can't be changed to INR).
- Trial promotion: **SGD 400, 2026-10-19 → 2026-11-17 23:59 UTC**
  (`oci organizations subscription get`, `promotion[].status = ACTIVE`).
  Usage above Always Free draws from it until then, and is billed to the card
  after.
- Budget `monthly-safety-net`: **SGD 10/month** on the root compartment, email
  alerts to paymanshus@gmail.com at 1 %, 50 %, 100 % actual and 100 %
  forecast. Alerts only; nothing is stopped automatically. Credit-covered
  usage is expected to count, so the 4-OCPU window will trip them.
- Reminder: a scheduled task in the Claude desktop app emails a switch-back
  checklist on **2026-11-10 10:00 IST** (runs when the app is open).

## Deploy an update

```bash
ssh -i ~/.ssh/oracle_agent ubuntu@129.225.126.59
cd /opt/agent/src && git pull --ff-only
sudo docker compose -f deploy/oracle/compose.yaml up -d --build agent
```

Two sessions have deployed to this VM; check `git log` on the VM against
`origin/main` before deploying, and don't deploy someone else's undeployed
commits without the owner's go-ahead.

Changing secrets: `scp` a new copy of `agent/.env.local` over
`/opt/agent/agent.env`, then `sudo docker compose -f deploy/oracle/compose.yaml
up -d --force-recreate agent`.

## Check it

```bash
curl https://ps-agent.duckdns.org/api/health
curl https://ps-agent.duckdns.org/api/voice/status       # available, active/cap, minutes used
sudo docker compose -f deploy/oracle/compose.yaml logs -f agent   # "registered worker", "llm canary"
sudo docker logs ps-agent-agent-1 2>&1 | grep turn-latency        # per-turn voice latency
sudo docker exec ps-agent-agent-1 python tests/dispatch_probe.py  # headless voice session (uses real minutes)
```

## Voice availability (5-call cap)

LiveKit Cloud's free Build plan allows **5 concurrent agent sessions** and
**1,000 agent minutes a month**. Past either, LiveKit doesn't refuse the
caller: the agent just never joins. `agent/voice_availability.py` turns
visitors away before that, with a reason the site explains:

| Reason | When | Back |
|---|---|---|
| `busy` | 5 live `voice-resume-*` rooms (plus tokens minted in the last 45 s) | minutes |
| `monthly_limit` | tracked agent minutes ≥ `VOICE_MONTHLY_MINUTES` (950) | `VOICE_QUOTA_RESET_DAY` (1st, UTC) |
| `daily_limit` | 300 tokens minted today (token server's global cap) | UTC midnight |
| `disabled` | `VOICE_DISABLED=true` in compose/env (kill switch) | when unset |
| `no_show` | browser-side: token granted but the agent didn't join in 20 s | retry |

The minutes counter only knows about sessions since it was deployed
(2026-10-22) and only for this VM. Compare with LiveKit Cloud's dashboard
(Usage) now and then; if LiveKit's billing cycle doesn't start on the 1st,
set `VOICE_QUOTA_RESET_DAY` to match.

**Waitlist.** Visitors can leave an email on the unavailable screen. Entries go
to `/app/state/voice_waitlist.jsonl`:

```bash
sudo docker exec ps-agent-agent-1 python voice_availability.py waitlist
sudo docker exec ps-agent-agent-1 python voice_availability.py usage
```

To have them emailed automatically ("AI me is back", sent once, every 5 min
check while voice is available), add to `/opt/agent/agent.env`:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<gmail address>
SMTP_PASSWORD=<Gmail app password, not the account password>
NOTIFY_FROM=<optional From:, defaults to SMTP_USER>
```

Without them, emails are only stored.

## One-time server setup (done)

- Docker CE + compose plugin from Docker's apt repo; container logs capped at
  3 × 10 MB.
- 2 GB swapfile (`vm.swappiness=10`). Timezone Asia/Kolkata.
- Oracle's Ubuntu image rejects all inbound traffic except SSH in iptables, even
  after the VCN security list allows it. 80/443 ACCEPT rules were inserted
  before the REJECT rule and saved with `netfilter-persistent` (survived the
  resize reboot).
- VCN default security list: ingress TCP 22, 80, 443 from `0.0.0.0/0`.
- Public IP is ephemeral: it survives reboots and resizes; if the VM is ever
  recreated, update the IP at duckdns.org.

## Resize

```bash
# from WSL (reboots the VM for ~1-2 min; A1 resizes can fail on capacity)
oci compute instance update --instance-id <instance OCID> \
  --shape-config '{"ocpus":2,"memoryInGBs":12}' --force --wait-for-state RUNNING
```

Always Free covers 2 OCPU / 12 GB in total across all A1 instances, and 200 GB
of block storage. Containers come back on their own (`restart: unless-stopped`).

## Capacity

With the 5-call cap, LiveKit is the limit, by design. Everything else was
checked against 5 concurrent calls: 4 OCPU / 24 GB VM (expected to be ample; a
5-call load test with tests/dispatch_probe.py is still to do), Cartesia Pro, Deepgram, OpenRouter (paid primaries, $10 key limit),
token-server rate limits (20 new sessions/min). To go beyond 5, upgrade LiveKit
(Ship, $50/mo, 20 sessions) and raise `VOICE_MAX_CONCURRENT`; or see
`readmes/livekit_selfhost_option.md` (local) for self-hosting LiveKit.
