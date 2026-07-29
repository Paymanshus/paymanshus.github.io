#!/usr/bin/env bash
# Start (or restart) the Next dev server detached; report status on stderr.
cd "$HOME/code/vibesite2k26" || exit 1
export PATH="$HOME/.nvm/versions/node/v22.22.0/bin:$PATH"
fuser -k 3000/tcp 2>/dev/null
sleep 2
: > /tmp/nextdev.log
setsid nohup npm run dev > /tmp/nextdev.log 2>&1 < /dev/null &
sleep 15
{
  echo "--- nextdev.log tail ---"
  tail -8 /tmp/nextdev.log
  curl -s -o /dev/null -w "site HTTP %{http_code}\n" -m 90 http://localhost:3000/experience/
} 1>&2
