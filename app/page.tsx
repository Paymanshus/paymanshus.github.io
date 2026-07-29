import HeroSection from '@/components/HeroSection';
import SiteShell from '@/components/SiteShell';
import StructuredData from '@/components/StructuredData';
import PageEngagement from '@/components/analytics/PageEngagement';
import { absoluteUrl, personJsonLd, personRef, siteConfig, websiteJsonLd } from '@/lib/site';

export default function HomePage() {
  return (
    <>
      <StructuredData data={websiteJsonLd()} />
      <StructuredData data={personJsonLd()} />
      <StructuredData
        data={{
          '@context': 'https://schema.org',
          '@type': 'ProfilePage',
          name: siteConfig.defaultTitle,
          url: absoluteUrl('/'),
          description: siteConfig.description,
          mainEntity: personRef(),
        }}
      />
      <SiteShell home>
        <PageEngagement section="home_hero" />
        <HeroSection />
      </SiteShell>
    </>
  );
}
