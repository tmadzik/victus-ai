'use server';

import { redirect } from 'next/navigation';

import type { ConsentType } from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth, unstable_update } from '@/lib/auth';

/**
 * Grant the given consents for the signed-in user, then enter a pathway.
 *
 * The pathway gate reads `session.user.consents` from the Auth.js JWT, so after
 * persisting the grant via the API we call `unstable_update({})` to re-run the
 * `jwt` callback (its `trigger === 'update'` branch re-fetches `/users/me`).
 * That refreshes the token's consents in place, so the subsequent redirect into
 * the pathway succeeds without forcing the user to sign out and back in.
 *
 * Designed for use as a bound `<form action>`; the FormData Next passes to the
 * bound action is ignored — every input comes from the bound arguments.
 */
export async function grantConsentAndEnterAction(
  consents: ConsentType[],
  redirectTo: string,
): Promise<void> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');

  if (consents.length > 0) {
    try {
      await apiClient.updateConsents(session.accessToken, { grants: consents });
    } catch (err) {
      if (err instanceof ApiError) {
        redirect('/dashboard?consent_error=1');
      }
      throw err;
    }
    await unstable_update({});
  }

  redirect(redirectTo);
}
