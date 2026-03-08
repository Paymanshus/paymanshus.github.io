import HeroSection from '@/components/HeroSection';
import SiteShell from '@/components/SiteShell';
import StructuredData from '@/components/StructuredData';
import { absoluteUrl, siteConfig } from '@/lib/site';

export default function HomePage() {
  return (
    <>
      <StructuredData
        data={{
          '@context': 'https://schema.org',
          '@type': 'WebSite',
          name: siteConfig.defaultTitle,
          url: absoluteUrl('/'),
          description: siteConfig.description,
        }}
      />
      <StructuredData
        data={{
          '@context': 'https://schema.org',
          '@type': 'Person',
          name: siteConfig.name,
          url: absoluteUrl('/'),
          jobTitle: 'Developer & Architect',
          address: {
            '@type': 'PostalAddress',
            addressLocality: 'Bangalore',
            addressCountry: 'IN',
          },
          email: siteConfig.email,
          sameAs: [siteConfig.links.github, siteConfig.links.linkedin],
        }}
      />
      <SiteShell home>
        <HeroSection />
      </SiteShell>
    </>
  );
}
