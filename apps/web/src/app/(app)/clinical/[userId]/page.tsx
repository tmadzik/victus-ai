import Link from 'next/link';
import { redirect } from 'next/navigation';

import {
  type ParticipantHistory,
  type ReferralResponse,
  type TrajectoryResponse,
  UserRole,
} from '@victus/contracts';

import { AssessmentTimeline } from '@/components/assessment-timeline';
import { TrajectoryPanel } from '@/components/trajectory-panel';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { formatLocale } from '@/i18n/config';
import { getLocale } from '@/i18n';
import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

import { ReferralsPanel } from './referrals-panel';

export const metadata = { title: 'Participant record — Victus AI' };

const CLINICAL_ROLES: readonly UserRole[] = [UserRole.CLINICIAN, UserRole.ADMIN];

export default async function ParticipantRecordPage({
  params,
}: {
  params: Promise<{ userId: string }>;
}): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');
  if (!CLINICAL_ROLES.includes(session.user.role)) redirect('/dashboard');

  const { userId } = await params;
  const formatLoc = formatLocale(await getLocale());

  let record: ParticipantHistory | null = null;
  let referrals: ReferralResponse[] = [];
  let error: string | null = null;
  try {
    [record, referrals] = await Promise.all([
      apiClient.getParticipantHistory(session.accessToken, userId),
      apiClient.listParticipantReferrals(session.accessToken, userId),
    ]);
  } catch (err) {
    error = err instanceof ApiError ? err.message : 'Could not load this participant.';
  }

  if (!record) {
    return (
      <div className="space-y-6">
        <BackLink />
        <Card>
          <CardContent className="py-10 text-center text-sm text-brand-600">
            {error ?? 'Participant not found.'}
          </CardContent>
        </Card>
      </div>
    );
  }

  const p = record.participant;
  // Longitudinal risk trend — best-effort; a failure must not blank the record.
  let trajectory: TrajectoryResponse | null = null;
  try {
    trajectory = await apiClient.getParticipantTrajectory(session.accessToken, userId);
  } catch {
    trajectory = null;
  }
  // Offer RED triage assessments that don't already have a referral linked.
  const linkedIds = new Set(
    referrals.map((r) => r.source_triage_assessment_id).filter(Boolean),
  );
  const suggestions = record.triage.filter(
    (t) => t.overall_state === 'RED' && !linkedIds.has(t.id),
  );
  return (
    <div className="space-y-6">
      <BackLink />

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
            Participant record
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
            {p.full_name ?? 'Unnamed participant'}
          </h1>
          <p className="mt-1 text-sm text-brand-600">
            {p.email ?? '—'} · {p.role} · site {p.site_code}
            {p.is_active ? '' : ' · inactive'}
          </p>
        </div>
        <div className="flex flex-col items-end gap-3">
          <div className="grid grid-cols-2 gap-3 text-right">
            <Stat label="Triage" value={String(p.triage_count)} />
            <Stat label="TOI" value={String(p.toi_count)} />
          </div>
          <Button asChild variant="outline" size="sm">
            <a href={`/api/clinical/${userId}/report`}>Download PDF</a>
          </Button>
        </div>
      </header>

      <ReferralsPanel
        participantId={userId}
        siteCode={p.site_code}
        referrals={referrals}
        suggestions={suggestions}
      />

      <TrajectoryPanel
        trajectory={trajectory}
        subtitle="across this participant's checks"
      />

      <AssessmentTimeline
        triage={record.triage}
        toi={record.toi}
        formatLoc={formatLoc}
        emptyHint="This participant has no assessments yet."
      />
    </div>
  );
}

function BackLink(): React.ReactElement {
  return (
    <Button asChild variant="outline" size="sm">
      <Link href="/clinical">← Participant search</Link>
    </Button>
  );
}

function Stat({ label, value }: { label: string; value: string }): React.ReactElement {
  return (
    <div className="rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 px-4 py-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-brand-700">{label}</p>
      <p className="mt-1 font-mono text-base text-brand-950">{value}</p>
    </div>
  );
}
