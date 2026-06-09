'use server';

import { redirect } from 'next/navigation';

import {
  type CreateSubjectRequest,
  CreateSubjectRequestSchema,
  type EndSessionRequest,
  type StartSessionRequest,
  StartSessionRequestSchema,
  type StudySessionResponse,
  type StudySubjectResponse,
} from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export type StudyActionResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: string; fieldErrors?: Record<string, string[]> };

async function requireAccessToken(): Promise<string> {
  const session = await auth();
  if (!session?.user) {
    redirect('/login?reason=session_expired');
  }
  return session.accessToken;
}

export async function createSubjectAction(
  payload: CreateSubjectRequest,
): Promise<StudyActionResult<StudySubjectResponse>> {
  const accessToken = await requireAccessToken();
  const parsed = CreateSubjectRequestSchema.safeParse(payload);
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
    const value = await apiClient.createSubject(accessToken, parsed.data);
    return { ok: true, value };
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

export async function listSubjectsAction(): Promise<StudySubjectResponse[]> {
  const accessToken = await requireAccessToken();
  return apiClient.listSubjects(accessToken);
}

export async function startSessionAction(
  payload: StartSessionRequest,
): Promise<StudyActionResult<StudySessionResponse>> {
  const accessToken = await requireAccessToken();
  const parsed = StartSessionRequestSchema.safeParse(payload);
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
    const value = await apiClient.startSession(accessToken, parsed.data);
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError) {
      return { ok: false, error: err.message };
    }
    throw err;
  }
}

export async function getActiveSessionAction(): Promise<StudySessionResponse | null> {
  const accessToken = await requireAccessToken();
  return apiClient.getActiveSession(accessToken);
}

export async function listSessionsAction(): Promise<StudySessionResponse[]> {
  const accessToken = await requireAccessToken();
  return apiClient.listSessions(accessToken);
}

export async function endSessionAction(
  sessionId: string,
  payload: EndSessionRequest,
): Promise<StudyActionResult<StudySessionResponse>> {
  const accessToken = await requireAccessToken();
  try {
    const value = await apiClient.endSession(accessToken, sessionId, payload);
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError) {
      return { ok: false, error: err.message };
    }
    throw err;
  }
}
