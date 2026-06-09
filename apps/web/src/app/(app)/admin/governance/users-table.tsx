'use client';

import { useState, useTransition } from 'react';

import {
  type AdminUserDataSummary,
  type AdminUserListItem,
  type AdminUserListResponse,
  ErasureJurisdiction,
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
import {
  adminGetUserDataSummaryAction,
  adminListUsersAction,
  adminProposeEraseAccountAction,
} from '@/server/admin-actions';

export function UsersTable({
  initialUsers,
}: {
  initialUsers: AdminUserListResponse;
}): React.ReactElement {
  const [data, setData] = useState<AdminUserListResponse>(initialUsers);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [eraseTarget, setEraseTarget] = useState<AdminUserListItem | null>(null);
  const [summary, setSummary] = useState<AdminUserDataSummary | null>(null);
  const [isPending, startTransition] = useTransition();

  const refresh = (offset: number): void => {
    startTransition(async () => {
      const next = await adminListUsersAction({
        limit: data.limit,
        offset,
        includeErased: true,
      });
      setData(next);
    });
  };

  const viewSummary = (userId: string): void => {
    setSummary(null);
    setError(null);
    startTransition(async () => {
      const result = await adminGetUserDataSummaryAction(userId);
      if (result.ok) setSummary(result.value);
      else setError(result.error);
    });
  };

  return (
    <div className="space-y-4">
      {error ? (
        <Alert tone="danger">
          <AlertTitle>Action failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {submitted ? (
        <Alert tone="success">
          <AlertTitle>Submitted for approval</AlertTitle>
          <AlertDescription>
            Erasure of {submitted} is now awaiting a second administrator&apos;s
            approval. See the “Pending approvals” tab. No data has been
            destroyed yet.
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <CardTitle>Users ({data.total})</CardTitle>
            <CardDescription>
              Erased accounts show de-identified shells — PII columns read —.
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={data.offset === 0 || isPending}
              onClick={() => refresh(Math.max(0, data.offset - data.limit))}
            >
              Prev
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={data.offset + data.limit >= data.total || isPending}
              onClick={() => refresh(data.offset + data.limit)}
            >
              Next
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="border-b border-brand-200 text-left text-xs uppercase tracking-wider text-brand-700">
                <tr>
                  <th className="py-2 pr-4">Email</th>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Role</th>
                  <th className="py-2 pr-4">Subjects</th>
                  <th className="py-2 pr-4">Pairs</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.users.map((u) => (
                  <tr key={u.id} className="border-b border-brand-100">
                    <td className="py-2 pr-4 font-mono text-xs text-brand-900">
                      {u.email ?? '—'}
                    </td>
                    <td className="py-2 pr-4 text-brand-700">
                      {u.full_name ?? '—'}
                    </td>
                    <td className="py-2 pr-4">
                      <Badge tone="brand">{u.role}</Badge>
                    </td>
                    <td className="py-2 pr-4 font-mono text-brand-700">
                      {u.subject_count}
                    </td>
                    <td className="py-2 pr-4 font-mono text-brand-700">
                      {u.calibration_count}
                    </td>
                    <td className="py-2 pr-4">
                      {u.erased_at ? (
                        <Badge tone="neutral">ERASED</Badge>
                      ) : u.is_active ? (
                        <Badge tone="green">ACTIVE</Badge>
                      ) : (
                        <Badge tone="yellow">INACTIVE</Badge>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => viewSummary(u.id)}
                          disabled={isPending}
                        >
                          Inspect
                        </Button>
                        {!u.erased_at ? (
                          <Button
                            size="sm"
                            variant="danger"
                            onClick={() => setEraseTarget(u)}
                            disabled={isPending}
                          >
                            Erase
                          </Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {summary ? (
        <Card>
          <CardHeader>
            <CardTitle>Data inventory · {summary.email ?? summary.user_id}</CardTitle>
            <CardDescription>
              Audited as DATA_ACCESS_REQUEST_FULFILLED under your actor ID.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <CountCell label="Triage" n={summary.counts.triage_assessments} />
              <CountCell label="TOI" n={summary.counts.toi_assessments} />
              <CountCell label="Calibration" n={summary.counts.calibration_records} />
              <CountCell label="Subjects" n={summary.counts.study_subjects} />
              <CountCell label="Sessions" n={summary.counts.study_sessions} />
              <CountCell label="Consents" n={summary.counts.consent_records} />
              <CountCell label="Erasures" n={summary.counts.erasure_requests} />
            </dl>
          </CardContent>
        </Card>
      ) : null}

      {eraseTarget ? (
        <EraseUserModal
          user={eraseTarget}
          onClose={() => setEraseTarget(null)}
          onErased={() => {
            setSubmitted(eraseTarget.email ?? eraseTarget.id);
            setEraseTarget(null);
            refresh(data.offset);
          }}
          onError={setError}
        />
      ) : null}
    </div>
  );
}

function EraseUserModal({
  user,
  onClose,
  onErased,
  onError,
}: {
  user: AdminUserListItem;
  onClose: () => void;
  onErased: () => void;
  onError: (msg: string) => void;
}): React.ReactElement {
  const [confirmEmail, setConfirmEmail] = useState('');
  const [jurisdiction, setJurisdiction] = useState<ErasureJurisdiction>(
    ErasureJurisdiction.GDPR,
  );
  const [notes, setNotes] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  const submit = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    if (
      (user.email ?? '').toLowerCase() !== confirmEmail.trim().toLowerCase()
    ) {
      setLocalError(
        `Type the target's exact email to confirm: ${user.email ?? '(no email)'}`,
      );
      return;
    }
    setIsPending(true);
    setLocalError(null);
    const result = await adminProposeEraseAccountAction(user.id, {
      jurisdiction,
      notes: notes.trim() || null,
    });
    setIsPending(false);
    if (result.ok) {
      onErased();
    } else {
      onError(result.error);
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-lg border-[color:var(--color-state-red-ring)]/40">
        <CardHeader>
          <CardTitle className="text-[color:var(--color-state-red-fg)]">
            Propose account erasure
          </CardTitle>
          <CardDescription>
            This submits the erasure for approval by a second administrator —
            no data is destroyed until then. Both your actor ID and the target
            user ID are recorded.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {localError ? (
            <Alert tone="danger" className="mb-4">
              <AlertTitle>Cannot erase</AlertTitle>
              <AlertDescription>{localError}</AlertDescription>
            </Alert>
          ) : null}
          <form onSubmit={submit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="confirm-email">
                Type{' '}
                <span className="font-mono text-brand-900">
                  {user.email ?? '(no email)'}
                </span>
              </Label>
              <Input
                id="confirm-email"
                type="email"
                required
                autoComplete="off"
                value={confirmEmail}
                onChange={(e) => setConfirmEmail(e.target.value)}
              />
            </div>
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
              <Label htmlFor="notes">Reason / reference (optional)</Label>
              <Input
                id="notes"
                type="text"
                maxLength={2000}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. DPO ticket #2026-0042"
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
                {isPending ? 'Submitting…' : 'Submit for approval'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
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
