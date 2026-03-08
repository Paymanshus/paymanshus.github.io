import type { Metadata } from 'next';
import SiteShell from '@/components/SiteShell';
import StructuredData from '@/components/StructuredData';
import ThoughtsSection from '@/components/ThoughtsSection';
import { getAllBlogPosts } from '@/lib/blog';
import { absoluteUrl, createMetadata } from '@/lib/site';

export const metadata: Metadata = createMetadata({
  title: 'Thoughts',
  description:
    'Markdown-backed essays and technical notes by Paymanshu Sharma, each with its own crawlable route and shareable URL.',
  path: '/thoughts',
  keywords: ['blog', 'technical writing', 'engineering essays'],
});

export default function ThoughtsPage() {
  const posts = getAllBlogPosts();

  return (
    <>
      <StructuredData
        data={{
          '@context': 'https://schema.org',
          '@type': 'CollectionPage',
          name: 'Thoughts',
          url: absoluteUrl('/thoughts'),
          description: 'Engineering essays and notes by Paymanshu Sharma.',
          mainEntity: {
            '@type': 'ItemList',
            itemListElement: posts.map((post, index) => ({
              '@type': 'ListItem',
              position: index + 1,
              url: absoluteUrl(`/thoughts/${post.slug}`),
              name: post.title,
            })),
          },
        }}
      />
      <SiteShell>
        <div className="w-full pb-24 pt-12">
          <ThoughtsSection posts={posts} />
        </div>
      </SiteShell>
    </>
  );
}
