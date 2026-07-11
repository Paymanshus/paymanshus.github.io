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
    check('Person declares Maersk employer', person?.worksFor?.name === 'Maersk');
    check('Person sameAs includes corrected LinkedIn', (person?.sameAs ?? []).includes('https://www.linkedin.com/in/paymanshus'));
    check('WebSite publisher references person @id', website?.publisher?.['@id'] === PERSON_ID);
    check('ProfilePage mainEntity references person @id', profile?.mainEntity?.['@id'] === PERSON_ID);
    check('meta description mentions role', html.includes('Machine Learning Engineer'));
  }
}

// ─── Section indexes ────────────────────────────────────────────────
for (const route of ['experience', 'thoughts']) {
  console.log(`route /${route}/`);
  const html = readHtml(`${route}/index.html`);
  if (html) {
    check('canonical points at own route', html.includes(`<link rel="canonical" href="${SITE_URL}/${route}/"`));
    check('at most one h1', countH1(html) <= 1); // B3 tightens /experience to exactly one
    check('og:title present', html.includes('property="og:title"'));
  }
}

// ─── Blog articles ──────────────────────────────────────────────────
for (const slug of publishedSlugs()) {
  console.log(`article /thoughts/${slug}/`);
  const html = readHtml(path.join('thoughts', slug, 'index.html'));
  if (html) {
    check('canonical points at article', html.includes(`<link rel="canonical" href="${SITE_URL}/thoughts/${slug}/"`));
    check('exactly one h1', countH1(html) === 1);
    const posting = jsonLdBlocks(html).find((b) => b['@type'] === 'BlogPosting');
    check('BlogPosting present', Boolean(posting));
    check('author reconciles to person @id', posting?.author?.['@id'] === PERSON_ID);
    check('og:type article', html.includes('property="og:type" content="article"'));
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
    for (const slug of publishedSlugs()) {
      check(`sitemap lists ${slug}`, sitemap.includes(`${SITE_URL}/thoughts/${slug}/`));
    }
  }
}

console.log(failures === 0 ? '\nSEO checks passed.' : `\n${failures} SEO check(s) FAILED.`);
process.exit(failures === 0 ? 0 : 1);
