import type { ReactElement } from 'react';

import { Badge } from '@victus/ui';

const PILLARS = [
  {
    title: 'Uncertainty-aware triage',
    description:
      'Evidential deep learning quantifies how confident the model is in every score. Members resolve to a strict GREEN / YELLOW / RED state — uncertain cases are escalated for human audit, never silently classified.',
  },
  {
    title: 'Deterministic safety overrides',
    description:
      'Red-flag clinical symptoms bypass the network entirely and escalate straight to urgent referral. The model is never the last line of defence.',
  },
  {
    title: 'Calibrated for African populations',
    description:
      'Risk models are built to be invariant across measurement provenance — community health worker tape-measure inputs behave like clinical-grade inputs by construction — and optical biomarker pipelines are tuned for Fitzpatrick III–VI skin types.',
  },
] as const;

export function ClinicalApproach(): ReactElement {
  return (
    <section id="clinical-approach" className="scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <h2 className="text-brand-950 text-3xl font-semibold tracking-tighter text-balance sm:text-4xl">
            Built for evidence. Engineered for safety.
          </h2>
          <p className="text-brand-700 mt-4 text-lg text-pretty">
            The platform is engineered for clinical-validation deployment from day one — uncertainty
            is surfaced, never hidden, and safety logic is deterministic.
          </p>
          <div className="mt-5 flex flex-wrap gap-2" aria-label="Triage states">
            <Badge tone="green">GREEN — Low risk</Badge>
            <Badge tone="yellow">YELLOW — Audit required</Badge>
            <Badge tone="red">RED — Urgent referral</Badge>
          </div>
        </div>

        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {PILLARS.map((pillar) => (
            <div
              key={pillar.title}
              className="ring-brand-100 rounded-[var(--radius-card)] bg-white p-8 ring-1 ring-inset"
            >
              <h3 className="text-brand-950 text-lg font-semibold tracking-tight">
                {pillar.title}
              </h3>
              <p className="text-brand-700 mt-2 text-sm leading-relaxed text-pretty">
                {pillar.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
