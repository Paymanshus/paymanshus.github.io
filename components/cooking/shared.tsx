import type { Project, ProjectStatus } from '@/lib/cooking';

export const metaClass = 'font-mono text-[11px] uppercase tracking-[0.18em] text-text-secondary';

const linkClass =
  'relative z-10 inline-flex items-center gap-2 font-mono text-xs uppercase tracking-[0.18em] text-text-primary/75 transition-colors duration-300 hover:text-brand-red';

const STATUS_LABEL: Record<ProjectStatus, string> = {
  building: 'building',
  early: 'early days',
  // shipped: 'shipped', // Pair with 'shipped' in PROJECT_STATUSES (lib/cooking.ts).
};

export function StatusTag({ status }: { status: ProjectStatus }) {
  return (
    <span className="flex items-center gap-2">
      {status === 'building' ? <span className="inline-block h-1.5 w-1.5 bg-brand-red" aria-hidden="true" /> : null}
      {STATUS_LABEL[status]}
    </span>
  );
}

/** The GitHub mark, drawn in currentColor so it follows the link's hover state. */
export function GitHubMark({ className = 'h-3.5 w-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M12 .3a12 12 0 0 0-3.8 23.38c.6.12.83-.26.83-.57l-.02-2.04c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.33-1.76-1.33-1.76-1.09-.74.08-.73.08-.73 1.2.09 1.84 1.24 1.84 1.24 1.07 1.83 2.8 1.3 3.49 1 .1-.78.42-1.31.76-1.61-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.14-.3-.54-1.52.1-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6 0c2.28-1.55 3.29-1.23 3.29-1.23.64 1.66.24 2.88.12 3.18a4.65 4.65 0 0 1 1.23 3.22c0 4.61-2.8 5.62-5.48 5.92.43.37.82 1.1.82 2.22l-.01 3.29c0 .32.21.69.82.57A12 12 0 0 0 12 .3" />
    </svg>
  );
}

export function ProjectLinks({ project, className = '' }: { project: Project; className?: string }) {
  if (!project.repo && !project.live) {
    return <p className={`${metaClass} ${className}`}>private repo</p>;
  }

  return (
    <div className={`flex flex-wrap items-center gap-x-6 gap-y-3 ${className}`}>
      {project.live ? (
        <a href={project.live} target="_blank" rel="noopener noreferrer" className={linkClass}>
          {'> live'}
        </a>
      ) : null}
      {project.repo ? (
        <a href={project.repo} target="_blank" rel="noopener noreferrer" className={linkClass}>
          {'> source'}
          <GitHubMark />
        </a>
      ) : null}
    </div>
  );
}

export function projectNumber(index: number) {
  return String(index + 1).padStart(2, '0');
}
