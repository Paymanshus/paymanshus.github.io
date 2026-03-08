'use client';

import { useEffect, useState } from 'react';
import { ExternalLink } from 'lucide-react';

export default function PdfResume() {
  const pdfUrl = '/assets/Paymanshu_Sharma_Resume.pdf';
  const [shouldLoadPdf, setShouldLoadPdf] = useState(false);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setShouldLoadPdf(true);
    });

    return () => window.cancelAnimationFrame(frame);
  }, []);

  return (
    <div className="w-full h-full flex flex-col relative">
      <div className="absolute top-4 right-4 z-10">
        <a
          href={pdfUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="group relative inline-flex items-center justify-center px-6 py-2 font-mono text-xs tracking-widest uppercase border border-brand-red text-brand-red overflow-hidden transition-colors hover:text-bg"
        >
          <span className="absolute inset-0 w-full h-full -translate-x-full bg-brand-red group-hover:translate-x-0 transition-transform duration-300 ease-out" />
          <span className="relative z-10 flex items-center gap-2">
            Open PDF <ExternalLink className="w-3 h-3" />
          </span>
        </a>
      </div>
      
      <div className="flex-1 w-full h-full bg-bg/50 flex items-center justify-center">
        {shouldLoadPdf ? (
          <iframe
            src={`${pdfUrl}#toolbar=0`}
            className="w-full h-full border-none"
            title="Resume PDF"
            loading="lazy"
          />
        ) : (
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-text-secondary">
            Preparing PDF Viewer
          </p>
        )}
      </div>
    </div>
  );
}
