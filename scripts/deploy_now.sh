#!/usr/bin/env bash
# One-shot deploy wrapper: node PATH + commit message + no-push audit mode.
set -euo pipefail
export PATH="$HOME/.nvm/versions/node/v22.22.0/bin:$PATH"
cd "$HOME/code/vibesite2k26"

MSG="$(cat <<'EOF'
Ship live voice + terminal LLM interfaces

- Voice mode: real LiveKit WebRTC session (token server w/ agent dispatch),
  amplitude-reactive particle field (red=user, green=agent, amber=thinking),
  live transcript, mic-permission persistence, degradation banners
- Terminal: Gemini-backed free-form Q&A with BM25 resume grounding,
  rate-limit handling, offline keyword fallback, command history
- Remove private planning docs (readmes/) from public repo; tighten
  deploy excludes and .gitignore so they stay local-only

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"

bash scripts/deploy-pages.sh -m "$MSG" --no-push
