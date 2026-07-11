#!/usr/bin/env bash
# Restart the agent, dispatch a headless session, report whether it crashed.
cd "$(dirname "$0")/.." || exit 1
# Kill any previous agent workers ([m] trick avoids matching this script itself)
pkill -f "python [m]ain.py" 2>/dev/null
pkill -f "tests/[m]ain_baseline.py" 2>/dev/null
fuser -k 8080/tcp 2>/dev/null
sleep 3
: > /tmp/voice_agent.log
ENTRY="${1:-main.py}"
export PYTHONFAULTHANDLER=1
setsid nohup .venv/bin/python "$ENTRY" start > /tmp/voice_agent.log 2>&1 < /dev/null &
sleep 25
if ! grep -aq "registered worker" /tmp/voice_agent.log; then
  echo "WORKER FAILED TO START"; tail -5 /tmp/voice_agent.log; exit 1
fi
.venv/bin/python tests/dispatch_probe.py
sleep 18
CRASHES=$(grep -a -cE "exited with non-zero" /tmp/voice_agent.log)
STARTED=$(grep -a -cE "session started successfully" /tmp/voice_agent.log)
echo "RESULT: crashes=$CRASHES session_started=$STARTED"
