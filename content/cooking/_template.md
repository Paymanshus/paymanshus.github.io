---
# Copy this file to <slug>.md, fill it in, then add <slug> to _order.txt.
# Files starting with "_" are never shown.
title: Project Name
summary: One sentence. It shows on the card and under the title in the detail view.
date: 2026-01-01            # last meaningful update, YYYY-MM-DD
status: building            # building | early
stack: [Tool, Framework, Model]
repo: https://github.com/Paymanshus/repo   # omit for private repos ("private repo" is shown)
live: https://example.com                  # optional
# Images live in public/cooking/<slug>/. Convert with:
#   node scripts/optimize-cooking-media.mjs <in.png> public/cooking/<slug>/<name>.webp [maxW] [maxH]
# and copy the printed size into width/height.
thumbnail:                  # card image, 16:9 crop; omit for a "visual pending" frame
  src: /cooking/slug/thumb.webp
  alt: What the image shows.
  width: 1600
  height: 900
hero:                       # optional; top of the detail view, defaults to the thumbnail
  src: /cooking/slug/hero.webp
  alt: What the image shows.
  width: 1600
  height: 900
media:                      # optional screenshot gallery at the bottom of the detail view
  - src: /cooking/slug/screen-1.webp
    alt: Caption shown under the screenshot.
    width: 1600
    height: 1000
---

The writeup. It renders with the blog's reading styles, so it can run a few minutes long: use
`##` headings, lists, quotes and code.

Images between paragraphs work as plain Markdown:

![Caption text](/cooking/slug/diagram.webp)

Inline SVG figures work the same way as in blog posts (see readmes/SPECs/BLOG_VISUALS.md).
