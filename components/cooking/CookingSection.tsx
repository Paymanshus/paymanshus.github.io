import type { Project } from '@/lib/cooking';
import PageEngagement from '@/components/analytics/PageEngagement';
import CookingGallery from '@/components/cooking/CookingGallery';

export default function CookingSection({ projects }: { projects: Project[] }) {
  return (
    <div className="relative w-full">
      <PageEngagement section="cooking_index" />
      <header className="mb-12 md:mb-16">
        <h1 className="mb-2 text-4xl font-light tracking-tight">What&apos;s cooking</h1>
        <p className="font-mono text-xs uppercase tracking-widest text-brand-red">{'// On the stove right now'}</p>
      </header>

      {projects.length === 0 ? (
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-text-secondary">
          Nothing on the stove. List a project in `content/cooking/_order.txt`.
        </p>
      ) : (
        <CookingGallery projects={projects} />
      )}
    </div>
  );
}
