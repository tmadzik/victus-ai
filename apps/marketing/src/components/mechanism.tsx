import { Activity, MapPin, ScanSearch, type LucideIcon } from 'lucide-react';
import type { ReactElement } from 'react';

interface MechanismStep {
  step: string;
  title: string;
  description: string;
  icon: LucideIcon;
}

const STEPS: MechanismStep[] = [
  {
    step: '01',
    title: 'Identify',
    description:
      'AI-driven scoring flags high-risk members via biometric signal processing before acute events occur.',
    icon: ScanSearch,
  },
  {
    step: '02',
    title: 'Intervene',
    description:
      'Seamlessly route flagged members to our brick-and-mortar fitness and wellness facilities.',
    icon: MapPin,
  },
  {
    step: '03',
    title: 'Track',
    description:
      'Monitor continuous biometric progress and adjust clinical interventions dynamically based on real-world data.',
    icon: Activity,
  },
];

export function Mechanism(): ReactElement {
  return (
    <section id="platform" className="scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <h2 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            Closed-Loop Population Health Management.
          </h2>
          <p className="text-brand-700 mt-4 text-lg text-pretty">
            We don&rsquo;t just flag biometric risk. We route members to physical interventions and
            track outcomes in real time.
          </p>
        </div>

        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {STEPS.map((item) => (
            <div
              key={item.step}
              className="group ring-brand-100 hover:bg-brand-50 rounded-[var(--radius-card)] bg-white p-8 ring-1 transition-colors ring-inset sm:p-10"
            >
              <div className="flex items-center justify-between">
                <span className="bg-brand-100 text-brand-700 group-hover:bg-brand-200 flex size-11 items-center justify-center rounded-lg transition-colors">
                  <item.icon aria-hidden="true" className="size-5" />
                </span>
                <span className="text-brand-400 font-mono text-xs tabular-nums">{item.step}</span>
              </div>
              <h3 className="text-brand-950 mt-6 text-lg font-semibold tracking-tight">
                {item.title}
              </h3>
              <p className="text-brand-700 mt-2 text-sm leading-relaxed text-pretty">
                {item.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
