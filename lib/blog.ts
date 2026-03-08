import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';
import { remark } from 'remark';
import html from 'remark-html';
import gfm from 'remark-gfm';
import { formatDisplayDate } from '@/lib/site';

const BLOG_DIRECTORY = path.join(process.cwd(), 'content', 'blog');
const BLOG_EXTENSIONS = new Set(['.md', '.mdx']);

type BlogFrontmatter = {
  title: string;
  excerpt: string;
  date: string;
  updatedAt?: string;
  tags?: string[];
  published?: boolean;
};

export type BlogPostPreview = BlogFrontmatter & {
  slug: string;
  displayDate: string;
  readingTimeText: string;
};

export type BlogPost = BlogPostPreview & {
  content: string;
};

function isBlogFile(fileName: string) {
  const extension = path.extname(fileName);

  return BLOG_EXTENSIONS.has(extension) && !fileName.startsWith('_');
}

function getReadingTimeText(markdown: string) {
  const words = markdown.trim().split(/\s+/).filter(Boolean).length;
  const minutes = Math.max(1, Math.round(words / 200));
  return `${minutes} min read`;
}

function normalizeDateValue(value: unknown, fieldName: string, slug: string) {
  if (typeof value === 'string') {
    return value;
  }

  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }

  throw new Error(`Blog post "${slug}" has an invalid ${fieldName} value.`);
}

function parseFrontmatter(slug: string, data: unknown): BlogFrontmatter {
  if (!data || typeof data !== 'object') {
    throw new Error(`Invalid frontmatter in blog post "${slug}".`);
  }

  const frontmatter = data as Partial<BlogFrontmatter>;

  if (!frontmatter.title || !frontmatter.excerpt || !frontmatter.date) {
    throw new Error(`Blog post "${slug}" is missing title, excerpt, or date.`);
  }

  return {
    title: frontmatter.title,
    excerpt: frontmatter.excerpt,
    date: normalizeDateValue(frontmatter.date, 'date', slug),
    updatedAt: frontmatter.updatedAt
      ? normalizeDateValue(frontmatter.updatedAt, 'updatedAt', slug)
      : undefined,
    tags: frontmatter.tags ?? [],
    published: frontmatter.published ?? true,
  };
}

function getBlogFiles() {
  if (!fs.existsSync(BLOG_DIRECTORY)) {
    return [];
  }

  return fs.readdirSync(BLOG_DIRECTORY).filter(isBlogFile);
}

function readBlogSourceBySlug(slug: string) {
  for (const extension of BLOG_EXTENSIONS) {
    const filePath = path.join(BLOG_DIRECTORY, `${slug}${extension}`);
    if (fs.existsSync(filePath)) {
      return fs.readFileSync(filePath, 'utf8');
    }
  }

  return null;
}

function toPreview(slug: string, frontmatter: BlogFrontmatter, markdown: string): BlogPostPreview {
  return {
    ...frontmatter,
    slug,
    displayDate: formatDisplayDate(frontmatter.date),
    readingTimeText: getReadingTimeText(markdown),
  };
}

export function getAllBlogPosts() {
  return getBlogFiles()
    .map((fileName) => {
      const slug = fileName.replace(path.extname(fileName), '');
      const source = fs.readFileSync(path.join(BLOG_DIRECTORY, fileName), 'utf8');
      const { data, content } = matter(source);
      const frontmatter = parseFrontmatter(slug, data);
      return toPreview(slug, frontmatter, content);
    })
    .filter((post) => post.published)
    .sort((a, b) => b.date.localeCompare(a.date));
}

export function getAllBlogSlugs() {
  return getAllBlogPosts().map((post) => post.slug);
}

export function getBlogPostBySlug(slug: string): BlogPost | null {
  const source = readBlogSourceBySlug(slug);

  if (!source) {
    return null;
  }

  const { data, content } = matter(source);
  const frontmatter = parseFrontmatter(slug, data);

  if (frontmatter.published === false) {
    return null;
  }

  const processedContent = remark().use(gfm).use(html).processSync(content);

  return {
    ...toPreview(slug, frontmatter, content),
    content: processedContent.toString(),
  };
}
