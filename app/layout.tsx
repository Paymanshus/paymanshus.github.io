import type {Metadata} from 'next';
import { Space_Grotesk, Instrument_Serif, JetBrains_Mono, Lora } from 'next/font/google';
import { absoluteUrl, siteConfig } from '@/lib/site';
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
  keywords: ['Paymanshu Sharma', 'developer portfolio', 'Next.js'],
  themeColor: '#040404',
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
  },
  openGraph: {
    type: 'website',
    locale: siteConfig.locale,
    url: siteConfig.url,
    title: siteConfig.defaultTitle,
    description: siteConfig.description,
    siteName: siteConfig.defaultTitle,
  },
  twitter: {
    card: 'summary_large_image',
    title: siteConfig.defaultTitle,
    description: siteConfig.description,
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

export default function RootLayout({children}: {children: React.ReactNode}) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} ${instrumentSerif.variable} ${lora.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-bg text-text-primary antialiased selection:bg-brand-red/30 selection:text-white" suppressHydrationWarning>
        <div className="mx-auto w-full max-w-7xl px-6 md:px-12 lg:px-24">
          {children}
        </div>
      </body>
    </html>
  );
}
