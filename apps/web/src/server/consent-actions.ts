'use server';

import type { ConsentType } from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export type GrantConsentResult = { ok: true } | { ok: false; error: string };

/**
 * Persist consent grants for the signed-in user and return a result the caller
 * can surface. The pathway pages re-read the current consents server-side, so a
 * plain navigation after this resolves enters the pathway — no sign-out/in.
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
