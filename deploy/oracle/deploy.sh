#!/usr/bin/env bash
# Deploy the voice agent on the Oracle VM to a given commit of main.
#
#   bash deploy/oracle/deploy.sh [<sha>|main]     # on the VM, by hand
#   (GitHub Actions runs it through /opt/agent/ci-entry.sh over SSH)
#
# Steps: lock -> fast-forward /opt/agent/src to <sha> -> wait for live voice
# calls to finish (up to WAIT_FOR_CALLS_S) -> keep the current image as
# ps-agent:previous -> docker compose up -d --build -> health check (HTTP +
# LiveKit worker registered) -> on failure, roll back to the previous image and
# commit. Exits non-zero on failure so CI shows red.
set -euo pipefail

# Re-exec from a temp copy: git rewrites this file during the fast-forward,
# and bash reads scripts incrementally.
if [[ -z "${DEPLOY_REEXEC:-}" ]]; then
  tmp="$(mktemp /tmp/agent-deploy.XXXXXX)"
  cp "$0" "$tmp"
  DEPLOY_REEXEC=1 exec bash "$tmp" "$@"
fi

SRC=/opt/agent/src
COMPOSE=(docker compose -f "$SRC/deploy/oracle/compose.yaml")
PUBLIC_URL="${PUBLIC_URL:-https://ps-agent.duckdns.org}"
WAIT_FOR_CALLS_S="${WAIT_FOR_CALLS_S:-600}"
HEALTH_TIMEOUT_S="${HEALTH_TIMEOUT_S:-180}"
TARGET="${1:-main}"

log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }

exec 9>/tmp/agent-deploy.lock
flock -w 900 9 || { log "another deploy is still running"; exit 1; }

docker info >/dev/null 2>&1 || COMPOSE=(sudo "${COMPOSE[@]}")
DOCKER=(docker); docker info >/dev/null 2>&1 || DOCKER=(sudo docker)

cd "$SRC"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  log "refusing: $SRC has local changes"; git status --short; exit 1
fi
git fetch -q origin main
[[ "$TARGET" == "main" ]] && TARGET="$(git rev-parse origin/main)"
if ! git merge-base --is-ancestor "$TARGET" origin/main; then
  log "refusing: $TARGET is not on origin/main"; exit 1
fi
PREV="$(git rev-parse HEAD)"
if [[ "$PREV" == "$(git rev-parse "$TARGET")" ]]; then
  log "already at $(git log --oneline -1); rebuilding anyway"
fi
git merge -q --ff-only "$TARGET"
log "code: $(git log --oneline -1)"

# Let live calls finish: a rebuild restarts the agent, and compose's 60 s
# stop_grace_period only drains, it doesn't wait for a 5-minute call.
waited=0
while :; do
  active="$(curl -fsS -m 5 "$PUBLIC_URL/api/voice/status" 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("active", 0))' 2>/dev/null || echo 0)"
  [[ "$active" == "0" ]] && break
  if (( waited >= WAIT_FOR_CALLS_S )); then
    log "still $active call(s) after ${waited}s; deploying anyway"; break
  fi
  log "$active live call(s), waiting..."; sleep 15; waited=$((waited + 15))
done

"${DOCKER[@]}" image inspect ps-agent:latest >/dev/null 2>&1 \
  && "${DOCKER[@]}" tag ps-agent:latest ps-agent:previous

started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "building and restarting"
"${COMPOSE[@]}" up -d --build 2>&1 | tail -n 5

# Registration is checked from the container's own start time: if nothing
# changed, compose keeps the running container and its registration predates
# this deploy.
since="$("${DOCKER[@]}" inspect -f '{{.State.StartedAt}}' ps-agent-agent-1 2>/dev/null || echo "$started")"
healthy() {
  curl -fsS -m 5 "$PUBLIC_URL/api/health" >/dev/null 2>&1 &&
    "${DOCKER[@]}" logs --since "$since" ps-agent-agent-1 2>&1 | grep -q "registered worker"
}
deadline=$((SECONDS + HEALTH_TIMEOUT_S))
until healthy; do
  if (( SECONDS >= deadline )); then
    log "UNHEALTHY after ${HEALTH_TIMEOUT_S}s; rolling back to $(git log --oneline -1 "$PREV")"
    "${DOCKER[@]}" logs --since "$started" ps-agent-agent-1 2>&1 | grep -v '^{' | tail -n 20 || true
    git reset -q --hard "$PREV"
    if "${DOCKER[@]}" image inspect ps-agent:previous >/dev/null 2>&1; then
      "${DOCKER[@]}" tag ps-agent:previous ps-agent:latest
      "${COMPOSE[@]}" up -d --no-build 2>&1 | tail -n 3
    fi
    exit 1
  fi
  sleep 5
done
log "healthy: /api/health ok, worker registered. deployed $(git log --oneline -1)"
