import Link from 'next/link';
import { redirect } from 'next/navigation';

import {
  type EnrollmentSummary,
  type ParticipantHistory,
  type ReferralResponse,
  type ToiTrajectoryResponse,
  type TrajectoryResponse,
  UserRole,
} from '@victus/contracts';

import { AssessmentTimeline } from '@/components/assessment-timeline';
import { ToiTrajectoryPanel } from '@/components/toi-trajectory-panel';
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
  // Longitudinal trends — best-effort; a failure must not blank the record. The
  // triage (risk) and TOI (vital-sign) trajectories are fetched independently so
  // one pathway's absence never hides the other.
  let trajectory: TrajectoryResponse | null = null;
  let toiTrajectory: ToiTrajectoryResponse | null = null;
  try {
    trajectory = await apiClient.getParticipantTrajectory(session.accessToken, userId);
  } catch {
    trajectory = null;
  }
  try {
    toiTrajectory = await apiClient.getParticipantToiTrajectory(
      session.accessToken,
      userId,
    );
  } catch {
    toiTrajectory = null;
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

      <EnrollmentCard enrollment={record.enrollment} formatLoc={formatLoc} />

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

      <ToiTrajectoryPanel trajectory={toiTrajectory} />

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

function EnrollmentCard({
  enrollment,
  formatLoc,
}: {
  enrollment: EnrollmentSummary;
  formatLoc: string;
}): React.ReactElement {
  if (!enrollment.enrolled) {
    return (
      <Card>
        <CardContent className="py-6">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
            Enrollment
          </p>
          <p className="mt-2 text-sm text-brand-600">
            No front-of-platform enrollment record for this participant.
          </p>
        </CardContent>
      </Card>
    );
  }
  const pid = enrollment.patient_id_hash;
  const enrolledAt = enrollment.enrolled_at
    ? new Date(enrollment.enrolled_at).toLocaleString(formatLoc)
    : '—';
  const fields: Array<{ label: string; value: string; mono?: boolean }> = [
    { label: 'Age band', value: enrollment.age_range ?? '—' },
    { label: 'Biological sex', value: enrollment.biological_sex ?? '—' },
    { label: 'Region', value: enrollment.region ?? '—' },
    { label: 'Jurisdiction', value: enrollment.jurisdiction ?? '—' },
    { label: 'Race / ethnicity', value: enrollment.race_ethnicity ?? 'Not stated' },
    { label: 'Enrolled', value: enrolledAt },
    {
      label: 'Patient ID',
      value: pid ? `${pid.slice(0, 12)}… (SHA-256)` : '—',
      mono: true,
    },
    {
      label: 'Consents',
      value: enrollment.consents.length ? enrollment.consents.join(', ') : 'None on file',
    },
  ];
  return (
    <Card>
      <CardContent className="py-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Enrollment
        </p>
        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
          {fields.map((f) => (
            <div key={f.label}>
              <dt className="text-xs font-semibold uppercase tracking-wider text-brand-600">
                {f.label}
              </dt>
              <dd
                className={`mt-1 text-sm text-brand-950${f.mono ? ' font-mono break-all' : ''}`}
              >
                {f.value}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
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
