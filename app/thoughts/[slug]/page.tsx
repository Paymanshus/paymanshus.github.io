import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import SiteShell from '@/components/SiteShell';
import StructuredData from '@/components/StructuredData';
import ThoughtPost from '@/components/ThoughtPost';
import { getAllBlogSlugs, getBlogPostBySlug } from '@/lib/blog';
import { absoluteUrl, createMetadata, siteConfig, toIsoDate } from '@/lib/site';

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
  });
}

export default async function ThoughtPostPage({ params }: ThoughtPostPageProps) {
  const { slug } = await params;
  const post = getBlogPostBySlug(slug);

  if (!post) {
    notFound();
  }

  const postUrl = absoluteUrl(`/thoughts/${post.slug}`);

  return (
    <>
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
          author: {
            '@type': 'Person',
            name: siteConfig.name,
            url: siteConfig.url,
          },
          publisher: {
            '@type': 'Person',
            name: siteConfig.name,
          },
        }}
      />
      <SiteShell>
        <ThoughtPost post={post} />
      </SiteShell>
    </>
  );
}
