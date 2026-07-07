import 'server-only';

import {
  type AdminAnonymiseSubjectRequest,
  type AdminEraseAccountRequest,
  type AdminErasureRequestResponse,
  AdminErasureRequestResponseSchema,
  type AdminUserDataSummary,
  AdminUserDataSummarySchema,
  type AdminUserListResponse,
  AdminUserListResponseSchema,
  type AnonymiseSubjectRequest,
  ApiErrorSchema,
  type KioskSessionResponse,
  KioskSessionResponseSchema,
  type KioskSessionStatusResponse,
  KioskSessionStatusResponseSchema,
  type KioskCaptureRequest,
  type KioskCaptureResponse,
  KioskCaptureResponseSchema,
  type KioskResultGateResponse,
  KioskResultGateResponseSchema,
  type KioskResultPayload,
  KioskResultPayloadSchema,
  type EnrollmentRequest,
  type EnrollmentStatusResponse,
  EnrollmentStatusResponseSchema,
  type EnrollmentProfile,
  EnrollmentProfileSchema,
  type AuditLogResponse,
  AuditLogResponseSchema,
  AuthSessionSchema,
  type AuthSession,
  type CalibrationRecordResponse,
  CalibrationRecordResponseSchema,
  type CalibrationStatsResponse,
  CalibrationStatsResponseSchema,
  type CreateSubjectRequest,
  type EndSessionRequest,
  type EraseAccountRequest,
  type ErasureRequestResponse,
  ErasureRequestResponseSchema,
  type LoginRequest,
  type MyDataSummary,
  MyDataSummarySchema,
  type NotificationListResponse,
  NotificationListResponseSchema,
  type ParticipantHistory,
  ParticipantHistorySchema,
  type ParticipantSummary,
  ParticipantSummarySchema,
  type CareLoopStats,
  CareLoopStatsSchema,
  type CreateReferral,
  type RecordReferralOutcome,
  type ReferralResponse,
  ReferralResponseSchema,
  type UpdateReferralStatus,
  type RecordCalibrationRequest,
  type RegisterRequest,
  type AcquisitionWorklistItem,
  AcquisitionWorklistItemSchema,
  type ResearchCaseCreate,
  type ResearchCaseResponse,
  ResearchCaseResponseSchema,
  type ResearchCorpusStats,
  ResearchCorpusStatsSchema,
  type StartSessionRequest,
  type StudySessionResponse,
  StudySessionResponseSchema,
  type StudySubjectResponse,
  StudySubjectResponseSchema,
  type ToiAssessmentRequest,
  type ToiAssessmentResponse,
  ToiAssessmentResponseSchema,
  type TrajectoryResponse,
  TrajectoryResponseSchema,
  type TriageAssessmentRequest,
  type TriageAssessmentResponse,
  TriageAssessmentResponseSchema,
  type UnreadCountResponse,
  UnreadCountResponseSchema,
  UserPublicSchema,
  type UserPublic,
} from '@victus/contracts';

import { serverEnv } from './env';

class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  accessToken?: string;
  internal?: boolean;
  /** Attach the per-deployment kiosk device credentials (X-Kiosk-Id/Token). */
  kiosk?: boolean;
  cache?: RequestCache;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, accessToken, internal, kiosk, cache = 'no-store' } = opts;

  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
  if (internal) headers['X-Internal-Token'] = serverEnv.INTERNAL_SERVICE_TOKEN;
  if (kiosk && serverEnv.KIOSK_ID && serverEnv.KIOSK_DEVICE_TOKEN) {
    headers['X-Kiosk-Id'] = serverEnv.KIOSK_ID;
    headers['X-Kiosk-Token'] = serverEnv.KIOSK_DEVICE_TOKEN;
  }

  const response = await fetch(`${serverEnv.INTERNAL_API_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text) as unknown;
    } catch {
      throw new ApiError(response.status, 'invalid_response', 'API returned malformed JSON.');
    }
  }

  if (!response.ok) {
    const errorParse = ApiErrorSchema.safeParse(parsed);
    if (errorParse.success) {
      throw new ApiError(
        response.status,
        errorParse.data.error.code,
        errorParse.data.error.message,
        errorParse.data.error.details,
      );
    }
    throw new ApiError(response.status, 'unknown_error', response.statusText || 'API call failed.');
  }

  return parsed as T;
}

export const apiClient = {
  ApiError,

  async register(payload: RegisterRequest): Promise<AuthSession> {
    const raw = await request<unknown>('/auth/register', { method: 'POST', body: payload });
    return AuthSessionSchema.parse(raw);
  },

  async login(payload: LoginRequest): Promise<AuthSession> {
    const raw = await request<unknown>('/auth/login', { method: 'POST', body: payload });
    return AuthSessionSchema.parse(raw);
  },

  async refresh(refreshToken: string): Promise<AuthSession> {
    const raw = await request<unknown>('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    });
    return AuthSessionSchema.parse(raw);
  },

  async logout(accessToken: string, refreshToken: string | null): Promise<void> {
    await request<void>('/auth/logout', {
      method: 'POST',
      accessToken,
      body: { refresh_token: refreshToken },
    });
  },

  async me(accessToken: string): Promise<UserPublic> {
    const raw = await request<unknown>('/users/me', { accessToken });
    return UserPublicSchema.parse(raw);
  },

  async updateConsents(
    accessToken: string,
    payload: { grants?: string[]; revokes?: string[] },
  ): Promise<UserPublic> {
    const raw = await request<unknown>('/users/me/consents', {
      method: 'PATCH',
      accessToken,
      body: payload,
    });
    return UserPublicSchema.parse(raw);
  },

  async enterPathwayA(accessToken: string): Promise<{ next_step: string }> {
    return request<{ next_step: string }>('/pathways/triage/enter', {
      method: 'POST',
      accessToken,
    });
  },

  async enterPathwayB(accessToken: string): Promise<{ next_step: string }> {
    return request<{ next_step: string }>('/pathways/toi/enter', {
      method: 'POST',
      accessToken,
    });
  },

  async assessTriage(
    accessToken: string,
    payload: TriageAssessmentRequest,
  ): Promise<TriageAssessmentResponse> {
    const raw = await request<unknown>('/pathways/triage/assess', {
      method: 'POST',
      accessToken,
      body: payload,
    });
    return TriageAssessmentResponseSchema.parse(raw);
  },

  async listMyTriageAssessments(
    accessToken: string,
    limit = 10,
  ): Promise<TriageAssessmentResponse[]> {
    const raw = await request<unknown>(`/pathways/triage/assessments/me?limit=${limit}`, {
      accessToken,
    });
    if (!Array.isArray(raw)) {
      throw new ApiError(502, 'invalid_response', 'Expected array of assessments.');
    }
    return raw.map((item) => TriageAssessmentResponseSchema.parse(item));
  },

  async getMyTrajectory(
    accessToken: string,
    limit = 50,
  ): Promise<TrajectoryResponse> {
    const raw = await request<unknown>(
      `/pathways/triage/trajectory/me?limit=${limit}`,
      { accessToken },
    );
    return TrajectoryResponseSchema.parse(raw);
  },

  async assessToi(
    accessToken: string,
    payload: ToiAssessmentRequest,
  ): Promise<ToiAssessmentResponse> {
    const raw = await request<unknown>('/pathways/toi/assess', {
      method: 'POST',
      accessToken,
      body: payload,
    });
    return ToiAssessmentResponseSchema.parse(raw);
  },

  async listMyToiAssessments(
    accessToken: string,
    limit = 10,
  ): Promise<ToiAssessmentResponse[]> {
    const raw = await request<unknown>(`/pathways/toi/assessments/me?limit=${limit}`, {
      accessToken,
    });
    if (!Array.isArray(raw)) {
      throw new ApiError(502, 'invalid_response', 'Expected array of assessments.');
    }
    return raw.map((item) => ToiAssessmentResponseSchema.parse(item));
  },

  // ---- Study pre-registration ---------------------------------------------

  async createSubject(
    accessToken: string,
    payload: CreateSubjectRequest,
  ): Promise<StudySubjectResponse> {
    const raw = await request<unknown>('/study/subjects', {
      method: 'POST',
      accessToken,
      body: payload,
    });
    return StudySubjectResponseSchema.parse(raw);
  },

  async listSubjects(accessToken: string): Promise<StudySubjectResponse[]> {
    const raw = await request<unknown>('/study/subjects', { accessToken });
    if (!Array.isArray(raw)) {
      throw new ApiError(502, 'invalid_response', 'Expected array of subjects.');
    }
    return raw.map((item) => StudySubjectResponseSchema.parse(item));
  },

  async startSession(
    accessToken: string,
    payload: StartSessionRequest,
  ): Promise<StudySessionResponse> {
    const raw = await request<unknown>('/study/sessions', {
      method: 'POST',
      accessToken,
      body: payload,
    });
    return StudySessionResponseSchema.parse(raw);
  },

  async getActiveSession(
    accessToken: string,
  ): Promise<StudySessionResponse | null> {
    const raw = await request<unknown>('/study/sessions/active', { accessToken });
    if (raw === null || raw === undefined) return null;
    return StudySessionResponseSchema.parse(raw);
  },

  async listSessions(
    accessToken: string,
    limit = 50,
  ): Promise<StudySessionResponse[]> {
    const raw = await request<unknown>(`/study/sessions?limit=${limit}`, {
      accessToken,
    });
    if (!Array.isArray(raw)) {
      throw new ApiError(502, 'invalid_response', 'Expected array of sessions.');
    }
    return raw.map((item) => StudySessionResponseSchema.parse(item));
  },

  async endSession(
    accessToken: string,
    sessionId: string,
    payload: EndSessionRequest,
  ): Promise<StudySessionResponse> {
    const raw = await request<unknown>(`/study/sessions/${sessionId}/end`, {
      method: 'POST',
      accessToken,
      body: payload,
    });
    return StudySessionResponseSchema.parse(raw);
  },

  async recordCalibration(
    accessToken: string,
    payload: RecordCalibrationRequest,
  ): Promise<CalibrationRecordResponse> {
    const raw = await request<unknown>('/calibration/record', {
      method: 'POST',
      accessToken,
      body: payload,
    });
    return CalibrationRecordResponseSchema.parse(raw);
  },

  async getCalibrationStats(
    accessToken: string,
  ): Promise<CalibrationStatsResponse> {
    const raw = await request<unknown>('/calibration/stats', { accessToken });
    return CalibrationStatsResponseSchema.parse(raw);
  },

  async listCalibrationRecords(
    accessToken: string,
    limit = 50,
  ): Promise<CalibrationRecordResponse[]> {
    const raw = await request<unknown>(
      `/calibration/records?limit=${limit}`,
      { accessToken },
    );
    if (!Array.isArray(raw)) {
      throw new ApiError(502, 'invalid_response', 'Expected array of records.');
    }
    return raw.map((item) => CalibrationRecordResponseSchema.parse(item));
  },

  // ---- Research console (labelled triage capture) -------------------------

  async createResearchCase(
    accessToken: string,
    payload: ResearchCaseCreate,
  ): Promise<ResearchCaseResponse> {
    const raw = await request<unknown>('/research/triage-cases', {
      method: 'POST',
      accessToken,
      body: payload,
    });
    return ResearchCaseResponseSchema.parse(raw);
  },

  async listResearchCases(
    accessToken: string,
    limit = 50,
  ): Promise<ResearchCaseResponse[]> {
    const raw = await request<unknown>(
      `/research/triage-cases?limit=${limit}`,
      { accessToken },
    );
    if (!Array.isArray(raw)) {
      throw new ApiError(502, 'invalid_response', 'Expected array of cases.');
    }
    return raw.map((item) => ResearchCaseResponseSchema.parse(item));
  },

  async getResearchStats(accessToken: string): Promise<ResearchCorpusStats> {
    const raw = await request<unknown>('/research/triage-cases/stats', {
      accessToken,
    });
    return ResearchCorpusStatsSchema.parse(raw);
  },

  async getAcquisitionWorklist(
    accessToken: string,
    limit = 25,
  ): Promise<AcquisitionWorklistItem[]> {
    const raw = await request<unknown>(
      `/research/acquisition-worklist?limit=${limit}`,
      { accessToken },
    );
    if (!Array.isArray(raw)) {
      throw new ApiError(502, 'invalid_response', 'Expected array of items.');
    }
    return raw.map((item) => AcquisitionWorklistItemSchema.parse(item));
  },

  // ---- Data governance ----------------------------------------------------

  async getMyDataSummary(accessToken: string): Promise<MyDataSummary> {
    const raw = await request<unknown>('/governance/my-data-summary', {
      accessToken,
    });
    return MyDataSummarySchema.parse(raw);
  },

  async eraseAccount(
    accessToken: string,
    payload: EraseAccountRequest,
  ): Promise<ErasureRequestResponse> {
    const raw = await request<unknown>('/governance/erase-account', {
      method: 'POST',
      accessToken,
      body: payload,
    });
    return ErasureRequestResponseSchema.parse(raw);
  },

  async anonymiseSubject(
    accessToken: string,
    subjectId: string,
    payload: AnonymiseSubjectRequest,
  ): Promise<ErasureRequestResponse> {
    const raw = await request<unknown>(
      `/governance/subjects/${subjectId}/anonymise`,
      {
        method: 'POST',
        accessToken,
        body: payload,
      },
    );
    return ErasureRequestResponseSchema.parse(raw);
  },

  async listMyErasureRequests(
    accessToken: string,
    limit = 50,
  ): Promise<ErasureRequestResponse[]> {
    const raw = await request<unknown>(
      `/governance/erasure-requests/me?limit=${limit}`,
      { accessToken },
    );
    if (!Array.isArray(raw)) {
      throw new ApiError(
        502,
        'invalid_response',
        'Expected array of erasure requests.',
      );
    }
    return raw.map((item) => ErasureRequestResponseSchema.parse(item));
  },

  // ---- Notifications ------------------------------------------------------

  async listNotifications(
    accessToken: string,
    opts: { unreadOnly?: boolean; limit?: number } = {},
  ): Promise<NotificationListResponse> {
    const params = new URLSearchParams({
      unread_only: String(opts.unreadOnly ?? false),
      limit: String(opts.limit ?? 50),
    });
    const raw = await request<unknown>(`/notifications/me?${params}`, {
      accessToken,
    });
    return NotificationListResponseSchema.parse(raw);
  },

  async getUnreadCount(accessToken: string): Promise<UnreadCountResponse> {
    const raw = await request<unknown>('/notifications/me/unread-count', {
      accessToken,
    });
    return UnreadCountResponseSchema.parse(raw);
  },

  async markNotificationRead(
    accessToken: string,
    notificationId: string,
  ): Promise<void> {
    await request<void>(`/notifications/${notificationId}/read`, {
      method: 'POST',
      accessToken,
    });
  },

  async markAllNotificationsRead(
    accessToken: string,
  ): Promise<UnreadCountResponse> {
    const raw = await request<unknown>('/notifications/read-all', {
      method: 'POST',
      accessToken,
    });
    return UnreadCountResponseSchema.parse(raw);
  },

  // ---- Admin governance ---------------------------------------------------

  async adminListUsers(
    accessToken: string,
    opts: { limit?: number; offset?: number; includeErased?: boolean } = {},
  ): Promise<AdminUserListResponse> {
    const params = new URLSearchParams({
      limit: String(opts.limit ?? 50),
      offset: String(opts.offset ?? 0),
      include_erased: String(opts.includeErased ?? true),
    });
    const raw = await request<unknown>(`/governance/admin/users?${params}`, {
      accessToken,
    });
    return AdminUserListResponseSchema.parse(raw);
  },

  async adminGetUserDataSummary(
    accessToken: string,
    userId: string,
  ): Promise<AdminUserDataSummary> {
    const raw = await request<unknown>(
      `/governance/admin/users/${userId}/data-summary`,
      { accessToken },
    );
    return AdminUserDataSummarySchema.parse(raw);
  },

  /** MAKER — proposes account erasure (creates AWAITING_APPROVAL). */
  async adminProposeEraseAccount(
    accessToken: string,
    userId: string,
    payload: AdminEraseAccountRequest,
  ): Promise<ErasureRequestResponse> {
    const raw = await request<unknown>(
      `/governance/admin/users/${userId}/erase`,
      { method: 'POST', accessToken, body: payload },
    );
    return ErasureRequestResponseSchema.parse(raw);
  },

  /** MAKER — proposes subject anonymisation (creates AWAITING_APPROVAL). */
  async adminProposeAnonymiseSubject(
    accessToken: string,
    subjectId: string,
    payload: AdminAnonymiseSubjectRequest,
  ): Promise<ErasureRequestResponse> {
    const raw = await request<unknown>(
      `/governance/admin/subjects/${subjectId}/anonymise`,
      { method: 'POST', accessToken, body: payload },
    );
    return ErasureRequestResponseSchema.parse(raw);
  },

  /** CHECKER — approves + executes a pending request. */
  async adminApproveErasure(
    accessToken: string,
    requestId: string,
  ): Promise<ErasureRequestResponse> {
    const raw = await request<unknown>(
      `/governance/admin/erasure-requests/${requestId}/approve`,
      { method: 'POST', accessToken },
    );
    return ErasureRequestResponseSchema.parse(raw);
  },

  /** CHECKER — rejects a pending request. */
  async adminRejectErasure(
    accessToken: string,
    requestId: string,
    reason: string | null,
  ): Promise<ErasureRequestResponse> {
    const raw = await request<unknown>(
      `/governance/admin/erasure-requests/${requestId}/reject`,
      { method: 'POST', accessToken, body: { reason } },
    );
    return ErasureRequestResponseSchema.parse(raw);
  },

  async adminListErasureRequests(
    accessToken: string,
    opts: { status?: string; limit?: number; offset?: number } = {},
  ): Promise<AdminErasureRequestResponse[]> {
    const params = new URLSearchParams({
      limit: String(opts.limit ?? 100),
      offset: String(opts.offset ?? 0),
    });
    if (opts.status) params.set('status', opts.status);
    const raw = await request<unknown>(
      `/governance/admin/erasure-requests?${params}`,
      { accessToken },
    );
    if (!Array.isArray(raw)) {
      throw new ApiError(
        502,
        'invalid_response',
        'Expected array of erasure requests.',
      );
    }
    return raw.map((item) => AdminErasureRequestResponseSchema.parse(item));
  },

  async adminQueryAuditLog(
    accessToken: string,
    opts: {
      action?: string;
      actorId?: string;
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<AuditLogResponse> {
    const params = new URLSearchParams({
      limit: String(opts.limit ?? 100),
      offset: String(opts.offset ?? 0),
    });
    if (opts.action) params.set('action', opts.action);
    if (opts.actorId) params.set('actor_id', opts.actorId);
    const raw = await request<unknown>(
      `/governance/admin/audit-log?${params}`,
      { accessToken },
    );
    return AuditLogResponseSchema.parse(raw);
  },

  // ---- Referrals ----------------------------------------------------------

  async createReferral(
    accessToken: string,
    payload: CreateReferral,
  ): Promise<ReferralResponse> {
    const raw = await request<unknown>('/referrals', {
      method: 'POST',
      accessToken,
      body: payload,
    });
    return ReferralResponseSchema.parse(raw);
  },

  async listMyReferrals(accessToken: string, limit = 25): Promise<ReferralResponse[]> {
    const raw = await request<unknown>(`/referrals/me?limit=${limit}`, { accessToken });
    if (!Array.isArray(raw)) {
      throw new ApiError(502, 'invalid_response', 'Expected array of referrals.');
    }
    return raw.map((item) => ReferralResponseSchema.parse(item));
  },

  async listParticipantReferrals(
    accessToken: string,
    userId: string,
    limit = 50,
  ): Promise<ReferralResponse[]> {
    const raw = await request<unknown>(
      `/referrals/participant/${userId}?limit=${limit}`,
      { accessToken },
    );
    if (!Array.isArray(raw)) {
      throw new ApiError(502, 'invalid_response', 'Expected array of referrals.');
    }
    return raw.map((item) => ReferralResponseSchema.parse(item));
  },

  async updateReferralStatus(
    accessToken: string,
    referralId: string,
    payload: UpdateReferralStatus,
  ): Promise<ReferralResponse> {
    const raw = await request<unknown>(`/referrals/${referralId}/status`, {
      method: 'PATCH',
      accessToken,
      body: payload,
    });
    return ReferralResponseSchema.parse(raw);
  },

  async recordReferralOutcome(
    accessToken: string,
    referralId: string,
    payload: RecordReferralOutcome,
  ): Promise<ReferralResponse> {
    const raw = await request<unknown>(`/referrals/${referralId}/outcome`, {
      method: 'PATCH',
      accessToken,
      body: payload,
    });
    return ReferralResponseSchema.parse(raw);
  },

  async getCareLoopStats(accessToken: string): Promise<CareLoopStats> {
    const raw = await request<unknown>('/referrals/analytics/care-loop', {
      accessToken,
    });
    return CareLoopStatsSchema.parse(raw);
  },

  // ---- Clinician participant review ---------------------------------------

  async searchParticipants(
    accessToken: string,
    query: string,
    limit = 25,
  ): Promise<ParticipantSummary[]> {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    const raw = await request<unknown>(`/clinical/participants?${params}`, {
      accessToken,
    });
    if (!Array.isArray(raw)) {
      throw new ApiError(502, 'invalid_response', 'Expected array of participants.');
    }
    return raw.map((item) => ParticipantSummarySchema.parse(item));
  },

  async getParticipantHistory(
    accessToken: string,
    userId: string,
    limit = 50,
  ): Promise<ParticipantHistory> {
    const raw = await request<unknown>(
      `/clinical/participants/${userId}/history?limit=${limit}`,
      { accessToken },
    );
    return ParticipantHistorySchema.parse(raw);
  },

  // ---- Mobile Clinic Gateway (kiosk rail) ---------------------------------

  /** Open a kiosk session (device-authed). Returns the QR/deep-link payload. */
  async createKioskSession(): Promise<KioskSessionResponse> {
    const raw = await request<unknown>('/kiosk/sessions', {
      method: 'POST',
      kiosk: true,
    });
    return KioskSessionResponseSchema.parse(raw);
  },

  /** Poll a kiosk session's status (device-authed). */
  async getKioskSessionStatus(
    sessionId: string,
  ): Promise<KioskSessionStatusResponse> {
    const raw = await request<unknown>(`/kiosk/sessions/${sessionId}`, {
      kiosk: true,
    });
    return KioskSessionStatusResponseSchema.parse(raw);
  },

  /** Submit derived capture signals for processing (device-authed). */
  async submitKioskCapture(
    sessionId: string,
    payload: KioskCaptureRequest,
  ): Promise<KioskCaptureResponse> {
    const raw = await request<unknown>(`/kiosk/sessions/${sessionId}/capture`, {
      method: 'POST',
      kiosk: true,
      body: payload,
    });
    return KioskCaptureResponseSchema.parse(raw);
  },

  /** Probe a result link before showing the OTP form (public). */
  async getKioskResultGate(token: string): Promise<KioskResultGateResponse> {
    const raw = await request<unknown>(
      `/kiosk/results/${encodeURIComponent(token)}`,
    );
    return KioskResultGateResponseSchema.parse(raw);
  },

  /** Unlock a result with the 4-digit OTP (public, single use). */
  async unlockKioskResult(
    token: string,
    otp: string,
  ): Promise<KioskResultPayload> {
    const raw = await request<unknown>(
      `/kiosk/results/${encodeURIComponent(token)}/unlock`,
      { method: 'POST', body: { otp } },
    );
    return KioskResultPayloadSchema.parse(raw);
  },

  /** Download a participant's record as PDF (clinician/admin). Raw bytes —
   *  the JSON ``request`` helper can't carry a binary body. */
  async getParticipantReportPdf(
    accessToken: string,
    userId: string,
  ): Promise<{ bytes: ArrayBuffer; filename: string }> {
    const response = await fetch(
      `${serverEnv.INTERNAL_API_BASE_URL}/clinical/participants/${userId}/report.pdf`,
      {
        headers: {
          Accept: 'application/pdf',
          Authorization: `Bearer ${accessToken}`,
        },
        cache: 'no-store',
      },
    );
    if (!response.ok) {
      let code = 'unknown_error';
      let message = response.statusText || 'PDF export failed.';
      try {
        const parsed = ApiErrorSchema.safeParse(await response.json());
        if (parsed.success) {
          code = parsed.data.error.code;
          message = parsed.data.error.message;
        }
      } catch {
        /* non-JSON error body — keep the generic message */
      }
      throw new ApiError(response.status, code, message);
    }
    const disposition = response.headers.get('content-disposition') ?? '';
    const match = /filename="?([^"]+)"?/.exec(disposition);
    const filename = match?.[1] ?? `participant-${userId}.pdf`;
    return { bytes: await response.arrayBuffer(), filename };
  },

  // ---- Enrollment (front-of-platform participant intake) ------------------

  async getEnrollmentStatus(
    accessToken: string,
  ): Promise<EnrollmentStatusResponse> {
    const raw = await request<unknown>('/enrollment/status', { accessToken });
    return EnrollmentStatusResponseSchema.parse(raw);
  },

  async enroll(
    accessToken: string,
    payload: EnrollmentRequest,
  ): Promise<EnrollmentProfile> {
    const raw = await request<unknown>('/enrollment', {
      method: 'POST',
      accessToken,
      body: payload,
    });
    return EnrollmentProfileSchema.parse(raw);
  },
};

export { ApiError };
