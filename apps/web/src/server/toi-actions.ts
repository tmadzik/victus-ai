'use server';

import { redirect } from 'next/navigation';

import {
  type ToiAssessmentRequest,
  type ToiAssessmentResponse,
  ToiAssessmentRequestSchema,
} from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export type ToiActionResult =
  | { ok: true; assessment: ToiAssessmentResponse }
  | { ok: false; error: string; fieldErrors?: Record<string, string[]> };

export async function assessToiAction(
  payload: ToiAssessmentRequest,
): Promise<ToiActionResult> {
  const session = await auth();
  if (!session?.user) {
    redirect('/login?reason=session_expired');
  }

  const parsed = ToiAssessmentRequestSchema.safeParse(payload);
  if (!parsed.success) {
    const flat = parsed.error.flatten();
    return {
      ok: false,
      error: 'Capture payload failed validation.',
      fieldErrors: {
        ...flat.fieldErrors,
        ...(flat.formErrors.length > 0 ? { _form: flat.formErrors } : {}),
      },
    };
  }

  try {
    const assessment = await apiClient.assessToi(session.accessToken, parsed.data);
    return { ok: true, assessment };
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.code === 'consent_required') {
        redirect('/dashboard?blocked_by=consent&pathway=B_TOI');
      }
      return { ok: false, error: err.message };
    }
    throw err;
  }
}
