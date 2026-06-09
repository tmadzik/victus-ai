'use server';

import { redirect } from 'next/navigation';

import {
  type CalibrationRecordResponse,
  type CalibrationStatsResponse,
  type RecordCalibrationRequest,
  RecordCalibrationRequestSchema,
} from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export type RecordCalibrationResult =
  | { ok: true; record: CalibrationRecordResponse }
  | { ok: false; error: string; fieldErrors?: Record<string, string[]> };

export async function recordCalibrationAction(
  payload: RecordCalibrationRequest,
): Promise<RecordCalibrationResult> {
  const session = await auth();
  if (!session?.user) {
    redirect('/login?reason=session_expired');
  }
  const parsed = RecordCalibrationRequestSchema.safeParse(payload);
  if (!parsed.success) {
    const flat = parsed.error.flatten();
    return {
      ok: false,
      error: 'Reference reading failed validation.',
      fieldErrors: {
        ...flat.fieldErrors,
        ...(flat.formErrors.length > 0 ? { _form: flat.formErrors } : {}),
      },
    };
  }
  try {
    const record = await apiClient.recordCalibration(
      session.accessToken,
      parsed.data,
    );
    return { ok: true, record };
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

export async function getCalibrationStatsAction(): Promise<CalibrationStatsResponse> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');
  return apiClient.getCalibrationStats(session.accessToken);
}

export async function listCalibrationRecordsAction(
  limit = 50,
): Promise<CalibrationRecordResponse[]> {
  const session = await auth();
  if (!session?.user) redirect('/login?reason=session_expired');
  return apiClient.listCalibrationRecords(session.accessToken, limit);
}
