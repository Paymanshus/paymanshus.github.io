import type { Metadata } from 'next';

export const siteConfig = {
  name: 'Paymanshu Sharma',
  defaultTitle: 'Paymanshu Sharma | Developer & Architect',
  description:
    'Austere Neon developer portfolio with interactive resume modes, route-based sections, and long-form engineering thoughts.',
  url: process.env.NEXT_PUBLIC_SITE_URL ?? 'https://paymanshus.github.io',
  locale: 'en_US',
  location: 'New Delhi, India',
  email: 'paymanshus@gmail.com',
  links: {
    github: 'https://github.com/Paymanshus',
    linkedin: 'https://www.linkedin.com/in/paymanshu',
  },
} as const;

type SeoInput = {
  title: string;
  description: string;
  path: string;
  keywords?: string[];
  type?: 'website' | 'article';
  publishedTime?: string;
  modifiedTime?: string;
};

const defaultKeywords = [
  'Paymanshu Sharma',
  'developer portfolio',
  'Next.js portfolio',
  'software engineer',
  'engineering blog',
];

export function absoluteUrl(path = '/') {
  if (path === '/') {
    return new URL('/', siteConfig.url).toString();
  }

  const normalizedPath = `${path.replace(/\/+$/, '')}/`;
  return new URL(normalizedPath, siteConfig.url).toString();
}

export function toIsoDate(date: string) {
  return new Date(`${date}T00:00:00.000Z`).toISOString();
}

export function formatDisplayDate(date: string) {
  return date.replaceAll('-', '.');
}

export function formatReadableDate(date: string) {
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'long',
    timeZone: 'UTC',
  }).format(new Date(`${date}T00:00:00.000Z`));
}

export function createMetadata({
  title,
  description,
  path,
  keywords = [],
  type = 'website',
  publishedTime,
  modifiedTime,
}: SeoInput): Metadata {
  const fullTitle = `${title} | ${siteConfig.name}`;

  return {
    title,
    description,
    keywords: [...defaultKeywords, ...keywords],
    alternates: {
      canonical: absoluteUrl(path),
    },
    openGraph: {
      type,
      url: absoluteUrl(path),
      title: fullTitle,
      description,
      siteName: siteConfig.defaultTitle,
      locale: siteConfig.locale,
      publishedTime,
      modifiedTime,
    },
    twitter: {
      card: 'summary_large_image',
      title: fullTitle,
      description,
    },
  };
}
