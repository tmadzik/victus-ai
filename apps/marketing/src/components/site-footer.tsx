import Link from 'next/link';
import type { ReactElement } from 'react';

import { LEGAL_NAME } from '@/lib/site';

const FOOTER_LINKS = [
  { href: '/legal', label: 'Legal' },
  { href: '/privacy', label: 'Privacy Policy' },
  { href: '/paia', label: 'PAIA Manual' },
] as const;

export function SiteFooter(): ReactElement {
  return (
    <footer className="border-brand-100 border-t px-4 py-10">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-6 sm:flex-row">
        <div className="flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/victus-logo.svg" alt="" aria-hidden="true" className="h-6 w-auto" />
          <p className="text-grey-500 text-sm">© 2026 {LEGAL_NAME}</p>
        </div>
        <nav aria-label="Legal" className="flex items-center gap-6">
          {FOOTER_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-brand-800 hover:text-brand-950 text-sm transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
