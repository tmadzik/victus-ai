'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';

import {
  type CreateReferral,
  CreateReferralSchema,
  type ReferralOutcome,
  RecordReferralOutcomeSchema,
  type ReferralStatus,
  UpdateReferralStatusSchema,
} from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export type ReferralActionResult =
  | { ok: true }
  | { ok: false; error: string; fieldErrors?: Record<string, string[] | undefined> };

export async function createReferralAction(
  payload: CreateReferral,
): Promise<ReferralActionResult> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');

  const parsed = CreateReferralSchema.safeParse(payload);
  if (!parsed.success) {
    return {
      ok: false,
      error: 'Please correct the highlighted fields.',
      fieldErrors: parsed.error.flatten().fieldErrors,
    };
  }
  try {
    await apiClient.createReferral(session.accessToken, parsed.data);
  } catch (err) {
    return {
      ok: false,
      error: err instanceof ApiError ? err.message : 'Could not raise the referral.',
    };
  }
  revalidatePath(`/clinical/${parsed.data.participant_user_id}`);
  return { ok: true };
}

export async function updateReferralStatusAction(
  referralId: string,
  participantUserId: string,
  status: ReferralStatus,
): Promise<ReferralActionResult> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');

  const parsed = UpdateReferralStatusSchema.safeParse({ status });
  if (!parsed.success) {
    return { ok: false, error: 'Invalid status.' };
  }
  try {
    await apiClient.updateReferralStatus(session.accessToken, referralId, parsed.data);
  } catch (err) {
    return {
      ok: false,
      error: err instanceof ApiError ? err.message : 'Could not update the referral.',
    };
  }
  revalidatePath(`/clinical/${participantUserId}`);
  return { ok: true };
}

export async function recordReferralOutcomeAction(
  referralId: string,
  participantUserId: string,
  outcome: ReferralOutcome,
): Promise<ReferralActionResult> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');

  const parsed = RecordReferralOutcomeSchema.safeParse({ outcome });
  if (!parsed.success) {
    return { ok: false, error: 'Invalid outcome.' };
  }
  try {
    await apiClient.recordReferralOutcome(session.accessToken, referralId, parsed.data);
  } catch (err) {
    return {
      ok: false,
      error:
        err instanceof ApiError ? err.message : 'Could not record the outcome.',
    };
  }
  revalidatePath(`/clinical/${participantUserId}`);
  return { ok: true };
}
