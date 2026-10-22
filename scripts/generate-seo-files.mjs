import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';

const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? 'https://paymanshus.github.io').replace(/\/+$/, '');
const ROOT_DIR = process.cwd();
const BLOG_DIR = path.join(ROOT_DIR, 'content', 'blog');
const PUBLIC_DIR = path.join(ROOT_DIR, 'public');
const BLOG_EXTENSIONS = new Set(['.md', '.mdx']);

function absoluteUrl(routePath = '/') {
  if (routePath === '/') {
    return `${SITE_URL}/`;
  }

  return `${SITE_URL}${routePath.replace(/\/+$/, '')}/`;
}

function escapeXml(value) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

function normalizeDateValue(value, fieldName, slug) {
  if (typeof value === 'string') {
    return value;
  }

  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }

  throw new Error(`Blog post "${slug}" has an invalid ${fieldName} value.`);
}

function getPublishedBlogPosts() {
  if (!fs.existsSync(BLOG_DIR)) {
    return [];
  }

  return fs
    .readdirSync(BLOG_DIR)
    .filter((fileName) => BLOG_EXTENSIONS.has(path.extname(fileName)) && !fileName.startsWith('_'))
    .map((fileName) => {
      const slug = fileName.replace(path.extname(fileName), '');
      const source = fs.readFileSync(path.join(BLOG_DIR, fileName), 'utf8');
      const { data } = matter(source);

      if (!data || typeof data !== 'object') {
        throw new Error(`Invalid frontmatter in blog post "${slug}".`);
      }

      const frontmatter = data;
      if (!frontmatter.title || !frontmatter.excerpt || !frontmatter.date) {
        throw new Error(`Blog post "${slug}" is missing title, excerpt, or date.`);
      }

      return {
        slug,
        title: frontmatter.title,
        excerpt: frontmatter.excerpt,
        tags: Array.isArray(frontmatter.tags) ? frontmatter.tags : [],
        date: normalizeDateValue(frontmatter.date, 'date', slug),
        updatedAt: frontmatter.updatedAt
          ? normalizeDateValue(frontmatter.updatedAt, 'updatedAt', slug)
          : undefined,
        published: frontmatter.published ?? true,
      };
    })
    .filter((post) => post.published);
}

function writeRobotsFile() {
  const content = [
    'User-Agent: *',
    'Allow: /',
    '',
    `Host: ${SITE_URL}`,
    `Sitemap: ${SITE_URL}/sitemap.xml`,
    '',
  ].join('\n');

  fs.writeFileSync(path.join(PUBLIC_DIR, 'robots.txt'), content, 'utf8');
}

function writeSitemapFile() {
  const staticRoutes = [
    {
      url: absoluteUrl('/'),
      lastModified: new Date().toISOString(),
      changeFrequency: 'weekly',
      priority: '1.0',
    },
    {
      url: absoluteUrl('/experience'),
      lastModified: new Date().toISOString(),
      changeFrequency: 'monthly',
      priority: '0.8',
    },
    {
      url: absoluteUrl('/cooking'),
      lastModified: new Date().toISOString(),
      changeFrequency: 'weekly',
      priority: '0.8',
    },
    {
      url: absoluteUrl('/thoughts'),
      lastModified: new Date().toISOString(),
      changeFrequency: 'weekly',
      priority: '0.9',
    },
  ];

  const blogRoutes = getPublishedBlogPosts().map((post) => ({
    url: absoluteUrl(`/thoughts/${post.slug}`),
    lastModified: new Date(`${post.updatedAt ?? post.date}T00:00:00.000Z`).toISOString(),
    changeFrequency: 'monthly',
    priority: '0.7',
  }));

  const xml = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ...[...staticRoutes, ...blogRoutes].map(
      (route) => [
        '<url>',
        `<loc>${escapeXml(route.url)}</loc>`,
        `<lastmod>${route.lastModified}</lastmod>`,
        `<changefreq>${route.changeFrequency}</changefreq>`,
        `<priority>${route.priority}</priority>`,
        '</url>',
      ].join(''),
    ),
    '</urlset>',
    '',
  ].join('\n');

  fs.writeFileSync(path.join(PUBLIC_DIR, 'sitemap.xml'), xml, 'utf8');
}

const FEED_TITLE = 'Thoughts — Paymanshu Sharma';
const FEED_DESCRIPTION =
  'Essays on machine learning, agents, and engineering by Paymanshu Sharma.';
const AUTHOR_NAME = 'Paymanshu Sharma';

/** Newest first — the order every feed reader expects. */
function getFeedPosts() {
  return getPublishedBlogPosts().sort((a, b) => b.date.localeCompare(a.date));
}

function writeRssFile() {
  const posts = getFeedPosts();
  const items = posts.map((post) => {
    const link = absoluteUrl(`/thoughts/${post.slug}`);
    return [
      '    <item>',
      `      <title>${escapeXml(post.title)}</title>`,
      `      <link>${escapeXml(link)}</link>`,
      `      <guid isPermaLink="true">${escapeXml(link)}</guid>`,
      `      <pubDate>${new Date(`${post.date}T00:00:00.000Z`).toUTCString()}</pubDate>`,
      `      <description>${escapeXml(post.excerpt)}</description>`,
      ...post.tags.map((tag) => `      <category>${escapeXml(String(tag))}</category>`),
      '    </item>',
    ].join('\n');
  });

  const xml = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
    '  <channel>',
    `    <title>${escapeXml(FEED_TITLE)}</title>`,
    `    <link>${escapeXml(absoluteUrl('/thoughts'))}</link>`,
    `    <description>${escapeXml(FEED_DESCRIPTION)}</description>`,
    '    <language>en-us</language>',
    `    <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>`,
    `    <atom:link href="${escapeXml(`${SITE_URL}/feed.xml`)}" rel="self" type="application/rss+xml" />`,
    ...items,
    '  </channel>',
    '</rss>',
    '',
  ].join('\n');

  fs.writeFileSync(path.join(PUBLIC_DIR, 'feed.xml'), xml, 'utf8');
}

function writeJsonFeedFile() {
  const feed = {
    version: 'https://jsonfeed.org/version/1.1',
    title: FEED_TITLE,
    home_page_url: absoluteUrl('/thoughts'),
    feed_url: `${SITE_URL}/feed.json`,
    description: FEED_DESCRIPTION,
    language: 'en-us',
    authors: [{ name: AUTHOR_NAME, url: absoluteUrl('/') }],
    items: getFeedPosts().map((post) => {
      const url = absoluteUrl(`/thoughts/${post.slug}`);
      return {
        id: url,
        url,
        title: post.title,
        summary: post.excerpt,
        date_published: new Date(`${post.date}T00:00:00.000Z`).toISOString(),
        ...(post.updatedAt
          ? { date_modified: new Date(`${post.updatedAt}T00:00:00.000Z`).toISOString() }
          : {}),
        ...(post.tags.length ? { tags: post.tags.map(String) } : {}),
        image: `${SITE_URL}/og/thoughts/${post.slug}.png`,
        authors: [{ name: AUTHOR_NAME, url: absoluteUrl('/') }],
      };
    }),
  };

  fs.writeFileSync(path.join(PUBLIC_DIR, 'feed.json'), `${JSON.stringify(feed, null, 2)}\n`, 'utf8');
}

fs.mkdirSync(PUBLIC_DIR, { recursive: true });
writeRobotsFile();
writeSitemapFile();
writeRssFile();
writeJsonFeedFile();
