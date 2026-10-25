import type { Metadata } from 'next';

export const siteConfig = {
  name: 'Paymanshu Sharma',
  firstName: 'Paymanshu',
  jobTitle: 'Machine Learning Engineer',
  defaultTitle: 'Paymanshu Sharma | AI Product Engineer',
  description:
    'Paymanshu Sharma is a Machine Learning Engineer in Bangalore, building agentic AI and voice systems. Portfolio with an interactive resume you can talk to — PDF, terminal, and voice — plus essays on ML and engineering.',
  url: process.env.NEXT_PUBLIC_SITE_URL ?? 'https://paymanshus.github.io',
  locale: 'en_US',
  location: 'Bangalore, India',
  email: 'paymanshus@gmail.com',
  links: {
    github: 'https://github.com/Paymanshus',
    linkedin: 'https://www.linkedin.com/in/paymanshus',
    huggingface: 'https://huggingface.co/paymanshus',
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
  ogImage?: string;
};

export const GOOGLE_SITE_VERIFICATION =
  process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION ||
  '0o-VrKZb3IemUzf8qmVFsl_dRpOwOPaZU1azIjFYnkw';

export const defaultKeywords = [
  'Paymanshu Sharma',
  'Paymanshu',
  'AI Product Engineer',
  'Machine Learning Engineer',
  'ML engineer Bangalore',
  'agentic AI',
  'voice AI',
  'engineering blog',
];

export function absoluteUrl(path = '/') {
  if (path === '/') {
    return new URL('/', siteConfig.url).toString();
  }

  const normalizedPath = `${path.replace(/\/+$/, '')}/`;
  return new URL(normalizedPath, siteConfig.url).toString();
}

// Stable node ids for the site-wide JSON-LD entity graph. Every page that
// mentions the person/site must reference these via {'@id': ...} instead of
// re-declaring its own Person copy, so crawlers reconcile a single entity.
/**
 * Absolute URL for a static file. Unlike absoluteUrl(), it does NOT append a
 * trailing slash — routes get one (trailingSlash: true), files must not.
 */
export function absoluteAssetUrl(filePath: string) {
  return new URL(filePath.replace(/^\/+/, ''), siteConfig.url).toString();
}

export const DEFAULT_OG_IMAGE = '/og/default.png';

export const PERSON_ID = `${siteConfig.url}/#person`;
export const WEBSITE_ID = `${siteConfig.url}/#website`;

// Minimal Person stub carrying the shared @id: locally valid on any page,
// reconciled with the full node emitted on the home page.
export function personRef() {
  return {
    '@type': 'Person',
    '@id': PERSON_ID,
    name: siteConfig.name,
    url: absoluteUrl('/'),
  };
}

export function personJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'Person',
    '@id': PERSON_ID,
    name: siteConfig.name,
    givenName: 'Paymanshu',
    familyName: 'Sharma',
    url: absoluteUrl('/'),
    email: `mailto:${siteConfig.email}`,
    jobTitle: siteConfig.jobTitle,
    alumniOf: {
      '@type': 'CollegeOrUniversity',
      name: 'MPSTME, NMIMS Mumbai',
    },
    address: {
      '@type': 'PostalAddress',
      addressLocality: 'Bangalore',
      addressCountry: 'IN',
    },
    knowsAbout: [
      'Machine Learning',
      'Agentic AI',
      'Large Language Models',
      'Voice AI',
      'Natural Language Processing',
      'Computer Vision',
      'MLOps',
      'LangGraph',
      'Retrieval-Augmented Generation',
    ],
    sameAs: [
      siteConfig.links.github,
      siteConfig.links.linkedin,
      siteConfig.links.huggingface,
    ],
  };
}

export function websiteJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    '@id': WEBSITE_ID,
    name: siteConfig.defaultTitle,
    url: absoluteUrl('/'),
    description: siteConfig.description,
    publisher: personRef(),
  };
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
  ogImage,
}: SeoInput): Metadata {
  const fullTitle = `${title} | ${siteConfig.name}`;
  // Cards are rendered at build time by scripts/generate-og-images.mjs.
  const images = [
    {
      url: absoluteAssetUrl(ogImage ?? DEFAULT_OG_IMAGE),
      width: 1200,
      height: 630,
      alt: fullTitle,
    },
  ];

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
      images,
    },
    twitter: {
      card: 'summary_large_image',
      title: fullTitle,
      description,
      images,
    },
  };
}
