import type { Metadata } from 'next';
import CookingSection from '@/components/cooking/CookingSection';
import SiteShell from '@/components/SiteShell';
import StructuredData from '@/components/StructuredData';
import { getAllProjects } from '@/lib/cooking';
import { absoluteAssetUrl, absoluteUrl, createMetadata, personRef } from '@/lib/site';

export const metadata: Metadata = createMetadata({
  title: "What's cooking",
  description:
    'Side projects Paymanshu Sharma is building right now: opinion mining, voice accessibility, local-first chat analytics, LLM search and personal knowledge tools.',
  path: '/cooking',
  keywords: ['side projects', 'portfolio', 'work in progress'],
});

export default function CookingPage() {
  const projects = getAllProjects();

  return (
    <>
      <StructuredData
        data={{
          '@context': 'https://schema.org',
          '@type': 'CollectionPage',
          name: "What's cooking",
          url: absoluteUrl('/cooking'),
          description: 'Side projects in progress by Paymanshu Sharma.',
          mainEntity: {
            '@type': 'ItemList',
            itemListElement: projects.map((project, index) => ({
              '@type': 'ListItem',
              position: index + 1,
              item: {
                '@type': 'CreativeWork',
                name: project.title,
                description: project.summary,
                url: `${absoluteUrl('/cooking')}#${project.slug}`,
                author: personRef(),
                ...(project.thumbnail ? { image: absoluteAssetUrl(project.thumbnail.src) } : {}),
                ...(project.repo ? { sameAs: project.repo } : {}),
              },
            })),
          },
        }}
      />
      <SiteShell>
        <div className="w-full pb-24 pt-12">
          <CookingSection projects={projects} />
        </div>
      </SiteShell>
    </>
  );
}
