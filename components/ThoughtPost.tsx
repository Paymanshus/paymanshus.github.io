import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import type { AdjacentPosts, BlogPost } from '@/lib/blog';
import { formatReadableDate } from '@/lib/site';
import ReadingProgressBar from '@/components/ReadingProgressBar';
import PageEngagement from '@/components/analytics/PageEngagement';

export default function ThoughtPost({
  post,
  adjacent,
}: {
  post: BlogPost;
  adjacent?: AdjacentPosts;
}) {
  return (
    <article className="mx-auto max-w-[50rem] pb-32 pt-12">
      <ReadingProgressBar />
      <PageEngagement section={`article:${post.slug}`} scrollDepth />

      <Link
        href="/thoughts"
        className="group mb-16 flex items-center gap-2 font-mono text-sm uppercase tracking-widest text-text-secondary transition-colors duration-300 hover:text-brand-red"
      >
        <ArrowLeft className="h-4 w-4 transition-transform duration-300 group-hover:-translate-x-2" />
        Back to Thoughts
      </Link>

      <header className="mb-16">
        <div className="mb-6 flex flex-wrap items-center gap-4 font-mono text-sm uppercase tracking-widest text-brand-red">
          <time dateTime={post.date}>{post.displayDate}</time>
          <span className="text-text-secondary">{post.readingTimeText}</span>
        </div>
        <h1 className="mb-8 text-4xl font-light leading-tight tracking-tight md:text-5xl">
          {post.title}
        </h1>
        <p className="max-w-[42rem] font-serif text-lg italic leading-relaxed text-text-secondary md:text-[1.325rem]">
          {post.excerpt}
        </p>
        <p className="mt-6 font-mono text-xs uppercase tracking-[0.24em] text-text-secondary">
          Published {formatReadableDate(post.date)}
        </p>
      </header>

      <div className="thought-post-content" dangerouslySetInnerHTML={{ __html: post.content }} />

      {adjacent && (adjacent.previous || adjacent.next) ? (
        <nav
          aria-label="More posts"
          className="mt-24 grid gap-8 border-t border-border pt-10 sm:grid-cols-2"
        >
          {adjacent.previous ? (
            <Link href={`/thoughts/${adjacent.previous.slug}`} className="group">
              <span className="font-mono text-xs uppercase tracking-[0.22em] text-text-secondary">
                Previous
              </span>
              <span className="mt-2 block text-lg font-light leading-snug transition-colors duration-300 group-hover:text-brand-red">
                {adjacent.previous.title}
              </span>
            </Link>
          ) : (
            <span />
          )}
          {adjacent.next ? (
            <Link href={`/thoughts/${adjacent.next.slug}`} className="group sm:text-right">
              <span className="font-mono text-xs uppercase tracking-[0.22em] text-text-secondary">
                Next
              </span>
              <span className="mt-2 block text-lg font-light leading-snug transition-colors duration-300 group-hover:text-brand-red">
                {adjacent.next.title}
              </span>
            </Link>
          ) : null}
        </nav>
      ) : null}
    </article>
  );
}
