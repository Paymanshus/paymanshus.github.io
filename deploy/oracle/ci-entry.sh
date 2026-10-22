#!/usr/bin/env bash
# The only thing the GitHub Actions deploy key can run on the VM.
#
# Installed once as /opt/agent/ci-entry.sh and pinned in ~/.ssh/authorized_keys:
#   command="/opt/agent/ci-entry.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA... agent-ci-deploy
# so a leaked key can trigger a deploy of a commit already on main, and nothing
# else. It runs deploy.sh as it exists at that commit, so changes to deploy.sh
# ship with the code (no reinstall needed; only this wrapper is fixed).
set -euo pipefail

read -r action sha extra <<<"${SSH_ORIGINAL_COMMAND:-}"
if [[ "$action" != "deploy" || ! "$sha" =~ ^[0-9a-f]{40}$ || -n "${extra:-}" ]]; then
  echo "usage: deploy <40-char sha>" >&2
  exit 2
fi

cd /opt/agent/src
git fetch -q origin main
git merge-base --is-ancestor "$sha" origin/main || { echo "$sha is not on main" >&2; exit 1; }
script="$(mktemp /tmp/agent-deploy.XXXXXX)"
git show "$sha:deploy/oracle/deploy.sh" >"$script"
DEPLOY_REEXEC=1 exec bash "$script" "$sha"
