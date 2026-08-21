import type { ReactElement } from 'react';

/* Factual capability statements only — never invented performance metrics. */
const POINTS = [
  { value: 'No bloods', label: 'Screen with a tape measure or a camera' },
  { value: 'Zimbabwe · Nigeria', label: 'Pilot deployments in preparation' },
  { value: '3 conditions', label: 'Diabetes, hypertension and obesity risk' },
  { value: 'POPIA · NDPA · CDPA', label: 'Data protection built in per country' },
] as const;

export function TrustStrip(): ReactElement {
  return (
    <section className="border-brand-100 border-b bg-white">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-x-6 gap-y-8 px-4 py-10 lg:grid-cols-4">
        {POINTS.map((point) => (
          <div key={point.value}>
            <p className="text-brand-700 text-lg font-semibold tracking-tight">{point.value}</p>
            <p className="text-grey-500 mt-1 text-sm text-pretty">{point.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
