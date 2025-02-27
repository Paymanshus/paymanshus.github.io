// This file would typically be placed in src/app/blog/[slug]/page.tsx
import { getAllPostIds, getPostData } from '@/lib/blog';
import Image from 'next/image';
import Link from 'next/link';

// Generate static params for all blog posts
export async function generateStaticParams() {
  const posts = getAllPostIds();
  return posts;
}

// Generate metadata for the page
export async function generateMetadata({ params }: { params: { slug: string } }) {
  const postData = await getPostData(params.slug);
  
  return {
    title: `${postData.title} | Paymanshu Sharma's Blog`,
    description: postData.excerpt,
  };
}

export default async function BlogPost({ params }: { params: { slug: string } }) {
  const postData = await getPostData(params.slug);
  
  return (
    <main className="container mx-auto px-4 py-8 max-w-3xl">
      <Link href="/blog" className="text-blue-600 hover:underline mb-6 inline-block">
        ← Back to all posts
      </Link>
      
      <article>
        <header className="mb-8">
          <h1 className="text-4xl font-bold mb-4">{postData.title}</h1>
          
          <div className="flex items-center justify-between mb-6">
            <p className="text-gray-600">
              {new Date(postData.date).toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </p>
            
            <div className="flex flex-wrap gap-2">
              {postData.tags && postData.tags.map(tag => (
                <Link 
                  key={tag} 
                  href={`/blog/tag/${tag.toLowerCase()}`}
                  className="text-xs bg-gray-100 px-2 py-1 rounded-full hover:bg-gray-200 transition-colors"
                >
                  {tag}
                </Link>
              ))}
            </div>
          </div>
          
          {postData.coverImage && (
            <div className="relative h-64 md:h-96 w-full mb-8">
              <Image
                src={postData.coverImage}
                alt={postData.title}
                fill
                className="object-cover rounded-lg"
                priority
              />
            </div>
          )}
        </header>
        
        <div 
          className="prose prose-lg max-w-none"
          dangerouslySetInnerHTML={{ __html: postData.contentHtml }} 
        />
      </article>
    </main>
  );
} 