import {
  type BiomarkerTrajectory,
  TOI_BIOMARKER_LABELS,
  type ToiTrajectoryResponse,
} from '@victus/contracts';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const DIRECTION_META: Record<
  BiomarkerTrajectory['direction'],
  { arrow: string; label: string; className: string }
> = {
  // For a vital sign, a rising resting rate is the concerning direction (rose);
  // falling is reassuring (emerald); stable is neutral.
  RISING: { arrow: '↑', label: 'Rising', className: 'text-rose-700' },
  FALLING: { arrow: '↓', label: 'Falling', className: 'text-emerald-700' },
  STABLE: { arrow: '→', label: 'Stable', className: 'text-brand-600' },
};

/**
 * Sparkline over native-unit values. Each series is normalised to its own
 * min/max so trends of different magnitudes (bpm vs breaths/min) read the same.
 */
function Sparkline({ values }: { values: number[] }): React.ReactElement {
  const w = 120;
  const h = 32;
  const n = values.length;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  // Flat series (or a single point) sits on the mid-line.
  const norm = (v: number): number => (span === 0 ? 0.5 : (v - min) / span);
  const pts =
    n === 1
      ? `0,${h / 2} ${w},${h / 2}`
      : values
          .map((v, i) => `${(i / (n - 1)) * w},${(h - norm(v) * h).toFixed(1)}`)
          .join(' ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
      <polyline
        points={pts}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Per-biomarker longitudinal vital-sign trajectory from contactless (rPPG)
 * checks — the Pathway B counterpart to the triage risk trajectory, and the
 * trend the "rising vital-sign" clinician nudge points at. Renders nothing until
 * at least one biomarker has ≥2 checks to trend. A change is flagged "real" only
 * when it exceeds the measurement's own confidence-interval uncertainty.
 * Presentational + server-safe.
 */
export function ToiTrajectoryPanel({
  trajectory,
  subtitle = "across this participant's contactless checks",
}: {
  trajectory: ToiTrajectoryResponse | null;
  subtitle?: string;
}): React.ReactElement | null {
  const trends = (trajectory?.trajectories ?? []).filter(
    (t) => t.points.length >= 2,
  );
  if (trends.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">
          Vital-sign trajectory{' '}
          <span className="text-sm font-normal text-brand-600">{subtitle}</span>
        </CardTitle>
        <p className="mt-1 max-w-3xl text-sm text-brand-700">
          How each contactless vital sign is moving over time. A change is only
          flagged as <em>real</em> when it exceeds the measurement&apos;s own
          uncertainty — otherwise it&apos;s treated as run-to-run noise, not a
          trend.
        </p>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2">
          {trends.map((t) => {
            const dir = DIRECTION_META[t.direction];
            const sign = t.delta >= 0 ? '+' : '';
            return (
              <div
                key={t.biomarker}
                className="rounded-[var(--radius-control)] border border-brand-100 p-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-brand-900">
                    {TOI_BIOMARKER_LABELS[t.biomarker]}
                  </span>
                  <span className={`text-sm font-semibold ${dir.className}`}>
                    {dir.arrow} {dir.label}
                  </span>
                </div>
                <div className="mt-1 flex items-end justify-between">
                  <span className="font-mono text-lg text-brand-950">
                    {t.latest_value.toFixed(t.biomarker === 'heart_rate' ? 0 : 1)}
                    <span className="ml-1 text-xs font-normal text-brand-600">
                      {t.unit}
                    </span>
                  </span>
                  <div className={dir.className}>
                    <Sparkline values={t.points.map((p) => p.value)} />
                  </div>
                </div>
                <p className="mt-2 text-xs text-brand-600">
                  {t.change_is_significant
                    ? `Significant change (Δ ${sign}${t.delta.toFixed(1)} ${t.unit})`
                    : 'Within measurement noise'}
                </p>
              </div>
            );
          })}
        </div>
        {trajectory && !trajectory.clinical_claims_authorised ? (
          <p className="mt-4 text-xs text-brand-500">
            Research demonstrator — an unvalidated pipeline output, not a clinical
            trend.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
