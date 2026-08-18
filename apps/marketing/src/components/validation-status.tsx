import type { ReactElement } from 'react';

const PILOTS = [
  { country: 'Zimbabwe', regime: 'Cyber & Data Protection Act' },
  { country: 'Nigeria', regime: 'NDPA' },
] as const;

export function ValidationStatus(): ReactElement {
  return (
    <section id="validation" className="scroll-mt-24 px-4 py-20 sm:py-28">
      <div className="ring-brand-100 mx-auto max-w-4xl rounded-[var(--radius-card)] bg-white p-8 ring-1 ring-inset sm:p-12">
        <p className="text-brand-500 text-xs font-semibold tracking-wider uppercase">
          Where we are
        </p>
        <h2 className="text-brand-950 mt-2 text-2xl font-semibold tracking-tighter text-balance sm:text-3xl">
          A research demonstrator, on a clear validation path.
        </h2>
        <div className="text-brand-700 mt-4 flex flex-col gap-4 text-pretty">
          <p>
            Victus is deployed today as a <strong>research demonstrator</strong>. Until the models
            complete prospective clinical validation, screening results are presented as research
            outputs — not clinical diagnoses. The platform enforces this in software: every result
            carries that framing, so a demo and a live deployment can never quietly look the same.
          </p>
          <p>
            Deterministic safety overrides for danger signs stay active in every mode — conservative
            first-aid guidance is never withheld, whatever the model does.
          </p>
        </div>

        <div className="border-brand-100 mt-8 border-t pt-6">
          <p className="text-brand-800 text-sm font-medium">In active pilots</p>
          <div className="mt-3 flex flex-wrap gap-3">
            {PILOTS.map((pilot) => (
              <div
                key={pilot.country}
                className="ring-brand-100 rounded-full px-4 py-1.5 text-sm ring-1 ring-inset"
              >
                <span className="text-brand-950 font-semibold">{pilot.country}</span>
                <span className="text-grey-500"> · {pilot.regime}</span>
              </div>
            ))}
          </div>
          <p className="text-grey-500 mt-3 text-sm text-pretty">
            Each pilot is its own jurisdiction-aware deployment, with clinical validation on local
            cohorts as an explicit precondition to any clinical claim.
          </p>
        </div>
      </div>
    </section>
  );
}
