'use client';

import { useState } from 'react';

import {
  ERASURE_BASIS_LABELS,
  ErasureBasis,
  ErasureJurisdiction,
  type ErasureRequestResponse,
  type MyDataSummary,
} from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { eraseAccountAction } from '@/server/governance-actions';

export function GovernanceClient({
  summary,
  initialErasureRequests,
}: {
  summary: MyDataSummary;
  initialErasureRequests: ErasureRequestResponse[];
}): React.ReactElement {
  const [showModal, setShowModal] = useState(false);

  return (
    <div className="space-y-8">
      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>
            Identifying fields the service holds for this account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-3 sm:grid-cols-2">
            <Field label="User ID" value={summary.user_id} mono />
            <Field label="Email" value={summary.email ?? '— (tombstoned)'} mono />
            <Field label="Full name" value={summary.full_name ?? '— (tombstoned)'} />
            <Field label="Role" value={summary.role} />
            <Field
              label="Account created"
              value={new Date(summary.created_at).toLocaleString('en-ZA')}
            />
            <Field
              label="Erased at"
              value={
                summary.erased_at
                  ? new Date(summary.erased_at).toLocaleString('en-ZA')
                  : '—'
              }
            />
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Data inventory</CardTitle>
          <CardDescription>
            Counts of every record type this account owns. Counts are
            authoritative — this endpoint itself is audited as{' '}
            <code className="font-mono text-xs">
              DATA_ACCESS_REQUEST_FULFILLED
            </code>
            .
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <CountCell label="Triage assessments" n={summary.counts.triage_assessments} />
            <CountCell label="TOI assessments" n={summary.counts.toi_assessments} />
            <CountCell label="Calibration pairs" n={summary.counts.calibration_records} />
            <CountCell label="Study subjects" n={summary.counts.study_subjects} />
            <CountCell label="Study sessions" n={summary.counts.study_sessions} />
            <CountCell label="Consent records" n={summary.counts.consent_records} />
            <CountCell label="Erasure requests" n={summary.counts.erasure_requests} />
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Retention policy</CardTitle>
          <CardDescription>
            What happens when you erase your account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-relaxed text-brand-800">
            {summary.retention_policy_summary}
          </p>
        </CardContent>
      </Card>

      {initialErasureRequests.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Erasure ledger</CardTitle>
            <CardDescription>
              Append-only history of erasure requests for this account.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ErasureLedger requests={initialErasureRequests} />
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-[color:var(--color-state-red-fg)]">
            Erase this account
          </CardTitle>
          <CardDescription>
            Cannot be undone. Tombstones PII, revokes all sessions, anonymises
            your study subjects, retains de-identified research records.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {summary.erased_at ? (
            <Alert tone="info">
              <AlertTitle>Already erased</AlertTitle>
              <AlertDescription>
                This account was erased on{' '}
                {new Date(summary.erased_at).toLocaleString('en-ZA')}.
              </AlertDescription>
            </Alert>
          ) : (
            <Button variant="danger" onClick={() => setShowModal(true)}>
              I want to erase my account
            </Button>
          )}
        </CardContent>
      </Card>

      {showModal && !summary.erased_at ? (
        <EraseAccountModal
          email={summary.email ?? ''}
          onClose={() => setShowModal(false)}
        />
      ) : null}
    </div>
  );
}

function EraseAccountModal({
  email,
  onClose,
}: {
  email: string;
  onClose: () => void;
}): React.ReactElement {
  const [confirmEmail, setConfirmEmail] = useState('');
  const [basis, setBasis] = useState<ErasureBasis>(
    ErasureBasis.ACCOUNT_DELETION,
  );
  const [jurisdiction, setJurisdiction] = useState<ErasureJurisdiction>(
    ErasureJurisdiction.GDPR,
  );
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  const submit = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    if (confirmEmail.trim().toLowerCase() !== email.trim().toLowerCase()) {
      setError(
        `The confirm email must match your account address exactly: ${email}`,
      );
      return;
    }
    setIsPending(true);
    setError(null);
    const result = await eraseAccountAction({
      confirm_email: confirmEmail.trim(),
      jurisdiction,
      request_basis: basis,
      notes: notes.trim() || null,
    });
    // Success redirects in the action; if we got here, it failed.
    if (!result.ok) {
      setError(result.error);
      setIsPending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-lg border-[color:var(--color-state-red-ring)]/40">
        <CardHeader>
          <CardTitle className="text-[color:var(--color-state-red-fg)]">
            Confirm account erasure
          </CardTitle>
          <CardDescription>
            Type your account email exactly to confirm. This is irreversible.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <Alert tone="danger" className="mb-4">
              <AlertTitle>Cannot erase</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <form onSubmit={submit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="confirm-email">
                Type{' '}
                <span className="font-mono text-brand-900">{email}</span>
              </Label>
              <Input
                id="confirm-email"
                type="email"
                required
                value={confirmEmail}
                onChange={(e) => setConfirmEmail(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="jurisdiction">Jurisdiction</Label>
                <select
                  id="jurisdiction"
                  value={jurisdiction}
                  onChange={(e) =>
                    setJurisdiction(e.target.value as ErasureJurisdiction)
                  }
                  className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                >
                  {(Object.values(ErasureJurisdiction) as ErasureJurisdiction[]).map(
                    (j) => (
                      <option key={j} value={j}>
                        {j}
                      </option>
                    ),
                  )}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="basis">Basis</Label>
                <select
                  id="basis"
                  value={basis}
                  onChange={(e) => setBasis(e.target.value as ErasureBasis)}
                  className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                >
                  {(Object.values(ErasureBasis) as ErasureBasis[]).map((b) => (
                    <option key={b} value={b}>
                      {ERASURE_BASIS_LABELS[b]}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="notes">Notes (optional)</Label>
              <Input
                id="notes"
                type="text"
                maxLength={2000}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                disabled={isPending}
              >
                Cancel
              </Button>
              <Button type="submit" variant="danger" disabled={isPending}>
                {isPending ? 'Erasing…' : 'Erase account permanently'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function ErasureLedger({
  requests,
}: {
  requests: ErasureRequestResponse[];
}): React.ReactElement {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="border-b border-brand-200 text-left text-xs uppercase tracking-wider text-brand-700">
          <tr>
            <th className="py-2 pr-4">Requested</th>
            <th className="py-2 pr-4">Target</th>
            <th className="py-2 pr-4">Jurisdiction</th>
            <th className="py-2 pr-4">Basis</th>
            <th className="py-2 pr-4">Status</th>
            <th className="py-2 pr-4">Retention?</th>
          </tr>
        </thead>
        <tbody>
          {requests.map((r) => (
            <tr key={r.id} className="border-b border-brand-100">
              <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                {new Date(r.requested_at).toLocaleString('en-ZA')}
              </td>
              <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                {r.target_type}
              </td>
              <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                {r.jurisdiction}
              </td>
              <td className="py-2 pr-4 text-xs text-brand-700">
                {ERASURE_BASIS_LABELS[r.request_basis]}
              </td>
              <td className="py-2 pr-4">
                <Badge
                  tone={
                    r.status === 'COMPLETED'
                      ? 'green'
                      : r.status === 'PENDING'
                        ? 'yellow'
                        : 'red'
                  }
                >
                  {r.status}
                </Badge>
              </td>
              <td className="py-2 pr-4 text-xs text-brand-700">
                {r.statutory_retention_applied ? 'yes' : 'no'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}): React.ReactElement {
  return (
    <div className="rounded-[var(--radius-control)] border border-brand-100 p-3">
      <dt className="text-xs font-semibold uppercase tracking-wider text-brand-700">
        {label}
      </dt>
      <dd
        className={
          'mt-1 text-sm text-brand-950' + (mono ? ' font-mono' : '')
        }
      >
        {value}
      </dd>
    </div>
  );
}

function CountCell({
  label,
  n,
}: {
  label: string;
  n: number;
}): React.ReactElement {
  return (
    <div className="rounded-[var(--radius-control)] border border-brand-100 bg-brand-50 p-3">
      <dt className="text-xs font-semibold uppercase tracking-wider text-brand-700">
        {label}
      </dt>
      <dd className="mt-1 font-mono text-2xl text-brand-950">{n}</dd>
    </div>
  );
}
