'use client';

import { useRef, type PointerEvent } from 'react';
import { motion, useMotionTemplate, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react';
import type { Project } from '@/lib/cooking';
import { ProjectLinks, StatusTag, metaClass, projectNumber } from '@/components/cooking/shared';

/** Peak tilt at the card's edge, in degrees. */
const MAX_TILT = 9;
const SPRING = { stiffness: 260, damping: 24, mass: 0.7 };

// 1px lines on a 24px lattice: grey at rest, and a red copy masked to a soft
// circle around the pointer so the grid "lights up" where you touch it.
const gridLines = (color: string) =>
  `linear-gradient(to right, ${color} 1px, transparent 1px), linear-gradient(to bottom, ${color} 1px, transparent 1px)`;

type ProjectCardProps = {
  project: Project;
  index: number;
  onOpen: (slug: string) => void;
};

/**
 * The card behaves like a flat metal plate and the pointer like a magnet: the
 * point under the pointer is pulled up toward the viewer and the opposite edge
 * dips away, so it reads as a weighted card tilting on its centre.
 */
export default function ProjectCard({ project, index, onOpen }: ProjectCardProps) {
  const reduceMotion = useReducedMotion();
  const plateRef = useRef<HTMLDivElement>(null);

  // Pointer position relative to the card centre, -0.5..0.5 on each axis.
  const px = useMotionValue(0);
  const py = useMotionValue(0);
  // Pointer position in px, for the glow mask.
  const gx = useMotionValue(0);
  const gy = useMotionValue(0);
  const hover = useSpring(0, SPRING);

  // CSS rotateX(+) pushes the top edge away and rotateY(+) pushes the right
  // edge away, so both signs are flipped to bring the pointed-at part closer.
  const rotateX = useSpring(useTransform(py, (v) => v * 2 * MAX_TILT), SPRING);
  const rotateY = useSpring(useTransform(px, (v) => -v * 2 * MAX_TILT), SPRING);
  const scale = useTransform(hover, [0, 1], [1, 1.025]);

  // Shadow falls away from the lifted side and spreads as the card rises.
  const shadowX = useTransform(px, (v) => -v * 28);
  const shadowY = useTransform(py, (v) => 18 - v * 28);
  const shadowBlur = useTransform(hover, [0, 1], [24, 56]);
  const boxShadow = useMotionTemplate`${shadowX}px ${shadowY}px ${shadowBlur}px -20px rgba(0, 0, 0, 0.95)`;

  const glowMask = useMotionTemplate`radial-gradient(200px circle at ${gx}px ${gy}px, #000 0%, transparent 72%)`;
  const glowWash = useMotionTemplate`radial-gradient(260px circle at ${gx}px ${gy}px, rgba(255, 42, 42, 0.08), transparent 70%)`;

  const track = (event: PointerEvent<HTMLElement>) => {
    const rect = plateRef.current?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    gx.set(event.clientX - rect.left);
    gy.set(event.clientY - rect.top);
    if (reduceMotion) {
      return;
    }
    px.set((event.clientX - rect.left) / rect.width - 0.5);
    py.set((event.clientY - rect.top) / rect.height - 0.5);
  };

  const engage = (event: PointerEvent<HTMLElement>) => {
    track(event);
    hover.set(1);
  };

  const release = () => {
    px.set(0);
    py.set(0);
    hover.set(0);
  };

  return (
    <motion.article
      layoutId={`cooking-card-${project.slug}`}
      className="relative"
      style={{ transformPerspective: 1000 }}
      onPointerEnter={engage}
      onPointerDown={engage}
      onPointerMove={track}
      onPointerLeave={release}
      onPointerUp={(event) => (event.pointerType === 'mouse' ? undefined : release())}
      onPointerCancel={release}
    >
      <motion.div
        ref={plateRef}
        className="group relative h-full overflow-hidden border border-border bg-surface transition-colors duration-300 hover:border-[#2e2e2e]"
        style={{ rotateX, rotateY, scale, boxShadow, transformPerspective: 1000 }}
      >
        {/* Grid at rest: faint grey, visible behind the text block. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{ backgroundImage: gridLines('rgba(255, 255, 255, 0.04)'), backgroundSize: '24px 24px' }}
        />

        <div className="relative aspect-video overflow-hidden border-b border-border bg-bg">
          {project.thumbnail ? (
            <motion.img
              layoutId={`cooking-image-${project.slug}`}
              src={project.thumbnail.src}
              alt={project.thumbnail.alt}
              width={project.thumbnail.width}
              height={project.thumbnail.height}
              loading="lazy"
              decoding="async"
              className="h-full w-full object-cover object-top"
            />
          ) : (
            <div className="flex h-full w-full flex-col justify-between p-5" aria-hidden="true">
              <span className={metaClass}>{'[ visual pending ]'}</span>
              <span className="text-3xl font-light tracking-tight text-[#2e2e2e]">{project.title}</span>
            </div>
          )}
        </div>

        {/* The same grid lit red under the pointer. Painted after the thumbnail
            so the glow crosses the image too, and before the text so copy stays clean. */}
        <motion.div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage: gridLines('rgba(255, 42, 42, 0.4)'),
            backgroundSize: '24px 24px',
            maskImage: glowMask,
            WebkitMaskImage: glowMask,
            opacity: hover,
          }}
        />
        <motion.div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{ backgroundImage: glowWash, opacity: hover }}
        />

        <div className="relative flex flex-col p-5 md:p-6">
          <div className={`${metaClass} flex items-center gap-4`}>
            <span>{projectNumber(index)}</span>
            <StatusTag status={project.status} />
            <span className="ml-auto">{project.displayDate}</span>
          </div>

          <h2 className="mt-4 text-2xl font-light tracking-tight transition-colors duration-300 group-hover:text-brand-red">
            {project.title}
          </h2>
          <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-text-secondary">{project.summary}</p>

          <div className="mt-6 flex items-end justify-between gap-4">
            <ProjectLinks project={project} />
            <span className={`${metaClass} shrink-0 transition-colors duration-300 group-hover:text-text-primary`}>
              {'[ open ]'}
            </span>
          </div>
        </div>

        {/* Stretched button: the whole card opens the detail view, while the
            links above it (z-10) stay independently clickable. */}
        <button
          type="button"
          onClick={() => onOpen(project.slug)}
          aria-label={`Open ${project.title}`}
          className="absolute inset-0 cursor-pointer focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-[-1px] focus-visible:outline-brand-red"
        />
      </motion.div>
    </motion.article>
  );
}
