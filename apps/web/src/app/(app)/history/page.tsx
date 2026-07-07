import Link from 'next/link';
import { redirect } from 'next/navigation';

import { AssessmentTimeline, fmtDate } from '@/components/assessment-timeline';
import { TrajectoryPanel } from '@/components/trajectory-panel';
import { Button } from '@/components/ui/button';
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
