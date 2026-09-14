# Design Specification

> Living source of truth for the shipped visual system. Update this file whenever the public UI meaningfully changes.

## Current Design Frame

The site is an austere dark portfolio with red used as a precision signal, not a wash. It is route-based rather than tabbed, but the three primary sections remain the same:

- `hi`
- `experience`
- `thoughts`

The visual mood is still "Austere Neon", but the implementation has settled into something calmer and more editorial than the early stitch explorations.

## Core Principles

- Keep the layout left-governed rather than centered by default.
- Use red to indicate system energy, active state, prompts, and progress. When in doubt about whether to add red somewhere: don't.
- Let typography carry hierarchy; avoid decorative chrome when structure can do the job.
- Preserve a quiet, high-contrast reading experience on blog pages.
- Motion should feel deliberate and fast, never floaty.
- **Dark mode is the primary experience. Light mode is a first-class alternate, not an afterthought** — it is not yet implemented but should be designed toward, not against.

## Color System

Current values come from `app/globals.css`.

| Role | Value | Usage |
| --- | --- | --- |
| Background | `#050505` | Global page background |
| Surface | `#0a0a0a` | Panels, mode containers |
| Border | `#1a1a1a` | Frames, separators |
| Text Primary | `#f5f5f5` | Main foreground |
| Text Secondary | `#8a8a8a` | Muted copy and metadata |
| Brand Red | `#ff2a2a` | Active state, prompts, progress, grid |
| Glow | `rgba(255, 42, 42, 0.15)` | Soft halo only |
| Tron Glow | `rgba(255, 42, 42, 0.3)` | Stronger accent glow only |

### Color rules

- The interface should still read as black/charcoal first, red second.
- Borders and spacing should define surfaces more often than background fills.
- Red should stay sparse enough that the progress bar, prompt, nav indicator, and grid feel intentional.

### Blog figures

Blog posts carry diagrams as inline SVG inside a `.post-figure` panel — bordered
in `#1a1a1a` on `#0a0a0a` surface, with a monospace caption below a top divider.
This reuses the site's frame language rather than introducing a chart aesthetic.

Within a figure, red marks the single quantity the figure exists to show and
nothing else; everything structural is `#242424`/`#2e2e2e` with `#8a8a8a` labels.
That keeps the same "red second" discipline as the rest of the site.

Full conventions, tokens and pipeline constraints: the `blog-figures` skill, or
`readmes/SPECs/BLOG_VISUALS.md` if the skill isn't loaded. Tables, blockquotes
and figures are styled in `app/globals.css` under the blog-post section.

## Typography

Current fonts are loaded in `app/layout.tsx`.

| Role | Font | Usage |
| --- | --- | --- |
| Display / UI Sans | Space Grotesk | Hero, headings, UI labels |
| Editorial Accent Serif | Instrument Serif | Thoughts excerpts and selective supporting text |
| Reading Serif | Lora | Thought post body copy |
| Monospace | JetBrains Mono | Nav, metadata, terminal, system labels |

### Forbidden fonts

Do not use: Inter, Plus Jakarta Sans, Outfit, DM Sans, Manrope, Figtree, Sora, Poppins, Nunito, General Sans, Cabinet Grotesk, or any system default. These are explicitly off the table regardless of context.

### Typography rules

- `Instrument Serif` is not the long-form reading face anymore.
  It works as an editorial accent, but it is too stylized for dense body copy at reading sizes.
- Thought post body copy should stay on the reading serif with generous line-height and moderate measure.
- Mono text should remain compact and uppercase only where it improves system tone.
- The hero name should stay heavy, compressed, and sharply tracked.

## Global Layout

- The site uses a shared centered shell with a `max-w-7xl` outer bound (1280px) and route-specific inner measures.
- Layout is 12-column grid with generous gutters.
- All spacing is in multiples of 8px.
- Default alignment is left. Centering is reserved for singular moments of emphasis.
- Hierarchy is established through scale and position, not background color or decoration.
- Home is intentionally fullscreen and non-scrolling.
- Experience and thoughts pages scroll within the same shell.
- The top navigation is always present and anchors the site identity.

## Navigation

Current shipped behavior:

- Left: `PS`
- Right: `hi`, `experience`, `thoughts`
- Active route: thin red underline with motion layout transition

Nav should stay light and structural. It is not meant to become a thick masthead.

## Footer

`components/SiteFooter.tsx`, rendered by `SiteShell` on every route **except home**
— the home hero is a fixed-height, non-scrolling composition (`h-screen
overflow-hidden`) and a footer there would be clipped.

Composition: a hairline `border-t`, then two columns — identity on the left (name
in mono caps, one line of role copy, email), and two link stacks on the right
(site routes + RSS, and external profiles). All links are mono, uppercase, wide
tracking (`0.18em`), `text-text-secondary` resting, `brand-red` on hover, matching
the nav's restraint. No logos, no social icons, no background fill.

The external links carry `rel="me"` — load-bearing for SEO, not decoration: they
are what ties the GitHub/LinkedIn/Hugging Face profiles to this domain as one
identity. Keep them in sync with `sameAs` in `personJsonLd()`.

## Home / "Hi"

### Current composition

- Two-line hero name:
  `PAYMANSHU`
  `SHARMA`
- Descriptor line:
  `ML Engineer / Product Engineer`
- Two CTAs:
  `Initialize Experience`
  `Read Thoughts`

### Background system

- The hero uses a fixed layered background.
- `RippleGrid` provides the animated technical floor.
- CSS perspective turns that grid into a horizon plane.
- A neutral dark vignette sits above the grid but remains non-interactive.

### Motion

- Character stagger on initial hero load
- Subtle descriptor and CTA reveal
- Continuous ripple animation in the floor
- Pointer-reactive grid behavior

The home route should feel atmospheric but still disciplined enough that the typography remains dominant.

## Experience

### Current structure

- Pill toggle for `pdf`, `chat`, `voice`
- Default mode on route entry: `chat`
- Shared framed panel below the toggle

### PDF mode

- Dark embedded PDF viewer
- Red outlined "Open PDF" action in the top-right — opens in a new tab as a PDF-only view, not a browser download
- The PDF must be accessible at a standalone URL (e.g. `paymanshus.github.io/assets/Paymanshu_Sharma_Resume.pdf`) so it can be shared directly with recruiters without exposing the full site
- Loading is deferred by one animation frame so route transition remains smooth
- The iframe is **never** `loading="lazy"`: the viewer sits below the fold, so a lazy iframe stayed unloaded and the tab read as a blank panel until the visitor happened to scroll
- A fallback layer sits permanently behind the iframe — "Inline preview unavailable" plus a red-outlined "Open the resume PDF" action. Mobile Safari and Chrome commonly refuse to render PDFs inline, leaving the frame empty; this guarantees a working route to the resume on every device

### Chat mode

- Black terminal surface, always dark regardless of any future light-mode toggle
- Monospace throughout — no sans or serif type anywhere in this surface
- Red `>` prompt with glow
- Boot sequence on first load
- Static command map for fast-path commands (`help`, `about`, `skills`, …)
- Free-form questions go to the live LLM backend (`POST /api/chat`, Gemini with BM25 resume context); keyword-matched offline fallback when unreachable or rate-limited
- When no agent is configured for the build, the terminal makes **no request at all** and answers from the cached keyword map. Header reads `[LOCAL MODE] Answering from cached resume data` rather than `[OFFLINE MODE] LLM unavailable` — nothing is broken, so nothing should claim to be
- The `help` free-form line matches what the build can deliver: it promises an LLM answer only when an agent is actually configured
- Keyword patterns use open-ended stems (`\bskill`, not `\bskill\b`) so plurals match. A trailing `\b` silently broke "what are your skills" — the single most likely question, and one the `help` text invites
- `PROCESSING QUERY` pulse line while awaiting the LLM
- Blinking red cursor follows typed text
- Up/Down arrows recall previously submitted commands (shell-style history buffer; consecutive duplicates skipped)
- Plain text responses only — no GUI elements, no cards, no markdown rendering, no icons

The chat should feel like Claude Code, Gemini CLI, or a modern TUI program — not a chatbot widget.

### Voice mode

Now a live LiveKit WebRTC session, no longer a scripted demo.

- Connection flow: idle view (`> START VOICE`) → themed mic-permission modal (with animated arrow pointing at the browser prompt) → connecting → live session
- Pre-connection idle view now renders the same particle field behind the START VOICE button in its quiet `idle` state (gentle drift, low-intensity red center), with a single pulsing red dot at the core — "a still surface just before something breaks through it". The field is `pointer-events-none` so it never intercepts the button; amplitude readers are inert (idle drift samples no audio)
- Black canvas field with dense structured particles (squares, crosses, pixels — not organic blobs)
- Audio-reactive states, driven by real amplitude from Web Audio `AnalyserNode`:
  - **User speaking (recording)**: inward contraction, **red** accent at center — red = recording, on-theme with the site
  - **Agent speaking (responding)**: outward expansion proportional to TTS amplitude, **green** accent at center
  - **Thinking**: slow inward spiral, dim amber accent
  - **Idle**: gentle drift, low-intensity red center
- Accent color crossfades gradually between states (no hard color snaps)
- Top-left session status dot + label (listening = red, speaking = green, thinking = amber). LLM fallback and TTS degraded add a 6px amber square next to that label (`title`/`aria-label` = "fallback model" or "fallback voice") — no full-width banner on greeting-turn failover
- While thinking: a rotating quirky-but-not-cartoony verb ("Rummaging…",
  "Cross-referencing…", "Jogging my memory…") pulses under the field —
  Claude Code register, one word picked per thinking episode
- Live rolling monospace transcript below the field: agent lines with red `>` prefix, user lines quieter with `~` prefix. Consecutive STT chunks from one speaker merge into a single flowing line — never bullet-like fragments; a new line starts only on turn change
- TTS down is the one remaining banner: "voice output unavailable — provider limits hit. try the chat tab"
- The mic-permission modal appears only on the first ever connect on a device; afterwards Start Voice connects directly
- `[ ESC TO DISCONNECT ]` anchored at the bottom — both the key and the label work

## Thoughts Index

Current list design:

- Large section title
- Serif italic intro sentence
- Post rows with date, title, excerpt, and reading time
- Hover translates the text block slightly and shifts title color toward red

The list should read as a writing archive, not as card-heavy marketing content.

## Thought Reading View

### Current reading model

- Narrow editorial column
- Fixed red `2px` progress bar at the top
- Route-based article pages
- Large title, restrained metadata, italic excerpt
- Long-form body set in `Lora`

### Reading rules

- Body measure should stay around a comfortable book/article width, not full-shell width.
- Body serif should prioritize legibility over stylization.
- Paragraph rhythm should be open but not so loose that text loses cohesion.
- Headings can remain sans-serif for contrast.
- Blockquotes should feel quieter and more literary than the terminal surfaces.

### Why the current body style changed

The earlier reading view relied too much on `Instrument Serif`, which behaves more like a display/editorial face than a durable reading face. The current reading view keeps the same dark editorial mood but uses a more legible book serif for article text, closer to the better stitch reading references.

## Motion Guidelines

- **All animations must run at 60fps or be removed. No exceptions.**
- Route-local transitions may fade + translate, but should remain brief.
- Nav indicator motion should stay springy and thin.
- Continuous animation is acceptable only for:
  - hero grid
  - terminal cursor (blink only)
  - voice particle field
- If a motion effect adds latency or makes the interface feel sticky, remove or defer it.

## Public Information Architecture

Public IA currently consists of:

- home hero
- experience route
- thoughts index
- thought detail routes
- downloadable/openable PDF asset

Repo-only docs under `readmes/` are not part of the public IA and should not influence visible page chrome or navigation.

## Deployment-Sensitive Design Constraints

Because the site is statically exported for GitHub Pages:

- Every public route must be build-time safe.
- Thought posts must remain renderable from local content files.
- Public assets must live in `public/`.
- Design decisions should avoid depending on a live backend for baseline rendering.

The future FastAPI backend should enhance chat/voice behavior without changing the core visual system or the static readability of the site.

