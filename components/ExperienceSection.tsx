'use client';

import dynamic from 'next/dynamic';
import { useEffect, useRef, useState, useTransition } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { FileText, Terminal, Mic } from 'lucide-react';
import { sectionTimer, trackEvent } from '@/lib/analytics';
import { useSectionView } from '@/hooks/useSectionView';

type ResumeMode = 'pdf' | 'chat' | 'voice';

function ResumePanelFallback({ label }: { label: string }) {
  return (
    <div className="flex h-full min-h-0 items-center justify-center bg-surface/20 px-6">
      <p className="font-mono text-xs uppercase tracking-[0.24em] text-text-secondary">
        {label}
      </p>
    </div>
  );
}

const HtmlResume = dynamic(() => import('./resume/HtmlResume'), {
  loading: () => <ResumePanelFallback label="Loading Resume" />,
  ssr: false,
});

// The 'pdf' key predates the HTML resume; it stays so the resume_mode_change
// and resume:pdf analytics series continue unbroken.
const MODE_LABELS: Record<ResumeMode, string> = {
  pdf: 'resume',
  chat: 'chat',
  voice: 'voice',
};

const ChatResume = dynamic(() => import('./resume/ChatResume'), {
  loading: () => <ResumePanelFallback label="Loading Terminal Interface" />,
  ssr: false,
});

const VoiceResume = dynamic(() => import('./resume/VoiceResume'), {
  loading: () => <ResumePanelFallback label="Loading Voice Interface" />,
  ssr: false,
});

export default function ExperienceSection() {
  const [mode, setMode] = useState<ResumeMode>('chat');
  const [isPending, startTransition] = useTransition();
  const sectionRef = useSectionView<HTMLDivElement>('experience');
  const panelRef = useRef<HTMLDivElement>(null);

  // One timer section per resume mode, so "time in voice" is separable from
  // "time on /experience". Only the active mode's clock runs.
  useEffect(() => {
    const section = `resume:${mode}`;
    sectionTimer.start(section);
    return () => sectionTimer.stop(section);
  }, [mode]);

  const selectMode = (next: ResumeMode) => {
    if (next !== mode) {
      trackEvent('resume_mode_change', { mode: next });
    }
    startTransition(() => setMode(next));
    // On phones the panel starts below the fold, which hid the voice call's
    // end button and the terminal prompt. Bring the whole panel into view.
    if (window.matchMedia('(max-width: 767px)').matches) {
      panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  };

  return (
    <div ref={sectionRef} className="flex h-full min-h-[80svh] w-full flex-col">
      <div className="mb-12 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-4xl font-light tracking-tight mb-2">Experience</h1>
          <p className="text-brand-red font-mono text-xs tracking-widest uppercase">{'// Select Interface Mode'}</p>
        </div>
        
        {/* Pill Toggle */}
        <div className="flex w-full sm:w-auto bg-surface border border-border rounded-full p-1 relative">
          {(['pdf', 'chat', 'voice'] as ResumeMode[]).map((m) => (
            <button
              key={m}
              onClick={() => selectMode(m)}
              className={`relative flex-1 sm:flex-none justify-center px-3 sm:px-6 py-2 rounded-full text-xs font-mono uppercase tracking-widest transition-colors duration-300 z-10 flex items-center gap-2 ${
                mode === m ? 'text-bg' : 'text-text-secondary hover:text-brand-red'
              }`}
            >
              {m === 'pdf' && <FileText className="w-3 h-3 max-[359px]:hidden" />}
              {m === 'chat' && <Terminal className="w-3 h-3 max-[359px]:hidden" />}
              {m === 'voice' && <Mic className="w-3 h-3 max-[359px]:hidden" />}
              {MODE_LABELS[m]}
              {mode === m && (
                <motion.div
                  layoutId="mode-pill"
                  className="absolute inset-0 bg-text-primary rounded-full -z-10"
                  initial={false}
                  transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                />
              )}
            </button>
          ))}
        </div>
      </div>

      <div
        ref={panelRef}
        className="relative min-h-[80svh] flex-1 overflow-hidden border border-border bg-surface/30"
      >
        {isPending ? (
          <div className="pointer-events-none absolute inset-x-0 top-0 z-20 h-px bg-brand-red/70" />
        ) : null}
        <AnimatePresence mode="wait">
          {mode === 'pdf' && (
            <motion.div
              key="pdf"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              // In flow, unlike the other modes: the resume is as tall as
              // it is and the panel grows with it.
              className="relative"
            >
              <HtmlResume />
            </motion.div>
          )}
          {mode === 'chat' && (
            <motion.div
              key="chat"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="absolute inset-0 min-h-0"
            >
              <ChatResume />
            </motion.div>
          )}
          {mode === 'voice' && (
            <motion.div
              key="voice"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="absolute inset-0 min-h-0"
            >
              <VoiceResume onUseTerminal={() => selectMode('chat')} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
