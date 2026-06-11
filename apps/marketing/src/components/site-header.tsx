import type { ReactElement } from 'react';

import { Button } from '@victus/ui';

import { APP_URL } from '@/lib/site';

const NAV_LINKS = [
  { href: '#platform', label: 'Platform' },
  { href: '#physical-network', label: 'Physical Network' },
  { href: '#clinical-approach', label: 'Clinical Approach' },
] as const;

export function SiteHeader(): ReactElement {
  return (
    <header className="fixed inset-x-0 top-4 z-50 px-4">
      <div className="ring-brand-100 mx-auto flex max-w-4xl items-center justify-between gap-4 rounded-full bg-white/80 py-2 pr-2 pl-5 ring-1 backdrop-blur-md ring-inset">
        <a href="#top" aria-label="Victus — home" className="flex shrink-0 items-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/victus-logo.svg" alt="Victus" className="h-8 w-auto" />
        </a>

        <nav aria-label="Primary" className="hidden items-center gap-6 md:flex">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-brand-800 hover:text-brand-950 text-sm font-medium transition-colors"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="flex shrink-0 items-center gap-1">
          <Button asChild variant="ghost" size="sm" className="rounded-full">
            <a href={`${APP_URL}/login`}>Sign In</a>
          </Button>
          <Button asChild size="sm" className="rounded-full">
            <a href="#request-pilot">Book a Demo</a>
          </Button>
        </div>
      </div>
    </header>
  );
}
