# SEO Setup Runbook

One-time setup for search engine verification, analytics, and indexing on
`https://paymanshus.github.io`. Do these sections in order — GSC and GA4 both
end with the same pattern: set a GitHub repository **variable**, uncomment a
line in the deploy workflow, push to `main`, wait for the Pages deploy, then
verify in the console.

This is written for the site owner doing it once by hand. It assumes you
already have push access to the repo and are signed in with the Google
account you want tied to Search Console / Analytics.

## Status (2026-08-19)

- **Search Console HTML file** is committed at
  `public/google51d43957481c87ef.html` (served at
  `https://paymanshus.github.io/google51d43957481c87ef.html`). Keep it forever.
- **Search Console HTML tag** is baked into `lib/site.ts` /
  `app/layout.tsx` (`content="0o-VrKZb3IemUzf8qmVFsl_dRpOwOPaZU1azIjFYnkw"`).
  The deploy workflow also passes `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION` when
  the GitHub Actions variable is set.
- **Owner still does:** click **Verify** in GSC (if not done) → submit
  `sitemap.xml` → confirm GA4 Realtime after deploy.
- **DNS TXT on `paymanshus.github.io`:** not possible. GitHub owns that DNS.
- **Google Tag Manager:** not used; skip.

## 1. What's already wired

The code side of this is done — nothing below requires a code change beyond
uncommenting two lines in the deploy workflow. Each env var is read at build
time (this is a static export, so these are baked in at `npm run build`, not
read at runtime):

| Env var | Where it's read | What it turns on |
| --- | --- | --- |
| `NEXT_PUBLIC_SITE_URL` | `lib/site.ts` (canonicals, sitemap, OG/JSON-LD URLs) | Already set to `https://paymanshus.github.io` in `.github/workflows/deploy.yml`. No action needed. |
| `NEXT_PUBLIC_GA_ID` | `lib/analytics.ts`, `components/analytics/Analytics.tsx` | GA4. When empty, `gtag.js` is never loaded and every `trackEvent`/`trackPageView` call is a no-op — analytics code ships in every build but stays inert until this is set. |
| `NEXT_PUBLIC_GA_DEBUG` | `lib/analytics.ts` | When set to the string `"true"`, every event gets a `debug_mode: true` param so it shows up live in GA4 DebugView. Only ever set this locally — never in the production build. |
| `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION` | `app/layout.tsx` (`metadata.verification.google`) | Renders `<meta name="google-site-verification" content="...">` in the page head. Omitted entirely when empty. This is the HTML-tag method for Google Search Console. |
| `NEXT_PUBLIC_AGENT_URL` | voice/terminal resume components | Points the chat and voice interfaces at the LLM backend. Not an SEO var, listed here because it lives in the same `.env.example` / deploy-workflow env block. |

The GSC and GA4 vars are both already declared (empty) in `.env.example`, and
both already have a commented-out line waiting in
`.github/workflows/deploy.yml`:

```yaml
# Uncomment once the GA4 property exists (SEOPLAN.md task E1) and the
# measurement id is stored as a repository variable or secret.
# NEXT_PUBLIC_GA_ID: ${{ vars.NEXT_PUBLIC_GA_ID }}
# Uncomment after starting Search Console HTML-tag verification (E1).
# NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION: ${{ vars.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION }}
```

## 2. Google Search Console

### 2.1 Create the property

1. Go to https://search.google.com/search-console and sign in.
2. Click **Add property** (property picker is in the top-left dropdown).
3. Under **URL prefix** (the right-hand box, not "Domain" on the left), enter:
   ```
   https://paymanshus.github.io/
   ```
   Use URL-prefix, not Domain. A Domain property verifies ownership via a DNS
   TXT record at the apex domain — you don't control DNS for `github.io`, so
   that method is impossible here. URL-prefix supports HTML-tag verification
   instead, which you do control.

### 2.2 Verify with the HTML tag or HTML file (already in the repo)

The HTML tag and the HTML file from Search Console are already in the
tree. You do **not** need to paste the meta tag by hand or upload the
file through GitHub's UI.

1. Wait for **Deploy GitHub Pages** to finish after a push to `main`.
2. Confirm both methods are live:
   ```bash
   curl -s https://paymanshus.github.io/ | grep google-site-verification
   curl -sI https://paymanshus.github.io/google51d43957481c87ef.html
   ```
3. In Search Console, click **Verify** (HTML tag or HTML file — either is enough).
4. Do not remove `public/google51d43957481c87ef.html` or the meta tag in
   `lib/site.ts` after verification succeeds.

If Google ever rotates the token, update `GOOGLE_SITE_VERIFICATION` in
`lib/site.ts`, replace the HTML file in `public/`, and optionally set the
GitHub Actions variable `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION`.

### 2.3 Submit the sitemap

1. In Search Console, with the `paymanshus.github.io` property selected, go to **Sitemaps** in the left sidebar.
2. Enter `sitemap.xml` in the "Add a new sitemap" box (it's relative to the property root) and click **Submit**. The full URL is:
   ```
   https://paymanshus.github.io/sitemap.xml
   ```
3. Status should move to "Success" within a few minutes to a day. If it stays "Couldn't fetch," re-check step 2.2.7 above — the site itself must be reachable and the sitemap must 200.

## 3. Bing Webmaster Tools

Bing (and Yahoo, which rides on Bing's index) supports importing directly from
a verified Google Search Console property, which skips a second verification
step entirely.

1. Go to https://www.bing.com/webmasters and sign in.
2. Look for **Import from Google Search Console** (labels shift occasionally — it may be presented as an option during onboarding, or under a "Add a site" / import flow).
3. Authorize Bing to read your Search Console account and select the `paymanshus.github.io` property.
4. Bing will pull in the verified site and sitemap automatically. If the sitemap doesn't come across, add it manually under **Sitemaps** with the same URL as above: `https://paymanshus.github.io/sitemap.xml`.

If the import option isn't available for any reason, fall back to Bing's own
XML-file or meta-tag verification — the meta-tag method mirrors section 2.2
above but there's no existing env var wired for it, so use the file-upload
method (drop the file Bing gives you into `public/` and redeploy) instead of
adding new code.

## 4. GA4 (Google Analytics)

### 4.1 Create the property and data stream

1. Go to https://analytics.google.com and sign in.
2. **Admin** (gear icon, bottom left) → **Create property**. Name it something like "Portfolio — paymanshus.github.io", set your timezone/currency, continue through the business details prompts.
3. Under **Data collection**, choose **Web**.
4. Enter the website URL:
   ```
   https://paymanshus.github.io
   ```
   Stream name: anything recognizable, e.g. "Portfolio site".
5. After the stream is created, copy the **Measurement ID** — it looks like `G-XXXXXXXXXX` and is shown at the top of the stream detail page.

### 4.2 Wire it into the deploy

1. Add it as a GitHub repository variable:
   - Repo → **Settings** → **Secrets and variables** → **Actions** → **Variables** → **New repository variable**.
   - Name: `NEXT_PUBLIC_GA_ID`
   - Value: your `G-XXXXXXXXXX` measurement ID.
2. Edit `.github/workflows/deploy.yml` and uncomment:
   ```yaml
   NEXT_PUBLIC_GA_ID: ${{ vars.NEXT_PUBLIC_GA_ID }}
   ```
3. Commit and push:
   ```bash
   git add .github/workflows/deploy.yml
   ```
   ```bash
   git commit -m "Enable GA4 analytics"
   ```
   ```bash
   git push
   ```
4. Wait for the deploy workflow to finish.

### 4.3 Confirm data is flowing

1. Visit https://paymanshus.github.io in a normal browser tab.
2. In GA4, go to **Reports** → **Realtime**. You should see 1 active user (yourself) within about 30 seconds. If nothing shows up, view source on the live page and confirm the `gtag/js?id=G-...` script tag is present with your measurement ID — if it's missing, the env var didn't make it into the build (check step 4.2 and re-run the workflow).

### 4.4 Local debugging with DebugView

`NEXT_PUBLIC_GA_DEBUG=true` stamps `debug_mode: true` onto every event so it
appears live in GA4's DebugView instead of waiting for normal processing.
Only use this locally — never set it in the deploy workflow / production env.

1. In your local `.env.local` (not `.env.example`), set:
   ```
   NEXT_PUBLIC_GA_ID="G-XXXXXXXXXX"
   NEXT_PUBLIC_GA_DEBUG="true"
   ```
2. Run the dev server and interact with the site.
   ```bash
   npm run dev
   ```
3. In GA4, go to **Admin** → **DebugView** (under the property's data display section). Your session should appear labeled as a debug device, with events arriving in near real time — useful for confirming new event names/params before they ship.
4. Remove or blank `NEXT_PUBLIC_GA_DEBUG` when done; don't commit it as `"true"`.

## 5. What the analytics layer reports

All events are sent via `trackEvent(name, params)` in `lib/analytics.ts`,
which no-ops entirely until `NEXT_PUBLIC_GA_ID` is set. Here's every event the
site currently emits, so GA4 reports/explorations can be built against them
directly rather than guessing:

| Event name | Fired from | Parameters | When |
| --- | --- | --- | --- |
| `page_view` | `lib/analytics.ts` → `trackPageView`, called by `components/analytics/Analytics.tsx` | `page_path`, `page_location`, `page_title` | Manual page view on every route change (GA's automatic page_view is disabled via `send_page_view: false` so this doesn't double-count on the SPA-style route changes). |
| `section_view` | `components/analytics/PageEngagement.tsx`, `hooks/useSectionView.ts` | `section` (e.g. `home_hero`, `thoughts_index`, `article:my-slug`, `experience`) | Once, the first time a tracked section becomes visible (or mounts, for full-page sections). |
| `section_time` | `lib/analytics.ts` → `reportSectionTimings`, called from `Analytics.tsx` on route change / tab hide / pagehide | `section`, `seconds`, `page_path` | Flushed dwell time per section, only if it accumulated ≥1 second (`MIN_SECTION_MS`), so pure scroll-throughs don't count. |
| `scroll_depth` | `components/analytics/PageEngagement.tsx` | `percent` (25, 50, 75, or 100), `page_path` | Once per milestone, on pages that opt into `scrollDepth` (long-form pages only, e.g. blog posts). |
| `resume_mode_change` | `components/ExperienceSection.tsx` | `mode` (`pdf`, `chat`, or `voice`) | Whenever the visitor switches tabs in the resume/experience section. |
| `terminal_chat` | `components/resume/ChatResume.tsx` | `llm` (boolean) | Every free-text question sent to the terminal. `true` when the LLM backend answered, `false` when it fell back to the offline keyword responder — worth watching as a proxy for backend uptime/latency. |
| `terminal_command` | `components/resume/ChatResume.tsx` | `command` (e.g. `clear`, or any recognized built-in command name) | Only built-in terminal commands are recorded — free-text questions never appear in this param, only in `terminal_chat`. |
| `voice_session_start` | `components/resume/VoiceResume.tsx` | none | Voice session successfully connects (LiveKit token minted). |
| `voice_session_end` | `components/resume/VoiceResume.tsx` | `duration_seconds` | Voice session ends, only if it had actually started. |
| `voice_error` | `components/resume/VoiceResume.tsx` | `stage` (`token` or `room`) | Voice session fails — either at token-fetch time or once inside the LiveKit room. |

### Register custom dimensions before building reports

GA4 does not surface event parameters in the UI (Explorations, custom
reports) until you register them as **custom dimensions**. Do this once, for
every parameter above you plan to slice by — at minimum, the five that carry
the most signal:

1. In GA4, go to **Admin** → **Custom definitions** (under "Data display", labels shift occasionally) → **Create custom dimension**.
2. For each of the following, set the dimension name to match, scope to **Event**, and the event parameter to the exact string:
   - `section` (from `section_view` / `section_time`)
   - `mode` (from `resume_mode_change`)
   - `command` (from `terminal_command`)
   - `percent` (from `scroll_depth`)
   - `stage` (from `voice_error`)
3. New custom dimensions only apply to events collected **after** registration — there's no backfill. Register these early so history isn't gappy.

## 6. Verifying indexing

Indexing is not instant — expect it to take anywhere from a few days to a few
weeks after the sitemap is submitted, especially for a low-authority new
domain. That's normal; don't resubmit or re-verify repeatedly in response.

1. Check what Google currently has indexed with a `site:` search:
   ```
   site:paymanshus.github.io
   ```
   Run this at https://www.google.com/search — results (or their absence) are indicative, not exhaustive.
2. For any specific URL, use Search Console's **URL Inspection** tool (top search bar in Search Console, paste the full URL). It shows whether the URL is indexed, when it was last crawled, and any coverage issues.
3. For a newly published blog post you want indexed sooner, use **Request indexing** from the URL Inspection result. This nudges Google to prioritize a crawl — it's a request, not a guarantee, and can still take days.

## 7. Feeds and AI discoverability

Three machine-readable summaries of the site already exist and are generated
automatically by `scripts/generate-seo-files.mjs` on every build:

- `https://paymanshus.github.io/feed.xml` — RSS 2.0, newest posts first.
- `https://paymanshus.github.io/feed.json` — JSON Feed 1.1, same content.
- `https://paymanshus.github.io/llms.txt` — a hand-maintained, plain-markdown summary of the site (routes, blog posts, elsewhere links, contact) intended for LLM/agent consumers rather than RSS readers.

`feed.xml` and `feed.json` are both advertised via `<link rel="alternate">`
tags in the page `<head>` (`alternates.types` in `app/layout.tsx`), so feed
readers can auto-discover them from any page. `llms.txt` is not linked from
the head — it follows the emerging `/llms.txt` convention of living at a
well-known root path for LLM crawlers/agents to find directly, and is
maintained by hand rather than templated per page.

No action needed here beyond keeping `llms.txt` up to date by hand when new
posts ship (see `readmes/SEOPLAN.md` task C4).
