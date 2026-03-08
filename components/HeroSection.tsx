'use client';

import Link from 'next/link';
import { motion } from 'motion/react';
import RippleGrid from './RippleGrid';

export default function HeroSection() {
  const name = 'PAYMANSHU SHARMA';
  const nameLines = ['PAYMANSHU', 'SHARMA'];
  const descriptorSegments = ['Developer & Architect', 'Bangalore', 'Systems & Interaction'];

  const container = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.05,
        delayChildren: 0.2,
      }
    }
  };

  const item = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 300, damping: 24 } }
  };

  return (
    <div className="relative h-full w-full overflow-hidden">
      <div className="fixed inset-0 z-0 bg-bg">
        <div className="absolute inset-0 bg-[linear-gradient(to_bottom,#040404_0%,#050505_34%,#010101_100%)]" />
        <div className="landing-grid-shell">
          <div className="landing-grid-floor">
            <RippleGrid
              gridColor="#ff2a2a"
              rippleIntensity={0.055}
              gridSize={10}
              gridThickness={16}
              fadeDistance={1.2}
              vignetteStrength={2.2}
              glowIntensity={0.14}
              opacity={0.9}
              mouseInteractionRadius={0.7}
            />
          </div>
        </div>
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_10%,transparent_0%,transparent_42%,rgba(0,0,0,0.45)_76%,rgba(0,0,0,0.9)_100%)]" />
      </div>

      <div className="relative z-10 flex h-full w-full flex-col justify-center pb-28 pt-24">
        <div className="max-w-5xl">
          <motion.h1
            aria-label={name}
            variants={container}
            initial="hidden"
            animate="show"
            className="mb-8 flex flex-col items-start text-[clamp(3.1rem,10vw,9rem)] font-black uppercase leading-[0.84] tracking-[-0.085em] text-white [text-shadow:0_0_22px_rgba(255,42,42,0.16)] [-webkit-text-stroke:1px_rgba(255,42,42,0.2)]"
          >
            {nameLines.map((line) => (
              <span key={line} className="inline-flex max-w-full whitespace-nowrap">
                {line.split('').map((char, index) => (
                  <motion.span
                    key={`${line}-${index}`}
                    variants={item}
                    className={char === ' ' ? 'w-[0.3em]' : ''}
                  >
                    {char}
                  </motion.span>
                ))}
              </span>
            ))}
          </motion.h1>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.45, ease: 'easeOut' }}
            className="mb-10 flex max-w-4xl flex-wrap items-center gap-x-3 gap-y-2 font-mono text-[0.72rem] uppercase tracking-[0.34em] text-brand-red/90 md:text-sm md:tracking-[0.42em]"
          >
            {descriptorSegments.map((segment, index) => (
              <span key={segment} className="flex items-center gap-x-3">
                <span>{segment}</span>
                {index < descriptorSegments.length - 1 && <span className="text-brand-red/55">/</span>}
              </span>
            ))}
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.7 }}
          >
            <div className="flex flex-wrap items-center gap-6">
              <Link
                href="/experience"
                className="group relative overflow-hidden border border-border px-6 py-3 font-mono text-sm uppercase tracking-widest transition-colors duration-300 hover:border-brand-red/50"
              >
                <div className="absolute inset-0 translate-y-full bg-brand-red/10 transition-transform duration-300 ease-out group-hover:translate-y-0" />
                <span className="relative z-10 flex items-center gap-2">
                  <span className="text-brand-red">&gt;</span> Initialize Experience
                </span>
              </Link>

              <Link
                href="/thoughts"
                className="group flex items-center gap-2 font-mono text-sm uppercase tracking-widest text-text-secondary transition-colors duration-300 hover:text-text-primary"
              >
                <span className="-ml-4 text-brand-red opacity-0 transition-all duration-300 group-hover:ml-0 group-hover:opacity-100">&gt;</span>
                Read Thoughts
              </Link>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
