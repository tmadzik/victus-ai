'use server';

import { redirect } from 'next/navigation';

import {
  type AnonymiseSubjectRequest,
  AnonymiseSubjectRequestSchema,
  type EraseAccountRequest,
  EraseAccountRequestSchema,
  type ErasureRequestResponse,
  type MyDataSummary,
} from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth, signOut } from '@/lib/auth';

export type GovernanceResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: string; fieldErrors?: Record<string, string[]> };

async function requireAccessToken(): Promise<string> {
  const session = await auth();
  if (!session?.user) {
    redirect('/login?reason=session_expired');
  }
  return session.accessToken;
}

export async function getMyDataSummaryAction(): Promise<MyDataSummary> {
  const accessToken = await requireAccessToken();
  return apiClient.getMyDataSummary(accessToken);
}

export async function listMyErasureRequestsAction(): Promise<
  ErasureRequestResponse[]
> {
  const accessToken = await requireAccessToken();
  return apiClient.listMyErasureRequests(accessToken);
}

export async function eraseAccountAction(
  payload: EraseAccountRequest,
): Promise<GovernanceResult<ErasureRequestResponse>> {
  const accessToken = await requireAccessToken();
  const parsed = EraseAccountRequestSchema.safeParse(payload);
  if (!parsed.success) {
    const flat = parsed.error.flatten();
    return {
      ok: false,
      error: 'Confirm email is required and must match your account.',
      fieldErrors: {
        ...flat.fieldErrors,
        ...(flat.formErrors.length > 0 ? { _form: flat.formErrors } : {}),
      },
    };
  }
  let result: ErasureRequestResponse;
  try {
    result = await apiClient.eraseAccount(accessToken, parsed.data);
  } catch (err) {
    if (err instanceof ApiError) {
      return { ok: false, error: err.message };
    }
    throw err;
  }
  // Server has destroyed the user's hashed_password and revoked refresh
  // tokens; we explicitly sign out the Auth.js session container then
  // redirect to the public /erased landing.
  await signOut({ redirect: false });
  redirect('/erased');
  // Unreachable — redirect() throws — but TypeScript needs it.
  return { ok: true, value: result };
}

export async function anonymiseSubjectAction(
  subjectId: string,
  payload: AnonymiseSubjectRequest,
): Promise<GovernanceResult<ErasureRequestResponse>> {
  const accessToken = await requireAccessToken();
  const parsed = AnonymiseSubjectRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return { ok: false, error: 'Anonymisation request failed validation.' };
  }
  try {
    const value = await apiClient.anonymiseSubject(
      accessToken,
      subjectId,
      parsed.data,
    );
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError) {
      return { ok: false, error: err.message };
    }
    throw err;
  }
}
