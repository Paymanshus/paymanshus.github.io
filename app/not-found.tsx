import type { Metadata } from 'next';
import Link from 'next/link';
import SiteShell from '@/components/SiteShell';

export const metadata: Metadata = {
  title: 'Not found',
  robots: { index: false },
};

export default function NotFound() {
  return (
    <SiteShell>
      <div className="relative flex min-h-[80vh] w-full items-center">
        <div className="mx-auto max-w-4xl">
          <h1 className="mb-4 text-4xl font-light tracking-tight">404</h1>
          <p className="mb-12 max-w-2xl font-serif text-xl italic leading-relaxed text-text-secondary">
            That page doesn&apos;t exist. Try one of these instead.
          </p>
          <div className="flex flex-col gap-4 font-mono text-sm uppercase tracking-[0.22em]">
            <Link href="/" className="text-text-secondary transition-colors hover:text-brand-red">
              Home
            </Link>
            <Link
              href="/experience/"
              className="text-text-secondary transition-colors hover:text-brand-red"
            >
              Experience
            </Link>
            <Link
              href="/thoughts/"
              className="text-text-secondary transition-colors hover:text-brand-red"
            >
              Thoughts
            </Link>
          </div>
        </div>
      </div>
    </SiteShell>
  );
}
