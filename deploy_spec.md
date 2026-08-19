# Deploy Spec

## Flow

Work on `main`. Commit with a concise imperative subject. Push to
`origin` (`https://github.com/Paymanshus/paymanshus.github.io.git`).
`.github/workflows/deploy.yml` runs on push to `main` (and
`workflow_dispatch`): `npm ci` → `npm run build` (static export to `out/`)
→ upload Pages artifact → `actions/deploy-pages`. Live site:
`https://paymanshus.github.io`.

## Environments

- `main` → production GitHub Pages only. No staging site.
- Voice agent (Fly.io) is a separate deploy; see `agent/RUN.md`. Do not
  treat a Pages push as an agent release.

## Restrictions

- Do not force-push `main`.
- Do not skip hooks.
- Secrets (`agent/.env.local`, root `.env.local`) never go in git.
- `NEXT_PUBLIC_GA_ID` stays commented in the workflow until the owner
  creates GA4 and sets the repo variable.

## Monitoring

GitHub Actions: workflow **Deploy GitHub Pages**. Typical duration a few
minutes. Confirm with the Actions run URL, then `curl -sI
https://paymanshus.github.io/`.

## Preferences

- Commit messages: concise, imperative, why over what.
- Pre-push: `npm run lint && npm run build && npm run test:seo` when SEO
  or frontend files change. Agent tests only when `agent/` changes.
- Direct push to `main` is the existing Pages path.

## Failure notes

- First Pages build needs network for `next/font/google`.
- Empty `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION` in Actions is fine: code
  falls back to the committed token.
- Rollback: revert the commit on `main` and push.
