import type { ReactNode } from 'react';
import SiteHeader from '@/components/SiteHeader';
import SiteFooter from '@/components/SiteFooter';
import { cn } from '@/lib/utils';

type SiteShellProps = {
  children: ReactNode;
  home?: boolean;
  mainClassName?: string;
};

export default function SiteShell({ children, home = false, mainClassName }: SiteShellProps) {
  return (
    <div className={cn('flex min-h-screen flex-col', home && 'h-screen overflow-hidden')}>
      <SiteHeader />
      <main className={cn('relative flex-1', mainClassName)}>{children}</main>
      {/* The home route is a fixed-height, non-scrolling hero — a footer there
          would be clipped by `overflow-hidden`. Its identity links live in the
          Person JSON-LD instead. */}
      {home ? null : <SiteFooter />}
    </div>
  );
}
