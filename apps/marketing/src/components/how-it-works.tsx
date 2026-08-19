import type { ReactElement } from 'react';

import { DashboardMockup } from '@/components/dashboard-mockup';

interface Step {
  step: string;
  title: string;
  description: string;
}

const STEPS: Step[] = [
  {
    step: '01',
    title: 'Screen in minutes',
    description:
      'A few tape-measure readings and questions, or a short face-video capture on a phone. No bloods, no lab, no clinic visit required.',
  },
  {
    step: '02',
    title: 'Know who needs attention',
    description:
      'Everyone comes back as low risk, watch, or urgent — with the uncertain cases sent for a human check rather than quietly guessed at.',
  },
  {
    step: '03',
    title: 'Act, then track',
    description:
      'Route people into a wellness programme or refer them to a clinic, and follow what changes over time in one longitudinal record.',
  },
];

export function HowItWorks(): ReactElement {
  return (
    <section id="how-it-works" className="bg-brand-50 scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <h2 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            From a five-minute screen to a tracked outcome.
          </h2>
          <p className="text-brand-700 mt-4 text-lg text-pretty">
            Most screening stops at a number on a page. Victus carries each person through to
            someone who can help — and shows you whether it worked.
          </p>
        </div>

        <div className="mt-12 grid gap-10 lg:grid-cols-12 lg:items-center">
          <ol className="flex flex-col gap-8 lg:col-span-5">
            {STEPS.map((item) => (
              <li key={item.step} className="flex gap-5">
                <span className="bg-brand-600 flex size-10 shrink-0 items-center justify-center rounded-full font-mono text-sm font-semibold text-white tabular-nums">
                  {item.step}
                </span>
                <div>
                  <h3 className="text-brand-950 text-lg font-semibold tracking-tight">
                    {item.title}
                  </h3>
                  <p className="text-brand-700 mt-1.5 text-pretty">{item.description}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="lg:col-span-7">
            <DashboardMockup />
            <p className="text-grey-500 mt-3 text-center text-xs">
              Concept illustration of population-level reporting.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
