'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, LayoutGroup, MotionConfig } from 'motion/react';
import type { Project } from '@/lib/cooking';
import { trackEvent } from '@/lib/analytics';
import ProjectCard from '@/components/cooking/ProjectCard';
import ProjectModal from '@/components/cooking/ProjectModal';

/**
 * Card grid plus the detail view. The open project lives in the URL hash
 * (/cooking/#cerebro), so a detail view can be linked directly and the
 * browser back button closes it.
 */
export default function CookingGallery({ projects }: { projects: Project[] }) {
  const [openSlug, setOpenSlug] = useState<string | null>(null);
  // True when opening pushed a history entry, so closing should pop it.
  const pushedRef = useRef(false);

  useEffect(() => {
    const syncFromHash = () => {
      const slug = decodeURIComponent(window.location.hash.slice(1));
      setOpenSlug(projects.some((project) => project.slug === slug) ? slug : null);
      if (!slug) pushedRef.current = false;
    };
    syncFromHash();
    window.addEventListener('popstate', syncFromHash);
    return () => window.removeEventListener('popstate', syncFromHash);
  }, [projects]);

  const open = useCallback((slug: string) => {
    window.history.pushState(null, '', `#${slug}`);
    pushedRef.current = true;
    setOpenSlug(slug);
    trackEvent('cooking_open', { project: slug });
  }, []);

  const close = useCallback(() => {
    if (pushedRef.current) {
      pushedRef.current = false;
      window.history.back();
    } else {
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
    setOpenSlug(null);
  }, []);

  const openIndex = projects.findIndex((project) => project.slug === openSlug);

  return (
    <MotionConfig reducedMotion="user">
      <LayoutGroup>
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
          {projects.map((project, index) => (
            <ProjectCard key={project.slug} project={project} index={index} onOpen={open} />
          ))}
        </div>

        <AnimatePresence>
          {openIndex >= 0 ? (
            <ProjectModal key={openSlug} project={projects[openIndex]} index={openIndex} onClose={close} />
          ) : null}
        </AnimatePresence>
      </LayoutGroup>
    </MotionConfig>
  );
}
