import Link from 'next/link';
import { redirect } from 'next/navigation';

import {
  type ParticipantHistory,
  type ReferralResponse,
  UserRole,
} from '@victus/contracts';

import { AssessmentTimeline } from '@/components/assessment-timeline';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
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
            {p.email ?? '—'} · {p.role}
            {p.is_active ? '' : ' · inactive'}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3 text-right">
          <Stat label="Triage" value={String(p.triage_count)} />
          <Stat label="TOI" value={String(p.toi_count)} />
        </div>
      </header>

      <ReferralsPanel participantId={userId} referrals={referrals} />

      <AssessmentTimeline
        triage={record.triage}
        toi={record.toi}
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
