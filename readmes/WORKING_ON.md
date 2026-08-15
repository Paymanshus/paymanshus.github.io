# Active Surfaces

Pointer doc, not a spec — see `readmes/SPECs/TECH_SPEC.md` for full detail on
any of this.

## Voice agent backend (`agent/`)
- `agent/main.py` — agent entrypoint, session lifecycle, resume context
  injection via `on_user_turn_completed`
- `agent/token_server.py` — HTTP token + chat endpoints (`:8080`), CORS,
  rate limiting
- `agent/observability.py` — Langfuse tracing (voice sessions + terminal
  chat)

## Frontend resume components
- `components/resume/VoiceResume.tsx` — LiveKitRoom wrapper,
  `useVoiceAssistant`, audio-reactive particle field, state machine
  (idle → permission → connecting → connected → error)
- `components/resume/ChatResume.tsx` — terminal interface, command history,
  LLM backend with keyword-canned-answer fallback

## In flight: analytics layer
Being added by another agent under `lib/analytics.ts` +
`components/analytics/` (GA4 page views, section-time tracking, resume-mode
and agent events). Not present yet as of this writing — see Phase B in
`readmes/SEOPLAN.md` for the spec.

## Task board
`readmes/SEOPLAN.md` is the current SEO/analytics/observability task board.
Phase A (entity graph) and Phase L (Langfuse) are **done**. Phases B
(analytics, OG images, crawlability), C (RSS/feeds, docs, meta polish), and D
(verification/reporting) are **in flight**. Phase E is owner-only.
