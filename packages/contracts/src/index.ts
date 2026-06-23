/**
 * Shared DTOs + enums between FastAPI (source of truth) and Next.js.
 *
 * These types mirror the Pydantic v2 schemas in `apps/api/src/victus_api/`.
 * When the API contract changes, regenerate these from the FastAPI OpenAPI
 * spec (planned tooling: `openapi-typescript` against `/openapi.json`).
 */

import { z } from 'zod';

// ---------------------------------------------------------------------------
// Enums (kept lockstep with apps/api/src/victus_api/db/models.py)
// ---------------------------------------------------------------------------

export const UserRole = {
  PATIENT: 'PATIENT',
  CHW: 'CHW',
  CLINICIAN: 'CLINICIAN',
  ADMIN: 'ADMIN',
} as const;
export type UserRole = (typeof UserRole)[keyof typeof UserRole];
export const UserRoleSchema = z.nativeEnum(UserRole);

export const ConsentType = {
  TRIAGE: 'TRIAGE',
  TOI_IMAGING: 'TOI_IMAGING',
  DATA_SHARING_RESEARCH: 'DATA_SHARING_RESEARCH',
} as const;
export type ConsentType = (typeof ConsentType)[keyof typeof ConsentType];
export const ConsentTypeSchema = z.nativeEnum(ConsentType);

export const PathwayKind = {
  A_TRIAGE: 'A_TRIAGE',
  B_TOI: 'B_TOI',
} as const;
export type PathwayKind = (typeof PathwayKind)[keyof typeof PathwayKind];

// Pathway A result state machine — drives all GREEN/YELLOW/RED UI affordances.
export const TriageState = {
  GREEN: 'GREEN',
  YELLOW: 'YELLOW',
  RED: 'RED',
} as const;
export type TriageState = (typeof TriageState)[keyof typeof TriageState];

// ---------------------------------------------------------------------------
// Auth schemas
// ---------------------------------------------------------------------------

export const PASSWORD_MIN_LENGTH = 12;

export const PasswordSchema = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `Must be at least ${PASSWORD_MIN_LENGTH} characters`)
  .max(128)
  .regex(/[a-z]/, 'Must contain a lowercase letter')
  .regex(/[A-Z]/, 'Must contain an uppercase letter')
  .regex(/\d/, 'Must contain a digit');

export const RegisterRequestSchema = z.object({
  email: z.string().email(),
  password: PasswordSchema,
  full_name: z.string().min(2).max(200),
  role: UserRoleSchema.default(UserRole.PATIENT),
});
export type RegisterRequest = z.infer<typeof RegisterRequestSchema>;

export const LoginRequestSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1).max(128),
});
export type LoginRequest = z.infer<typeof LoginRequestSchema>;

export const UserPublicSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  full_name: z.string(),
  role: UserRoleSchema,
  is_active: z.boolean(),
  created_at: z.string(),
  consents: z.array(ConsentTypeSchema),
});
export type UserPublic = z.infer<typeof UserPublicSchema>;

export const TokenPairSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.literal('Bearer').default('Bearer'),
  expires_in: z.number().int().positive(),
});
export type TokenPair = z.infer<typeof TokenPairSchema>;

export const AuthSessionSchema = z.object({
  user: UserPublicSchema,
  tokens: TokenPairSchema,
});
export type AuthSession = z.infer<typeof AuthSessionSchema>;

export const ConsentUpdateRequestSchema = z.object({
  grants: z.array(ConsentTypeSchema).default([]),
  revokes: z.array(ConsentTypeSchema).default([]),
  version: z.string().max(32).default('1.0.0'),
});
export type ConsentUpdateRequest = z.infer<typeof ConsentUpdateRequestSchema>;

export const ApiErrorSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.string(), z.unknown()).optional(),
  }),
});
export type ApiError = z.infer<typeof ApiErrorSchema>;

// ---------------------------------------------------------------------------
// RBAC + consent matrix per pathway
// ---------------------------------------------------------------------------

export const PATHWAY_REQUIREMENTS: Record<
  PathwayKind,
  { roles: readonly UserRole[]; consents: readonly ConsentType[] }
> = {
  [PathwayKind.A_TRIAGE]: {
    roles: [UserRole.PATIENT, UserRole.CHW, UserRole.CLINICIAN],
    consents: [ConsentType.TRIAGE],
  },
  [PathwayKind.B_TOI]: {
    roles: [UserRole.PATIENT, UserRole.CLINICIAN],
    consents: [ConsentType.TOI_IMAGING],
  },
};

export function userMayEnterPathway(
  pathway: PathwayKind,
  role: UserRole,
  consents: readonly ConsentType[],
): { allowed: true } | { allowed: false; reason: 'role' | 'consent'; missing: string[] } {
  const req = PATHWAY_REQUIREMENTS[pathway];
  if (!req.roles.includes(role)) {
    return { allowed: false, reason: 'role', missing: [...req.roles] };
  }
  const missingConsents = req.consents.filter((c) => !consents.includes(c));
  if (missingConsents.length > 0) {
    return { allowed: false, reason: 'consent', missing: missingConsents };
  }
  return { allowed: true };
}

// ===========================================================================
// PATHWAY A — 3B-TRIAGE
// ===========================================================================

export const Sex = {
  MALE: 'MALE',
  FEMALE: 'FEMALE',
  OTHER: 'OTHER',
} as const;
export type Sex = (typeof Sex)[keyof typeof Sex];
export const SexSchema = z.nativeEnum(Sex);

/** Risk classes the EDL Dirichlet head distributes evidence over. */
export const RiskClass = {
  LOW_RISK: 'LOW_RISK',
  ELEVATED_RISK: 'ELEVATED_RISK',
  HIGH_RISK: 'HIGH_RISK',
  VERY_HIGH_RISK: 'VERY_HIGH_RISK',
} as const;
export type RiskClass = (typeof RiskClass)[keyof typeof RiskClass];
export const RiskClassSchema = z.nativeEnum(RiskClass);
export const RISK_CLASSES: readonly RiskClass[] = [
  RiskClass.LOW_RISK,
  RiskClass.ELEVATED_RISK,
  RiskClass.HIGH_RISK,
  RiskClass.VERY_HIGH_RISK,
];

/**
 * The three NCDs Pathway A weights INDEPENDENTLY. Each disease carries its own
 * Dirichlet over {@link RiskClass}, its own uncertainty decomposition and its
 * own {@link TriageState}. There is no single global risk class — the overall
 * state is the worst of the three (with safety overrides forcing RED).
 */
export const Disease = {
  OBESITY: 'OBESITY',
  HYPERTENSION: 'HYPERTENSION',
  DIABETES: 'DIABETES',
} as const;
export type Disease = (typeof Disease)[keyof typeof Disease];
export const DiseaseSchema = z.nativeEnum(Disease);
/** Fixed order — mirrors the model's per-disease heads and the UI layout. */
export const DISEASES: readonly Disease[] = [
  Disease.OBESITY,
  Disease.HYPERTENSION,
  Disease.DIABETES,
];
/** Human-readable disease labels for the UI. */
export const DISEASE_LABELS: Record<Disease, string> = {
  [Disease.OBESITY]: 'Obesity',
  [Disease.HYPERTENSION]: 'Hypertension',
  [Disease.DIABETES]: 'Diabetes (proxy)',
};

/** EDL state-machine thresholds — single source of truth shared with the API. */
export const EDL_THRESHOLDS = {
  /** u = K/S above this triggers YELLOW (too uncertain to act on). */
  VACUITY_YELLOW: 0.5,
  /** Top expected-probability must clear this AND vacuity must be low for RED. */
  CONFIDENCE_RED: 0.6,
  /** Classes that count as elevated outcomes for RED escalation. */
  RED_RISK_CLASSES: [RiskClass.HIGH_RISK, RiskClass.VERY_HIGH_RISK] as const,
} as const;

/**
 * Deterministic safety-override symptom keys.
 *
 * Per the Victus AI clinical-safety brief, ANY of these — when affirmed by the
 * user — must trigger RED before the EDL inference ever runs. The frontend AND
 * the backend independently evaluate these triggers; defence in depth.
 */
export const SAFETY_OVERRIDE_SYMPTOM_KEYS = [
  'polydipsia_unquenchable_thirst',
  'blurred_vision_progressive',
  'non_healing_foot_sore',
  'chest_pain_radiating',
  'severe_headache_with_visual_change',
  'polyuria_nocturia_severe',
  'unexplained_weight_loss_recent',
] as const;
export type SafetyOverrideSymptomKey = (typeof SAFETY_OVERRIDE_SYMPTOM_KEYS)[number];

/**
 * Non-safety symptoms collected for context and downstream model features.
 * (Currently informational; YELLOW fallback path may surface them.)
 */
export const CONTEXTUAL_SYMPTOM_KEYS = [
  'fatigue_persistent',
  'family_history_diabetes',
  'family_history_hypertension',
  'smoker_current',
  'physical_activity_low',
] as const;
export type ContextualSymptomKey = (typeof CONTEXTUAL_SYMPTOM_KEYS)[number];

/** Anthropometric and (optional) BP inputs collected via tape measure / cuff. */
export const TapeMeasureInputsSchema = z.object({
  height_cm: z.number().positive('Height must be > 0').min(50).max(250),
  weight_kg: z.number().positive('Weight must be > 0').min(5).max(400),
  waist_cm: z.number().positive('Waist must be > 0').min(30).max(250),
  hip_cm: z.number().positive().min(40).max(250).optional(),
  age_years: z.number().int().positive().min(1).max(120),
  sex: SexSchema,
  systolic_bp_mmhg: z.number().positive().min(50).max(260).optional(),
  diastolic_bp_mmhg: z.number().positive().min(30).max(160).optional(),
});
export type TapeMeasureInputs = z.infer<typeof TapeMeasureInputsSchema>;

export const SymptomAuditSchema = z.object({
  safety_triggers: z.array(z.enum(SAFETY_OVERRIDE_SYMPTOM_KEYS)).default([]),
  contextual: z.array(z.enum(CONTEXTUAL_SYMPTOM_KEYS)).default([]),
});
export type SymptomAudit = z.infer<typeof SymptomAuditSchema>;

export const TriageAssessmentRequestSchema = z.object({
  inputs: TapeMeasureInputsSchema,
  symptoms: SymptomAuditSchema,
});
export type TriageAssessmentRequest = z.infer<typeof TriageAssessmentRequestSchema>;

export const PlausibilityFlag = {
  BMI_OUT_OF_RANGE: 'BMI_OUT_OF_RANGE',
  WAIST_GT_HEIGHT: 'WAIST_GT_HEIGHT',
  WAIST_TOO_SMALL: 'WAIST_TOO_SMALL',
  BP_INVERTED: 'BP_INVERTED',
  BP_EXTREME: 'BP_EXTREME',
  POSSIBLE_UNIT_CONFUSION_HEIGHT: 'POSSIBLE_UNIT_CONFUSION_HEIGHT',
  POSSIBLE_UNIT_CONFUSION_WEIGHT: 'POSSIBLE_UNIT_CONFUSION_WEIGHT',
} as const;
export type PlausibilityFlag = (typeof PlausibilityFlag)[keyof typeof PlausibilityFlag];

export const TriageUncertaintySchema = z.object({
  /** u = K/S — Dirichlet vacuity (epistemic proxy). */
  vacuity: z.number().min(0).max(1),
  /** E[H(p)] expected categorical entropy under the Dirichlet (aleatoric). */
  aleatoric: z.number().min(0),
  /** H[E[p]] - E[H(p)] mutual information (BALD, epistemic). */
  epistemic: z.number().min(0),
  /** Dirichlet strength S = K + Σevidence. */
  strength: z.number().positive(),
});
export type TriageUncertainty = z.infer<typeof TriageUncertaintySchema>;

/** Independent evidential risk assessment for a single NCD. */
export const PerDiseaseRiskSchema = z.object({
  disease: DiseaseSchema,
  state: z.nativeEnum(TriageState),
  top_class: RiskClassSchema,
  class_probabilities: z.record(RiskClassSchema, z.number().min(0).max(1)),
  evidence: z.record(RiskClassSchema, z.number().min(0)),
  uncertainty: TriageUncertaintySchema,
  /** Human-readable clinical drivers (e.g. "BMI ≥ 30", "Family history"). */
  contributing_factors: z.array(z.string()),
  next_action: z.string(),
});
export type PerDiseaseRisk = z.infer<typeof PerDiseaseRiskSchema>;

export const TriageAssessmentResponseSchema = z.object({
  id: z.string().uuid(),
  /** Worst of the per-disease states; RED whenever a safety override fires. */
  overall_state: z.nativeEnum(TriageState),
  /** One entry per disease in {@link DISEASES}, each independently weighted. */
  per_disease: z.array(PerDiseaseRiskSchema),
  derived_features: z.object({
    bmi: z.number().nullable(),
    whtr: z.number().nullable(),
    whr: z.number().nullable(),
    pulse_pressure_mmhg: z.number().nullable(),
  }),
  plausibility_flags: z.array(z.nativeEnum(PlausibilityFlag)),
  safety_override_triggered: z.boolean(),
  override_reasons: z.array(z.enum(SAFETY_OVERRIDE_SYMPTOM_KEYS)),
  /** "trained_torch_dann_multihead_v1" once a checkpoint ships; "rule_based_fallback_v1" otherwise. */
  model_kind: z.string(),
  next_action: z.string(),
  created_at: z.string(),
});
export type TriageAssessmentResponse = z.infer<typeof TriageAssessmentResponseSchema>;

/**
 * Client-side defence in depth: the wizard checks this before submitting so
 * the user sees the RED state instantly. The API re-checks server-side and is
 * authoritative.
 */
export function detectSafetyOverride(
  symptoms: SymptomAudit,
): { triggered: true; reasons: SafetyOverrideSymptomKey[] } | { triggered: false } {
  if (symptoms.safety_triggers.length === 0) return { triggered: false };
  return { triggered: true, reasons: [...symptoms.safety_triggers] };
}

// ===========================================================================
// PATHWAY B — TOI / rPPG
// ===========================================================================

export const ToiQuality = {
  GOOD: 'GOOD',
  DEGRADED: 'DEGRADED',
  POOR: 'POOR',
} as const;
export type ToiQuality = (typeof ToiQuality)[keyof typeof ToiQuality];
export const ToiQualitySchema = z.nativeEnum(ToiQuality);

export const FitzpatrickScale = {
  I: 'I',
  II: 'II',
  III: 'III',
  IV: 'IV',
  V: 'V',
  VI: 'VI',
} as const;
export type FitzpatrickScale =
  (typeof FitzpatrickScale)[keyof typeof FitzpatrickScale];
export const FitzpatrickScaleSchema = z.nativeEnum(FitzpatrickScale);

export const TOI_CAPTURE = {
  TARGET_DURATION_S: 30,
  MIN_DURATION_S: 5,
  MAX_DURATION_S: 60,
  TARGET_FPS: 30,
  MIN_FRAMES: 100,
  MAX_FRAMES: 3600,
} as const;

export const RppgFrameSchema = z.object({
  t_ms: z.number().int().min(0).max(120_000),
  r: z.number().min(0).max(255),
  g: z.number().min(0).max(255),
  b: z.number().min(0).max(255),
});
export type RppgFrame = z.infer<typeof RppgFrameSchema>;

export const ToiAssessmentRequestSchema = z.object({
  frames: z
    .array(RppgFrameSchema)
    .min(TOI_CAPTURE.MIN_FRAMES)
    .max(TOI_CAPTURE.MAX_FRAMES),
  sample_rate_hz: z.number().positive().max(240),
  duration_s: z
    .number()
    .min(TOI_CAPTURE.MIN_DURATION_S)
    .max(TOI_CAPTURE.MAX_DURATION_S),
  skin_tone_estimate: FitzpatrickScaleSchema.nullable().optional(),
  motion_score: z.number().min(0).max(1).default(1),
  lighting_score: z.number().min(0).max(1).nullable().optional(),
  face_presence_ratio: z.number().min(0).max(1).default(1),
});
export type ToiAssessmentRequest = z.infer<typeof ToiAssessmentRequestSchema>;

export const BiomarkerEstimateSchema = z.object({
  value: z.number(),
  ci_low: z.number().nullable().optional(),
  ci_high: z.number().nullable().optional(),
  unit: z.string(),
  experimental: z.boolean().default(false),
});
export type BiomarkerEstimate = z.infer<typeof BiomarkerEstimateSchema>;

export const SignalQualitySchema = z.object({
  snr_chrom_db: z.number(),
  snr_pos_db: z.number(),
  method_selected: z.enum(['chrom', 'pos', 'none']),
  motion_score: z.number().min(0).max(1),
  lighting_score: z.number().min(0).max(1),
  face_presence_ratio: z.number().min(0).max(1),
  frames_used: z.number().int().nonnegative(),
});
export type SignalQuality = z.infer<typeof SignalQualitySchema>;

export const ToiAssessmentResponseSchema = z.object({
  id: z.string().uuid(),
  quality: ToiQualitySchema,
  duration_s: z.number(),
  sample_rate_hz: z.number(),
  frame_count: z.number().int().nonnegative(),
  biomarkers: z.record(z.string(), BiomarkerEstimateSchema),
  signal_quality: SignalQualitySchema,
  method_details: z.record(z.string(), z.unknown()),
  warnings: z.array(z.string()),
  next_action: z.string(),
  pipeline_version: z.string(),
  created_at: z.string(),
});
export type ToiAssessmentResponse = z.infer<typeof ToiAssessmentResponseSchema>;

// ===========================================================================
// rPPG CALIBRATION STUDY
// ===========================================================================

export const ReferenceDeviceType = {
  PULSE_OXIMETER: 'PULSE_OXIMETER',
  SMART_WATCH: 'SMART_WATCH',
  ECG_STRAP: 'ECG_STRAP',
  MEDICAL_ECG: 'MEDICAL_ECG',
  MANUAL_PULSE_COUNT: 'MANUAL_PULSE_COUNT',
} as const;
export type ReferenceDeviceType =
  (typeof ReferenceDeviceType)[keyof typeof ReferenceDeviceType];
export const ReferenceDeviceTypeSchema = z.nativeEnum(ReferenceDeviceType);

export const REFERENCE_DEVICE_LABELS: Record<ReferenceDeviceType, string> = {
  PULSE_OXIMETER: 'Pulse oximeter (fingertip)',
  SMART_WATCH: 'Smart watch (Apple, Fitbit, Garmin, …)',
  ECG_STRAP: 'Chest-strap ECG (Polar, Wahoo, …)',
  MEDICAL_ECG: 'Medical-grade ECG',
  MANUAL_PULSE_COUNT: 'Manual pulse count (carotid / wrist)',
};

export const RecordCalibrationRequestSchema = z.object({
  toi_assessment_id: z.string().uuid(),
  reference_device_type: ReferenceDeviceTypeSchema,
  reference_device_label: z.string().max(120).optional().nullable(),
  reference_hr_bpm: z.number().min(30).max(240),
  reference_rr_bpm: z.number().min(4).max(60).optional().nullable(),
  // BLE auto-pair payload — all optional so manual recording still works.
  auto_paired_from_ble: z.boolean().default(false),
  reference_hr_sample_count: z
    .number()
    .int()
    .nonnegative()
    .optional()
    .nullable(),
  /**
   * Raw RR intervals (ms) streamed from a BLE Heart Rate Service that
   * exposes the optional RR-Interval field of characteristic 0x2A37.
   * Polar H10, Wahoo TICKR, MyZone deliver these natively. The server
   * recomputes RMSSD/SDNN from these so the persisted reference HRV is
   * canonical and any future formula fix propagates to existing data.
   */
  reference_rr_intervals_ms: z
    .array(z.number().min(250).max(2000))
    .optional()
    .nullable(),
  skin_tone_estimate: FitzpatrickScaleSchema.optional().nullable(),
  notes: z.string().max(500).optional().nullable(),
});
export type RecordCalibrationRequest = z.infer<
  typeof RecordCalibrationRequestSchema
>;

export const CalibrationRecordResponseSchema = z.object({
  id: z.string().uuid(),
  toi_assessment_id: z.string().uuid().nullable(),
  reference_device_type: ReferenceDeviceTypeSchema,
  reference_device_label: z.string().nullable(),
  reference_hr_bpm: z.number(),
  reference_rr_bpm: z.number().nullable(),
  reference_hr_sample_count: z.number().int().nullable(),
  reference_hrv_rmssd_ms: z.number().nullable(),
  reference_hrv_sdnn_ms: z.number().nullable(),
  reference_rr_intervals_ms: z.array(z.number()).nullable(),
  auto_paired_from_ble: z.boolean(),
  rppg_hr_bpm: z.number(),
  rppg_rr_bpm: z.number().nullable(),
  rppg_hrv_rmssd_ms: z.number().nullable(),
  rppg_hrv_sdnn_ms: z.number().nullable(),
  rppg_quality: ToiQualitySchema,
  rppg_method_selected: z.string(),
  rppg_snr_chrom_db: z.number(),
  rppg_snr_pos_db: z.number(),
  rppg_pipeline_version: z.string(),
  skin_tone_estimate: FitzpatrickScaleSchema.nullable(),
  notes: z.string().nullable(),
  error_bpm: z.number(),
  hrv_error_ms: z.number().nullable(),
  study_session_id: z.string().uuid().nullable(),
  study_subject_external_id: z.string().nullable(),
  posture: z.string().nullable(),
  time_of_day: z.string().nullable(),
  created_at: z.string(),
});
export type CalibrationRecordResponse = z.infer<
  typeof CalibrationRecordResponseSchema
>;

export const HrvCalibrationStatsBlockSchema = z.object({
  n: z.number().int().nonnegative(),
  rmssd_mae_ms: z.number(),
  rmssd_rmse_ms: z.number(),
  rmssd_bias_ms: z.number(),
  rmssd_std_diff_ms: z.number(),
  rmssd_loa_lower_ms: z.number(),
  rmssd_loa_upper_ms: z.number(),
  rmssd_pearson_r: z.number().nullable(),
  rmssd_pearson_p: z.number().nullable(),
  sdnn_mae_ms: z.number().nullable(),
  sdnn_bias_ms: z.number().nullable(),
  rmssd_means: z.array(z.number()),
  rmssd_differences: z.array(z.number()),
  flags: z.array(z.string()),
});
export type HrvCalibrationStatsBlock = z.infer<
  typeof HrvCalibrationStatsBlockSchema
>;

export const CalibrationStatsBlockSchema = z.object({
  n: z.number().int().nonnegative(),
  mae_bpm: z.number(),
  rmse_bpm: z.number(),
  bias_bpm: z.number(),
  std_diff_bpm: z.number(),
  loa_lower_bpm: z.number(),
  loa_upper_bpm: z.number(),
  pearson_r: z.number().nullable(),
  pearson_p: z.number().nullable(),
  ref_min: z.number(),
  ref_max: z.number(),
  ref_mean: z.number(),
  means: z.array(z.number()),
  differences: z.array(z.number()),
  flags: z.array(z.string()),
});
export type CalibrationStatsBlock = z.infer<
  typeof CalibrationStatsBlockSchema
>;

export const CalibrationStatsResponseSchema = z.object({
  overall: CalibrationStatsBlockSchema.nullable(),
  overall_hrv: HrvCalibrationStatsBlockSchema.nullable(),
  by_quality: z.record(z.string(), CalibrationStatsBlockSchema.nullable()),
  by_fitzpatrick: z.record(z.string(), CalibrationStatsBlockSchema.nullable()),
  by_reference_device: z.record(
    z.string(),
    CalibrationStatsBlockSchema.nullable(),
  ),
  by_posture: z.record(z.string(), CalibrationStatsBlockSchema.nullable()),
  by_time_of_day: z.record(z.string(), CalibrationStatsBlockSchema.nullable()),
  by_subject: z.record(z.string(), CalibrationStatsBlockSchema.nullable()),
  pipeline_version: z.string(),
});
export type CalibrationStatsResponse = z.infer<
  typeof CalibrationStatsResponseSchema
>;

// ===========================================================================
// STUDY PRE-REGISTRATION
// ===========================================================================

export const SexAtBirth = {
  MALE: 'MALE',
  FEMALE: 'FEMALE',
  INTERSEX: 'INTERSEX',
  PREFER_NOT_TO_SAY: 'PREFER_NOT_TO_SAY',
} as const;
export type SexAtBirth = (typeof SexAtBirth)[keyof typeof SexAtBirth];
export const SexAtBirthSchema = z.nativeEnum(SexAtBirth);

export const Posture = {
  SITTING: 'SITTING',
  STANDING: 'STANDING',
  SUPINE: 'SUPINE',
  SEMI_RECLINED: 'SEMI_RECLINED',
} as const;
export type Posture = (typeof Posture)[keyof typeof Posture];
export const PostureSchema = z.nativeEnum(Posture);

export const POSTURE_LABELS: Record<Posture, string> = {
  SITTING: 'Sitting upright',
  STANDING: 'Standing',
  SUPINE: 'Supine (lying flat)',
  SEMI_RECLINED: 'Semi-reclined',
};

export const TimeOfDay = {
  MORNING: 'MORNING',
  AFTERNOON: 'AFTERNOON',
  EVENING: 'EVENING',
  NIGHT: 'NIGHT',
} as const;
export type TimeOfDay = (typeof TimeOfDay)[keyof typeof TimeOfDay];
export const TimeOfDaySchema = z.nativeEnum(TimeOfDay);

export const TIME_OF_DAY_LABELS: Record<TimeOfDay, string> = {
  MORNING: 'Morning (04:00–11:59)',
  AFTERNOON: 'Afternoon (12:00–16:59)',
  EVENING: 'Evening (17:00–21:59)',
  NIGHT: 'Night (22:00–03:59)',
};

export const CreateSubjectRequestSchema = z.object({
  external_subject_id: z
    .string()
    .min(1)
    .max(64)
    .regex(/^[A-Za-z0-9_\-:.]+$/, 'Only letters, digits, _ - : . are allowed'),
  age_years: z.number().int().min(0).max(130),
  sex_assigned_at_birth: SexAtBirthSchema,
  fitzpatrick_scale: FitzpatrickScaleSchema.nullable().optional(),
  height_cm: z.number().positive().max(250).nullable().optional(),
  weight_kg: z.number().positive().max(400).nullable().optional(),
  medical_history_summary: z.string().max(2000).nullable().optional(),
  consent_protocol_version: z.string().max(64).nullable().optional(),
});
export type CreateSubjectRequest = z.infer<typeof CreateSubjectRequestSchema>;

export const StudySubjectResponseSchema = z.object({
  id: z.string().uuid(),
  external_subject_id: z.string(),
  age_years: z.number().int(),
  sex_assigned_at_birth: SexAtBirthSchema,
  fitzpatrick_scale: FitzpatrickScaleSchema.nullable(),
  height_cm: z.number().nullable(),
  weight_kg: z.number().nullable(),
  medical_history_summary: z.string().nullable(),
  consent_protocol_version: z.string(),
  enrolled_at: z.string(),
  is_active: z.boolean(),
  session_count: z.number().int().nonnegative(),
  pair_count: z.number().int().nonnegative(),
});
export type StudySubjectResponse = z.infer<typeof StudySubjectResponseSchema>;

export const StartSessionRequestSchema = z.object({
  study_subject_id: z.string().uuid(),
  posture: PostureSchema,
  time_of_day: TimeOfDaySchema.nullable().optional(),
  ambient_lux: z.number().min(0).max(200_000).nullable().optional(),
  ambient_temperature_c: z.number().min(-20).max(60).nullable().optional(),
  room_humidity_pct: z.number().min(0).max(100).nullable().optional(),
  fasted_hours: z.number().min(0).max(72).nullable().optional(),
  caffeine_within_2h: z.boolean().default(false),
  nicotine_within_2h: z.boolean().default(false),
  alcohol_within_24h: z.boolean().default(false),
  last_exercise_hours_ago: z.number().min(0).max(168).nullable().optional(),
  recording_site_label: z.string().max(120).nullable().optional(),
  protocol_version: z.string().max(64).nullable().optional(),
  notes: z.string().max(2000).nullable().optional(),
});
export type StartSessionRequest = z.infer<typeof StartSessionRequestSchema>;

export const StudySessionResponseSchema = z.object({
  id: z.string().uuid(),
  study_subject_id: z.string().uuid(),
  external_subject_id: z.string(),
  session_started_at: z.string(),
  posture: PostureSchema,
  time_of_day: TimeOfDaySchema,
  ambient_lux: z.number().nullable(),
  ambient_temperature_c: z.number().nullable(),
  room_humidity_pct: z.number().nullable(),
  fasted_hours: z.number().nullable(),
  caffeine_within_2h: z.boolean(),
  nicotine_within_2h: z.boolean(),
  alcohol_within_24h: z.boolean(),
  last_exercise_hours_ago: z.number().nullable(),
  recording_site_label: z.string().nullable(),
  protocol_version: z.string(),
  notes: z.string().nullable(),
  is_locked: z.boolean(),
  locked_at: z.string().nullable(),
  ended_at: z.string().nullable(),
  pair_count: z.number().int().nonnegative(),
});
export type StudySessionResponse = z.infer<typeof StudySessionResponseSchema>;

export const EndSessionRequestSchema = z.object({
  notes: z.string().max(2000).nullable().optional(),
});
export type EndSessionRequest = z.infer<typeof EndSessionRequestSchema>;

// ===========================================================================
// DATA GOVERNANCE (GDPR Art 17 / POPIA s24)
// ===========================================================================

export const ErasureJurisdiction = {
  GDPR: 'GDPR',
  POPIA: 'POPIA',
  NDPA: 'NDPA', // Nigeria Data Protection Act 2023 (regulator: NDPC)
  OTHER: 'OTHER',
} as const;
export type ErasureJurisdiction =
  (typeof ErasureJurisdiction)[keyof typeof ErasureJurisdiction];
export const ErasureJurisdictionSchema = z.nativeEnum(ErasureJurisdiction);

export const ErasureBasis = {
  DATA_SUBJECT_REQUEST: 'DATA_SUBJECT_REQUEST',
  WITHDRAWN_CONSENT: 'WITHDRAWN_CONSENT',
  ACCOUNT_DELETION: 'ACCOUNT_DELETION',
  ADMIN_ACTION: 'ADMIN_ACTION',
} as const;
export type ErasureBasis = (typeof ErasureBasis)[keyof typeof ErasureBasis];
export const ErasureBasisSchema = z.nativeEnum(ErasureBasis);

export const ERASURE_BASIS_LABELS: Record<ErasureBasis, string> = {
  DATA_SUBJECT_REQUEST: 'Data subject request',
  WITHDRAWN_CONSENT: 'Withdrawn consent',
  ACCOUNT_DELETION: 'Account deletion',
  ADMIN_ACTION: 'Administrative action',
};

export const ErasureTargetType = {
  USER_ACCOUNT: 'USER_ACCOUNT',
  STUDY_SUBJECT: 'STUDY_SUBJECT',
  CALIBRATION_RECORD: 'CALIBRATION_RECORD',
} as const;
export type ErasureTargetType =
  (typeof ErasureTargetType)[keyof typeof ErasureTargetType];
export const ErasureTargetTypeSchema = z.nativeEnum(ErasureTargetType);

export const ErasureStatus = {
  PENDING: 'PENDING',
  AWAITING_APPROVAL: 'AWAITING_APPROVAL',
  COMPLETED: 'COMPLETED',
  REJECTED: 'REJECTED',
  FAILED: 'FAILED',
} as const;
export type ErasureStatus = (typeof ErasureStatus)[keyof typeof ErasureStatus];
export const ErasureStatusSchema = z.nativeEnum(ErasureStatus);

export const ERASURE_STATUS_LABELS: Record<ErasureStatus, string> = {
  PENDING: 'Pending',
  AWAITING_APPROVAL: 'Awaiting approval',
  COMPLETED: 'Completed',
  REJECTED: 'Rejected',
  FAILED: 'Failed',
};

export const EraseAccountRequestSchema = z.object({
  confirm_email: z.string().email(),
  jurisdiction: ErasureJurisdictionSchema.default(ErasureJurisdiction.GDPR),
  request_basis: ErasureBasisSchema.default(ErasureBasis.ACCOUNT_DELETION),
  notes: z.string().max(2000).nullable().optional(),
});
export type EraseAccountRequest = z.infer<typeof EraseAccountRequestSchema>;

export const AnonymiseSubjectRequestSchema = z.object({
  jurisdiction: ErasureJurisdictionSchema.default(ErasureJurisdiction.POPIA),
  request_basis: ErasureBasisSchema.default(ErasureBasis.WITHDRAWN_CONSENT),
  notes: z.string().max(2000).nullable().optional(),
});
export type AnonymiseSubjectRequest = z.infer<
  typeof AnonymiseSubjectRequestSchema
>;

export const ErasureRequestResponseSchema = z.object({
  id: z.string().uuid(),
  target_type: ErasureTargetTypeSchema,
  target_id: z.string().uuid(),
  jurisdiction: ErasureJurisdictionSchema,
  request_basis: ErasureBasisSchema,
  requested_at: z.string(),
  processed_at: z.string().nullable(),
  status: ErasureStatusSchema,
  statutory_retention_applied: z.boolean(),
  retention_basis: z.string().nullable(),
  notes: z.string().nullable(),
});
export type ErasureRequestResponse = z.infer<
  typeof ErasureRequestResponseSchema
>;

export const DataInventoryCountsSchema = z.object({
  triage_assessments: z.number().int().nonnegative(),
  toi_assessments: z.number().int().nonnegative(),
  calibration_records: z.number().int().nonnegative(),
  study_subjects: z.number().int().nonnegative(),
  study_sessions: z.number().int().nonnegative(),
  consent_records: z.number().int().nonnegative(),
  erasure_requests: z.number().int().nonnegative(),
});
export type DataInventoryCounts = z.infer<typeof DataInventoryCountsSchema>;

export const MyDataSummarySchema = z.object({
  user_id: z.string().uuid(),
  email: z.string().nullable(),
  full_name: z.string().nullable(),
  role: z.string(),
  is_active: z.boolean(),
  created_at: z.string(),
  erased_at: z.string().nullable(),
  counts: DataInventoryCountsSchema,
  retention_policy_summary: z.string(),
});
export type MyDataSummary = z.infer<typeof MyDataSummarySchema>;

// ===========================================================================
// NOTIFICATIONS
// ===========================================================================

export const NotificationType = {
  ERASURE_APPROVAL_REQUESTED: 'ERASURE_APPROVAL_REQUESTED',
  ERASURE_REQUEST_APPROVED: 'ERASURE_REQUEST_APPROVED',
  ERASURE_REQUEST_REJECTED: 'ERASURE_REQUEST_REJECTED',
  GENERIC: 'GENERIC',
} as const;
export type NotificationType =
  (typeof NotificationType)[keyof typeof NotificationType];
export const NotificationTypeSchema = z.nativeEnum(NotificationType);

export const NotificationResponseSchema = z.object({
  id: z.string().uuid(),
  type: NotificationTypeSchema,
  title: z.string(),
  body: z.string(),
  resource: z.string().nullable(),
  payload: z.record(z.string(), z.unknown()),
  read_at: z.string().nullable(),
  created_at: z.string(),
});
export type NotificationResponse = z.infer<typeof NotificationResponseSchema>;

export const NotificationListResponseSchema = z.object({
  notifications: z.array(NotificationResponseSchema),
  unread_count: z.number().int().nonnegative(),
});
export type NotificationListResponse = z.infer<
  typeof NotificationListResponseSchema
>;

export const UnreadCountResponseSchema = z.object({
  unread_count: z.number().int().nonnegative(),
});
export type UnreadCountResponse = z.infer<typeof UnreadCountResponseSchema>;

// ===========================================================================
// ADMIN GOVERNANCE
// ===========================================================================

export const AdminUserListItemSchema = z.object({
  id: z.string().uuid(),
  email: z.string().nullable(),
  full_name: z.string().nullable(),
  role: z.string(),
  is_active: z.boolean(),
  created_at: z.string(),
  erased_at: z.string().nullable(),
  subject_count: z.number().int().nonnegative(),
  calibration_count: z.number().int().nonnegative(),
});
export type AdminUserListItem = z.infer<typeof AdminUserListItemSchema>;

export const AdminUserListResponseSchema = z.object({
  users: z.array(AdminUserListItemSchema),
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});
export type AdminUserListResponse = z.infer<
  typeof AdminUserListResponseSchema
>;

export const AdminEraseAccountRequestSchema = z.object({
  confirm_user_id: z.string().uuid(),
  jurisdiction: ErasureJurisdictionSchema.default(ErasureJurisdiction.GDPR),
  request_basis: ErasureBasisSchema.default(ErasureBasis.ADMIN_ACTION),
  notes: z.string().max(2000).nullable().optional(),
});
export type AdminEraseAccountRequest = z.infer<
  typeof AdminEraseAccountRequestSchema
>;

export const AdminAnonymiseSubjectRequestSchema = z.object({
  jurisdiction: ErasureJurisdictionSchema.default(ErasureJurisdiction.POPIA),
  request_basis: ErasureBasisSchema.default(ErasureBasis.ADMIN_ACTION),
  notes: z.string().max(2000).nullable().optional(),
});
export type AdminAnonymiseSubjectRequest = z.infer<
  typeof AdminAnonymiseSubjectRequestSchema
>;

export const AdminUserDataSummarySchema = z.object({
  user_id: z.string().uuid(),
  email: z.string().nullable(),
  full_name: z.string().nullable(),
  role: z.string(),
  is_active: z.boolean(),
  created_at: z.string(),
  erased_at: z.string().nullable(),
  counts: DataInventoryCountsSchema,
});
export type AdminUserDataSummary = z.infer<
  typeof AdminUserDataSummarySchema
>;

export const AdminErasureRequestResponseSchema = z.object({
  id: z.string().uuid(),
  requesting_actor_user_id: z.string().uuid().nullable(),
  requesting_actor_email: z.string().nullable(),
  target_user_id: z.string().uuid().nullable(),
  target_user_email: z.string().nullable(),
  target_type: ErasureTargetTypeSchema,
  target_id: z.string().uuid(),
  jurisdiction: ErasureJurisdictionSchema,
  request_basis: ErasureBasisSchema,
  requested_at: z.string(),
  processed_at: z.string().nullable(),
  status: ErasureStatusSchema,
  statutory_retention_applied: z.boolean(),
  notes: z.string().nullable(),
  requires_approval: z.boolean(),
  approved_by_user_id: z.string().uuid().nullable(),
  approved_by_email: z.string().nullable(),
  approved_at: z.string().nullable(),
  rejected_by_user_id: z.string().uuid().nullable(),
  rejected_by_email: z.string().nullable(),
  rejected_at: z.string().nullable(),
  rejection_reason: z.string().nullable(),
});
export type AdminErasureRequestResponse = z.infer<
  typeof AdminErasureRequestResponseSchema
>;

export const AuditLogEntrySchema = z.object({
  id: z.string().uuid(),
  actor_id: z.string().uuid().nullable(),
  actor_email: z.string().nullable(),
  action: z.string(),
  resource: z.string().nullable(),
  ip_address: z.string().nullable(),
  metadata_json: z.record(z.string(), z.unknown()),
  created_at: z.string(),
});
export type AuditLogEntry = z.infer<typeof AuditLogEntrySchema>;

export const AuditLogResponseSchema = z.object({
  entries: z.array(AuditLogEntrySchema),
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});
export type AuditLogResponse = z.infer<typeof AuditLogResponseSchema>;

// ---- Research console: labelled triage capture (Model 1 training data) ----

export const CaptureDomain = {
  CLINICAL_GRADE: 'CLINICAL_GRADE',
  CHW_TAPE_MEASURE: 'CHW_TAPE_MEASURE',
} as const;
export type CaptureDomain = (typeof CaptureDomain)[keyof typeof CaptureDomain];
export const CaptureDomainSchema = z.nativeEnum(CaptureDomain);

/** A labelled case. Obesity/hypertension are derived from measured BMI/BP;
 *  diabetes from HbA1c / fasting glucose. Any label may be overridden. */
export const ResearchCaseCreateSchema = z.object({
  age_years: z.number().int().min(1).max(120),
  sex: SexSchema,
  height_cm: z.number().min(50).max(250),
  weight_kg: z.number().min(5).max(400),
  waist_cm: z.number().min(30).max(250),
  hip_cm: z.number().min(40).max(250).optional(),
  systolic_bp_mmhg: z.number().min(50).max(300).optional(),
  diastolic_bp_mmhg: z.number().min(30).max(200).optional(),
  safety_triggers: z.array(z.enum(SAFETY_OVERRIDE_SYMPTOM_KEYS)).default([]),
  contextual: z.array(z.enum(CONTEXTUAL_SYMPTOM_KEYS)).default([]),
  fasting_glucose_mmol_l: z.number().min(1).max(50).optional(),
  hba1c_percent: z.number().min(3).max(20).optional(),
  capture_domain: CaptureDomainSchema.default(CaptureDomain.CLINICAL_GRADE),
  study_subject_id: z.string().uuid().optional(),
  obesity_label: RiskClassSchema.optional(),
  hypertension_label: RiskClassSchema.optional(),
  diabetes_label: RiskClassSchema.optional(),
  notes: z.string().max(2000).optional(),
});
export type ResearchCaseCreate = z.infer<typeof ResearchCaseCreateSchema>;

export const ResearchCaseResponseSchema = z.object({
  id: z.string().uuid(),
  capture_domain: z.string(),
  age_years: z.number().int(),
  sex: z.string(),
  height_cm: z.number(),
  weight_kg: z.number(),
  waist_cm: z.number(),
  bmi: z.number(),
  whtr: z.number().nullable(),
  systolic_bp_mmhg: z.number().nullable(),
  diastolic_bp_mmhg: z.number().nullable(),
  hba1c_percent: z.number().nullable(),
  fasting_glucose_mmol_l: z.number().nullable(),
  obesity_label: RiskClassSchema,
  hypertension_label: RiskClassSchema,
  diabetes_label: RiskClassSchema,
  label_basis: z.record(z.string(), z.string()),
  study_subject_id: z.string().uuid().nullable(),
  created_at: z.string(),
});
export type ResearchCaseResponse = z.infer<typeof ResearchCaseResponseSchema>;

export const ResearchCorpusStatsSchema = z.object({
  total: z.number().int().nonnegative(),
  by_domain: z.record(z.string(), z.number()),
  by_site: z.record(z.string(), z.number()),
  label_distribution: z.object({
    obesity: z.record(z.string(), z.number()),
    hypertension: z.record(z.string(), z.number()),
    diabetes: z.record(z.string(), z.number()),
  }),
  with_bp: z.number().int().nonnegative(),
  with_diabetes_marker: z.number().int().nonnegative(),
});
export type ResearchCorpusStats = z.infer<typeof ResearchCorpusStatsSchema>;

// ===========================================================================
// CLINICIAN PARTICIPANT REVIEW
// ===========================================================================

export const ParticipantSummarySchema = z.object({
  user_id: z.string().uuid(),
  email: z.string().nullable(),
  full_name: z.string().nullable(),
  role: z.string(),
  is_active: z.boolean(),
  site_code: z.string(),
  triage_count: z.number().int().nonnegative(),
  toi_count: z.number().int().nonnegative(),
  last_activity: z.string().nullable(),
});
export type ParticipantSummary = z.infer<typeof ParticipantSummarySchema>;

export const ParticipantHistorySchema = z.object({
  participant: ParticipantSummarySchema,
  triage: z.array(TriageAssessmentResponseSchema),
  toi: z.array(ToiAssessmentResponseSchema),
});
export type ParticipantHistory = z.infer<typeof ParticipantHistorySchema>;

// ===========================================================================
// CARE-NAVIGATION REFERRALS
// ===========================================================================

export const ReferralUrgency = {
  ROUTINE: 'ROUTINE',
  URGENT: 'URGENT',
  EMERGENCY: 'EMERGENCY',
} as const;
export type ReferralUrgency = (typeof ReferralUrgency)[keyof typeof ReferralUrgency];

export const ReferralStatus = {
  PENDING: 'PENDING',
  ACKNOWLEDGED: 'ACKNOWLEDGED',
  COMPLETED: 'COMPLETED',
  CANCELLED: 'CANCELLED',
} as const;
export type ReferralStatus = (typeof ReferralStatus)[keyof typeof ReferralStatus];

export const ReferralDestinationType = {
  VICTUS_FACILITY: 'VICTUS_FACILITY',
  PUBLIC_CLINIC: 'PUBLIC_CLINIC',
  HOSPITAL: 'HOSPITAL',
  OTHER: 'OTHER',
} as const;
export type ReferralDestinationType =
  (typeof ReferralDestinationType)[keyof typeof ReferralDestinationType];

export const REFERRAL_DESTINATION_LABELS: Record<ReferralDestinationType, string> = {
  VICTUS_FACILITY: 'Victus facility',
  PUBLIC_CLINIC: 'Public clinic',
  HOSPITAL: 'Hospital',
  OTHER: 'Other',
};

export const CreateReferralSchema = z.object({
  participant_user_id: z.string().uuid(),
  destination_type: z.nativeEnum(ReferralDestinationType),
  destination_name: z.string().min(1).max(200),
  reason: z.string().min(1).max(1000),
  urgency: z.nativeEnum(ReferralUrgency),
  source_triage_assessment_id: z.string().uuid().optional().nullable(),
  notes: z.string().max(1000).optional().nullable(),
});
export type CreateReferral = z.infer<typeof CreateReferralSchema>;

export const UpdateReferralStatusSchema = z.object({
  status: z.nativeEnum(ReferralStatus),
  notes: z.string().max(1000).optional().nullable(),
});
export type UpdateReferralStatus = z.infer<typeof UpdateReferralStatusSchema>;

export const ReferralResponseSchema = z.object({
  id: z.string().uuid(),
  participant_user_id: z.string().uuid(),
  created_by_user_id: z.string().uuid().nullable(),
  source_triage_assessment_id: z.string().uuid().nullable(),
  destination_type: z.string(),
  destination_name: z.string(),
  reason: z.string(),
  urgency: z.string(),
  status: z.string(),
  notes: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type ReferralResponse = z.infer<typeof ReferralResponseSchema>;
