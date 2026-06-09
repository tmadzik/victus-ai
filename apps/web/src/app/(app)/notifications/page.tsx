import { redirect } from 'next/navigation';

import { auth } from '@/lib/auth';
import { listNotificationsAction } from '@/server/notification-actions';

import { NotificationsClient } from './notifications-client';

export const metadata = { title: 'Notifications' };

export default async function NotificationsPage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login');

  const list = await listNotificationsAction({ limit: 50 });

  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Account
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          Notifications
        </h1>
        <p className="mt-2 max-w-2xl text-brand-700">
          Governance approval requests and other actionable alerts. Clicking a
          notification marks it read and takes you to the relevant page.
        </p>
      </header>

      <NotificationsClient initialList={list} />
    </div>
  );
}
