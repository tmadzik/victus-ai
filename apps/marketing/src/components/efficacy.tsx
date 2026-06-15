import type { ReactElement } from 'react';

export function Efficacy(): ReactElement {
  return (
    <section className="bg-brand-950 px-4 py-24 text-white sm:py-32">
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-6 text-center">
        <h2 className="text-4xl font-semibold tracking-tighter text-balance sm:text-6xl">
          Stop the 90 Million.
        </h2>
        <p className="text-lg leading-relaxed text-pretty text-white/80">
          NCDs will claim 90 million avoidable lives this decade. Stop waiting for lagging claims
          data. Act on predictive, high-fidelity biometric signals today.
        </p>
        <p className="text-sm text-pretty text-white/60">
          Calibrated for African populations and Fitzpatrick III–VI skin types to isolate
          cardiovascular and metabolic risk.
        </p>
        <p className="text-xs text-white/40">
          Source: NCD Alliance projection of avoidable NCD deaths, 2020–2030.
        </p>
      </div>
    </section>
  );
}
