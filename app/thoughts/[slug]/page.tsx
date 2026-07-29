import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import SiteShell from '@/components/SiteShell';
import StructuredData from '@/components/StructuredData';
import ThoughtPost from '@/components/ThoughtPost';
import { getAdjacentBlogPosts, getAllBlogSlugs, getBlogPostBySlug } from '@/lib/blog';
import { absoluteAssetUrl, absoluteUrl, createMetadata, personRef, toIsoDate } from '@/lib/site';

type ThoughtPostPageProps = {
  params: Promise<{
    slug: string;
  }>;
};

export function generateStaticParams() {
  return getAllBlogSlugs().map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: ThoughtPostPageProps): Promise<Metadata> {
  const { slug } = await params;
  const post = getBlogPostBySlug(slug);

  if (!post) {
    return {};
  }

  return createMetadata({
    title: post.title,
    description: post.excerpt,
    path: `/thoughts/${post.slug}`,
    type: 'article',
    keywords: post.tags,
    publishedTime: toIsoDate(post.date),
    modifiedTime: toIsoDate(post.updatedAt ?? post.date),
    ogImage: `/og/thoughts/${post.slug}.png`,
  });
}

export default async function ThoughtPostPage({ params }: ThoughtPostPageProps) {
  const { slug } = await params;
  const post = getBlogPostBySlug(slug);

  if (!post) {
    notFound();
  }

  const postUrl = absoluteUrl(`/thoughts/${post.slug}`);
  const adjacent = getAdjacentBlogPosts(post.slug);

  return (
    <>
      <StructuredData
        data={{
          '@context': 'https://schema.org',
          '@type': 'BreadcrumbList',
          itemListElement: [
            { '@type': 'ListItem', position: 1, name: 'Home', item: absoluteUrl('/') },
            { '@type': 'ListItem', position: 2, name: 'Thoughts', item: absoluteUrl('/thoughts') },
            { '@type': 'ListItem', position: 3, name: post.title, item: postUrl },
          ],
        }}
      />
      <StructuredData
        data={{
          '@context': 'https://schema.org',
          '@type': 'BlogPosting',
          headline: post.title,
          description: post.excerpt,
          datePublished: toIsoDate(post.date),
          dateModified: toIsoDate(post.updatedAt ?? post.date),
          url: postUrl,
          mainEntityOfPage: postUrl,
          image: absoluteAssetUrl(`/og/thoughts/${post.slug}.png`),
          keywords: post.tags,
          author: personRef(),
          publisher: personRef(),
        }}
      />
      <SiteShell>
        <ThoughtPost post={post} adjacent={adjacent} />
      </SiteShell>
    </>
  );
}
