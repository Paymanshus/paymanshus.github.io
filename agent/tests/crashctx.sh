#!/usr/bin/env bash
# Print the log lines immediately before the job-process crash.
LOG=/tmp/voice_agent.log
L=$(grep -a -n "exited with non-zero" "$LOG" | head -1 | cut -d: -f1)
if [ -z "$L" ]; then echo "no crash line found"; exit 0; fi
START=$((L - 25))
[ "$START" -lt 1 ] && START=1
sed -n "${START},${L}p" "$LOG" | cut -c1-200
