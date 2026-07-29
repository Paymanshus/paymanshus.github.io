'use client';

import { useEffect } from 'react';
import { analyticsEnabled, sectionTimer, trackEvent } from '@/lib/analytics';

const SCROLL_THRESHOLDS = [25, 50, 75, 100] as const;

type PageEngagementProps = {
  /** Timer bucket, e.g. 'home_hero', 'thoughts_index', 'article:my-slug'. */
  section: string;
  /** Emit scroll_depth milestones — worth it on long-form pages only. */
  scrollDepth?: boolean;
};

/**
 * Drop-in engagement tracking for server-rendered pages: accumulates dwell
 * time for `section` while mounted and (optionally) reports scroll milestones.
 * Renders nothing; inert without NEXT_PUBLIC_GA_ID.
 *
 * Sections that only occupy part of a page should use `useSectionView`
 * instead, which gates on actual visibility.
 */
export default function PageEngagement({ section, scrollDepth = false }: PageEngagementProps) {
  useEffect(() => {
    if (!analyticsEnabled()) {
      return;
    }

    sectionTimer.start(section);
    trackEvent('section_view', { section });

    return () => sectionTimer.stop(section);
  }, [section]);

  useEffect(() => {
    if (!analyticsEnabled() || !scrollDepth) {
      return;
    }

    const reached = new Set<number>();

    const onScroll = () => {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      // Pages shorter than the viewport are 100% read by definition.
      const percent =
        scrollable <= 0 ? 100 : ((window.scrollY + window.innerHeight) / document.documentElement.scrollHeight) * 100;

      for (const threshold of SCROLL_THRESHOLDS) {
        if (percent >= threshold && !reached.has(threshold)) {
          reached.add(threshold);
          trackEvent('scroll_depth', { percent: threshold, page_path: window.location.pathname });
        }
      }
    };

    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [scrollDepth, section]);

  return null;
}
