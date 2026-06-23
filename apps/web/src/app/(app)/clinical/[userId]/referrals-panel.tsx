'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';

import {
  type Disease,
  DISEASE_LABELS,
  REFERRAL_DESTINATION_LABELS,
  type ReferralDestinationType,
  referralDestinationsForSite,
  type ReferralResponse,
  type ReferralStatus,
  ReferralUrgency,
  type TriageAssessmentResponse,
} from '@victus/contracts';

import { Badge, type BadgeProps } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  createReferralAction,
  updateReferralStatusAction,
} from '@/server/referral-actions';

const URGENCIES: ReferralUrgency[] = ['ROUTINE', 'URGENT', 'EMERGENCY'];

const STATUS_TONE: Record<string, BadgeProps['tone']> = {
  PENDING: 'yellow',
  ACKNOWLEDGED: 'brand',
  COMPLETED: 'green',
  CANCELLED: 'neutral',
};
const URGENCY_TONE: Record<string, BadgeProps['tone']> = {
  ROUTINE: 'neutral',
  URGENT: 'yellow',
  EMERGENCY: 'red',
};
// Allowed forward transitions a clinician can apply from each status.
const NEXT_STATUSES: Record<string, ReferralStatus[]> = {
  PENDING: ['ACKNOWLEDGED', 'CANCELLED'],
  ACKNOWLEDGED: ['COMPLETED', 'CANCELLED'],
  COMPLETED: [],
  CANCELLED: [],
};

const INPUT_CLASS =
  'w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-900 outline-none focus:border-brand-500';

function suggestionDate(a: TriageAssessmentResponse): string {
  return new Date(a.created_at).toLocaleDateString('en-ZA', { dateStyle: 'medium' });
}

// A RED triage assessment implies an urgent referral; a safety override (the
// deterministic immediate-referral path) escalates it to an emergency.
function suggestionUrgency(a: TriageAssessmentResponse): ReferralUrgency {
  return a.safety_override_triggered ? 'EMERGENCY' : 'URGENT';
}

function suggestionReason(a: TriageAssessmentResponse): string {
  const reds = a.per_disease
    .filter((d) => d.state === 'RED')
    .map((d) => DISEASE_LABELS[d.disease as Disease]);
  const drivers = reds.length > 0 ? `${reds.join(', ')} flagged RED` : 'overall RED';
  const override = a.safety_override_triggered ? ' Safety override triggered.' : '';
  return `Pathway A triage (${suggestionDate(a)}): ${drivers}.${override}`;
}

export function ReferralsPanel({
  participantId,
  siteCode,
  referrals,
  suggestions,
}: {
  participantId: string;
  // Participant's deployment site — gates which destination types are offered.
  siteCode: string;
  referrals: ReferralResponse[];
  // RED triage assessments not yet linked to a referral — offered as pre-fills.
  suggestions: TriageAssessmentResponse[];
}): React.ReactElement {
  const router = useRouter();
  const destTypes = referralDestinationsForSite(siteCode);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [destinationType, setDestinationType] =
    useState<ReferralDestinationType>(destTypes[0] ?? 'PUBLIC_CLINIC');
  const [destinationName, setDestinationName] = useState('');
  const [urgency, setUrgency] = useState<ReferralUrgency>(ReferralUrgency.ROUTINE);
  const [reason, setReason] = useState('');
  const [sourceAssessmentId, setSourceAssessmentId] = useState<string | null>(null);

  function applySuggestion(a: TriageAssessmentResponse): void {
    setReason(suggestionReason(a));
    setUrgency(suggestionUrgency(a));
    setSourceAssessmentId(a.id);
    setError(null);
  }

  function submit(e: React.FormEvent): void {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      const res = await createReferralAction({
        participant_user_id: participantId,
        destination_type: destinationType,
        destination_name: destinationName,
        urgency,
        reason,
        source_triage_assessment_id: sourceAssessmentId,
      });
      if (!res.ok) {
        setError(res.error);
        return;
      }
      setDestinationName('');
      setReason('');
      setUrgency(ReferralUrgency.ROUTINE);
      setSourceAssessmentId(null);
      router.refresh();
    });
  }

  function changeStatus(referralId: string, status: ReferralStatus): void {
    setError(null);
    startTransition(async () => {
      const res = await updateReferralStatusAction(referralId, participantId, status);
      if (!res.ok) {
        setError(res.error);
        return;
      }
      router.refresh();
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Referrals</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {suggestions.length > 0 ? (
          <div className="rounded-[var(--radius-control)] border border-rose-200 bg-rose-50 p-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-rose-700">
              Suggested from RED triage
            </p>
            <ul className="mt-2 space-y-2">
              {suggestions.map((a) => (
                <li
                  key={a.id}
                  className="flex flex-wrap items-center justify-between gap-2 text-sm"
                >
                  <span className="text-brand-800">
                    <Badge tone="red">RED</Badge>{' '}
                    <span className="ml-1">{suggestionReason(a)}</span>
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={pending}
                    onClick={() => applySuggestion(a)}
                  >
                    Pre-fill referral
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block font-medium text-brand-800">Destination type</span>
            <select
              className={INPUT_CLASS}
              value={destinationType}
              onChange={(e) =>
                setDestinationType(e.target.value as ReferralDestinationType)
              }
            >
              {destTypes.map((t) => (
                <option key={t} value={t}>
                  {REFERRAL_DESTINATION_LABELS[t]}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-brand-800">Destination name</span>
            <input
              required
              className={INPUT_CLASS}
              value={destinationName}
              onChange={(e) => setDestinationName(e.target.value)}
              placeholder="e.g. Victus Wellness — Harare"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-brand-800">Urgency</span>
            <select
              className={INPUT_CLASS}
              value={urgency}
              onChange={(e) => setUrgency(e.target.value as ReferralUrgency)}
            >
              {URGENCIES.map((u) => (
                <option key={u} value={u}>
                  {u.charAt(0) + u.slice(1).toLowerCase()}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm sm:col-span-2">
            <span className="mb-1 block font-medium text-brand-800">Reason</span>
            <textarea
              required
              rows={2}
              className={INPUT_CLASS}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Clinical reason for the referral"
            />
          </label>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
            <Button type="submit" disabled={pending}>
              {pending ? 'Saving…' : 'Raise referral'}
            </Button>
            {sourceAssessmentId ? (
              <span className="inline-flex items-center gap-1 text-xs text-brand-600">
                Linked to a triage assessment
                <button
                  type="button"
                  className="underline hover:text-brand-900"
                  onClick={() => setSourceAssessmentId(null)}
                >
                  clear
                </button>
              </span>
            ) : null}
            {error ? <span className="text-sm text-rose-700">{error}</span> : null}
          </div>
        </form>

        {referrals.length === 0 ? (
          <p className="text-sm text-brand-600">No referrals for this participant yet.</p>
        ) : (
          <ul className="space-y-3">
            {referrals.map((r) => (
              <li
                key={r.id}
                className="rounded-[var(--radius-control)] border border-brand-100 p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge tone={STATUS_TONE[r.status] ?? 'neutral'}>{r.status}</Badge>
                    <Badge tone={URGENCY_TONE[r.urgency] ?? 'neutral'}>{r.urgency}</Badge>
                    <span className="text-sm font-medium text-brand-900">
                      {r.destination_name}
                    </span>
                    <span className="text-xs text-brand-500">
                      {REFERRAL_DESTINATION_LABELS[
                        r.destination_type as ReferralDestinationType
                      ] ?? r.destination_type}
                    </span>
                  </div>
                  <time className="text-xs text-brand-600">
                    {new Date(r.created_at).toLocaleDateString('en-ZA', {
                      dateStyle: 'medium',
                    })}
                  </time>
                </div>
                <p className="mt-2 text-sm text-brand-800">{r.reason}</p>
                {r.notes ? (
                  <p className="mt-1 text-xs text-brand-600">Note: {r.notes}</p>
                ) : null}
                {(NEXT_STATUSES[r.status] ?? []).length > 0 ? (
                  <div className="mt-2 flex gap-2">
                    {(NEXT_STATUSES[r.status] ?? []).map((s) => (
                      <Button
                        key={s}
                        size="sm"
                        variant="outline"
                        disabled={pending}
                        onClick={() => changeStatus(r.id, s)}
                      >
                        {s === 'ACKNOWLEDGED'
                          ? 'Acknowledge'
                          : s === 'COMPLETED'
                            ? 'Complete'
                            : 'Cancel'}
                      </Button>
                    ))}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
