# Paymanshu Sharma Portfolio

Static-exported Next.js portfolio and blog, intended for deployment to `paymanshus.github.io` via GitHub Pages.

## Local Development

1. Install dependencies with `npm install`
2. Copy `.env.example` to `.env.local` if you want to override the production URL locally
3. Run `npm run dev`

## Production Build

Run `npm run build`. The static site is emitted to `out/`.

## GitHub Pages Deployment

This project is configured for:

- Next.js app router
- static export via `output: 'export'`
- GitHub Actions deployment from `.github/workflows/deploy.yml`

When this code lives inside the `paymanshus.github.io` repository, pushing to `main` will build and deploy the exported site to GitHub Pages.

For one-command local deployment into an existing clone of `paymanshus.github.io`, use:

```bash
./scripts/deploy-pages.sh -m "Your commit message"
```

The script builds the app, rsyncs the public-safe project files into the target clone, commits, and pushes.

## Content

- Blog posts live in `content/blog`
- SEO metadata is centralized in `lib/site.ts`
- `readmes/` is repo-only documentation and is not publicly served
