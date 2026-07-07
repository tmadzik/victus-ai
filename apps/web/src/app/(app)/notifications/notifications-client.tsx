'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';

import {
  type NotificationListResponse,
  type NotificationResponse,
  NotificationType,
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
import { useFormatLocale } from '@/i18n/context';
import { emitNotificationsUpdated } from '@/lib/notifications-events';
import { cn } from '@/lib/utils';
import {
  markAllNotificationsReadAction,
  markNotificationReadAction,
} from '@/server/notification-actions';

const TYPE_TONE: Record<
  NotificationType,
  { tone: 'red' | 'green' | 'yellow' | 'brand'; label: string }
> = {
  ERASURE_APPROVAL_REQUESTED: { tone: 'yellow', label: 'Approval needed' },
  ERASURE_REQUEST_APPROVED: { tone: 'green', label: 'Approved' },
  ERASURE_REQUEST_REJECTED: { tone: 'red', label: 'Rejected' },
  REFERRAL_RAISED: { tone: 'brand', label: 'Referral' },
  RISK_TRAJECTORY_RISE: { tone: 'yellow', label: 'Risk rising' },
  GENERIC: { tone: 'brand', label: 'Notice' },
};

const FALLBACK_TONE: { tone: 'brand'; label: string } = {
  tone: 'brand',
  label: 'Notice',
};

export function NotificationsClient({
  initialList,
}: {
  initialList: NotificationListResponse;
}): React.ReactElement {
  const router = useRouter();
  const fmtLoc = useFormatLocale();
  const [items, setItems] = useState<NotificationResponse[]>(
    initialList.notifications,
  );
  const [isPending, startTransition] = useTransition();

  const unread = items.filter((n) => n.read_at === null).length;

  const openNotification = (n: NotificationResponse): void => {
    startTransition(async () => {
      if (n.read_at === null) {
        await markNotificationReadAction(n.id);
        setItems((prev) =>
          prev.map((x) =>
            x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x,
          ),
        );
        emitNotificationsUpdated();
      }
      if (n.resource) {
        router.push(n.resource as Parameters<typeof router.push>[0]);
      }
    });
  };

  const markAll = (): void => {
    startTransition(async () => {
      await markAllNotificationsReadAction();
      setItems((prev) =>
        prev.map((x) =>
          x.read_at === null
            ? { ...x, read_at: new Date().toISOString() }
            : x,
        ),
      );
      emitNotificationsUpdated();
    });
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>Inbox</CardTitle>
          <CardDescription>
            {items.length === 0
              ? 'No notifications.'
              : `${unread} unread of ${items.length}.`}
          </CardDescription>
        </div>
        {unread > 0 ? (
          <Button size="sm" variant="outline" onClick={markAll} disabled={isPending}>
            Mark all read
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="py-6 text-center text-sm text-brand-600">
            You&apos;re all caught up.
          </p>
        ) : (
          <ul className="divide-y divide-brand-100">
            {items.map((n) => {
              const meta = TYPE_TONE[n.type] ?? FALLBACK_TONE;
              const isUnread = n.read_at === null;
              return (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => openNotification(n)}
                    disabled={isPending}
                    className={cn(
                      'flex w-full items-start gap-3 px-1 py-3 text-left transition-colors hover:bg-brand-50',
                      isUnread ? 'bg-brand-50/40' : '',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-1.5 h-2 w-2 shrink-0 rounded-full',
                        isUnread
                          ? 'bg-[color:var(--color-state-red-ring)]'
                          : 'bg-transparent',
                      )}
                      aria-hidden="true"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={cn(
                            'text-sm',
                            isUnread
                              ? 'font-semibold text-brand-950'
                              : 'font-medium text-brand-800',
                          )}
                        >
                          {n.title}
                        </span>
                        <Badge tone={meta.tone}>{meta.label}</Badge>
                      </div>
                      <p className="mt-0.5 text-sm text-brand-700">{n.body}</p>
                      <p className="mt-1 text-xs text-brand-500">
                        {new Date(n.created_at).toLocaleString(fmtLoc, {
                          dateStyle: 'medium',
                          timeStyle: 'short',
                        })}
                        {n.resource ? ' · click to open' : ''}
                      </p>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
