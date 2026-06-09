'use server';

import type { ConsentType } from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export type GrantConsentResult = { ok: true } | { ok: false; error: string };

/**
 * Persist consent grants for the signed-in user. Returns a result the caller
 * can surface; the client then calls `useSession().update()` to refresh the
 * JWT's consents in place before navigating into the pathway — so no
 * sign-out/in is required.
 */
export async function grantConsentAction(
  consents: ConsentType[],
): Promise<GrantConsentResult> {
  const session = await auth();
  if (!session?.user) {
    return { ok: false, error: 'Your session has expired — please sign in again.' };
  }
  if (consents.length === 0) return { ok: true };

  try {
    await apiClient.updateConsents(session.accessToken, { grants: consents });
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) {
      return { ok: false, error: err.message };
    }
    return { ok: false, error: 'Could not record your consent. Please try again.' };
  }
}
