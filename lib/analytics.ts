/**
 * GA4 analytics helpers.
 *
 * Everything here degrades to a no-op when `NEXT_PUBLIC_GA_ID` is unset (dev
 * builds stay clean and no gtag request is ever made). The section timer is
 * deliberately free of browser/GA wiring so it can be unit-tested — see
 * tests/seo/section-timer.test.mjs.
 */

export const GA_ID = process.env.NEXT_PUBLIC_GA_ID ?? '';
export const GA_DEBUG = process.env.NEXT_PUBLIC_GA_DEBUG === 'true';

/** Minimum dwell time before a section counts — filters out scroll-throughs. */
export const MIN_SECTION_MS = 1000;

type GtagParams = Record<string, string | number | boolean>;

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
    dataLayer?: unknown[];
  }
}

export function analyticsEnabled() {
  return GA_ID.length > 0;
}

export function trackEvent(name: string, params: GtagParams = {}) {
  if (typeof window === 'undefined' || typeof window.gtag !== 'function') {
    return;
  }

  window.gtag('event', name, GA_DEBUG ? { ...params, debug_mode: true } : params);
}

export function trackPageView(path: string) {
  if (typeof window === 'undefined' || typeof window.gtag !== 'function') {
    return;
  }

  window.gtag('event', 'page_view', {
    page_path: path,
    page_location: window.location.href,
    page_title: document.title,
    ...(GA_DEBUG ? { debug_mode: true } : {}),
  });
}

export type SectionTiming = {
  section: string;
  ms: number;
};

export type SectionTimer = ReturnType<typeof createSectionTimer>;

/**
 * Accumulates visible-time per section.
 *
 * Sections overlap freely (an article body and its page shell can both be
 * running), so each tracked section keeps its own start timestamp and running
 * total. `pauseAll`/`resumeAll` back the tab-visibility handling: time spent
 * on a backgrounded tab is not engagement.
 */
export function createSectionTimer(nowFn: () => number = () => Date.now()) {
  const totals = new Map<string, number>();
  const running = new Map<string, number>();
  let paused = false;

  function start(section: string) {
    if (running.has(section)) {
      return;
    }
    running.set(section, paused ? Number.NaN : nowFn());
  }

  function accumulate(section: string, startedAt: number) {
    if (Number.isNaN(startedAt)) {
      return;
    }
    const elapsed = nowFn() - startedAt;
    if (elapsed > 0) {
      totals.set(section, (totals.get(section) ?? 0) + elapsed);
    }
  }

  function stop(section: string) {
    const startedAt = running.get(section);
    if (startedAt === undefined) {
      return;
    }
    accumulate(section, startedAt);
    running.delete(section);
  }

  function pauseAll() {
    if (paused) {
      return;
    }
    paused = true;
    for (const [section, startedAt] of running) {
      accumulate(section, startedAt);
      running.set(section, Number.NaN);
    }
  }

  function resumeAll() {
    if (!paused) {
      return;
    }
    paused = false;
    const now = nowFn();
    for (const section of running.keys()) {
      running.set(section, now);
    }
  }

  /** Returns accumulated timings and resets, leaving running sections running. */
  function flush(): SectionTiming[] {
    const now = nowFn();
    for (const [section, startedAt] of running) {
      accumulate(section, startedAt);
      running.set(section, paused ? Number.NaN : now);
    }

    const timings = [...totals.entries()].map(([section, ms]) => ({ section, ms }));
    totals.clear();
    return timings;
  }

  function isRunning(section: string) {
    return running.has(section);
  }

  return { start, stop, pauseAll, resumeAll, flush, isRunning };
}

/**
 * Process-wide timer shared by <Analytics> (which flushes it) and
 * useSectionView (which starts/stops sections). Safe at module scope: it
 * touches no browser API until a section actually starts.
 */
export const sectionTimer = createSectionTimer();

/** Sends one `section_time` event per section with ≥ MIN_SECTION_MS of dwell. */
export function reportSectionTimings(timings: SectionTiming[], pagePath: string) {
  for (const { section, ms } of timings) {
    if (ms < MIN_SECTION_MS) {
      continue;
    }
    trackEvent('section_time', {
      section,
      seconds: Math.round(ms / 1000),
      page_path: pagePath,
    });
  }
}
