import type { Metadata, Viewport } from 'next';

import { LEGAL_NAME, SITE_NAME, SITE_URL } from '@/lib/site';

import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: 'Victus — Find Undiagnosed NCDs. Get People Into Care.',
    template: `%s — ${SITE_NAME}`,
  },
  description:
    'Victus screens for undiagnosed non-communicable disease in the community — no bloods, no clinic visit — and tracks every flagged person through to care, with an owned physical wellness network behind it.',
  applicationName: SITE_NAME,
  referrer: 'strict-origin-when-cross-origin',
  formatDetection: { telephone: false, email: false, address: false },
  alternates: { canonical: '/' },
  openGraph: {
    type: 'website',
    url: SITE_URL,
    siteName: SITE_NAME,
    title: 'Victus — Find Undiagnosed NCDs. Get People Into Care.',
    description:
      'Closed-loop population health for healthcare funders: community NCD screening with reported uncertainty, owned physical intervention facilities, and referral-to-outcome tracking.',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Victus — Find Undiagnosed NCDs. Get People Into Care.',
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
  logo: `${SITE_URL}/victus-logo.png`,
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
