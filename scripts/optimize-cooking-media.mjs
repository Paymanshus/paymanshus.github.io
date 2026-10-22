/**
 * Convert raw project screenshots into web-ready WebP for /cooking.
 *
 *   node scripts/optimize-cooking-media.mjs <input.png> <public/cooking/...webp> [maxWidth] [maxHeight]
 *
 * Not part of the build: run it once per new image and commit the output.
 * Prints the final pixel size, which goes into the project's frontmatter so the
 * page can reserve space for the image before it loads.
 */
import path from 'node:path';
import fs from 'node:fs';
import sharp from 'sharp';

const [input, output, maxWidth = '1600', maxHeight = '1200'] = process.argv.slice(2);

if (!input || !output) {
  console.error('usage: optimize-cooking-media.mjs <input> <output.webp> [maxWidth] [maxHeight]');
  process.exit(1);
}

fs.mkdirSync(path.dirname(output), { recursive: true });
const info = await sharp(input)
  .resize({ width: Number(maxWidth), height: Number(maxHeight), fit: 'inside', withoutEnlargement: true })
  .webp({ quality: 82 })
  .toFile(output);

console.log(`${output}  ${info.width}x${info.height}  ${(info.size / 1024).toFixed(0)} KB`);
