import type { Route } from 'next';
import Link from 'next/link';
import type { ReactElement } from 'react';

import { Button } from '@victus/ui';

const NAV_LINKS = [
  { href: '/#who-its-for', label: 'Who it’s for' },
  { href: '/#how-it-works', label: 'How it works' },
  { href: '/platform', label: 'Platform' },
  { href: '/#faq', label: 'FAQ' },
] as const;

export function SiteHeader(): ReactElement {
  return (
    <header className="fixed inset-x-0 top-4 z-50 px-4">
      <div className="ring-brand-100 mx-auto flex max-w-5xl items-center justify-between gap-4 rounded-full bg-white/85 py-2 pr-2 pl-5 shadow-sm ring-1 backdrop-blur-md ring-inset">
        <Link href="/" aria-label="Victus — home" className="flex shrink-0 items-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/victus-logo.svg" alt="Victus" className="h-7 w-auto" />
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-6 lg:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href as Route}
              className="text-brand-800 hover:text-brand-950 text-sm font-medium transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex shrink-0 items-center gap-1">
          <Button asChild variant="ghost" size="sm" className="rounded-full">
            <Link href="/signin">Sign In</Link>
          </Button>
          <Button asChild size="sm" className="rounded-full">
            <Link href={'/#book-demo' as Route}>Book a Demo</Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
