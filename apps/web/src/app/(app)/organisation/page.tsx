import Link from 'next/link';
import { redirect } from 'next/navigation';

import { type CohortReport, UserRole } from '@victus/contracts';

import { Card, CardContent } from '@/components/ui/card';
import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

import { SuppressedBreakdown } from './suppressed';

export const metadata = { title: 'Cohort overview' };

const ORG_ROLES: readonly UserRole[] = [
  UserRole.ORG_ADMIN,
  UserRole.CARE_MANAGER,
  UserRole.ADMIN,
];

const TRIAGE_ORDER = ['GREEN', 'YELLOW', 'RED'] as const;
const TRIAGE_TONE: Record<string, string> = {
  GREEN: 'text-emerald-700',
  YELLOW: 'text-amber-700',
  RED: 'text-red-700',
};

function percent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

export default async function OrganisationPage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');
  if (!ORG_ROLES.includes(session.user.role)) redirect('/dashboard');

  let report: CohortReport | null = null;
  let error: string | null = null;
  try {
    report = await apiClient.getCohortReport(session.accessToken);
  } catch (err) {
    error = err instanceof ApiError ? err.message : 'Could not load the cohort overview.';
  }

  const totalSuppressed = report
    ? Object.values(report.suppression).reduce(
        (sum, s) => sum + s.cells_suppressed + s.complementary_suppressed,
        0,
      )
    : 0;

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Population reporting
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          Cohort overview
        </h1>
        <p className="mt-2 max-w-2xl text-brand-700">
          Screening across your member base, and whether the people it flags reach
          care. Groups too small to report are withheld rather than shown, so no
          individual can be identified from a breakdown.
        </p>
      </header>

      {error ? (
        <Card>
          <CardContent className="py-6">
            <p className="text-brand-800">{error}</p>
          </CardContent>
        </Card>
      ) : null}

      {report ? (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <CardContent className="py-6">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-600">
                  Members screened
                </p>
                <p className="mt-2 text-4xl font-semibold tabular-nums tracking-tight text-brand-950">
                  {report.members_screened.toLocaleString()}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="py-6">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-600">
                  Reached care
                </p>
                <p className="mt-2 text-4xl font-semibold tabular-nums tracking-tight text-brand-950">
                  {percent(report.care_loop.attendance_rate)}
                </p>
                <p className="mt-1 text-xs text-brand-600">
                  {report.care_loop.attended.toLocaleString()} of{' '}
                  {report.care_loop.outcomes_recorded.toLocaleString()} with a
                  recorded outcome
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="py-6">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-600">
                  Referrals closed
                </p>
                <p className="mt-2 text-4xl font-semibold tabular-nums tracking-tight text-brand-950">
                  {percent(report.care_loop.closure_rate)}
                </p>
                <p className="mt-1 text-xs text-brand-600">
                  {report.care_loop.referrals_total.toLocaleString()} referrals
                  raised in total
                </p>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardContent className="py-6">
                <SuppressedBreakdown
                  title="Triage state"
                  cells={report.triage_distribution}
                  order={TRIAGE_ORDER}
                  tone={TRIAGE_TONE}
                />
              </CardContent>
            </Card>
            <Card>
              <CardContent className="py-6">
                <SuppressedBreakdown title="Age" cells={report.by_age_band} />
              </CardContent>
            </Card>
            <Card>
              <CardContent className="py-6">
                <SuppressedBreakdown title="Sex" cells={report.by_sex} />
              </CardContent>
            </Card>
          </div>

          {totalSuppressed > 0 ? (
            <Card>
              <CardContent className="py-5">
                <h2 className="text-sm font-semibold text-brand-950">
                  {totalSuppressed} group{totalSuppressed === 1 ? '' : 's'} withheld
                </h2>
                <p className="mt-2 max-w-3xl text-sm text-brand-700">
                  Groups containing fewer than the minimum number of members are
                  not shown, because a small group can identify the people in it.
                  Where withholding one group would let its size be worked out by
                  subtracting the rest from the total, a second is withheld too.
                </p>
                <p className="mt-2 max-w-3xl text-sm text-brand-600">
                  This falls hardest on the smallest groups, which is worth
                  remembering when reading the breakdowns: a withheld group is
                  not an empty one.
                </p>
              </CardContent>
            </Card>
          ) : null}

          {session.user.role === UserRole.CARE_MANAGER ? (
            <Card>
              <CardContent className="flex flex-wrap items-center justify-between gap-4 py-5">
                <div>
                  <h2 className="text-sm font-semibold text-brand-950">
                    Route people into care
                  </h2>
                  <p className="mt-1 max-w-xl text-sm text-brand-700">
                    Open the list of members whose latest screening flagged them,
                    so you can follow up individually.
                  </p>
                </div>
                <Link
                  href="/organisation/members"
                  className="rounded-full bg-brand-700 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-brand-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700"
                >
                  Flagged members
                </Link>
              </CardContent>
            </Card>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
