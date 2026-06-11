import { Building2, Dumbbell, RefreshCcw, type LucideIcon } from 'lucide-react';
import type { ReactElement } from 'react';

interface NetworkPoint {
  title: string;
  description: string;
  icon: LucideIcon;
}

const POINTS: NetworkPoint[] = [
  {
    title: 'Owned and operated',
    description:
      'Victus owns its fitness and wellness facilities outright — no referral partners, no attribution gaps, full accountability for the intervention.',
    icon: Building2,
  },
  {
    title: 'Structured programmes',
    description:
      'Flagged members enter structured exercise and lifestyle programmes designed around their specific cardiovascular and metabolic risk profile.',
    icon: Dumbbell,
  },
  {
    title: 'Data flows back',
    description:
      'Attendance and biometric measurements stream back into the platform, so every intervention is measured against the risk score that triggered it.',
    icon: RefreshCcw,
  },
];

export function PhysicalNetwork(): ReactElement {
  return (
    <section id="physical-network" className="bg-brand-50 scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="mx-auto grid max-w-6xl gap-12 lg:grid-cols-12 lg:items-start">
        <div className="lg:col-span-5">
          <h2 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            An intervention network we own — not a referral list.
          </h2>
          <p className="text-brand-700 mt-4 text-lg text-pretty">
            Software alone doesn&rsquo;t lower claims. The Victus platform routes risk into physical
            facilities we own and operate, closing the loop between prediction and measurable
            outcome.
          </p>
        </div>
        <div className="flex flex-col gap-4 lg:col-span-7">
          {POINTS.map((point) => (
            <div
              key={point.title}
              className="ring-brand-100 flex gap-5 rounded-[var(--radius-card)] bg-white p-6 ring-1 ring-inset"
            >
              <span className="bg-brand-100 text-brand-700 flex size-11 shrink-0 items-center justify-center rounded-lg">
                <point.icon aria-hidden="true" className="size-5" />
              </span>
              <div>
                <h3 className="text-brand-950 font-semibold tracking-tight">{point.title}</h3>
                <p className="text-brand-700 mt-1 text-sm leading-relaxed text-pretty">
                  {point.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
