// This file would typically be placed in src/app/blog/page.tsx
import Link from 'next/link';
import Image from 'next/image';
import { getSortedPostsData } from '@/lib/blog';

export const metadata = {
  title: 'Blog | Paymanshu Sharma',
  description: 'Articles about machine learning, data science, and web development',
};

export default function BlogPage() {
  const allPostsData = getSortedPostsData();
  
  return (
    <main className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-8">Blog</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {allPostsData.map(({ id, title, date, excerpt, coverImage, tags }) => (
          <article key={id} className="border rounded-lg overflow-hidden shadow-md hover:shadow-lg transition-shadow">
            {coverImage && (
              <div className="relative h-48 w-full">
                <Image
                  src={coverImage}
                  alt={title}
                  fill
                  className="object-cover"
                />
              </div>
            )}
            
            <div className="p-4">
              <h2 className="text-xl font-semibold mb-2">
                <Link href={`/blog/${id}`} className="hover:text-blue-600 transition-colors">
                  {title}
                </Link>
              </h2>
              
              <p className="text-gray-500 text-sm mb-2">{new Date(date).toLocaleDateString()}</p>
              
              <p className="text-gray-700 mb-4">{excerpt}</p>
              
              <div className="flex flex-wrap gap-2">
                {tags && tags.map(tag => (
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
          </article>
        ))}
      </div>
    </main>
  );
} 