import { redirect } from 'next/navigation';

import { UserRole } from '@victus/contracts';

import { auth } from '@/lib/auth';
import {
  adminListErasureRequestsAction,
  adminListUsersAction,
} from '@/server/admin-actions';

import { AdminClient } from './admin-client';

export const metadata = { title: 'Admin · Governance' };

export default async function AdminGovernancePage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login');
  if (session.user.role !== UserRole.ADMIN) redirect('/dashboard');

  const [userList, erasureRequests, pendingRequests] = await Promise.all([
    adminListUsersAction({ limit: 50, offset: 0, includeErased: true }),
    adminListErasureRequestsAction({ limit: 100 }),
    adminListErasureRequestsAction({ status: 'AWAITING_APPROVAL', limit: 100 }),
  ]);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Admin · Data governance
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          Governance console
        </h1>
        <p className="mt-2 max-w-3xl text-brand-700">
          Process regulator-forwarded erasure requests on behalf of data
          subjects, anonymise study subjects across tenants, and query the
          platform audit log. Every action here is doubly audited — your
          actor ID and the target user ID are both recorded.
        </p>
      </header>

      <AdminClient
        currentAdminId={session.user.id}
        initialUsers={userList}
        initialErasureRequests={erasureRequests}
        initialPending={pendingRequests}
      />
    </div>
  );
}
