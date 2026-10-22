# Deploying

Two things deploy from `main`:

| Part | Where | How |
|---|---|---|
| Site (Next.js static export) | GitHub Pages | `.github/workflows/deploy.yml`, automatic on every push to `main` |
| Voice/terminal agent | Oracle VM, `https://ps-agent.duckdns.org` | `.github/workflows/agent.yml`, automatic on pushes to `main` that touch the agent; or manually |

**Pushing to `main` is deploying.** Work on a branch; merging or pushing to `main`
needs the owner's OK.

## Agent: automatic (CI/CD)

On a push to `main` touching `agent/**`, `content/resumedump.md`,
`deploy/oracle/**` or the workflow itself:

1. **test**: `pytest agent/tests` on Python 3.12. If it fails, nothing deploys.
2. **deploy**: SSH to the VM with a deploy key that can only run
   `/opt/agent/ci-entry.sh deploy <sha>`. That runs `deploy/oracle/deploy.sh` as it
   exists at that commit:
   - fast-forwards `/opt/agent/src` to the commit (refuses local changes or a
     commit that isn't on `main`);
   - waits for live voice calls to end (up to 10 min, via `/api/voice/status`);
   - keeps the current image as `ps-agent:previous`, then `docker compose up -d --build`;
   - checks `/api/health` and that the LiveKit worker registered (3 min);
   - on failure, rolls back to the previous image and commit, and the run goes red.

One deploy at a time (`concurrency: agent-deploy`). Redeploy without a code change:
**Actions → Deploy voice agent → Run workflow** on `main`.

Watch it: Actions tab, or `gh run watch -R Paymanshus/paymanshus.github.io`.

### Secrets (already set, 2026-10-22)

| Secret | Value |
|---|---|
| `AGENT_DEPLOY_SSH_KEY` | private key of the `agent-ci-deploy` ed25519 key |
| `AGENT_DEPLOY_HOST` | VM public IP (`129.225.126.59`) |
| `AGENT_DEPLOY_KNOWN_HOSTS` | the VM's host-key lines (`ssh-keygen -F <ip>`) |

On the VM, `~/.ssh/authorized_keys` pins that key to the wrapper:

```
command="/opt/agent/ci-entry.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA... agent-ci-deploy
```

A leaked key can only redeploy a commit that's already on `main`.

### Rotate the deploy key, or the VM IP changes

```bash
ssh-keygen -t ed25519 -N "" -C agent-ci-deploy -f ~/.ssh/agent_ci_deploy   # new key
# replace the agent-ci-deploy line in the VM's ~/.ssh/authorized_keys with the new .pub (same command= prefix)
gh secret set AGENT_DEPLOY_SSH_KEY -R Paymanshus/paymanshus.github.io < ~/.ssh/agent_ci_deploy
gh secret set AGENT_DEPLOY_HOST -R Paymanshus/paymanshus.github.io --body "<new ip>"   # IP change only
ssh-keygen -F <ip> | grep -v '^#' | gh secret set AGENT_DEPLOY_KNOWN_HOSTS -R Paymanshus/paymanshus.github.io
```

`ci-entry.sh` is the one file installed by hand. If it ever changes:
`sudo install -m 755 -o ubuntu -g ubuntu deploy/oracle/ci-entry.sh /opt/agent/ci-entry.sh` on the VM.
`deploy.sh` changes ship with the code; nothing to reinstall.

## Agent: manual

Still works, from WSL (admin key `~/.ssh/oracle_agent`):

```bash
ssh -i ~/.ssh/oracle_agent ubuntu@129.225.126.59
bash /opt/agent/src/deploy/oracle/deploy.sh main     # same steps as CI, without the tests
```

or the bare runbook (`deploy/oracle/README.md`):

```bash
cd /opt/agent/src && git pull --ff-only
sudo docker compose -f deploy/oracle/compose.yaml up -d --build
```

Check after either:

```bash
curl https://ps-agent.duckdns.org/api/health
sudo docker logs --since 5m ps-agent-agent-1 2>&1 | grep -E "registered worker|ERROR|Traceback"
```

Roll back by hand: `git reset --hard <good sha>` in `/opt/agent/src`, then the
`up -d --build` line (or `docker tag ps-agent:previous ps-agent:latest && docker
compose ... up -d --no-build` to reuse the last image).

## Secrets for the agent itself

`/opt/agent/agent.env` on the VM (copy of `agent/.env.local`, never committed).
After editing it, run the `up -d` line again (or Run workflow).
