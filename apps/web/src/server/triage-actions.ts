'use server';

import { redirect } from 'next/navigation';

import {
  type TriageAssessmentRequest,
  type TriageAssessmentResponse,
  TriageAssessmentRequestSchema,
} from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export type TriageActionResult =
  | { ok: true; assessment: TriageAssessmentResponse }
  | { ok: false; error: string; fieldErrors?: Record<string, string[]> };

export async function assessTriageAction(
  payload: TriageAssessmentRequest,
): Promise<TriageActionResult> {
  const session = await auth();
  if (!session?.user) {
    redirect('/login?reason=session_expired');
  }

  const parsed = TriageAssessmentRequestSchema.safeParse(payload);
  if (!parsed.success) {
    const flat = parsed.error.flatten();
    return {
      ok: false,
      error: 'Please correct the highlighted fields.',
      fieldErrors: {
        ...flat.fieldErrors,
        ...(flat.formErrors.length > 0 ? { _form: flat.formErrors } : {}),
      },
    };
  }

  try {
    const assessment = await apiClient.assessTriage(session.accessToken, parsed.data);
    return { ok: true, assessment };
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.code === 'consent_required') {
        redirect('/dashboard?blocked_by=consent&pathway=A_TRIAGE');
      }
      return { ok: false, error: err.message };
    }
    throw err;
  }
}
