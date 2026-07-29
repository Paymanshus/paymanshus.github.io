/**
 * Tests for the blog content collection.
 *
 * These assert on the markdown source files rather than importing lib/blog.ts,
 * because that module imports via the `@/` tsconfig path alias which bare Node
 * cannot resolve. The frontmatter contract enforced here is the same one
 * lib/blog.ts parses (title, excerpt, date, tags, published).
 *
 * Run: node --test tests/
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';

const BLOG_DIR = path.join(process.cwd(), 'content', 'blog');

/** Mirrors the isBlogFile() filter in lib/blog.ts: no underscore-prefixed files. */
function readPosts() {
  return fs
    .readdirSync(BLOG_DIR)
    .filter((name) => name.endsWith('.md') && !name.startsWith('_'))
    .map((name) => {
      const { data, content } = matter(fs.readFileSync(path.join(BLOG_DIR, name), 'utf8'));
      return { slug: name.replace(/\.md$/, ''), data, content };
    });
}

const REAL_POSTS = ['llm-optimization-memory-gpu-cpu', 'on-device-llms-on-android'];
const PLACEHOLDER_POSTS = [
  'austere-neon-designing-for-focus',
  'building-audio-reactive-particle-systems',
  'the-cli-as-a-first-class-interface',
];

test('only the real authored posts are published', () => {
  const published = readPosts()
    .filter((post) => post.data.published !== false)
    .map((post) => post.slug)
    .sort();

  assert.deepEqual(published, REAL_POSTS);
});

test('placeholder posts are kept on disk but hidden', () => {
  const posts = readPosts();

  for (const slug of PLACEHOLDER_POSTS) {
    const post = posts.find((candidate) => candidate.slug === slug);
    assert.ok(post, `expected placeholder ${slug} to still exist as a template`);
    assert.equal(post.data.published, false, `${slug} must not be visible online`);
  }
});

test('published posts satisfy the frontmatter contract', () => {
  for (const post of readPosts().filter((candidate) => candidate.data.published !== false)) {
    const { slug, data } = post;

    assert.equal(typeof data.title, 'string', `${slug} needs a title`);
    assert.ok(data.title.length > 0, `${slug} title must not be empty`);
    assert.equal(typeof data.excerpt, 'string', `${slug} needs an excerpt`);
    assert.ok(data.excerpt.length > 0, `${slug} excerpt must not be empty`);
    assert.match(String(data.date), /^\d{4}-\d{2}-\d{2}$/, `${slug} needs an ISO date`);
    assert.ok(Array.isArray(data.tags) && data.tags.length > 0, `${slug} needs tags`);
  }
});

test('authored posts are dated to 2024 and flag their age', () => {
  for (const post of readPosts().filter((candidate) => REAL_POSTS.includes(candidate.slug))) {
    assert.match(String(post.data.date), /^2024-/, `${post.slug} should carry its original 2024 date`);
    assert.match(
      post.content,
      /^_Written in [^\n]*2024/m,
      `${post.slug} should open with an italic note marking it as dated`,
    );
  }
});

test('authored posts carry no leftover draft artifacts', () => {
  // The Notion sources were working drafts with unfilled placeholders and
  // duplicated DRAFT/DUMP sections. None of that should reach the site.
  const forbidden = [
    /\[Results Tabular/i,
    /\[specific metric\]/i,
    /\[LLM\.int8\(\) photo\]/i,
    /\[Fp16 vector image/i,
    /^#+\s*(DRAFT|DUMP)\s*$/m,
    /\[Challenges Mentioned in/i,
  ];

  for (const post of readPosts().filter((candidate) => REAL_POSTS.includes(candidate.slug))) {
    for (const pattern of forbidden) {
      assert.doesNotMatch(post.content, pattern, `${post.slug} still contains a draft artifact`);
    }
  }
});

test('inline SVG figures contain no blank lines', () => {
  // Markdown terminates a raw HTML block at the first blank line. A blank line
  // inside a <figure> silently leaks the rest of the SVG onto the page as text,
  // which renders as visible markup rather than failing loudly.
  for (const post of readPosts()) {
    const figures = post.content.match(/<figure[\s\S]*?<\/figure>/g) ?? [];

    for (const [index, figure] of figures.entries()) {
      assert.doesNotMatch(
        figure,
        /\n[ \t]*\n/,
        `${post.slug} figure ${index + 1} has a blank line; its SVG will leak as raw text`,
      );
    }
  }
});

test('figures are self-contained and captioned', () => {
  for (const post of readPosts()) {
    const figures = post.content.match(/<figure[\s\S]*?<\/figure>/g) ?? [];

    for (const [index, figure] of figures.entries()) {
      const label = `${post.slug} figure ${index + 1}`;
      assert.ok(figure.includes('<figcaption'), `${label} needs a caption`);
      // No external fetches: the site is exported statically and must render offline.
      assert.doesNotMatch(figure, /<img|href="http|src="http/, `${label} must not load remote assets`);
      assert.match(figure, /aria-label=|role="img"/, `${label} needs an accessible description`);
    }
  }
});

test('blog-figures skill and its reference copy stay in sync', () => {
  // readmes/SPECs/BLOG_VISUALS.md exists so the workflow survives on a machine
  // where the skill isn't loaded. It must not drift from the skill itself.
  const skill = fs.readFileSync(
    path.join(process.cwd(), '.claude', 'skills', 'blog-figures', 'SKILL.md'),
    'utf8',
  );
  const copy = fs.readFileSync(
    path.join(process.cwd(), 'readmes', 'SPECs', 'BLOG_VISUALS.md'),
    'utf8',
  );

  // Compare bodies: the skill carries YAML frontmatter, the copy a blockquote note.
  const skillBody = skill.split('---').slice(2).join('---').trim();
  const copyBody = copy.slice(copy.indexOf('# Blog figures')).trim();

  assert.equal(copyBody, skillBody, 'BLOG_VISUALS.md has drifted from SKILL.md — regenerate it');
});

test('no duplicated Introduction headings survive the dedupe', () => {
  const post = readPosts().find((candidate) => candidate.slug === 'llm-optimization-memory-gpu-cpu');
  const intros = post.content.match(/^##\s+Introduction\s*$/gm) ?? [];

  assert.equal(intros.length, 1, 'the whitepaper draft had several Introductions; only one should remain');
});
