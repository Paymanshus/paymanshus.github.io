import Link from 'next/link';
import type { BlogPostPreview } from '@/lib/blog';

export default function ThoughtsSection({ posts }: { posts: BlogPostPreview[] }) {
  return (
    <div className="relative min-h-[80vh] w-full">
      <div className="mx-auto max-w-4xl">
        <header className="mb-16">
          <h1 className="mb-4 text-4xl font-light tracking-tight">Thoughts</h1>
          <p className="max-w-2xl font-serif text-xl italic leading-relaxed text-text-secondary">
            Route-based writing, rendered from Markdown, with each post getting its own crawlable page.
          </p>
        </header>

        <div className="flex flex-col gap-12">
          {posts.length === 0 ? (
            <div className="border border-border bg-surface/40 p-8">
              <p className="font-mono text-sm uppercase tracking-[0.22em] text-text-secondary">
                No posts yet. Add a Markdown file in `content/blog/`.
              </p>
            </div>
          ) : null}
          {posts.map((post) => (
            <Link
              key={post.slug}
              href={`/thoughts/${post.slug}`}
              className="group flex flex-col gap-4 border-b border-border pb-8 text-left transition-colors duration-300 hover:border-brand-red/30 md:flex-row md:items-baseline md:gap-12"
            >
              <div className="w-32 shrink-0 font-mono text-sm tracking-widest text-text-secondary">
                {post.displayDate}
              </div>
              <div className="flex-1 transition-transform duration-300 group-hover:translate-x-2">
                <h2 className="mb-3 text-2xl font-light tracking-tight transition-colors duration-300 group-hover:text-brand-red">
                  {post.title}
                </h2>
                <p className="font-serif text-xl italic leading-relaxed text-text-secondary">
                  {post.excerpt}
                </p>
              </div>
              <div className="shrink-0 font-mono text-xs uppercase tracking-[0.24em] text-text-secondary">
                {post.readingTimeText}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
