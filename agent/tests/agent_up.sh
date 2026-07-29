#!/usr/bin/env bash
# (Re)start the voice agent detached; report status on stderr.
cd "$HOME/code/vibesite2k26/agent" || exit 1
pkill -f "python [m]ain.py" 2>/dev/null
fuser -k 8080/tcp 2>/dev/null
sleep 3
: > /tmp/voice_agent.log
setsid nohup .venv/bin/python main.py start > /tmp/voice_agent.log 2>&1 < /dev/null &
sleep 20
{
  echo "--- worker registered count ---"
  grep -a -c "registered worker" /tmp/voice_agent.log
  echo "--- errors ---"
  grep -a -iE "error|traceback" /tmp/voice_agent.log | head -5
  echo "--- health ---"
  curl -s -m 5 http://localhost:8080/api/health; echo
  echo "--- preflight headers ---"
  curl -s -m 5 -X OPTIONS -H "Origin: https://paymanshus.github.io" -D - -o /dev/null http://localhost:8080/api/chat | grep -i "access-control"
} 1>&2
