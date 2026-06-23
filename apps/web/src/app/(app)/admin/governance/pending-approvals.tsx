'use client';

import { useState, useTransition } from 'react';

import {
  type AdminErasureRequestResponse,
  ERASURE_BASIS_LABELS,
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
  adminApproveErasureAction,
  adminListErasureRequestsAction,
  adminRejectErasureAction,
} from '@/server/admin-actions';

export function PendingApprovals({
  currentAdminId,
  initialPending,
}: {
  currentAdminId: string;
  initialPending: AdminErasureRequestResponse[];
}): React.ReactElement {
  const [pending, setPending] =
    useState<AdminErasureRequestResponse[]>(initialPending);
  const [error, setError] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] =
    useState<AdminErasureRequestResponse | null>(null);
  const [isPending, startTransition] = useTransition();

  const refresh = (): void => {
    startTransition(async () => {
      const next = await adminListErasureRequestsAction({
        status: 'AWAITING_APPROVAL',
      });
      setPending(next);
    });
  };

  const approve = (req: AdminErasureRequestResponse): void => {
    setError(null);
    startTransition(async () => {
      const result = await adminApproveErasureAction(req.id);
      if (!result.ok) setError(result.error);
      else refresh();
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

      <Alert tone="info">
        <AlertTitle>Segregation of duties</AlertTitle>
        <AlertDescription>
          You cannot approve or reject a request you created yourself. Those
          rows show a disabled “Your request” marker — a different
          administrator must action them.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <CardTitle>Awaiting approval ({pending.length})</CardTitle>
            <CardDescription>
              Each request was proposed by one admin and must be approved by a
              second before any data is destroyed.
            </CardDescription>
          </div>
          <Button size="sm" variant="outline" onClick={refresh} disabled={isPending}>
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {pending.length === 0 ? (
            <p className="text-sm text-brand-600">
              No requests are awaiting approval.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="border-b border-brand-200 text-left text-xs uppercase tracking-wider text-brand-700">
                  <tr>
                    <th className="py-2 pr-4">Proposed</th>
                    <th className="py-2 pr-4">Maker</th>
                    <th className="py-2 pr-4">Target</th>
                    <th className="py-2 pr-4">Type</th>
                    <th className="py-2 pr-4">Basis</th>
                    <th className="py-2 pr-4">Reason</th>
                    <th className="py-2 pr-4">Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {pending.map((r) => {
                    const isOwnRequest =
                      r.requesting_actor_user_id === currentAdminId;
                    return (
                      <tr key={r.id} className="border-b border-brand-100 align-top">
                        <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                          {new Date(r.requested_at).toLocaleString('en-GB')}
                        </td>
                        <td className="py-2 pr-4 font-mono text-xs text-brand-900">
                          {r.requesting_actor_email ?? '—'}
                        </td>
                        <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                          {r.target_user_email ?? r.target_id.slice(0, 8)}
                        </td>
                        <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                          {r.target_type}
                        </td>
                        <td className="py-2 pr-4 text-xs text-brand-700">
                          {ERASURE_BASIS_LABELS[r.request_basis]}
                        </td>
                        <td className="py-2 pr-4 text-xs text-brand-600">
                          {r.notes ?? '—'}
                        </td>
                        <td className="py-2 pr-4">
                          {isOwnRequest ? (
                            <Badge tone="neutral">Your request</Badge>
                          ) : (
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                onClick={() => approve(r)}
                                disabled={isPending}
                              >
                                Approve
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setRejectTarget(r)}
                                disabled={isPending}
                              >
                                Reject
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {rejectTarget ? (
        <RejectModal
          request={rejectTarget}
          onClose={() => setRejectTarget(null)}
          onRejected={() => {
            setRejectTarget(null);
            refresh();
          }}
          onError={(msg) => {
            setRejectTarget(null);
            setError(msg);
          }}
        />
      ) : null}
    </div>
  );
}

function RejectModal({
  request,
  onClose,
  onRejected,
  onError,
}: {
  request: AdminErasureRequestResponse;
  onClose: () => void;
  onRejected: () => void;
  onError: (msg: string) => void;
}): React.ReactElement {
  const [reason, setReason] = useState('');
  const [isPending, setIsPending] = useState(false);

  const submit = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    setIsPending(true);
    const result = await adminRejectErasureAction(
      request.id,
      reason.trim() || null,
    );
    setIsPending(false);
    if (result.ok) onRejected();
    else onError(result.error);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Reject erasure request</CardTitle>
          <CardDescription>
            No data will be touched. The maker (
            <span className="font-mono">{request.requesting_actor_email}</span>)
            is recorded; provide a reason for the ledger.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="reason">Reason</Label>
              <Input
                id="reason"
                type="text"
                maxLength={2000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Duplicate of DPO ticket #41; subject re-consented"
              />
            </div>
            <div className="flex justify-end gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                disabled={isPending}
              >
                Cancel
              </Button>
              <Button type="submit" variant="danger" disabled={isPending}>
                {isPending ? 'Rejecting…' : 'Reject request'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
