'use client';

import { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import type { Project } from '@/lib/cooking';
import ScreenGallery from '@/components/cooking/ScreenGallery';
import { ProjectLinks, StatusTag, metaClass, projectNumber } from '@/components/cooking/shared';

type ProjectModalProps = {
  project: Project;
  index: number;
  onClose: () => void;
};

// The panel's own shared-layout morph runs first; the contents then rise in.
const reveal = {
  hidden: { opacity: 0, y: 12 },
  shown: (order: number) => ({ opacity: 1, y: 0, transition: { delay: 0.18 + order * 0.06, duration: 0.4 } }),
};

/** Small L-shaped ticks on the panel's corners: a viewfinder, not a border. */
function CornerTicks() {
  const tick = 'pointer-events-none absolute h-3 w-3 border-text-secondary/60';
  return (
    <>
      <span aria-hidden="true" className={`${tick} left-1.5 top-1.5 border-l border-t`} />
      <span aria-hidden="true" className={`${tick} right-1.5 top-1.5 border-r border-t`} />
      <span aria-hidden="true" className={`${tick} bottom-1.5 left-1.5 border-b border-l`} />
      <span aria-hidden="true" className={`${tick} bottom-1.5 right-1.5 border-b border-r`} />
    </>
  );
}

function SideFact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-border pt-4">
      <p className={metaClass}>{label}</p>
      <div className="mt-2 text-sm leading-relaxed text-text-primary/90">{children}</div>
    </div>
  );
}

/**
 * Detail view. Shares a layoutId with its card, so opening reads as the card
 * itself lifting off the grid, growing toward the viewer and settling into a
 * large panel. Escape, the close control and the backdrop all close it.
 */
export default function ProjectModal({ project, index, onClose }: ProjectModalProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const reduceMotion = useReducedMotion();
  const hero = project.hero ?? project.thumbnail;
  const titleId = `cooking-modal-title-${project.slug}`;
  const [landed, setLanded] = useState(false);

  // Fallback for opens with no morph to wait on (e.g. straight from a #slug link).
  useEffect(() => {
    const timer = setTimeout(() => setLanded(true), 900);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    closeRef.current?.focus({ preventScroll: true });

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);

    // Lock the page behind the panel; the panel scrolls on its own.
    const { overflow } = document.body.style;
    document.body.style.overflow = 'hidden';

    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      previousFocus?.focus({ preventScroll: true });
    };
  }, [onClose]);

  return (
    <>
      <motion.div
        aria-hidden="true"
        className="fixed inset-0 z-[60] bg-bg/85"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.25 }}
        onClick={onClose}
      />

      <div className="pointer-events-none fixed inset-0 z-[70] flex items-center justify-center p-2 sm:p-6">
        <motion.div
          layoutId={`cooking-card-${project.slug}`}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          className="pointer-events-auto relative flex h-[calc(100dvh-1rem)] w-full max-w-6xl flex-col overflow-hidden border border-[#2e2e2e] bg-surface sm:h-[min(88dvh,960px)]"
          style={{ boxShadow: '0 40px 120px -40px rgba(0, 0, 0, 1), 0 0 0 1px rgba(255, 42, 42, 0.06)' }}
          transition={{ type: 'spring', stiffness: 220, damping: 28, mass: 0.9 }}
          onLayoutAnimationComplete={() => setLanded(true)}
        >
          <CornerTicks />

          {/* One red scan pass on open: the "lift" lands, then the panel reads in.
              It waits for the morph to finish; started mid-morph, it ran inside the
              still card-sized panel on desktop and was never seen. */}
          {landed ? (
            <motion.span
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 top-0 z-20 h-px bg-brand-red/70"
              initial={{ y: 0, opacity: 0 }}
              animate={{ y: ['0dvh', '86dvh'], opacity: [0, 0.8, 0] }}
              transition={{ duration: 0.7, ease: 'easeOut' }}
            />
          ) : null}

          <header className="relative z-10 flex shrink-0 items-center justify-between gap-4 border-b border-border px-4 py-3 sm:px-6">
            <p className={`${metaClass} truncate normal-case tracking-[0.08em]`}>
              <span className="text-brand-red">{'>'}</span> ~/cooking/{project.slug}
            </p>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              className={`${metaClass} shrink-0 transition-colors duration-300 hover:text-brand-red active:text-brand-red focus-visible:text-brand-red focus-visible:outline-none`}
            >
              {'[ esc ] close'}
            </button>
          </header>

          <div className="relative flex-1 overflow-y-auto overscroll-contain">
            {project.video ? (
              <div className="border-b border-border bg-bg">
                <video
                  src={project.video.src}
                  poster={project.video.poster}
                  width={project.video.width}
                  height={project.video.height}
                  aria-label={project.video.alt}
                  // Reduced motion: hold on the poster and let the reader press play.
                  autoPlay={!reduceMotion}
                  controls={Boolean(reduceMotion)}
                  muted
                  loop
                  playsInline
                  preload="metadata"
                  className="mx-auto block max-h-[62dvh] w-full object-contain"
                />
              </div>
            ) : hero ? (
              <div className="border-b border-border bg-bg">
                <motion.img
                  // Morph from the card image only when it is the same picture.
                  layoutId={hero.src === project.thumbnail?.src ? `cooking-image-${project.slug}` : undefined}
                  src={hero.src}
                  alt={hero.alt}
                  width={hero.width}
                  height={hero.height}
                  className="mx-auto block max-h-[62dvh] w-full object-contain"
                />
              </div>
            ) : null}

            <div className="px-5 py-8 sm:px-10 sm:py-12">
              <div className="grid gap-12 lg:grid-cols-12">
                <div className="lg:col-span-8">
                  <motion.div
                    variants={reveal}
                    initial="hidden"
                    animate="shown"
                    custom={0}
                    className={`${metaClass} flex flex-wrap items-center gap-x-4 gap-y-2`}
                  >
                    <span>{projectNumber(index)}</span>
                    <StatusTag status={project.status} />
                    <span>{project.displayDate}</span>
                    <span>{project.readingTimeText}</span>
                  </motion.div>

                  <motion.h2
                    id={titleId}
                    variants={reveal}
                    initial="hidden"
                    animate="shown"
                    custom={1}
                    className="mt-5 text-4xl font-light tracking-tight md:text-5xl"
                  >
                    {project.title}
                  </motion.h2>
                  <motion.p
                    variants={reveal}
                    initial="hidden"
                    animate="shown"
                    custom={2}
                    className="mt-4 font-serif text-2xl italic leading-relaxed text-text-secondary"
                  >
                    {project.summary}
                  </motion.p>

                  <motion.div
                    variants={reveal}
                    initial="hidden"
                    animate="shown"
                    custom={3}
                    className="thought-post-content cooking-writeup mt-10"
                    dangerouslySetInnerHTML={{ __html: project.content }}
                  />
                </div>

                <motion.aside
                  variants={reveal}
                  initial="hidden"
                  animate="shown"
                  custom={4}
                  className="flex flex-col gap-6 self-start lg:sticky lg:top-8 lg:col-span-4"
                >
                  <SideFact label="Status">
                    <span className={metaClass}>
                      <StatusTag status={project.status} />
                    </span>
                  </SideFact>
                  <SideFact label="Last touched">{project.displayDate}</SideFact>
                  {project.stack.length > 0 ? (
                    <SideFact label="Stack">
                      <ul className="flex flex-wrap gap-2">
                        {project.stack.map((item) => (
                          <li key={item} className="border border-border px-2 py-1 font-mono text-[11px] text-text-secondary">
                            {item}
                          </li>
                        ))}
                      </ul>
                    </SideFact>
                  ) : null}
                  <SideFact label="Links">
                    <ProjectLinks project={project} />
                  </SideFact>
                </motion.aside>
              </div>

              {project.media.length > 0 ? (
                <motion.section
                  variants={reveal}
                  initial="hidden"
                  animate="shown"
                  custom={5}
                  className="mt-16 border-t border-border pt-8"
                  aria-label={`${project.title} screenshots`}
                >
                  <p className={`${metaClass} mb-5`}>{'// screens'}</p>
                  <ScreenGallery images={project.media} />
                </motion.section>
              ) : null}

              <p className={`${metaClass} mt-16 border-t border-border pt-6`}>{'// end of file'}</p>
            </div>
          </div>
        </motion.div>
      </div>
    </>
  );
}
