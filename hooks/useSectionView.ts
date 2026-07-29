'use client';

import { useEffect, useRef } from 'react';
import { analyticsEnabled, sectionTimer, trackEvent } from '@/lib/analytics';

/**
 * Tracks how long a section is actually on screen.
 *
 * Attach the returned ref to the section's root element. While ≥50% of it is
 * visible the shared section timer accumulates dwell time; the first time it
 * becomes visible a one-shot `section_view` event fires.
 *
 * The timer is flushed by <Analytics> on route change / tab hide / pagehide —
 * this hook only starts and stops sections.
 */
export function useSectionView<T extends HTMLElement = HTMLDivElement>(sectionId: string) {
  const ref = useRef<T>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element || !analyticsEnabled() || typeof IntersectionObserver === 'undefined') {
      return;
    }

    let hasReportedView = false;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            sectionTimer.start(sectionId);
            if (!hasReportedView) {
              hasReportedView = true;
              trackEvent('section_view', { section: sectionId });
            }
          } else {
            sectionTimer.stop(sectionId);
          }
        }
      },
      { threshold: 0.5 },
    );

    observer.observe(element);

    return () => {
      observer.disconnect();
      sectionTimer.stop(sectionId);
    };
  }, [sectionId]);

  return ref;
}

export default useSectionView;
