import type { Metadata, Viewport } from 'next';

import { LEGAL_NAME, SITE_NAME, SITE_URL } from '@/lib/site';

import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: 'Victus — Predict NCD Risk. Prevent Avoidable Claims.',
    template: `%s — ${SITE_NAME}`,
  },
  description:
    'Victus combines predictive AI risk modeling with an owned physical wellness network so healthcare funders can identify, monitor and mitigate non-communicable diseases before they escalate.',
  applicationName: SITE_NAME,
  referrer: 'strict-origin-when-cross-origin',
  formatDetection: { telephone: false, email: false, address: false },
  alternates: { canonical: '/' },
  openGraph: {
    type: 'website',
    url: SITE_URL,
    siteName: SITE_NAME,
    title: 'Victus — Predict NCD Risk. Prevent Avoidable Claims.',
    description:
      'Closed-loop population health management for healthcare funders: AI-driven NCD risk scoring, owned physical intervention facilities, real-time outcome tracking.',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Victus — Predict NCD Risk. Prevent Avoidable Claims.',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#ffffff' },
    { media: '(prefers-color-scheme: dark)', color: '#0c1a24' },
  ],
};

const organizationJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: LEGAL_NAME,
  url: SITE_URL,
  logo: `${SITE_URL}/victus-logo.svg`,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="text-brand-950 min-h-dvh bg-white antialiased">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationJsonLd) }}
        />
        {children}
      </body>
    </html>
  );
}
