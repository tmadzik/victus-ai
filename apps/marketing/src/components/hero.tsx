import Link from 'next/link';
import type { ReactElement } from 'react';

import { Button } from '@victus/ui';

import { DashboardMockup } from '@/components/dashboard-mockup';

export function Hero(): ReactElement {
  return (
    <section id="top" className="px-4 pt-32 pb-20 sm:pt-40">
      <div className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-12 lg:grid-cols-12">
        <div className="flex flex-col gap-y-6 lg:col-span-5">
          <span className="ring-brand-100 text-brand-700 inline-flex w-fit items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset">
            <span aria-hidden="true" className="bg-brand-500 size-1.5 rounded-full" />
            Research demonstrator · In pilot across Sub-Saharan Africa
          </span>
          <h1 className="text-brand-950 text-4xl font-semibold tracking-tighter text-balance sm:text-5xl">
            Predict NCD Risk. Prevent Avoidable Claims.
          </h1>
          <p className="text-brand-700 text-lg leading-relaxed text-pretty">
            We combine predictive AI risk modeling with an integrated wellness and referral network.
            Identify, monitor and mitigate non-communicable diseases across your member base before
            they escalate.
          </p>
          <div className="flex flex-wrap items-center gap-5">
            <Button asChild size="lg">
              <a href="#request-pilot">Request Pilot</a>
            </Button>
            <Link
              href="/platform"
              className="text-brand-700 hover:text-brand-950 text-sm font-medium transition-colors"
            >
              Explore the Platform <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
        <div className="lg:col-span-7">
          <DashboardMockup />
        </div>
      </div>
    </section>
  );
}
