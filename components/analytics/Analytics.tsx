'use client';

import Script from 'next/script';
import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import {
  GA_DEBUG,
  GA_ID,
  analyticsEnabled,
  reportSectionTimings,
  sectionTimer,
  trackPageView,
} from '@/lib/analytics';

/**
 * Loads gtag.js and owns the page-level analytics lifecycle:
 * manual page_view on SPA navigation, tab-visibility pause/resume of the
 * section timer, and a final flush on pagehide.
 *
 * Renders nothing (and loads no script) when NEXT_PUBLIC_GA_ID is unset.
 */
export default function Analytics() {
  const pathname = usePathname();
  const previousPath = useRef<string | null>(null);

  // page_view per route, and flush the previous route's section timings so
  // dwell time is attributed to the page it happened on.
  useEffect(() => {
    if (!analyticsEnabled() || !pathname) {
      return;
    }

    const from = previousPath.current;
    if (from && from !== pathname) {
      reportSectionTimings(sectionTimer.flush(), from);
    }

    previousPath.current = pathname;
    trackPageView(pathname);
  }, [pathname]);

  // Backgrounded tabs are not engagement; a hidden tab may also never fire
  // pagehide, so flush there too.
  useEffect(() => {
    if (!analyticsEnabled()) {
      return;
    }

    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        sectionTimer.pauseAll();
        reportSectionTimings(sectionTimer.flush(), previousPath.current ?? '/');
      } else {
        sectionTimer.resumeAll();
      }
    };

    const onPageHide = () => {
      sectionTimer.pauseAll();
      reportSectionTimings(sectionTimer.flush(), previousPath.current ?? '/');
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', onPageHide);

    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', onPageHide);
    };
  }, []);

  if (!analyticsEnabled()) {
    return null;
  }

  return (
    <>
      <Script
        src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`}
        strategy="afterInteractive"
      />
      <Script id="ga-init" strategy="afterInteractive">
        {`
          window.dataLayer = window.dataLayer || [];
          function gtag(){dataLayer.push(arguments);}
          window.gtag = gtag;
          gtag('js', new Date());
          gtag('config', '${GA_ID}', {
            send_page_view: false,
            transport_type: 'beacon'${GA_DEBUG ? ",\n            debug_mode: true" : ''}
          });
        `}
      </Script>
    </>
  );
}
