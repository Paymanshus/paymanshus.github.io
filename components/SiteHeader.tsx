'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion } from 'motion/react';
import { Terminal } from 'lucide-react';

const navItems = [
  { href: '/', label: 'hi', key: 'hi' },
  { href: '/experience', label: 'experience', key: 'experience' },
  { href: '/thoughts', label: 'thoughts', key: 'thoughts' },
] as const;

function getActiveKey(pathname: string) {
  if (pathname.startsWith('/thoughts')) {
    return 'thoughts';
  }

  if (pathname.startsWith('/experience')) {
    return 'experience';
  }

  return 'hi';
}

export default function SiteHeader() {
  const pathname = usePathname();
  const activeKey = getActiveKey(pathname);

  return (
    <nav className="relative z-50 flex items-center justify-between py-8">
      <Link href="/" className="flex items-center gap-2">
        {/* <Terminal className="h-5 w-5 text-brand-red" /> */} {/* Let this stay commented */}
        <motion.span
          className="font-mono text-base md:text-lg tracking-wider uppercase"
          style={{ color: '#ffffff' }}
          whileHover={{ color: '#ff2a2a', scale: 1.05 }}
          transition={{ type: 'spring', stiffness: 260, damping: 20 }}
        >
          PS
        </motion.span>
      </Link>

      <div className="flex items-center gap-5 font-mono text-xs tracking-[0.28em] text-text-secondary md:gap-8 md:text-sm">
        {navItems.map((item) => {
          const isActive = activeKey === item.key;

          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? 'page' : undefined}
              className={`relative py-2 transition-colors duration-300 ${isActive ? 'text-text-primary' : 'hover:text-text-primary'
                }`}
            >
              {item.label}
              {isActive ? (
                <motion.span
                  layoutId="nav-indicator"
                  className="absolute inset-x-0 bottom-0 h-px bg-brand-red glow-box"
                  initial={false}
                  transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                />
              ) : null}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
