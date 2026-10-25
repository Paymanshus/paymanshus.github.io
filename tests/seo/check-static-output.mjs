/**
 * SEO regression check over the static export in out/.
 *
 * Run after a build:  npm run build && npm run test:seo
 *
 * Validates, per route, the invariants that the SEO work depends on:
 * canonical URLs, single h1, the Person entity graph (@id reconciliation),
 * BlogPosting metadata on articles, and robots/sitemap agreement.
 */
import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';

const ROOT = process.cwd();
const OUT = path.join(ROOT, 'out');
const BLOG_DIR = path.join(ROOT, 'content', 'blog');
const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? 'https://paymanshus.github.io').replace(/\/+$/, '');
const PERSON_ID = `${SITE_URL}/#person`;

let failures = 0;

function check(label, condition) {
  if (condition) {
    console.log(`  ok   ${label}`);
  } else {
    failures += 1;
    console.error(`  FAIL ${label}`);
  }
}

function readHtml(relPath) {
  const filePath = path.join(OUT, relPath);
  if (!fs.existsSync(filePath)) {
    failures += 1;
    console.error(`  FAIL missing file: ${relPath}`);
    return null;
  }
  return fs.readFileSync(filePath, 'utf8');
}

function jsonLdBlocks(html) {
  const blocks = [];
  const re = /<script type="application\/ld\+json">(.*?)<\/script>/gs;
  let match;
  while ((match = re.exec(html)) !== null) {
    try {
      blocks.push(JSON.parse(match[1]));
    } catch {
      failures += 1;
      console.error('  FAIL unparseable JSON-LD block');
    }
  }
  return blocks;
}

function countH1(html) {
  return (html.match(/<h1[\s>]/g) ?? []).length;
}

function publishedSlugs() {
  return fs
    .readdirSync(BLOG_DIR)
    .filter((f) => ['.md', '.mdx'].includes(path.extname(f)) && !f.startsWith('_'))
    .map((f) => ({ slug: f.replace(path.extname(f), ''), data: matter(fs.readFileSync(path.join(BLOG_DIR, f), 'utf8')).data }))
    .filter((p) => p.data.published !== false)
    .map((p) => p.slug);
}

// ─── Home page ──────────────────────────────────────────────────────
console.log('home /');
{
  const html = readHtml('index.html');
  if (html) {
    check('canonical is site root', html.includes(`<link rel="canonical" href="${SITE_URL}/"`));
    check('exactly one h1', countH1(html) === 1);
    const blocks = jsonLdBlocks(html);
    const person = blocks.find((b) => b['@type'] === 'Person');
    const website = blocks.find((b) => b['@type'] === 'WebSite');
    const profile = blocks.find((b) => b['@type'] === 'ProfilePage');
    check('Person node with stable @id', person?.['@id'] === PERSON_ID);
    check('Person sameAs includes corrected LinkedIn', (person?.sameAs ?? []).includes('https://www.linkedin.com/in/paymanshus'));
    check('WebSite publisher references person @id', website?.publisher?.['@id'] === PERSON_ID);
    check('ProfilePage mainEntity references person @id', profile?.mainEntity?.['@id'] === PERSON_ID);
    check('meta description mentions role', html.includes('Machine Learning Engineer'));
    check(
      'GSC HTML-tag verification is present',
      html.includes('name="google-site-verification"') &&
        html.includes('0o-VrKZb3IemUzf8qmVFsl_dRpOwOPaZU1azIjFYnkw'),
    );
    check(
      'document title uses AI Product Engineer',
      html.includes('Paymanshu Sharma | AI Product Engineer'),
    );
    check(
      'og:image is the default card (no trailing slash)',
      html.includes(`property="og:image" content="${SITE_URL}/og/default.png"`),
    );
    check('RSS feed is discoverable', html.includes(`${SITE_URL}/feed.xml`));
  }
}

// ─── Section indexes ────────────────────────────────────────────────
for (const route of ['experience', 'cooking', 'thoughts']) {
  console.log(`route /${route}/`);
  const html = readHtml(`${route}/index.html`);
  if (html) {
    check('canonical points at own route', html.includes(`<link rel="canonical" href="${SITE_URL}/${route}/"`));
    check('exactly one h1', countH1(html) === 1);
    check('og:title present', html.includes('property="og:title"'));
    check('og:image present', html.includes('property="og:image"'));
    // Footer identity links: rel="me" is what ties the profiles to this domain.
    check('footer links to GitHub with rel=me', /rel="me[^"]*"[^>]*github\.com|github\.com[^>]*rel="me/.test(html));
    check('footer links to LinkedIn', html.includes('linkedin.com/in/paymanshus'));
    check('footer links to Hugging Face', html.includes('huggingface.co/paymanshus'));
  }
}

// ─── Blog articles ──────────────────────────────────────────────────
for (const slug of publishedSlugs()) {
  console.log(`article /thoughts/${slug}/`);
  const html = readHtml(path.join('thoughts', slug, 'index.html'));
  if (html) {
    check('canonical points at article', html.includes(`<link rel="canonical" href="${SITE_URL}/thoughts/${slug}/"`));
    check('exactly one h1', countH1(html) === 1);
    const blocks = jsonLdBlocks(html);
    const posting = blocks.find((b) => b['@type'] === 'BlogPosting');
    const breadcrumbs = blocks.find((b) => b['@type'] === 'BreadcrumbList');
    check('BlogPosting present', Boolean(posting));
    check('author reconciles to person @id', posting?.author?.['@id'] === PERSON_ID);
    check('og:type article', html.includes('property="og:type" content="article"'));
    check(
      'per-post og:image',
      html.includes(`property="og:image" content="${SITE_URL}/og/thoughts/${slug}.png"`),
    );
    check('og image file exists in out/', fs.existsSync(path.join(OUT, 'og', 'thoughts', `${slug}.png`)));
    check('BreadcrumbList has 3 levels', breadcrumbs?.itemListElement?.length === 3);
    check(
      'breadcrumb trail is Home → Thoughts → post',
      breadcrumbs?.itemListElement?.[0]?.item === `${SITE_URL}/` &&
        breadcrumbs?.itemListElement?.[1]?.item === `${SITE_URL}/thoughts/`,
    );
  }
}

// ─── 404 ────────────────────────────────────────────────────────────
console.log('404');
{
  const html = readHtml('404.html');
  if (html) {
    check('has an h1', countH1(html) === 1);
    check('is noindex', html.includes('name="robots"') && html.includes('noindex'));
    check('links back into the site', html.includes('/thoughts') && html.includes('/experience'));
  }
}

// ─── Feeds + llms.txt ───────────────────────────────────────────────
console.log('feeds');
{
  const rssPath = path.join(OUT, 'feed.xml');
  const jsonPath = path.join(OUT, 'feed.json');
  const llmsPath = path.join(OUT, 'llms.txt');
  check('feed.xml exists', fs.existsSync(rssPath));
  check('feed.json exists', fs.existsSync(jsonPath));
  check('llms.txt exists', fs.existsSync(llmsPath));

  const slugs = publishedSlugs();
  if (fs.existsSync(rssPath)) {
    const rss = fs.readFileSync(rssPath, 'utf8');
    check('rss lists every published post', slugs.every((s) => rss.includes(`/thoughts/${s}/`)));
    check('rss declares a self link', rss.includes('rel="self"'));
  }
  if (fs.existsSync(jsonPath)) {
    let feed = null;
    try {
      feed = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
    } catch {
      /* reported below */
    }
    check('feed.json parses', feed !== null);
    check('feed.json is JSON Feed 1.1', feed?.version === 'https://jsonfeed.org/version/1.1');
    check('feed.json has an item per post', feed?.items?.length === slugs.length);
  }
  if (fs.existsSync(llmsPath)) {
    const llms = fs.readFileSync(llmsPath, 'utf8');
    check('llms.txt names the site owner', llms.includes('Paymanshu Sharma'));
    check('llms.txt lists posts', slugs.every((s) => llms.includes(`/thoughts/${s}/`)));
  }
}

// ─── Google Search Console HTML file ────────────────────────────────
console.log('GSC HTML file');
{
  const gscPath = path.join(OUT, 'google51d43957481c87ef.html');
  check('verification HTML file is exported at site root', fs.existsSync(gscPath));
  if (fs.existsSync(gscPath)) {
    const body = fs.readFileSync(gscPath, 'utf8');
    check(
      'verification HTML file has Google token line',
      body.includes('google-site-verification: google51d43957481c87ef.html'),
    );
  }
}

// ─── robots.txt + sitemap.xml ───────────────────────────────────────
console.log('robots + sitemap');
{
  const robotsPath = path.join(OUT, 'robots.txt');
  const sitemapPath = path.join(OUT, 'sitemap.xml');
  check('robots.txt exists', fs.existsSync(robotsPath));
  check('sitemap.xml exists', fs.existsSync(sitemapPath));
  if (fs.existsSync(robotsPath) && fs.existsSync(sitemapPath)) {
    const robots = fs.readFileSync(robotsPath, 'utf8');
    const sitemap = fs.readFileSync(sitemapPath, 'utf8');
    check('robots.txt points at sitemap', robots.includes(`Sitemap: ${SITE_URL}/sitemap.xml`));
    check('sitemap lists /cooking/', sitemap.includes(`${SITE_URL}/cooking/`));
    for (const slug of publishedSlugs()) {
      check(`sitemap lists ${slug}`, sitemap.includes(`${SITE_URL}/thoughts/${slug}/`));
    }
  }
}

console.log(failures === 0 ? '\nSEO checks passed.' : `\n${failures} SEO check(s) FAILED.`);
process.exit(failures === 0 ? 0 : 1);
