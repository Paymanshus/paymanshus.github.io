import type { ReactNode } from 'react';
import SiteHeader from '@/components/SiteHeader';
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
    </div>
  );
}
