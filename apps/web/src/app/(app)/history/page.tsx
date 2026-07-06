import Link from 'next/link';
import { redirect } from 'next/navigation';

import {
  type DiseaseTrajectory,
  DISEASE_LABELS,
  type TrajectoryResponse,
} from '@victus/contracts';

import { AssessmentTimeline, fmtDate } from '@/components/assessment-timeline';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatLocale } from '@/i18n/config';
import { getLocale } from '@/i18n';
import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export const metadata = { title: 'Assessment history — Victus AI' };

// The two list endpoints are consent-gated, so a participant who has only used
// one pathway gets a 403 on the other. Treat that as "no records", not an error.
async function safeList<T>(p: Promise<T[]>): Promise<T[]> {
  try {
    return await p;
  } catch (err) {
    if (err instanceof ApiError && (err.status === 403 || err.status === 404)) return [];
    throw err;
  }
}

async function safeOne<T>(p: Promise<T>): Promise<T | null> {
  try {
    return await p;
  } catch (err) {
    if (err instanceof ApiError && (err.status === 403 || err.status === 404)) return null;
    throw err;
  }
}

export default async function HistoryPage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');

  const [triage, toi, trajectory] = await Promise.all([
    safeList(apiClient.listMyTriageAssessments(session.accessToken, 50)),
    safeList(apiClient.listMyToiAssessments(session.accessToken, 50)),
    safeOne(apiClient.getMyTrajectory(session.accessToken, 50)),
  ]);

  const formatLoc = formatLocale(await getLocale());
  const times = [...triage, ...toi].map((a) => new Date(a.created_at).getTime());
  const lastActivity =
    times.length > 0 ? fmtDate(new Date(Math.max(...times)).toISOString(), formatLoc) : '—';

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
            Longitudinal record
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
            Assessment history
          </h1>
          <p className="mt-2 max-w-2xl text-brand-700">
            Every Pathway A triage and Pathway B TOI capture you have run, newest
            first. Repeat measures over time are how risk trajectory — not just a
            single snapshot — becomes visible.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/triage">New triage →</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/toi">New TOI →</Link>
          </Button>
        </div>
      </header>

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Metric label="Total assessments" value={String(triage.length + toi.length)} />
        <Metric label="Pathway A — Triage" value={String(triage.length)} />
        <Metric label="Pathway B — TOI" value={String(toi.length)} />
        <Metric label="Last activity" value={lastActivity} mono={false} />
      </section>

      <TrajectoryPanel trajectory={trajectory} />

      <AssessmentTimeline
        triage={triage}
        toi={toi}
        formatLoc={formatLoc}
        emptyHint={
          <>
            No assessments yet. Start with a{' '}
            <Link href="/triage" className="font-medium text-brand-800 underline">
              Pathway A triage
            </Link>{' '}
            or a{' '}
            <Link href="/toi" className="font-medium text-brand-800 underline">
              Pathway B TOI capture
            </Link>
            .
          </>
        }
      />
    </div>
  );
}

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

function TrajectoryPanel({
  trajectory,
}: {
  trajectory: TrajectoryResponse | null;
}): React.ReactElement | null {
  const trends = (trajectory?.trajectories ?? []).filter((t) => t.points.length >= 2);
  if (trends.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">
          Risk trajectory{' '}
          <span className="text-sm font-normal text-brand-600">
            over your repeated checks
          </span>
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

function Metric({
  label,
  value,
  mono = true,
}: {
  label: string;
  value: string;
  mono?: boolean;
}): React.ReactElement {
  return (
    <div className="rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 p-3">
      <p className="text-xs font-semibold uppercase tracking-wider text-brand-700">{label}</p>
      <p className={`mt-1 text-base text-brand-950 ${mono ? 'font-mono' : ''}`}>{value}</p>
    </div>
  );
}
