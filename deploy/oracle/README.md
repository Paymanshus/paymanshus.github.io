# Voice agent on Oracle Always Free

The agent (`agent/main.py start`: token/chat HTTP server plus LiveKit worker)
runs on one Oracle Cloud ARM VM behind Caddy, which handles HTTPS.

| | |
|---|---|
| Public URL | `https://ps-agent.duckdns.org` (DuckDNS → VM public IP) |
| VM | `VM.Standard.A1.Flex`, 1 OCPU / 6 GB, Ubuntu 24.04 aarch64, `ap-hyderabad-1` |
| SSH | `ssh -i ~/.ssh/oracle_agent ubuntu@<public-ip>` (key only in WSL) |
| Code on VM | `/opt/agent/src` (git clone of this repo) |
| Secrets on VM | `/opt/agent/agent.env` (copy of `agent/.env.local`, mode 600, never committed) |

## Deploy an update

```bash
ssh -i ~/.ssh/oracle_agent ubuntu@<public-ip>
cd /opt/agent/src && git pull --ff-only
sudo docker compose -f deploy/oracle/compose.yaml up -d --build
```

Changing secrets: edit `/opt/agent/agent.env` (or `scp` a new copy of
`agent/.env.local` over it), then run the `up -d` line again.

## Check it

```bash
curl https://ps-agent.duckdns.org/api/health
sudo docker compose -f deploy/oracle/compose.yaml logs -f agent   # look for "registered worker"
sudo docker compose -f deploy/oracle/compose.yaml ps
```

## One-time server setup (already done)

- Docker CE + compose plugin from Docker's apt repo; container logs capped at
  3 × 10 MB.
- 2 GB swapfile (`vm.swappiness=10`).
- Oracle's Ubuntu image rejects all inbound traffic except SSH in iptables, even
  after the VCN security list allows it. 80/443 ACCEPT rules were inserted
  before the REJECT rule and saved with `netfilter-persistent`.
- VCN default security list: ingress TCP 22, 80, 443 from `0.0.0.0/0`.
- Public IP is ephemeral. It survives reboots; if the VM is ever recreated,
  update the IP at duckdns.org.

## Capacity

About 2–4 concurrent voice calls on 1 OCPU (CPU-bound: VAD + turn detector).
LiveKit Cloud's free plan (~5 concurrent, 1,000 agent minutes/month) and the
rate limits in `agent/token_server.py` cap usage before the box does. Resize to
2 OCPU / 12 GB (still Always Free) from the OCI console if needed; it reboots
the VM.
