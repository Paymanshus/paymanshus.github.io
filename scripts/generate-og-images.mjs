/**
 * Build-time Open Graph image generation.
 *
 * The site is a static export with no server, so there is no dynamic
 * /api/og route: every card is rendered to a PNG at build time and served
 * from public/og/. Runs as part of `npm run generate:seo`.
 *
 * Fonts are committed under scripts/assets/fonts (never fetched at build —
 * a network hiccup must not break a deploy). They are static instances of the
 * Space Grotesk variable font, produced with:
 *   fonttools varLib.instancer "SpaceGrotesk[wght].ttf" wght=400 -o SpaceGrotesk-Regular.ttf
 * satori's opentype.js fork cannot parse the variable font's fvar table, so
 * static instances are required.
 */
import fs from 'node:fs';
import path from 'node:path';
import satori from 'satori';
import { Resvg } from '@resvg/resvg-js';
import matter from 'gray-matter';

const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? 'https://paymanshus.github.io').replace(/\/+$/, '');
const ROOT_DIR = process.cwd();
const BLOG_DIR = path.join(ROOT_DIR, 'content', 'blog');
const OG_DIR = path.join(ROOT_DIR, 'public', 'og');
const POSTS_OG_DIR = path.join(OG_DIR, 'thoughts');
const FONT_DIR = path.join(ROOT_DIR, 'scripts', 'assets', 'fonts');
const FONT_REGULAR = path.join(FONT_DIR, 'SpaceGrotesk-Regular.ttf');
const FONT_BOLD = path.join(FONT_DIR, 'SpaceGrotesk-Bold.ttf');
const BLOG_EXTENSIONS = new Set(['.md', '.mdx']);

// Matches app/globals.css design tokens.
const COLORS = {
  bg: '#050505',
  border: '#1a1a1a',
  text: '#f5f5f5',
  secondary: '#8a8a8a',
  red: '#ff2a2a',
};

const WIDTH = 1200;
const HEIGHT = 630;

const fonts = [
  { name: 'Space Grotesk', data: fs.readFileSync(FONT_REGULAR), weight: 400, style: 'normal' },
  { name: 'Space Grotesk', data: fs.readFileSync(FONT_BOLD), weight: 700, style: 'normal' },
];

/** Shared card chrome: hairline frame, red rule, and the site URL footer. */
function card(children, footerLeft, footerRight) {
  return {
    type: 'div',
    props: {
      style: {
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        backgroundColor: COLORS.bg,
        padding: '64px 72px',
        border: `1px solid ${COLORS.border}`,
        fontFamily: 'Space Grotesk',
      },
      children: [
        {
          type: 'div',
          props: {
            style: { display: 'flex', width: '120px', height: '3px', backgroundColor: COLORS.red },
          },
        },
        { type: 'div', props: { style: { display: 'flex', flexDirection: 'column' }, children } },
        {
          type: 'div',
          props: {
            style: {
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: 24,
              color: COLORS.secondary,
              letterSpacing: '0.12em',
            },
            children: [
              { type: 'div', props: { style: { display: 'flex' }, children: footerLeft } },
              { type: 'div', props: { style: { display: 'flex' }, children: footerRight } },
            ],
          },
        },
      ],
    },
  };
}

function defaultCard() {
  return card(
    [
      {
        type: 'div',
        props: {
          style: { display: 'flex', fontSize: 82, color: COLORS.text, letterSpacing: '-0.02em', lineHeight: 1.1 },
          children: 'Paymanshu Sharma',
        },
      },
      {
        type: 'div',
        props: {
          style: { display: 'flex', marginTop: 20, fontSize: 36, color: COLORS.secondary },
          children: 'Machine Learning Engineer · Maersk',
        },
      },
      {
        type: 'div',
        props: {
          style: { display: 'flex', marginTop: 28, fontSize: 26, color: COLORS.red, letterSpacing: '0.08em' },
          children: 'Agentic AI · Voice systems · Engineering notes',
        },
      },
    ],
    'paymanshus.github.io',
    'Portfolio',
  );
}

function postCard(post) {
  // Long titles must not overflow the card; satori has no ellipsis support
  // for multi-line clamps, so wrap and hard-truncate defensively.
  const title = post.title.length > 92 ? `${post.title.slice(0, 89)}…` : post.title;
  const fontSize = title.length > 60 ? 56 : title.length > 38 ? 66 : 76;

  return card(
    [
      {
        type: 'div',
        props: {
          style: { display: 'flex', fontSize: 24, color: COLORS.red, letterSpacing: '0.18em' },
          children: 'THOUGHTS',
        },
      },
      {
        type: 'div',
        props: {
          style: {
            display: 'flex',
            marginTop: 24,
            fontSize,
            color: COLORS.text,
            letterSpacing: '-0.02em',
            lineHeight: 1.15,
          },
          children: title,
        },
      },
    ],
    'Paymanshu Sharma',
    post.date.replaceAll('-', '.'),
  );
}

function normalizeDateValue(value, slug) {
  if (typeof value === 'string') return value;
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  throw new Error(`Blog post "${slug}" has an invalid date value.`);
}

function getPublishedBlogPosts() {
  if (!fs.existsSync(BLOG_DIR)) return [];

  return fs
    .readdirSync(BLOG_DIR)
    .filter((f) => BLOG_EXTENSIONS.has(path.extname(f)) && !f.startsWith('_'))
    .map((fileName) => {
      const slug = fileName.replace(path.extname(fileName), '');
      const filePath = path.join(BLOG_DIR, fileName);
      const { data } = matter(fs.readFileSync(filePath, 'utf8'));
      return {
        slug,
        filePath,
        title: data.title,
        date: normalizeDateValue(data.date, slug),
        published: data.published ?? true,
      };
    })
    .filter((post) => post.published);
}

/** True when `output` is missing or older than any of `sources`. */
function needsRebuild(output, sources) {
  if (process.env.OG_FORCE === 'true' || !fs.existsSync(output)) return true;
  const outputTime = fs.statSync(output).mtimeMs;
  return sources.some((src) => fs.existsSync(src) && fs.statSync(src).mtimeMs > outputTime);
}

async function renderToFile(element, outputPath) {
  const svg = await satori(element, { width: WIDTH, height: HEIGHT, fonts });
  const png = new Resvg(svg, { fitTo: { mode: 'width', value: WIDTH } }).render().asPng();
  fs.writeFileSync(outputPath, png);
}

async function main() {
  fs.mkdirSync(POSTS_OG_DIR, { recursive: true });

  const selfSources = [FONT_REGULAR, FONT_BOLD, path.join(ROOT_DIR, 'scripts', 'generate-og-images.mjs')];
  let rendered = 0;
  let skipped = 0;

  const defaultOut = path.join(OG_DIR, 'default.png');
  if (needsRebuild(defaultOut, selfSources)) {
    await renderToFile(defaultCard(), defaultOut);
    rendered += 1;
  } else {
    skipped += 1;
  }

  for (const post of getPublishedBlogPosts()) {
    const out = path.join(POSTS_OG_DIR, `${post.slug}.png`);
    if (needsRebuild(out, [...selfSources, post.filePath])) {
      await renderToFile(postCard(post), out);
      rendered += 1;
    } else {
      skipped += 1;
    }
  }

  console.log(`og images: ${rendered} rendered, ${skipped} up to date → public/og/`);
}

await main();
