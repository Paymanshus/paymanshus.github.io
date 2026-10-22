import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';
import { remark } from 'remark';
import html from 'remark-html';
import gfm from 'remark-gfm';
import { formatDisplayDate } from '@/lib/site';

const COOKING_DIRECTORY = path.join(process.cwd(), 'content', 'cooking');
const ORDER_FILE = path.join(COOKING_DIRECTORY, '_order.txt');

export const PROJECT_STATUSES = [
  'building',
  'early',
  // 'shipped', // Nothing is shipped yet; re-enable (and its label in CookingCard) when something is.
] as const;
export type ProjectStatus = (typeof PROJECT_STATUSES)[number];

/**
 * An image in `public/`. Width and height are the file's real pixel size,
 * written into frontmatter by `scripts/optimize-cooking-media.mjs`, so the
 * page can reserve the right box before the image loads.
 */
export type ProjectImage = {
  src: string;
  alt: string;
  width: number;
  height: number;
};

type ProjectFrontmatter = {
  title: string;
  summary: string;
  date: string;
  status: ProjectStatus;
  stack: string[];
  repo?: string;
  live?: string;
  /** Card image. */
  thumbnail?: ProjectImage;
  /** Top of the detail view; falls back to the thumbnail. */
  hero?: ProjectImage;
  /** Screenshot gallery in the detail view. */
  media: ProjectImage[];
};

export type Project = ProjectFrontmatter & {
  slug: string;
  displayDate: string;
  /** Long-form writeup: Markdown rendered to HTML. */
  content: string;
  readingTimeText: string;
};

function normalizeDateValue(value: unknown, slug: string) {
  if (typeof value === 'string') {
    return value;
  }

  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }

  throw new Error(`Project "${slug}" has an invalid date value.`);
}

function parseImage(value: unknown, slug: string, field: string): ProjectImage {
  const image = value as Partial<ProjectImage> | undefined;

  if (!image?.src || !image.alt || !image.width || !image.height) {
    throw new Error(`Project "${slug}" has an incomplete ${field} (needs src, alt, width, height).`);
  }

  return { src: image.src, alt: image.alt, width: Number(image.width), height: Number(image.height) };
}

function parseFrontmatter(slug: string, data: unknown): ProjectFrontmatter {
  if (!data || typeof data !== 'object') {
    throw new Error(`Invalid frontmatter in project "${slug}".`);
  }

  const frontmatter = data as Record<string, unknown>;

  if (!frontmatter.title || !frontmatter.summary || !frontmatter.date) {
    throw new Error(`Project "${slug}" is missing title, summary, or date.`);
  }

  const status = frontmatter.status as ProjectStatus;
  if (!PROJECT_STATUSES.includes(status)) {
    throw new Error(`Project "${slug}" has status "${String(status)}"; expected ${PROJECT_STATUSES.join(' | ')}.`);
  }

  return {
    title: String(frontmatter.title),
    summary: String(frontmatter.summary),
    date: normalizeDateValue(frontmatter.date, slug),
    status,
    stack: (frontmatter.stack as string[] | undefined) ?? [],
    repo: frontmatter.repo as string | undefined,
    live: frontmatter.live as string | undefined,
    thumbnail: frontmatter.thumbnail ? parseImage(frontmatter.thumbnail, slug, 'thumbnail') : undefined,
    hero: frontmatter.hero ? parseImage(frontmatter.hero, slug, 'hero') : undefined,
    media: ((frontmatter.media as unknown[] | undefined) ?? []).map((item, index) =>
      parseImage(item, slug, `media[${index}]`),
    ),
  };
}

function getReadingTimeText(markdown: string) {
  const words = markdown.trim().split(/\s+/).filter(Boolean).length;
  return `${Math.max(1, Math.round(words / 200))} min read`;
}

/** Slugs listed in `_order.txt`, in display order. Comment lines (#) are hidden projects. */
function readOrder(): string[] {
  return fs
    .readFileSync(ORDER_FILE, 'utf8')
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'));
}

function readProject(slug: string): Project {
  const filePath = path.join(COOKING_DIRECTORY, `${slug}.md`);
  if (!fs.existsSync(filePath)) {
    throw new Error(`content/cooking/_order.txt lists "${slug}", but ${slug}.md does not exist.`);
  }

  const { data, content } = matter(fs.readFileSync(filePath, 'utf8'));
  const frontmatter = parseFrontmatter(slug, data);

  return {
    ...frontmatter,
    slug,
    displayDate: formatDisplayDate(frontmatter.date),
    // sanitize: false so writeups can embed inline SVG figures, as blog posts
    // do. Safe for the same reason: authored in-repo, never user submitted.
    content: remark().use(gfm).use(html, { sanitize: false }).processSync(content).toString(),
    readingTimeText: getReadingTimeText(content),
  };
}

/** Projects to show, in the order `content/cooking/_order.txt` lists them. */
export function getAllProjects(): Project[] {
  if (!fs.existsSync(ORDER_FILE)) {
    return [];
  }

  const order = readOrder();
  const unlisted = fs
    .readdirSync(COOKING_DIRECTORY)
    .filter((fileName) => fileName.endsWith('.md') && !fileName.startsWith('_'))
    .map((fileName) => fileName.replace(/\.md$/, ''))
    .filter((slug) => !order.includes(slug));

  if (unlisted.length > 0) {
    console.warn(`[cooking] hidden (not in _order.txt): ${unlisted.join(', ')}`);
  }

  return order.map(readProject);
}
