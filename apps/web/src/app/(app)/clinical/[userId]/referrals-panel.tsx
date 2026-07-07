'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';

import {
  type Disease,
  DISEASE_LABELS,
  REFERRAL_DESTINATION_LABELS,
  REFERRAL_OUTCOME_LABELS,
  type ReferralDestinationType,
  type ReferralOutcome,
  referralDestinationsForSite,
  type ReferralResponse,
  type ReferralStatus,
  ReferralUrgency,
  type TriageAssessmentResponse,
} from '@victus/contracts';

import { Badge, type BadgeProps } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useFormatLocale } from '@/i18n/context';
import {
  createReferralAction,
  recordReferralOutcomeAction,
  updateReferralStatusAction,
} from '@/server/referral-actions';

// The outcomes a clinician can record (PENDING is the un-recorded default).
const OUTCOME_OPTIONS: ReferralOutcome[] = [
  'ATTENDED_CONFIRMED',
  'ATTENDED_NOT_CONFIRMED',
  'ATTENDED_INCONCLUSIVE',
  'TREATMENT_STARTED',
  'DID_NOT_ATTEND',
  'DECLINED_CARE',
];
const OUTCOME_TONE: Record<string, BadgeProps['tone']> = {
  ATTENDED_CONFIRMED: 'green',
  TREATMENT_STARTED: 'green',
  ATTENDED_NOT_CONFIRMED: 'neutral',
  ATTENDED_INCONCLUSIVE: 'yellow',
  DID_NOT_ATTEND: 'red',
  DECLINED_CARE: 'red',
};

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
  return new Date(a.created_at).toLocaleDateString('en-GB', { dateStyle: 'medium' });
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
  const fmtLoc = useFormatLocale();
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
                    {new Date(r.created_at).toLocaleDateString(fmtLoc, {
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

                <OutcomeRecorder
                  referralId={r.id}
                  participantId={participantId}
                  currentOutcome={r.outcome}
                />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

const SMALL_INPUT =
  'rounded-[var(--radius-control)] border border-brand-200 bg-white px-2 py-1 text-xs text-brand-900 outline-none focus:border-brand-500';

// Care-loop closure with the data flywheel: recording a facility outcome, and —
// on an attended outcome — optionally the confirmed HbA1c / fasting glucose. With
// the participant's research consent that seeds a labelled training case server-side.
function OutcomeRecorder({
  referralId,
  participantId,
  currentOutcome,
}: {
  referralId: string;
  participantId: string;
  currentOutcome: string;
}): React.ReactElement {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [outcome, setOutcome] = useState<ReferralOutcome | ''>('');
  const [hba1c, setHba1c] = useState('');
  const [fpg, setFpg] = useState('');
  const [error, setError] = useState<string | null>(null);

  function submit(): void {
    if (!outcome) return;
    setError(null);
    startTransition(async () => {
      const res = await recordReferralOutcomeAction(referralId, participantId, outcome, {
        hba1c: hba1c ? Number(hba1c) : null,
        fpg: fpg ? Number(fpg) : null,
      });
      if (!res.ok) {
        setError(res.error);
        return;
      }
      setOutcome('');
      setHba1c('');
      setFpg('');
      router.refresh();
    });
  }

  return (
    <div className="mt-3 space-y-2 border-t border-brand-100 pt-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
          Facility outcome
        </span>
        {currentOutcome === 'PENDING' ? (
          <span className="text-xs text-brand-500">not yet recorded</span>
        ) : (
          <Badge tone={OUTCOME_TONE[currentOutcome] ?? 'neutral'}>
            {REFERRAL_OUTCOME_LABELS[currentOutcome as ReferralOutcome] ??
              currentOutcome}
          </Badge>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Facility outcome"
          className={SMALL_INPUT}
          value={outcome}
          disabled={pending}
          onChange={(e) => setOutcome(e.target.value as ReferralOutcome | '')}
        >
          <option value="">Record outcome…</option>
          {OUTCOME_OPTIONS.map((o) => (
            <option key={o} value={o}>
              {REFERRAL_OUTCOME_LABELS[o]}
            </option>
          ))}
        </select>
        <input
          type="number"
          step="0.1"
          placeholder="HbA1c %"
          aria-label="Confirmed HbA1c percent"
          className={`${SMALL_INPUT} w-24`}
          value={hba1c}
          disabled={pending}
          onChange={(e) => setHba1c(e.target.value)}
        />
        <input
          type="number"
          step="0.1"
          placeholder="FPG mmol/L"
          aria-label="Confirmed fasting glucose"
          className={`${SMALL_INPUT} w-28`}
          value={fpg}
          disabled={pending}
          onChange={(e) => setFpg(e.target.value)}
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={pending || !outcome}
          onClick={submit}
        >
          Record
        </Button>
      </div>
      <p className="text-[0.65rem] text-brand-500">
        Adding a facility HbA1c / glucose (with the participant&apos;s research
        consent) seeds a labelled training case — closing the data loop.
      </p>
      {error ? <p className="text-xs text-rose-700">{error}</p> : null}
    </div>
  );
}
