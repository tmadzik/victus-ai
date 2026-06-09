'use client';

import { useSearchParams } from 'next/navigation';
import { useState } from 'react';

import type {
  AdminErasureRequestResponse,
  AdminUserListResponse,
} from '@victus/contracts';

import { cn } from '@/lib/utils';

import { AuditQuery } from './audit-query';
import { ErasureLedger } from './erasure-ledger';
import { PendingApprovals } from './pending-approvals';
import { UsersTable } from './users-table';

type Tab = 'users' | 'pending' | 'ledger' | 'audit';

const VALID_TABS: readonly Tab[] = ['users', 'pending', 'ledger', 'audit'];

export function AdminClient({
  currentAdminId,
  initialUsers,
  initialErasureRequests,
  initialPending,
}: {
  currentAdminId: string;
  initialUsers: AdminUserListResponse;
  initialErasureRequests: AdminErasureRequestResponse[];
  initialPending: AdminErasureRequestResponse[];
}): React.ReactElement {
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get('tab');
  const initialTab: Tab = VALID_TABS.includes(requestedTab as Tab)
    ? (requestedTab as Tab)
    : 'users';
  const [tab, setTab] = useState<Tab>(initialTab);

  const tabs: { key: Tab; label: string; badge?: number }[] = [
    { key: 'users', label: 'Users' },
    {
      key: 'pending',
      label: 'Pending approvals',
      badge: initialPending.length || undefined,
    },
    { key: 'ledger', label: 'Erasure ledger' },
    { key: 'audit', label: 'Audit log' },
  ];

  return (
    <div className="space-y-6">
      <div
        role="tablist"
        aria-label="Admin sections"
        className="flex gap-1 border-b border-brand-200"
      >
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              'flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              tab === t.key
                ? 'border-brand-600 text-brand-900'
                : 'border-transparent text-brand-600 hover:text-brand-900',
            )}
          >
            {t.label}
            {t.badge ? (
              <span className="rounded-full bg-[color:var(--color-state-yellow-ring)] px-1.5 py-0.5 text-xs font-semibold text-white">
                {t.badge}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {tab === 'users' ? <UsersTable initialUsers={initialUsers} /> : null}
      {tab === 'pending' ? (
        <PendingApprovals
          currentAdminId={currentAdminId}
          initialPending={initialPending}
        />
      ) : null}
      {tab === 'ledger' ? (
        <ErasureLedger initialRequests={initialErasureRequests} />
      ) : null}
      {tab === 'audit' ? <AuditQuery /> : null}
    </div>
  );
}
