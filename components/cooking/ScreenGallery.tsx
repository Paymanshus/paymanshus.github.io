'use client';

import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import type { ProjectImage } from '@/lib/cooking';
import { metaClass } from '@/components/cooking/shared';

const stepButton =
  'flex h-9 w-9 items-center justify-center border border-border bg-bg/80 font-mono text-sm text-text-secondary transition-colors duration-300 hover:border-brand-red hover:text-brand-red';

/**
 * One large viewer plus a row of selectable thumbnails. Phone and desktop
 * captures share one fixed-ratio stage (letterboxed), so switching between
 * them never shifts the layout. Left/right arrow keys step through.
 */
export default function ScreenGallery({ images }: { images: ProjectImage[] }) {
  const [active, setActive] = useState(0);
  const count = images.length;
  const step = (delta: number) => setActive((current) => (current + delta + count) % count);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'ArrowRight') setActive((current) => (current + 1) % count);
      if (event.key === 'ArrowLeft') setActive((current) => (current - 1 + count) % count);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [count]);

  const image = images[active];

  return (
    <div>
      <div className="relative aspect-[16/10] overflow-hidden border border-border bg-bg">
        <AnimatePresence mode="wait" initial={false}>
          <motion.img
            key={image.src}
            src={image.src}
            alt={image.alt}
            width={image.width}
            height={image.height}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="absolute inset-0 h-full w-full object-contain"
          />
        </AnimatePresence>
        {count > 1 ? (
          <div className="absolute bottom-3 right-3 flex gap-2">
            <button type="button" onClick={() => step(-1)} aria-label="Previous screenshot" className={stepButton}>
              {'<'}
            </button>
            <button type="button" onClick={() => step(1)} aria-label="Next screenshot" className={stepButton}>
              {'>'}
            </button>
          </div>
        ) : null}
      </div>

      <div className="mt-3 flex items-start justify-between gap-6">
        <p className="text-sm leading-relaxed text-text-secondary">{image.alt}</p>
        <p className={`${metaClass} shrink-0`}>
          {String(active + 1).padStart(2, '0')} / {String(count).padStart(2, '0')}
        </p>
      </div>

      {count > 1 ? (
        <ul className="mt-4 flex flex-wrap gap-2" aria-label="Screenshots">
          {images.map((thumb, index) => (
            <li key={thumb.src}>
              <button
                type="button"
                onClick={() => setActive(index)}
                aria-label={`Show screenshot ${index + 1}: ${thumb.alt}`}
                aria-current={index === active}
                className={`block border bg-bg p-0.5 transition-colors duration-300 ${
                  index === active ? 'border-brand-red' : 'border-border opacity-60 hover:opacity-100'
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={thumb.src} alt="" width={thumb.width} height={thumb.height} className="h-12 w-auto sm:h-14" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
