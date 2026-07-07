import {
  type DiseaseTrajectory,
  DISEASE_LABELS,
  type TrajectoryResponse,
} from '@victus/contracts';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const DIRECTION_META: Record<
  DiseaseTrajectory['direction'],
  { arrow: string; label: string; className: string }
> = {
  // Rising risk is bad (rose); falling risk is good (emerald); stable neutral.
  RISING: { arrow: '↑', label: 'Rising', className: 'text-rose-700' },
  FALLING: { arrow: '↓', label: 'Falling', className: 'text-emerald-700' },
  STABLE: { arrow: '→', label: 'Stable', className: 'text-brand-600' },
};

function Sparkline({ values }: { values: number[] }): React.ReactElement {
  const w = 120;
  const h = 32;
  const n = values.length;
  const first = values[0] ?? 0;
  const pts =
    n === 1
      ? `0,${h - first * h} ${w},${h - first * h}`
      : values
          .map((v, i) => `${(i / (n - 1)) * w},${(h - v * h).toFixed(1)}`)
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
 * Per-disease longitudinal risk trajectory. Renders nothing until at least one
 * disease has ≥2 assessments to trend. A change is flagged "real" only when it
 * exceeds the model's own measurement uncertainty. Presentational + server-safe;
 * shared by the participant's /history and the clinician participant record.
 */
export function TrajectoryPanel({
  trajectory,
  subtitle = 'over repeated checks',
}: {
  trajectory: TrajectoryResponse | null;
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
          Risk trajectory{' '}
          <span className="text-sm font-normal text-brand-600">{subtitle}</span>
        </CardTitle>
        <p className="mt-1 max-w-3xl text-sm text-brand-700">
          How each disease&apos;s risk is moving over time. A change is only
          flagged as <em>real</em> when it exceeds the model&apos;s own
          measurement uncertainty — otherwise it&apos;s treated as run-to-run
          noise, not a trend.
        </p>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-3">
          {trends.map((t) => {
            const dir = DIRECTION_META[t.direction];
            return (
              <div
                key={t.disease}
                className="rounded-[var(--radius-control)] border border-brand-100 p-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-brand-900">
                    {DISEASE_LABELS[t.disease]}
                  </span>
                  <span className={`text-sm font-semibold ${dir.className}`}>
                    {dir.arrow} {dir.label}
                  </span>
                </div>
                <div className={`mt-2 ${dir.className}`}>
                  <Sparkline values={t.points.map((p) => p.risk_index)} />
                </div>
                <p className="mt-2 text-xs text-brand-600">
                  {t.change_is_significant
                    ? `Significant change (Δ ${t.delta >= 0 ? '+' : ''}${t.delta.toFixed(2)})`
                    : 'Within measurement noise'}
                </p>
              </div>
            );
          })}
        </div>
        {trajectory && !trajectory.clinical_claims_authorised ? (
          <p className="mt-4 text-xs text-brand-500">
            Research demonstrator — an unvalidated model output, not a clinical
            trend.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
