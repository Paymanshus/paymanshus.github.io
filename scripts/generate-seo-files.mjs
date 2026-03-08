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

fs.mkdirSync(PUBLIC_DIR, { recursive: true });
writeRobotsFile();
writeSitemapFile();
