import Link from 'next/link';
import { redirect } from 'next/navigation';

import { auth } from '@/lib/auth';
import {
  getMyDataSummaryAction,
  listMyErasureRequestsAction,
} from '@/server/governance-actions';

import { GovernanceClient } from './governance-client';

export const metadata = { title: 'Your data + erasure' };

export default async function AccountDataPage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login');

  const [summary, erasureRequests] = await Promise.all([
    getMyDataSummaryAction(),
    listMyErasureRequestsAction(),
  ]);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Account · Data governance
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          Your data + erasure
        </h1>
        <p className="mt-2 max-w-3xl text-brand-700">
          GDPR Article 15 / POPIA section 23 grants you the right to know what
          data this service holds about you. Article 17 / section 24 grants you
          the right to erasure. Below is everything we hold for{' '}
          <span className="font-mono">{session.user.email ?? '—'}</span>, and
          the tools to act on it.{' '}
          <Link
            href="/toi/calibration/study"
            className="font-semibold underline"
          >
            Study subjects
          </Link>{' '}
          can also be anonymised individually if a participant withdraws
          consent.
        </p>
      </header>

      <GovernanceClient
        summary={summary}
        initialErasureRequests={erasureRequests}
      />
    </div>
  );
}
