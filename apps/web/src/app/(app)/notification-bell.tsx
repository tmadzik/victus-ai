'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

import { onNotificationsUpdated } from '@/lib/notifications-events';
import { getUnreadCountAction } from '@/server/notification-actions';

const POLL_INTERVAL_MS = 30_000;

/**
 * Header notification bell with a live unread badge.
 *
 * Update strategy (cheapest correct option — a single COUNT query per tick
 * hitting the partial unread index):
 *
 * - Poll every 30 s while the tab is visible.
 * - Pause polling when the tab is hidden (Page Visibility API) — no point
 *   counting for a backgrounded tab.
 * - Refetch immediately on tab refocus (`visibilitychange` → visible and
 *   window `focus`), so returning to the tab shows a fresh count at once.
 * - Refetch immediately when any component emits `notifications-updated`
 *   (e.g. the /notifications page after mark-read), so in-SPA actions update
 *   the badge without waiting for a poll tick.
 *
 * `initialCount` comes from the server layout so there is no flash of a stale
 * or zero badge on first paint.
 */
export function NotificationBell({
  initialCount,
}: {
  initialCount: number;
}): React.ReactElement {
  const [count, setCount] = useState(initialCount);
  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);

  const refresh = useCallback(async (): Promise<void> => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const { unread_count } = await getUnreadCountAction();
      if (mountedRef.current) setCount(unread_count);
    } catch {
      // Best-effort — a failed poll must never crash the shell. Keep the
      // last known count and try again next tick.
    } finally {
      inFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    let timer: ReturnType<typeof setInterval> | null = null;

    const startPolling = (): void => {
      if (timer !== null) return;
      timer = setInterval(() => {
        if (document.visibilityState === 'visible') void refresh();
      }, POLL_INTERVAL_MS);
    };
    const stopPolling = (): void => {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    };

    const onVisibility = (): void => {
      if (document.visibilityState === 'visible') {
        void refresh();
        startPolling();
      } else {
        stopPolling();
      }
    };
    const onFocus = (): void => void refresh();

    // Start in whatever the current visibility is.
    if (document.visibilityState === 'visible') startPolling();
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('focus', onFocus);
    const unsubscribe = onNotificationsUpdated(() => void refresh());

    return () => {
      mountedRef.current = false;
      stopPolling();
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('focus', onFocus);
      unsubscribe();
    };
  }, [refresh]);

  const label =
    count > 0 ? `Notifications, ${count} unread` : 'Notifications';

  return (
    <Link
      href="/notifications"
      aria-label={label}
      className="relative inline-flex h-9 w-9 items-center justify-center rounded-[var(--radius-control)] text-brand-700 transition-colors hover:bg-brand-50 hover:text-brand-900"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-5 w-5"
        aria-hidden="true"
      >
        <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
        <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
      </svg>
      {count > 0 ? (
        <span
          aria-hidden="true"
          className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[color:var(--color-state-red-ring)] px-1 text-[10px] font-semibold text-white"
        >
          {count > 99 ? '99+' : count}
        </span>
      ) : null}
    </Link>
  );
}
