import type {Metadata, Viewport} from 'next';
import { Space_Grotesk, Instrument_Serif, JetBrains_Mono, Lora } from 'next/font/google';
import Analytics from '@/components/analytics/Analytics';
import {
  DEFAULT_OG_IMAGE,
  absoluteAssetUrl,
  absoluteUrl,
  defaultKeywords,
  siteConfig,
} from '@/lib/site';
import './globals.css';

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-space-grotesk',
});

const instrumentSerif = Instrument_Serif({
  weight: '400',
  subsets: ['latin'],
  variable: '--font-instrument-serif',
});

const lora = Lora({
  subsets: ['latin'],
  variable: '--font-lora',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
});

export const metadata: Metadata = {
  metadataBase: new URL(siteConfig.url),
  title: {
    default: siteConfig.defaultTitle,
    template: `%s | ${siteConfig.name}`,
  },
  description: siteConfig.description,
  applicationName: siteConfig.defaultTitle,
  manifest: '/favicons/site.webmanifest',
  authors: [{ name: siteConfig.name, url: siteConfig.url }],
  creator: siteConfig.name,
  publisher: siteConfig.name,
  keywords: [...defaultKeywords],
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/favicons/favicon-32x32.png', type: 'image/png', sizes: '32x32' },
      { url: '/favicons/favicon-16x16.png', type: 'image/png', sizes: '16x16' },
    ],
    apple: [{ url: '/favicons/apple-touch-icon.png', type: 'image/png', sizes: '180x180' }],
    other: [
      { rel: 'icon', url: '/favicons/android-chrome-192x192.png', type: 'image/png', sizes: '192x192' },
      { rel: 'icon', url: '/favicons/android-chrome-512x512.png', type: 'image/png', sizes: '512x512' },
    ],
  },
  alternates: {
    canonical: absoluteUrl('/'),
    types: {
      'application/rss+xml': absoluteAssetUrl('/feed.xml'),
      'application/feed+json': absoluteAssetUrl('/feed.json'),
    },
  },
  verification: {
    google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION,
  },
  openGraph: {
    type: 'website',
    locale: siteConfig.locale,
    url: siteConfig.url,
    title: siteConfig.defaultTitle,
    description: siteConfig.description,
    siteName: siteConfig.defaultTitle,
    images: [
      {
        url: absoluteAssetUrl(DEFAULT_OG_IMAGE),
        width: 1200,
        height: 630,
        alt: siteConfig.defaultTitle,
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: siteConfig.defaultTitle,
    description: siteConfig.description,
    images: [absoluteAssetUrl(DEFAULT_OG_IMAGE)],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-image-preview': 'large',
      'max-snippet': -1,
      'max-video-preview': -1,
    },
  },
};

// themeColor belongs on the viewport export, not metadata (Next 15+).
export const viewport: Viewport = {
  themeColor: '#040404',
};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} ${instrumentSerif.variable} ${lora.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-bg text-text-primary antialiased selection:bg-brand-red/30 selection:text-white" suppressHydrationWarning>
        <div className="mx-auto w-full max-w-7xl px-6 md:px-12 lg:px-24">
          {children}
        </div>
        <Analytics />
      </body>
    </html>
  );
}
