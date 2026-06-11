import type { ReactElement } from 'react';

/* Illustrative population-risk figures only — rendered from the shared design
   system, never from patient records. */
const METRICS = [
  { label: 'Members screened', value: '12,482', delta: '+8.2%' },
  { label: 'RED referrals', value: '316', delta: '−4.1%' },
  { label: 'Median risk score', value: '0.34', delta: '−0.05' },
] as const;

const RISK_DISTRIBUTION = [
  { label: 'GREEN', share: 71, colorVar: '--color-state-green-ring' },
  { label: 'YELLOW', share: 21, colorVar: '--color-state-yellow-ring' },
  { label: 'RED', share: 8, colorVar: '--color-state-red-ring' },
] as const;

const TRENDLINES = [
  {
    label: 'Systolic BP — flagged cohort',
    value: '131 mmHg',
    points: '0,26 12,24 24,27 36,22 48,23 60,19 72,20 84,16 96,17 108,13 120,14',
  },
  {
    label: 'Resting HR — flagged cohort',
    value: '74 bpm',
    points: '0,18 12,21 24,17 36,22 48,18 60,21 72,16 84,19 96,14 108,16 120,12',
  },
] as const;

export function DashboardMockup(): ReactElement {
  return (
    <div
      aria-label="Illustration of the Victus population risk dashboard"
      role="img"
      className="bg-brand-950 rounded-[var(--radius-card)] p-6 text-white shadow-2xl ring-1 ring-white/10 ring-inset sm:p-8"
    >
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs font-medium tracking-wider text-white/50 uppercase">
            Population Risk · Q2 2026
          </p>
          <p className="mt-1 text-sm font-semibold">Fund-wide NCD overview</p>
        </div>
        <span className="rounded-full px-2.5 py-0.5 text-[10px] font-semibold tracking-wider text-white/60 uppercase ring-1 ring-white/20 ring-inset">
          Illustrative data
        </span>
      </div>

      <dl className="mt-6 grid grid-cols-3 gap-3">
        {METRICS.map((metric) => (
          <div
            key={metric.label}
            className="rounded-lg bg-white/5 p-3 ring-1 ring-white/10 ring-inset"
          >
            <dt className="text-[10px] font-medium tracking-wider text-white/50 uppercase">
              {metric.label}
            </dt>
            <dd className="mt-1.5 font-mono text-lg font-semibold tabular-nums sm:text-xl">
              {metric.value}
            </dd>
            <dd className="text-brand-300 font-mono text-[11px] tabular-nums">{metric.delta}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-4 rounded-lg bg-white/5 p-4 ring-1 ring-white/10 ring-inset">
        <p className="text-[10px] font-medium tracking-wider text-white/50 uppercase">
          Triage state distribution
        </p>
        <div className="mt-3 flex h-2.5 w-full overflow-hidden rounded-full">
          {RISK_DISTRIBUTION.map((segment) => (
            <div
              key={segment.label}
              style={{
                width: `${segment.share}%`,
                backgroundColor: `var(${segment.colorVar})`,
              }}
            />
          ))}
        </div>
        <div className="mt-3 flex gap-5">
          {RISK_DISTRIBUTION.map((segment) => (
            <p key={segment.label} className="flex items-center gap-1.5 text-[11px] text-white/70">
              <span
                aria-hidden="true"
                className="size-2 rounded-full"
                style={{ backgroundColor: `var(${segment.colorVar})` }}
              />
              {segment.label}
              <span className="font-mono text-white/50 tabular-nums">{segment.share}%</span>
            </p>
          ))}
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {TRENDLINES.map((trend) => (
          <div
            key={trend.label}
            className="rounded-lg bg-white/5 p-4 ring-1 ring-white/10 ring-inset"
          >
            <div className="flex items-baseline justify-between gap-2">
              <p className="text-[10px] font-medium tracking-wider text-white/50 uppercase">
                {trend.label}
              </p>
              <p className="font-mono text-xs font-semibold tabular-nums">{trend.value}</p>
            </div>
            <svg
              viewBox="0 0 120 32"
              preserveAspectRatio="none"
              aria-hidden="true"
              className="text-brand-400 mt-3 h-10 w-full"
            >
              <polyline
                points={trend.points}
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
        ))}
      </div>
    </div>
  );
}
