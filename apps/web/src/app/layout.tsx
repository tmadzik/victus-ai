import type { Metadata, Viewport } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'Victus AI',
    template: '%s — Victus AI',
  },
  description:
    'Dual-pathway NCD risk and TOI biomarker platform for clinical screening in Sub-Saharan Africa.',
  applicationName: 'Victus AI',
  referrer: 'strict-origin-when-cross-origin',
  formatDetection: { telephone: false, email: false, address: false },
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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-dvh bg-brand-50 text-brand-950 antialiased">{children}</body>
    </html>
  );
}
