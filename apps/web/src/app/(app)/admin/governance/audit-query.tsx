'use client';

import { useState, useTransition } from 'react';

import type { AuditLogEntry, AuditLogResponse } from '@victus/contracts';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
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
import { adminQueryAuditLogAction } from '@/server/admin-actions';

// A representative subset of audit actions for the dropdown. Free-text is
// also accepted — the server validates against the full enum.
const COMMON_ACTIONS = [
  '',
  'AUTH_LOGIN_SUCCESS',
  'AUTH_LOGIN_FAILURE',
  'ACCOUNT_ERASURE_REQUESTED',
  'ACCOUNT_ERASED',
  'SUBJECT_ANONYMISED',
  'DATA_ACCESS_REQUEST_FULFILLED',
  'CALIBRATION_PAIR_RECORDED',
  'PATHWAY_A_SAFETY_OVERRIDE',
  'STUDY_SESSION_LOCKED',
] as const;

const PAGE_SIZE = 50;

export function AuditQuery(): React.ReactElement {
  const [action, setAction] = useState('');
  const [actorId, setActorId] = useState('');
  const [result, setResult] = useState<AuditLogResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [isPending, startTransition] = useTransition();

  const run = (nextOffset: number): void => {
    setError(null);
    startTransition(async () => {
      try {
        const res = await adminQueryAuditLogAction({
          action: action || undefined,
          actorId: actorId.trim() || undefined,
          limit: PAGE_SIZE,
          offset: nextOffset,
        });
        setResult(res);
        setOffset(nextOffset);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    });
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Audit log query</CardTitle>
          <CardDescription>
            Filter the platform audit log by action and/or actor user ID.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="action">Action</Label>
              <select
                id="action"
                value={action}
                onChange={(e) => setAction(e.target.value)}
                className="flex h-10 w-full rounded-[var(--radius-control)] border border-brand-200 bg-white px-3 py-2 text-sm text-brand-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                {COMMON_ACTIONS.map((a) => (
                  <option key={a} value={a}>
                    {a === '' ? 'Any action' : a}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="actor">Actor user ID (optional)</Label>
              <Input
                id="actor"
                type="text"
                value={actorId}
                onChange={(e) => setActorId(e.target.value)}
                placeholder="UUID"
              />
            </div>
            <div className="flex items-end">
              <Button onClick={() => run(0)} disabled={isPending}>
                {isPending ? 'Querying…' : 'Run query'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {error ? (
        <Alert tone="danger">
          <AlertTitle>Query failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {result ? (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-3">
            <div>
              <CardTitle>Results ({result.total})</CardTitle>
              <CardDescription>
                Showing {result.entries.length}, offset {result.offset}.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={offset === 0 || isPending}
                onClick={() => run(Math.max(0, offset - PAGE_SIZE))}
              >
                Prev
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={offset + PAGE_SIZE >= result.total || isPending}
                onClick={() => run(offset + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <AuditTable entries={result.entries} />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function AuditTable({
  entries,
}: {
  entries: AuditLogEntry[];
}): React.ReactElement {
  if (entries.length === 0) {
    return <p className="text-sm text-brand-600">No matching entries.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="border-b border-brand-200 text-left text-xs uppercase tracking-wider text-brand-700">
          <tr>
            <th className="py-2 pr-4">When</th>
            <th className="py-2 pr-4">Actor</th>
            <th className="py-2 pr-4">Action</th>
            <th className="py-2 pr-4">Resource</th>
            <th className="py-2 pr-4">IP</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id} className="border-b border-brand-100 align-top">
              <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                {new Date(e.created_at).toLocaleString('en-GB')}
              </td>
              <td className="py-2 pr-4 font-mono text-xs text-brand-700">
                {e.actor_email ?? e.actor_id ?? '—'}
              </td>
              <td className="py-2 pr-4 font-mono text-xs text-brand-900">
                {e.action}
              </td>
              <td className="py-2 pr-4 font-mono text-xs text-brand-600">
                {e.resource ?? '—'}
              </td>
              <td className="py-2 pr-4 font-mono text-xs text-brand-600">
                {e.ip_address ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
