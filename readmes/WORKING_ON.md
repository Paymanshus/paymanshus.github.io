# Active Surfaces

Pointer doc, not a spec — see `readmes/SPECs/TECH_SPEC.md` for full detail on
any of this.

## Voice agent backend (`agent/`)
- `agent/main.py` — agent entrypoint, session lifecycle, resume context
  injection via `on_user_turn_completed`, per-turn `turn-latency` logging,
  agent-minute recording
- `agent/token_server.py` — HTTP token + chat endpoints (`:8080`), CORS,
  rate limiting, `/api/voice/status` + `/api/voice/notify`
- `agent/voice_availability.py` — 5-call cap (LiveKit free plan), monthly
  minutes, kill switch, email waitlist
- `agent/llm_voice.py`, `agent/llm_health.py`, `agent/llm_models.py` — voice
  primary (DeepSeek v4.1 flash 1017) with hedge, canaries, warm-up; terminal
  primary Haiku 5.5; ladder as fallback
- `agent/observability.py` — Langfuse tracing (voice sessions + terminal
  chat)

## Frontend resume components
- `components/resume/VoiceResume.tsx` — LiveKitRoom wrapper,
  `useVoiceAssistant`, audio-reactive particle field, state machine
  (idle → checking → permission → connecting → connected, plus resting /
  unavailable / error); unavailable view with terminal hand-off and waitlist
- `components/resume/ChatResume.tsx` — terminal interface, command history,
  LLM backend with keyword-canned-answer fallback

## Deployment and ops
- Agent runs on an Oracle VM: `deploy/oracle/README.md` (runbook, budget,
  trial credit ends 2026-11-17, resize back to free tier by 2026-11-10).
- Perf baselines and benchmark scripts: `readmes/perf/` (local).
- GA4 is live (`G-5LV14G6B05`); view at analytics.google.com.

## In progress (branch `claude/changes`, worktree `~/code/vibesite2k26-llm`)
Not merged or deployed; deploys need the owner's OK.
- Voice persona in the owner's own words (minimal prompt, `agent/prompts.py`)
- Cached greetings (`agent/voice_greeting.py`)
- 5-minute cap per voice session
- Streamed terminal replies (`lib/chatStream.ts`, `ChatResume.tsx`)

## In progress (branch `fix/voice-ui-resume-html`, worktree `~/code/vibesite2k26-ui`)
Not committed, merged or deployed (2026-10-22). Frontend only.
- Voice call layout rebuilt as `SessionLayout` (in-flow rows, legible
  transcript, End call on touch), mic read as RMS level, inward ring cue
- Resume tab: HTML resume iframe + "Get the PDF"; new PDF at the same URL
- `ChatResume.tsx`: input attributes + "resume tab" copy only. Expect small
  conflicts with `claude/changes` in `ChatResume.tsx` / `VoiceResume.tsx`

## Later
- Turn-detection / endpointing tuning (~1.2 s median end-of-turn delay)
- Cached full-resume prefix instead of per-turn BM25 injection (the injection
  invalidates LiveKit's preemptive generation)
- STT region (Deepgram's endpoint is in the US, ~250 ms RTT from the VM)
- `SMTP_*` on the VM so waitlist emails go out automatically
- 5-call concurrent load test (`tests/dispatch_probe.py`)
- Resize the VM back to ≤ 2 OCPU / 12 GB by 2026-11-10 (trial credit ends
  2026-11-17)

## Task board
`readmes/SEOPLAN.md` is the current SEO/analytics/observability task board.
Phase A (entity graph) and Phase L (Langfuse) are **done**. Phases B
(analytics, OG images, crawlability), C (RSS/feeds, docs, meta polish), and D
(verification/reporting) are **in flight**. Phase E is owner-only.
