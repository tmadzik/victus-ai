"""Study pre-registration: anonymous subjects + locked-context sessions.

Every calibration capture auto-attaches to the researcher's active session
so cohort covariates (posture, ambient lux, caffeine status, …) are pinned
in lockstep with the agreement statistics. Per Bland & Altman 1999 §5.2,
repeated-measures study designs need per-subject tracking to compute
within-subject vs between-subject agreement components; the subject FK is
the gateway to that analysis (deferred to a future milestone).
"""

STUDY_PROTOCOL_VERSION = "VICTUS-CALIB-V1"
CONSENT_PROTOCOL_VERSION = "VICTUS-IRB-CONSENT-V1"
