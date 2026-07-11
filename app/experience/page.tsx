import type { Metadata } from 'next';
import ExperienceSection from '@/components/ExperienceSection';
import SiteShell from '@/components/SiteShell';
import StructuredData from '@/components/StructuredData';
import { absoluteUrl, createMetadata, personRef } from '@/lib/site';

export const metadata: Metadata = createMetadata({
  title: 'Experience',
  description:
    'Interactive resume of Paymanshu Sharma, Machine Learning Engineer at Maersk — read the PDF, ask the terminal, or talk to a voice agent grounded in his experience.',
  path: '/experience',
  keywords: ['resume', 'interactive resume', 'voice resume', 'Maersk'],
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
          mainEntity: personRef(),
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
