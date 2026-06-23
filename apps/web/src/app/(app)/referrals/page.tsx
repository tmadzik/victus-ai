import { redirect } from 'next/navigation';

import {
  REFERRAL_DESTINATION_LABELS,
  type ReferralDestinationType,
  type ReferralResponse,
} from '@victus/contracts';

import { Badge, type BadgeProps } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { formatLocale } from '@/i18n/config';
import { getLocale } from '@/i18n';
import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export const metadata = { title: 'Referrals — Victus AI' };

const STATUS_TONE: Record<string, BadgeProps['tone']> = {
  PENDING: 'yellow',
  ACKNOWLEDGED: 'brand',
  COMPLETED: 'green',
  CANCELLED: 'neutral',
};
const URGENCY_TONE: Record<string, BadgeProps['tone']> = {
  ROUTINE: 'neutral',
  URGENT: 'yellow',
  EMERGENCY: 'red',
};

export default async function ReferralsPage(): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');

  const formatLoc = formatLocale(await getLocale());
  let referrals: ReferralResponse[] = [];
  let error: string | null = null;
  try {
    referrals = await apiClient.listMyReferrals(session.accessToken, 50);
  } catch (err) {
    error = err instanceof ApiError ? err.message : 'Could not load your referrals.';
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
          Care navigation
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-brand-950">
          Your referrals
        </h1>
        <p className="mt-2 max-w-2xl text-brand-700">
          Where your care team has referred you for follow-up, and the current
          status of each referral.
        </p>
      </header>

      {error ? (
        <Card>
          <CardContent className="py-6 text-sm text-rose-700">{error}</CardContent>
        </Card>
      ) : referrals.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-brand-600">
            You have no referrals.
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-3">
          {referrals.map((r) => (
            <li key={r.id}>
              <Card>
                <CardContent className="space-y-2 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Badge tone={STATUS_TONE[r.status] ?? 'neutral'}>{r.status}</Badge>
                      <Badge tone={URGENCY_TONE[r.urgency] ?? 'neutral'}>{r.urgency}</Badge>
                      <span className="font-medium text-brand-900">
                        {r.destination_name}
                      </span>
                      <span className="text-xs text-brand-500">
                        {REFERRAL_DESTINATION_LABELS[
                          r.destination_type as ReferralDestinationType
                        ] ?? r.destination_type}
                      </span>
                    </div>
                    <time className="text-xs text-brand-600">
                      {new Date(r.created_at).toLocaleDateString(formatLoc, {
                        dateStyle: 'medium',
                      })}
                    </time>
                  </div>
                  <p className="text-sm text-brand-800">{r.reason}</p>
                  {r.notes ? (
                    <p className="text-xs text-brand-600">Note: {r.notes}</p>
                  ) : null}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
