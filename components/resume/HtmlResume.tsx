'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ExternalLink } from 'lucide-react';

// Both files are the owner's own exports, dropped into public/assets as-is.
// The PDF URL is the one shared with recruiters and on profiles — keep it.
const PDF_URL = '/assets/Paymanshu_Sharma_Resume.pdf';
const HTML_URL = '/assets/Paymanshu_Sharma_Resume.html';

// Screen-only adjustments injected into the HTML resume. The file is built
// for print (fixed A4 width, point sizes, its own paper colour), so here it
// is let out to the panel: transparent paper, a touch larger on wide
// screens, and reflowing on phones instead of scrolling sideways. Injected
// rather than edited in, so a fresh export can replace the file untouched.
// iOS Safari "text autosizing" otherwise inflates the bullets to about twice
// their size inside the frame, so text-size-adjust is pinned to 100%.
const EMBED_CSS = `
html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }
html, body { background: transparent !important; }
html { scrollbar-width: none; }
main { width: auto !important; max-width: 210mm; zoom: 1.12; }
@media (max-width: 640px) {
  main { zoom: 1.08; padding: 20px 16px 24px !important; }
  .row { flex-wrap: wrap; column-gap: 12pt; }
  /* The separators are white-space: pre, which left the links line with no
     break point at all on a phone */
  .contact .sep { white-space: normal; }
}
`;

function prepareDocument(doc: Document) {
  if (!doc.getElementById('site-embed')) {
    const style = doc.createElement('style');
    style.id = 'site-embed';
    style.textContent = EMBED_CSS;
    doc.head.append(style);
  }
  // Links must leave the frame: web links in a new tab, mail/phone at the
  // top level (where the OS handler picks them up).
  for (const a of doc.querySelectorAll<HTMLAnchorElement>('a[href]')) {
    if (/^https?:/i.test(a.getAttribute('href') ?? '')) {
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
    } else {
      a.target = '_top';
    }
  }
}

export default function HtmlResume() {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const [ready, setReady] = useState(false);

  // The frame is sized to its content, so the resume scrolls with the page
  // rather than as a box inside a box (which traps the scroll on phones).
  const handleLoad = useCallback(() => {
    const frame = frameRef.current;
    const doc = frame?.contentDocument;
    const win = frame?.contentWindow as (Window & typeof globalThis) | null;
    if (!frame || !doc || !win) return;

    prepareDocument(doc);
    // The body's box, not documentElement.scrollHeight: the latter never
    // reports less than the frame's current height, so it could only grow.
    const fit = () => {
      frame.style.height = `${Math.ceil(doc.body.getBoundingClientRect().height)}px`;
    };
    fit();
    observerRef.current?.disconnect();
    observerRef.current = new win.ResizeObserver(fit);
    observerRef.current.observe(doc.body);
    setReady(true);
  }, []);

  useEffect(() => () => observerRef.current?.disconnect(), []);

  return (
    <div className="flex w-full flex-col">
      {/* Lined up with the resume's own margins: 210mm and its 0.42in
          padding, both at the 1.12 zoom above. */}
      <div className="mx-auto flex w-full max-w-[889px] flex-wrap items-center justify-between gap-4 px-[18px] pb-2 pt-6 sm:px-[45px] sm:pt-8">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-text-secondary">
          {'// Resume'}
        </p>
        <a
          href={PDF_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="group relative inline-flex items-center justify-center px-6 py-2 font-mono text-xs tracking-widest uppercase border border-brand-red text-brand-red overflow-hidden transition-colors hover:text-bg"
        >
          <span className="absolute inset-0 w-full h-full -translate-x-full bg-brand-red group-hover:translate-x-0 transition-transform duration-300 ease-out" />
          <span className="relative z-10 flex items-center gap-2">
            Get the PDF <ExternalLink className="w-3 h-3" />
          </span>
        </a>
      </div>

      <div className="relative">
        {!ready && (
          <p className="absolute inset-x-0 top-16 text-center font-mono text-xs uppercase tracking-[0.24em] text-text-secondary">
            Loading resume
          </p>
        )}
        {/* Loaded eagerly: the panel sits below the fold, and a lazy frame
            stayed blank until the visitor happened to scroll. */}
        <iframe
          ref={frameRef}
          src={HTML_URL}
          onLoad={handleLoad}
          title="Paymanshu Sharma resume"
          scrolling="no"
          className={`block h-[80svh] w-full border-none transition-opacity duration-300 ${
            ready ? 'opacity-100' : 'opacity-0'
          }`}
        />
      </div>
    </div>
  );
}
