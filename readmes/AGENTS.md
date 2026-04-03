# Repository Guidelines

## Project Structure & Module Organization
This repository is a Next.js 16 + TypeScript portfolio app.

- `app/`: App Router entrypoints (`page.tsx`, `layout.tsx`) and route segments like `blog/[slug]` and `resume/`.
- `components/`: Reusable UI components (`Nav.tsx`, `Terminal.tsx`, `ThemeProvider.tsx`).
- `lib/`: Content/data helpers (for example `posts.ts`, `resumeData.ts`).
- `public/`: Static files and downloadable assets (`public/assets/Paymanshu_Sharma_Resume.pdf`).
- `stitch_assets/`: Design reference exports; not primary runtime code.
- Root docs (`DESIGN_SPEC.md`, `TECH_SPEC.md`, `implementation_plan.md`) describe product and implementation intent.

## Build, Test, and Development Commands
- `npm install`: Install dependencies.
- `npm run dev`: Start local dev server with Turbopack (default `http://localhost:3000`).
- `npm run build`: Create a production build. Note: first-time builds need network access for `next/font/google`.
- `npm run start`: Run the production build locally.
- `npm run lint`: Runs ESLint v9 (`eslint`). This currently requires an `eslint.config.(js|mjs|cjs)` file to succeed.

## Coding Style & Naming Conventions
- Use TypeScript/TSX with strict typing (`tsconfig.json` has `"strict": true`).
- Prefer the `@/*` import alias for internal modules (example: `@/components/Nav`).
- Match existing style: 2-space indentation, semicolons, and single quotes in TS/TSX files.
- Component files use PascalCase (`ResumePreview.tsx`); helpers in `lib/` use descriptive camelCase names.
- Route folder names stay lowercase; dynamic routes use bracket syntax (`app/blog/[slug]`).

## Testing Guidelines
- No automated test framework is configured yet.
- Minimum pre-PR checks are manual route smoke tests for `/`, `/blog`, `/blog/[slug]`, and `/resume`.
- Run `npm run build` before requesting review.
- If adding tests, colocate as `*.test.ts` or `*.test.tsx` near the source under test.

## Commit & Pull Request Guidelines
- Commit history is currently minimal; use concise, imperative commit subjects (example: `Add resume data parser`).
- Keep commits focused and avoid mixing unrelated refactors with feature changes.
- PRs should include:
  - clear summary of what changed and why
  - screenshots/GIFs for visual changes
  - manual verification notes (routes checked, build/lint status)
  - linked issue/task when available
