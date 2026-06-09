'use server';

import { redirect } from 'next/navigation';

import type {
  NotificationListResponse,
  UnreadCountResponse,
} from '@victus/contracts';

import { apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

async function requireAccessToken(): Promise<string> {
  const session = await auth();
  if (!session?.user) {
    redirect('/login?reason=session_expired');
  }
  return session.accessToken;
}

export async function listNotificationsAction(
  opts: { unreadOnly?: boolean; limit?: number } = {},
): Promise<NotificationListResponse> {
  const accessToken = await requireAccessToken();
  return apiClient.listNotifications(accessToken, opts);
}

export async function getUnreadCountAction(): Promise<UnreadCountResponse> {
  const accessToken = await requireAccessToken();
  return apiClient.getUnreadCount(accessToken);
}

export async function markNotificationReadAction(
  notificationId: string,
): Promise<void> {
  const accessToken = await requireAccessToken();
  await apiClient.markNotificationRead(accessToken, notificationId);
}

export async function markAllNotificationsReadAction(): Promise<UnreadCountResponse> {
  const accessToken = await requireAccessToken();
  return apiClient.markAllNotificationsRead(accessToken);
}
