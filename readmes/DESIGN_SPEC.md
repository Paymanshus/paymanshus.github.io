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
- Use red to indicate system energy, active state, prompts, and progress.
- Let typography carry hierarchy; avoid decorative chrome when structure can do the job.
- Preserve a quiet, high-contrast reading experience on blog pages.
- Motion should feel deliberate and fast, never floaty.

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

## Typography

Current fonts are loaded in `app/layout.tsx`.

| Role | Font | Usage |
| --- | --- | --- |
| Display / UI Sans | Space Grotesk | Hero, headings, UI labels |
| Editorial Accent Serif | Instrument Serif | Thoughts excerpts and selective supporting text |
| Reading Serif | Lora | Thought post body copy |
| Monospace | JetBrains Mono | Nav, metadata, terminal, system labels |

### Typography rules

- `Instrument Serif` is not the long-form reading face anymore.
  It works as an editorial accent, but it is too stylized for dense body copy at reading sizes.
- Thought post body copy should stay on the reading serif with generous line-height and moderate measure.
- Mono text should remain compact and uppercase only where it improves system tone.
- The hero name should stay heavy, compressed, and sharply tracked.

## Global Layout

- The site uses a shared centered shell with a `max-w-7xl` outer bound and route-specific inner measures.
- Home is intentionally fullscreen and non-scrolling.
- Experience and thoughts pages scroll within the same shell.
- The top navigation is always present and anchors the site identity.

## Navigation

Current shipped behavior:

- Left: `PS`
- Right: `hi`, `experience`, `thoughts`
- Active route: thin red underline with motion layout transition

Nav should stay light and structural. It is not meant to become a thick masthead.

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
- Red outlined "Open PDF" action in the top-right
- Loading is deferred slightly so route transition remains smooth

### Chat mode

- Black terminal surface
- Red prompt
- Boot sequence on first load
- Static command map
- Blinking red cursor follows typed text

The current chat is intentionally mocked, but it should feel plausible and polished rather than toy-like.

### Voice mode

- Black canvas field with dense particles
- Three implied states: idle, user, system
- Scripted transcript beneath the field

The voice panel is still a demo, but visually it should feel like a system surface, not a novelty animation.

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

- Route-local transitions may fade, but should remain brief.
- Nav indicator motion should stay springy and thin.
- Continuous animation is acceptable only for:
  - hero grid
  - terminal cursor
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

