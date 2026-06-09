'use server';

import { redirect } from 'next/navigation';

import {
  type AdminErasureRequestResponse,
  type AdminUserDataSummary,
  type AdminUserListResponse,
  type AuditLogResponse,
  type ErasureRequestResponse,
  ErasureBasis,
  ErasureJurisdiction,
  UserRole,
} from '@victus/contracts';

import { ApiError, apiClient } from '@/lib/api-client';
import { auth } from '@/lib/auth';

export type AdminResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: string };

interface AdminContext {
  accessToken: string;
}

async function requireAdmin(): Promise<AdminContext> {
  const session = await auth();
  if (!session?.user) {
    redirect('/login?reason=session_expired');
  }
  // Server-side defence in depth — the API also enforces ADMIN, but we fail
  // fast here so non-admins never see admin data even momentarily.
  if (session.user.role !== UserRole.ADMIN) {
    redirect('/dashboard');
  }
  return { accessToken: session.accessToken };
}

export async function adminListUsersAction(
  opts: { limit?: number; offset?: number; includeErased?: boolean } = {},
): Promise<AdminUserListResponse> {
  const { accessToken } = await requireAdmin();
  return apiClient.adminListUsers(accessToken, opts);
}

export async function adminGetUserDataSummaryAction(
  userId: string,
): Promise<AdminResult<AdminUserDataSummary>> {
  const { accessToken } = await requireAdmin();
  try {
    const value = await apiClient.adminGetUserDataSummary(accessToken, userId);
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, error: err.message };
    throw err;
  }
}

export async function adminProposeEraseAccountAction(
  userId: string,
  opts: {
    jurisdiction?: ErasureJurisdiction;
    notes?: string | null;
  } = {},
): Promise<AdminResult<ErasureRequestResponse>> {
  const { accessToken } = await requireAdmin();
  try {
    const value = await apiClient.adminProposeEraseAccount(accessToken, userId, {
      confirm_user_id: userId,
      jurisdiction: opts.jurisdiction ?? ErasureJurisdiction.GDPR,
      request_basis: ErasureBasis.ADMIN_ACTION,
      notes: opts.notes ?? null,
    });
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, error: err.message };
    throw err;
  }
}

export async function adminProposeAnonymiseSubjectAction(
  subjectId: string,
  opts: { jurisdiction?: ErasureJurisdiction; notes?: string | null } = {},
): Promise<AdminResult<ErasureRequestResponse>> {
  const { accessToken } = await requireAdmin();
  try {
    const value = await apiClient.adminProposeAnonymiseSubject(
      accessToken,
      subjectId,
      {
        jurisdiction: opts.jurisdiction ?? ErasureJurisdiction.POPIA,
        request_basis: ErasureBasis.ADMIN_ACTION,
        notes: opts.notes ?? null,
      },
    );
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, error: err.message };
    throw err;
  }
}

export async function adminApproveErasureAction(
  requestId: string,
): Promise<AdminResult<ErasureRequestResponse>> {
  const { accessToken } = await requireAdmin();
  try {
    const value = await apiClient.adminApproveErasure(accessToken, requestId);
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, error: err.message };
    throw err;
  }
}

export async function adminRejectErasureAction(
  requestId: string,
  reason: string | null,
): Promise<AdminResult<ErasureRequestResponse>> {
  const { accessToken } = await requireAdmin();
  try {
    const value = await apiClient.adminRejectErasure(
      accessToken,
      requestId,
      reason,
    );
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, error: err.message };
    throw err;
  }
}

export async function adminListErasureRequestsAction(
  opts: { status?: string; limit?: number; offset?: number } = {},
): Promise<AdminErasureRequestResponse[]> {
  const { accessToken } = await requireAdmin();
  return apiClient.adminListErasureRequests(accessToken, opts);
}

export async function adminQueryAuditLogAction(
  opts: {
    action?: string;
    actorId?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<AuditLogResponse> {
  const { accessToken } = await requireAdmin();
  return apiClient.adminQueryAuditLog(accessToken, opts);
}
