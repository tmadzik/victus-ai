"""Enrollment credential hashing.

The external patient/client identifier is never persisted in the clear — only a
salted one-way SHA-256 of ``{raw}:{pseudo_salt}``. Re-identification therefore
requires the source system that issued the id, not a read of our database.
"""

from __future__ import annotations

import hashlib

# Consent version stamped on every enrollment-time ConsentRecord.
CONSENT_VERSION = "enroll-v1"


def hash_patient_id(raw: str, *, salt: str) -> str:
    """Full SHA-256 hex of the external patient id, salted per deployment."""
    return hashlib.sha256(f"{raw.strip()}:{salt}".encode()).hexdigest()
