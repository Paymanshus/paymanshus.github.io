import type { Metadata } from 'next';
import ExperienceSection from '@/components/ExperienceSection';
import SiteShell from '@/components/SiteShell';
import StructuredData from '@/components/StructuredData';
import { absoluteUrl, createMetadata, siteConfig } from '@/lib/site';

export const metadata: Metadata = createMetadata({
  title: 'Experience',
  description:
    'Interactive resume modes for Paymanshu Sharma, including PDF, terminal chat, and voice-driven views.',
  path: '/experience',
  keywords: ['resume', 'portfolio experience', 'interactive resume'],
});

export default function ExperiencePage() {
  return (
    <>
      <StructuredData
        data={{
          '@context': 'https://schema.org',
          '@type': 'ProfilePage',
          name: 'Experience',
          url: absoluteUrl('/experience'),
          description: 'Interactive resume section for Paymanshu Sharma.',
          mainEntity: {
            '@type': 'Person',
            name: siteConfig.name,
            jobTitle: 'Developer & Architect',
          },
        }}
      />
      <SiteShell>
        <div className="w-full pb-24 pt-12">
          <ExperienceSection />
        </div>
      </SiteShell>
    </>
  );
}
