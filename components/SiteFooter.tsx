import Link from 'next/link';
import { siteConfig } from '@/lib/site';

/**
 * Site-wide footer.
 *
 * Beyond navigation, this is the site's identity anchor: the profile links
 * carry rel="me", which is what lets search engines and IndieWeb consumers
 * tie github.com/Paymanshus, LinkedIn and Hugging Face to this domain as the
 * same person. Keep them in sync with the `sameAs` list in personJsonLd().
 */
const profiles = [
  { href: siteConfig.links.github, label: 'GitHub' },
  { href: siteConfig.links.linkedin, label: 'LinkedIn' },
  { href: siteConfig.links.huggingface, label: 'Hugging Face' },
] as const;

const internalLinks = [
  { href: '/experience', label: 'Experience' },
  { href: '/thoughts', label: 'Thoughts' },
] as const;

export default function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-border py-12">
      <div className="flex flex-col gap-10 md:flex-row md:justify-between">
        <div className="max-w-sm">
          <p className="font-mono text-sm uppercase tracking-[0.22em] text-text-primary">
            {siteConfig.name}
          </p>
          <p className="mt-3 text-sm leading-relaxed text-text-secondary">
            {siteConfig.jobTitle} at {siteConfig.employer}, {siteConfig.location}. Building agentic
            AI and real-time voice systems.
          </p>
          <a
            href={`mailto:${siteConfig.email}`}
            className="mt-4 inline-block font-mono text-xs tracking-[0.18em] text-text-secondary transition-colors duration-300 hover:text-brand-red"
          >
            {siteConfig.email}
          </a>
        </div>

        <div className="flex gap-16">
          <nav aria-label="Site" className="flex flex-col gap-3">
            {internalLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="font-mono text-xs uppercase tracking-[0.18em] text-text-secondary transition-colors duration-300 hover:text-brand-red"
              >
                {link.label}
              </Link>
            ))}
            <Link
              href="/feed.xml"
              prefetch={false}
              className="font-mono text-xs uppercase tracking-[0.18em] text-text-secondary transition-colors duration-300 hover:text-brand-red"
            >
              RSS
            </Link>
          </nav>

          <nav aria-label="Elsewhere" className="flex flex-col gap-3">
            {profiles.map((profile) => (
              <a
                key={profile.href}
                href={profile.href}
                rel="me noopener noreferrer"
                target="_blank"
                className="font-mono text-xs uppercase tracking-[0.18em] text-text-secondary transition-colors duration-300 hover:text-brand-red"
              >
                {profile.label}
              </a>
            ))}
          </nav>
        </div>
      </div>
    </footer>
  );
}
