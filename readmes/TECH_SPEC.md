# Technical Specification

> Living source of truth for the shipped implementation. Update this file whenever architecture, runtime behavior, deployment, or content-loading behavior changes.

## Current Product Shape

This repo is a static-exported Next.js 15 portfolio intended for `paymanshus.github.io`.

Current public routes:

- `/`: fullscreen landing / hero
- `/experience/`: resume surface with `pdf`, `chat`, and `voice` modes
- `/thoughts/`: blog index
- `/thoughts/[slug]/`: static article pages generated from local Markdown

The home route is a no-scroll hero state. The experience and thoughts routes are normal scroll pages inside the shared site shell.

## Stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Framework | Next.js 15 App Router | Static export build target |
| Language | TypeScript | All first-party code is TS/TSX |
| Styling | Tailwind CSS v4 | Theme tokens live in `app/globals.css` |
| Animation | `motion` | Used for hero, nav, and section transitions |
| WebGL | `ogl` | Drives the landing `RippleGrid` |
| Content parsing | `gray-matter`, `remark`, `remark-gfm`, `remark-html` | Blog frontmatter + Markdown to HTML |
| Icons | `lucide-react` | Navigation and resume mode controls |

## Runtime Architecture

### Shell and routing

- `app/layout.tsx`
  Loads global fonts, metadata, and the outer width-constrained shell.
- `components/SiteShell.tsx`
  Wraps routes with the shared header and main content area.
- `components/SiteHeader.tsx`
  Top navigation with route-aware active state from `usePathname()`.

### Home route

- `app/page.tsx`
  Renders the landing page and structured data for the website/person.
- `components/HeroSection.tsx`
  Renders the two-line hero title, descriptor line, CTAs, and fixed background layers.
- `components/RippleGrid.tsx`
  Uses `ogl` to render a shader grid, then maps pointer movement into shader uniforms while the floor perspective is applied in CSS.

### Experience route

- `app/experience/page.tsx`
  Static route wrapper with SEO metadata and structured data.
- `components/ExperienceSection.tsx`
  Owns the resume mode toggle.
  Current default mode is `chat`.
  Mode panels are lazy-loaded with `next/dynamic` to reduce route JS.
- `components/resume/PdfResume.tsx`
  Loads the PDF iframe after mount to avoid competing with initial route transition.
- `components/resume/ChatResume.tsx`
  Mock terminal interface with boot sequence and local command map.
- `components/resume/VoiceResume.tsx`
  Scripted particle-field demo using `canvas`.

### Thoughts route

- `app/thoughts/page.tsx`
  Blog index route with collection-page structured data.
- `app/thoughts/[slug]/page.tsx`
  Static article route with `generateStaticParams()`, metadata per post, and `BlogPosting` structured data.
- `components/ThoughtsSection.tsx`
  Lists available posts from the local content directory.
- `components/ThoughtPost.tsx`
  Renders the article header, reading view, and progress bar.
- `components/ReadingProgressBar.tsx`
  Client-side top progress bar using `useScroll()`.

## Content System

Blog content lives in `content/blog/`.

Supported source files:

- `.md`
- `.mdx`

Current behavior in `lib/blog.ts`:

- Reads frontmatter with `gray-matter`
- Filters unpublished content via `published: false`
- Computes reading time locally
- Sorts posts by descending date
- Converts Markdown to HTML with `remark + gfm + html`

Frontmatter currently expected:

- `title`
- `excerpt`
- `date`
- optional `updatedAt`
- optional `tags`
- optional `published`

## Typography Implementation

Loaded in `app/layout.tsx`:

- `Space_Grotesk`
- `Instrument_Serif`
- `Lora`
- `JetBrains_Mono`

Current font roles:

- `Space Grotesk`: display/UI sans
- `Instrument Serif`: editorial accent serif, mostly for excerpts and selected supporting text
- `Lora`: long-form reading serif for article body copy
- `JetBrains Mono`: navigation, metadata, terminal, and system labels

## Theme Tokens

Theme tokens live in `app/globals.css`.

Current named tokens:

- `--color-bg`
- `--color-surface`
- `--color-border`
- `--color-text-primary`
- `--color-text-secondary`
- `--color-brand-red`
- `--color-glow`
- `--color-tron-glow`
- `--font-sans`
- `--font-serif`
- `--font-reading`
- `--font-mono`

## SEO and Discoverability

SEO is already wired for a static site.

Current pieces:

- `lib/site.ts`
  Central canonical URL, metadata helpers, display-date helpers, and identity fields
- Route metadata in `app/layout.tsx`, `app/experience/page.tsx`, `app/thoughts/page.tsx`, and `app/thoughts/[slug]/page.tsx`
- JSON-LD via `components/StructuredData.tsx`
- `app/robots.ts`
- `app/sitemap.ts`

Important current behavior:

- Canonicals are generated from `NEXT_PUBLIC_SITE_URL`
- Blog post routes emit article metadata and structured data
- Static sitemap includes home, experience, thoughts, and each blog post

## Static Export and GitHub Pages

### Current setup

This repo is already configured for GitHub Pages deployment.

Relevant files:

- `next.config.ts`
  Uses `output: 'export'`
  Uses `trailingSlash: true`
  Uses `images.unoptimized = true`
- `public/.nojekyll`
  Prevents GitHub Pages from treating `_next/` as Jekyll content
- `.github/workflows/deploy.yml`
  Builds and deploys the exported `out/` directory through GitHub Actions

Workflow behavior:

- Triggers on push to `main`
- Also supports manual dispatch
- Sets `NEXT_PUBLIC_SITE_URL=https://paymanshus.github.io`
- Runs `npm ci`
- Runs `npm run build`
- Uploads `./out`
- Deploys via `actions/deploy-pages`

GitHub Pages should be configured to use:

- Source: GitHub Actions

### Repo replacement plan

For migration into the existing `paymanshus.github.io` repository:

1. Clone the existing GitHub Pages repo separately.
2. Keep its git history intact for rollback.
3. Replace the old site source with this Next.js app source.
4. Preserve `.github/workflows/deploy.yml`, `public/.nojekyll`, `content/blog`, and the PDF asset.
5. Push to `main` so GitHub Actions rebuilds and deploys the static export.

This keeps rollback simple because the old history remains in the same repository.

## Future Backend Plan

Planned architecture after the static frontend is stable:

- Frontend remains this static GitHub Pages deployment.
- Backend moves to a separate FastAPI repository.
- Backend deploy target is Railway.
- Chat and voice modes can progressively switch from local mocks to API-backed behavior.

Recommended integration rules:

- Keep the blog fully static and independent of the backend.
- Use environment-based API origin configuration in the frontend.
- Restrict backend CORS to the Pages domain and local dev origin.
- Treat PDF/blog/SEO generation as build-time concerns, not backend concerns.

## Public vs Repo-Only Content

Publicly shipped:

- `app/`
- `components/`
- `content/blog/`
- `public/`
- generated `out/`

Repo-only documentation:

- `readmes/`

That means the spec files in `readmes/` do not get published to GitHub Pages unless they are copied into public-facing routes explicitly.

## Verification

Minimum checks after UI or content-system changes:

- `npm run lint`
- `npm run build`

For deployment changes, also verify:

- `out/` is produced successfully
- blog routes are emitted
- `sitemap.xml` and `robots.txt` are generated

