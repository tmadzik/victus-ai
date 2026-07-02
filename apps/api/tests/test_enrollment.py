"""Unit tests for enrollment hashing + request validation (no DB, no HTTP)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from victus_api.db.models import SexAtBirth
from victus_api.enrollment.schemas import AgeRange, EnrollmentRequest, Region
from victus_api.enrollment.security import hash_patient_id


def _valid(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "full_name": "Ada Lovelace",
        "email": "ada@example.com",
        "patient_id": "MRN-001",
        "age_range": AgeRange.A30_39,
        "biological_sex": SexAtBirth.FEMALE,
        "region": Region.NG,
        "consent_triage": True,
        "consent_toi_imaging": True,
    }
    base.update(overrides)
    return base


# --- patient-id hashing ------------------------------------------------------


def test_hash_is_deterministic_and_full_length() -> None:
    h1 = hash_patient_id("MRN-001", salt="s")
    h2 = hash_patient_id("MRN-001", salt="s")
    assert h1 == h2
    assert len(h1) == 64 and all(c in "0123456789abcdef" for c in h1)
    # The hash never equals (or contains) the raw id.
    assert "MRN-001" not in h1


def test_hash_varies_by_salt_and_input() -> None:
    assert hash_patient_id("MRN-001", salt="a") != hash_patient_id("MRN-001", salt="b")
    assert hash_patient_id("MRN-001", salt="s") != hash_patient_id("MRN-002", salt="s")


def test_hash_trims_whitespace() -> None:
    assert hash_patient_id("  MRN-001 ", salt="s") == hash_patient_id("MRN-001", salt="s")


# --- request validation ------------------------------------------------------


def test_valid_request_parses() -> None:
    req = EnrollmentRequest(**_valid())
    assert req.consent_research is False  # defaulted
    assert req.race_ethnicity is None


def test_both_pathway_consents_required() -> None:
    with pytest.raises(ValidationError, match="both"):
        EnrollmentRequest(**_valid(consent_toi_imaging=False))
    with pytest.raises(ValidationError, match="both"):
        EnrollmentRequest(**_valid(consent_triage=False))


def test_age_range_is_adults_only() -> None:
    # There is no under-18 band, so an under-age value cannot be expressed.
    assert "10-17" not in {r.value for r in AgeRange}
    with pytest.raises(ValidationError):
        EnrollmentRequest(**_valid(age_range="10-17"))


def test_email_must_be_valid() -> None:
    with pytest.raises(ValidationError):
        EnrollmentRequest(**_valid(email="not-an-email"))
