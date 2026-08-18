import type { Metadata, Route } from 'next';
import Link from 'next/link';
import type { ReactElement } from 'react';

import { Button } from '@victus/ui';

import { ClosedLoop } from '@/components/closed-loop';
import { Gateway } from '@/components/gateway';
import { Pathways } from '@/components/pathways';
import { SiteFooter } from '@/components/site-footer';
import { SiteHeader } from '@/components/site-header';

export const metadata: Metadata = {
  title: 'Platform',
  description:
    'How the Victus platform works: two NCD-risk screening pathways (3B-Triage and Transdermal Optical Imaging), the Mobile Clinic Gateway, and a closed loop from screen to referral to outcome.',
  alternates: { canonical: '/platform' },
};

export default function PlatformPage(): ReactElement {
  return (
    <>
      <SiteHeader />
      <main>
        <section className="px-4 pt-32 pb-4 sm:pt-40">
          <div className="mx-auto max-w-4xl">
            <p className="text-brand-500 text-xs font-semibold tracking-wider uppercase">
              The Platform
            </p>
            <h1 className="text-brand-950 mt-2 text-4xl font-semibold tracking-tighter text-balance sm:text-5xl">
              How Victus turns a screen into an outcome.
            </h1>
            <p className="text-brand-700 mt-4 max-w-2xl text-lg leading-relaxed text-pretty">
              Two screening pathways, a public-kiosk gateway for community reach, and a single
              closed loop that carries each participant from consent to a tracked result — built to
              run in real Sub-Saharan clinical settings.
            </p>
          </div>
        </section>

        <Pathways />
        <ClosedLoop />
        <Gateway />

        <section className="px-4 py-20 sm:py-28">
          <div className="ring-brand-100 bg-brand-950 mx-auto flex max-w-4xl flex-col items-center gap-6 rounded-[var(--radius-card)] px-6 py-16 text-center text-white ring-1 ring-inset sm:px-12">
            <h2 className="text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
              See it running in your context.
            </h2>
            <p className="max-w-xl text-pretty text-white/80">
              Each pilot is its own jurisdiction-aware deployment. Tell us about your member base
              and we&rsquo;ll scope a pilot with you.
            </p>
            <Button asChild size="lg" variant="secondary" className="rounded-full">
              <Link href={'/#request-pilot' as Route}>Request Pilot</Link>
            </Button>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
