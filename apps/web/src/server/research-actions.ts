'use server';

import { redirect } from 'next/navigation';

import {
  type ResearchCaseCreate,
  ResearchCaseCreateSchema,
  type ResearchCaseResponse,
} from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export type CreateResearchCaseResult =
  | { ok: true; record: ResearchCaseResponse }
  | { ok: false; error: string; fieldErrors?: Record<string, string[] | undefined> };

export async function createResearchCaseAction(
  payload: ResearchCaseCreate,
): Promise<CreateResearchCaseResult> {
  const session = await auth();
  if (!session?.user) {
    redirect('/login?reason=session_expired');
  }
  const parsed = ResearchCaseCreateSchema.safeParse(payload);
  if (!parsed.success) {
    return {
      ok: false,
      error: 'Please correct the highlighted fields.',
      fieldErrors: parsed.error.flatten().fieldErrors,
    };
  }
  try {
    const record = await apiClient.createResearchCase(session.accessToken, parsed.data);
    return { ok: true, record };
  } catch (err) {
    if (err instanceof ApiError) {
      return { ok: false, error: err.message };
    }
    return { ok: false, error: 'Could not record the case. Please try again.' };
  }
}
