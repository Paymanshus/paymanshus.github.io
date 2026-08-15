# Blog Visuals — reference copy

> Mirror of `.claude/skills/blog-figures/SKILL.md`, kept so this workflow still
> works on a machine where the skill isn't loaded. If the skill is available,
> invoke it instead. Keep the two in sync — `tests/blog/blog-content.test.mjs`
> asserts they match.

# Blog figures

Inline SVG embedded in the post markdown. No external files, no chart libraries —
the site is statically exported and must render offline.

Authoritative tokens: `app/globals.css`. Design rules: `readmes/SPECs/DESIGN_SPEC.md`.

## Three constraints that break figures silently

1. **No blank lines inside `<figure>`.** Markdown ends a raw-HTML block at the
   first blank line, then dumps the rest of the SVG on the page as literal text.
2. **Keep `sanitize: false` in `lib/blog.ts`.** `remark-html` strips raw HTML by
   default, removing SVG entirely. Safe here: posts are repo-authored, never user input.
3. **Self-contained only.** No `<img>`, no `http` URLs, no web fonts. Use
   `font-family="ui-monospace, monospace"`.

`tests/blog/blog-content.test.mjs` enforces all three.

## Tokens

| Role | Value |
|---|---|
| Figure background | `#0a0a0a` (full-bleed `<rect>`, first child) |
| Neutral fill / alt | `#242424` / `#2e2e2e` |
| Stroke | `#1a1a1a` |
| Text primary / secondary | `#f5f5f5` / `#8a8a8a` |
| Brand red | `#ff2a2a` |

**Red marks the one thing the figure is about** — the field that differs, the
value that crosses a threshold. Two reds means two points; make two figures.
Use `opacity="0.85"`, dropping to `0.45` for a lesser instance of the same thing.

## Structure

```html
<figure class="post-figure">
<svg viewBox="0 0 760 250" role="img" aria-label="Full sentence with the actual numbers, for screen readers.">
  <rect width="760" height="250" fill="#0a0a0a"/>
  <g font-family="ui-monospace, monospace" font-size="11">
    <text x="20" y="26" fill="#8a8a8a" letter-spacing="1.6">SECTION LABEL</text>
  </g>
</svg>
<figcaption>The takeaway, not a description of the picture.</figcaption>
</figure>
```

`viewBox` width 760, height to fit; CSS scales it. `role`/`aria-label` required
and tested. `.post-figure` styling already exists in `globals.css` — don't inline styles.

## Geometry

The likeliest bug is a bar or reference line in the wrong place — invisible
unless checked. (Real case: a "24 GB" line drawn at x=592 on a 19 px/GB scale
from origin 88 was actually 26.5 GB. Every bar was right; only the line was wrong.)

Fix a scale, derive every coordinate, verify before rendering:

```bash
python3 -c "
x0, s = 88, 19.0   # origin, px per unit
for label, v in [('batch 4',22),('24 GB line',24),('batch 8',30)]:
    print(f'{label:12} -> x={x0+v*s:.0f}')"
```

Put value labels in a fixed right-hand column (e.g. `x=690`), not trailing each
bar, or they collide with threshold lines.

## Verify visually — required

Element counts are not verification.

```bash
nvm use   # Node 22; Node 23 crashes next build
node .claude/skills/blog-figures/render-figures.mjs content/blog/<post>.md
```

Read the PNGs back as images. Both real bugs so far were caught only here.

## Templates

`templates/bar-comparison.svg` (segmented bars: how a fixed budget divides) and
`templates/stacked-bar.svg` (fixed + growing component vs a threshold). Both live
in `content/blog/llm-optimization-memory-gpu-cpu.md`.

## Checklist

1. Confirm tokens in `globals.css`
2. Decide the one takeaway — that gets red
3. Fix a scale, compute coordinates, verify arithmetic
4. Write with no blank lines inside `<figure>`
5. Render to PNG and look at it
6. `npm run test:unit`
