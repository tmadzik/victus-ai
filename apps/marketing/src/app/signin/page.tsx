import { Building2, Lock, Stethoscope, Truck, type LucideIcon } from 'lucide-react';
import type { Metadata, Route } from 'next';
import Link from 'next/link';
import type { ReactElement } from 'react';

import { APP_URL, LEGAL_NAME } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Sign in',
  description:
    'Choose how you use Victus — clinician, health insurer, or mobile clinic kiosk — and continue to the secure Victus application.',
  alternates: { canonical: '/signin' },
  // A routing page, not content worth indexing.
  robots: { index: false, follow: true },
};

interface Destination {
  title: string;
  description: string;
  cta: string;
  href: string;
  icon: LucideIcon;
}

/* Every destination leaves this domain. Credentials are only ever entered on
   the application origin — the marketing site never handles a password. */
const DESTINATIONS: Destination[] = [
  {
    title: 'Clinician or care team',
    description:
      'Review participant records, screening history and referrals for the people in your care.',
    cta: 'Continue to sign in',
    href: `${APP_URL}/login?role=clinician`,
    icon: Stethoscope,
  },
  {
    title: 'Health insurer or funder',
    description:
      'View population risk across your member base, and how flagged members move through care.',
    cta: 'Continue to sign in',
    href: `${APP_URL}/login?role=insurer`,
    icon: Building2,
  },
  {
    title: 'Mobile clinic kiosk',
    description:
      'Start a screening terminal at a community site. Kiosks are authorised by device, not by a personal login.',
    cta: 'Open kiosk mode',
    href: `${APP_URL}/kiosk`,
    icon: Truck,
  },
];

export default function SignInPage(): ReactElement {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="px-4 py-6">
        <div className="mx-auto max-w-3xl">
          <Link href="/" aria-label="Victus — home" className="inline-flex">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/victus-logo.png"
              alt="Victus"
              width={600}
              height={99}
              className="h-8 w-auto"
            />
          </Link>
        </div>
      </header>

      <main className="flex-1 px-4 py-10 sm:py-16">
        <div className="mx-auto max-w-3xl">
          <h1 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            Sign in to Victus
          </h1>
          <p className="text-brand-700 mt-3 text-lg text-pretty">
            Choose how you use Victus. We&rsquo;ll take you to the secure Victus application to
            enter your credentials.
          </p>

          <div className="mt-10 flex flex-col gap-3">
            {DESTINATIONS.map((destination) => (
              <a
                key={destination.title}
                href={destination.href}
                className="ring-brand-100 hover:ring-brand-300 focus-visible:ring-brand-500 group flex items-center gap-5 rounded-[var(--radius-card)] bg-white p-6 ring-1 transition-all ring-inset hover:shadow-md focus-visible:ring-2"
              >
                <span className="bg-brand-100 text-brand-700 group-hover:bg-brand-200 flex size-12 shrink-0 items-center justify-center rounded-xl transition-colors">
                  <destination.icon aria-hidden="true" className="size-6" />
                </span>
                <span className="flex-1">
                  <span className="text-brand-950 block font-semibold tracking-tight">
                    {destination.title}
                  </span>
                  <span className="text-brand-700 mt-1 block text-sm text-pretty">
                    {destination.description}
                  </span>
                </span>
                <span
                  aria-hidden="true"
                  className="text-brand-400 group-hover:text-brand-700 shrink-0 transition-colors"
                >
                  →
                </span>
                <span className="sr-only">{destination.cta}</span>
              </a>
            ))}
          </div>

          <p className="text-grey-500 mt-8 flex items-start gap-2.5 text-sm text-pretty">
            <Lock aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span>
              For your security, passwords are only ever entered on the Victus application at{' '}
              <strong className="text-brand-800 font-medium">app.victusdata.com</strong> — never on
              this website. Check that address before you sign in.
            </span>
          </p>

          <div className="border-brand-100 mt-10 border-t pt-8">
            <h2 className="text-brand-950 font-semibold tracking-tight">
              Don&rsquo;t have an account yet?
            </h2>
            <p className="text-brand-700 mt-2 text-pretty">
              Victus accounts are provisioned through your organisation. Tell us about your team and
              we&rsquo;ll set you up.
            </p>
            <Link
              href={'/#book-demo' as Route}
              className="text-brand-700 hover:text-brand-950 mt-3 inline-block font-semibold transition-colors"
            >
              Request access <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
      </main>

      <footer className="px-4 py-8">
        <div className="text-grey-500 mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-4 text-sm">
          <p>© 2026 {LEGAL_NAME}</p>
          <nav aria-label="Legal" className="flex gap-5">
            <Link href="/privacy" className="hover:text-brand-900 transition-colors">
              Privacy Policy
            </Link>
            <Link href="/legal" className="hover:text-brand-900 transition-colors">
              Legal
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
