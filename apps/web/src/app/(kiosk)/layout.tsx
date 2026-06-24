import type { Metadata, Viewport } from 'next';

/**
 * Zero-footprint kiosk shell. No app chrome, no auth, no navigation — a public
 * terminal surface. Dark, full-bleed, and locked to a single column so a person
 * walking up sees only the check-up flow.
 */

export const metadata: Metadata = {
  title: 'Victus wellness kiosk',
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function KioskLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <div className="grid min-h-dvh place-items-center bg-brand-950 text-brand-50">
      {children}
    </div>
  );
}
