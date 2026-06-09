'use client';

import { useState, useTransition } from 'react';

import {
  type AdminErasureRequestResponse,
  ERASURE_BASIS_LABELS,
} from '@victus/contracts';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { adminListErasureRequestsAction } from '@/server/admin-actions';

export function ErasureLedger({
  initialRequests,
}: {
  initialRequests: AdminErasureRequestResponse[];
}): React.ReactElement {
  const [requests, setRequests] =
    useState<AdminErasureRequestResponse[]>(initialRequests);
  const [isPending, startTransition] = useTransition();

  const refresh = (): void => {
    startTransition(async () => {
      const next = await adminListErasureRequestsAction({ limit: 100 });
      setRequests(next);
    });
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>Platform erasure ledger ({requests.length})</CardTitle>
          <CardDescription>
            Every erasure + anonymisation across all tenants, with resolved
            actor and target emails. Append-only.
          </CardDescription>
        </div>
        <Button size="sm" variant="outline" onClick={refresh} disabled={isPending}>
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        {requests.length === 0 ? (
          <p className="text-sm text-brand-600">No erasure requests yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="border-b border-brand-200 text-left text-xs uppercase tracking-wider text-brand-700">
                <tr>
                  <th className="py-2 pr-4">When</th>
                  <th className="py-2 pr-4">Actor</th>
                  <th className="py-2 pr-4">Target user</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Basis</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Decided by</th>
                  <th className="py-2 pr-4">Retention</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((r) => {
                  const isAdminAction =
                    r.requesting_actor_user_id !== r.target_user_id &&
                    r.requesting_actor_user_id !== null;
                  return (
                    <tr key={r.id} className="border-b border-brand-100">
                      <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                        {new Date(r.requested_at).toLocaleString('en-ZA')}
                      </td>
                      <td className="py-2 pr-4 text-xs text-brand-900">
                        <span className="font-mono">
                          {r.requesting_actor_email ?? '—'}
                        </span>
                        {isAdminAction ? (
                          <Badge tone="yellow" className="ml-1">
                            ADMIN
                          </Badge>
                        ) : null}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                        {r.target_user_email ?? '—'}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                        {r.target_type}
                      </td>
                      <td className="py-2 pr-4 text-xs text-brand-700">
                        {ERASURE_BASIS_LABELS[r.request_basis]}
                      </td>
                      <td className="py-2 pr-4">
                        <Badge
                          tone={
                            r.status === 'COMPLETED'
                              ? 'green'
                              : r.status === 'AWAITING_APPROVAL' ||
                                  r.status === 'PENDING'
                                ? 'yellow'
                                : 'red'
                          }
                        >
                          {r.status}
                        </Badge>
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                        {r.approved_by_email
                          ? `✓ ${r.approved_by_email}`
                          : r.rejected_by_email
                            ? `✗ ${r.rejected_by_email}`
                            : '—'}
                      </td>
                      <td className="py-2 pr-4 text-xs text-brand-700">
                        {r.statutory_retention_applied ? 'yes' : 'no'}
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
  );
}
