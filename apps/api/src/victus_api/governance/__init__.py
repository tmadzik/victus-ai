"""GDPR Article 17 / POPIA section 24 erasure flow.

Pseudonymisation, not deletion, is the operating principle. Per GDPR
Recital 26, data anonymised such that the natural person is no longer
identifiable falls outside the personal-data regime entirely — so we
preserve the de-identified biometric record (assessments, calibration
pairs, sessions) while tombstoning PII fields on the user and rotating
study-subject identifiers via a salted SHA-256.

Article 17(3)(d) and POPIA section 14(3) carve out research retention
where appropriate technical safeguards exist; the audit ledger
(``erasure_requests``) is the regulator's evidence that those safeguards
were applied.
"""

GOVERNANCE_VERSION = "1.0.0"
TOMBSTONE_EMAIL_DOMAIN = "victus.invalid"
TOMBSTONE_NAME = "[ERASED]"
ANONYMISED_SUBJECT_PREFIX = "SUBJ-ANON-"
