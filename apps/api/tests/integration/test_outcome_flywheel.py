"""Integration: the care-loop flywheel — a confirmed referral outcome with
facility glycaemia seeds a labelled research case, gated on research consent."""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration._helpers import grant_consent, register

pytestmark = pytest.mark.integration


def _assess_with_bp(client: Any, headers: dict[str, str]) -> str:
    body = {
        "inputs": {
            "height_cm": 170,
            "weight_kg": 96,
            "waist_cm": 108,
            "hip_cm": 104,
            "age_years": 57,
            "sex": "MALE",
            "systolic_bp_mmhg": 150,
            "diastolic_bp_mmhg": 96,
        },
        "symptoms": {"safety_triggers": [], "contextual": []},
    }
    r = client.post("/pathways/triage/assess", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _referral(client: Any, clinician: dict, participant_id: str, assessment_id: str) -> dict:
    r = client.post(
        "/referrals",
        headers=clinician["headers"],
        json={
            "participant_user_id": participant_id,
            "destination_type": "HOSPITAL",
            "destination_name": "Lagos General",
            "reason": "RED diabetes flag — confirm with HbA1c.",
            "urgency": "URGENT",
            "source_triage_assessment_id": assessment_id,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _find_case_by_hba1c(client: Any, clinician: dict, hba1c: float) -> dict | None:
    r = client.get("/research/triage-cases?limit=200", headers=clinician["headers"])
    assert r.status_code == 200, r.text
    for c in r.json():
        if c["hba1c_percent"] is not None and abs(c["hba1c_percent"] - hba1c) < 0.01:
            return c
    return None


def test_confirmed_outcome_with_consent_seeds_a_labelled_case(client: Any) -> None:
    patient = register(client, "PATIENT")
    grant_consent(client, patient["headers"], "TRIAGE")
    grant_consent(client, patient["headers"], "DATA_SHARING_RESEARCH")
    assessment_id = _assess_with_bp(client, patient["headers"])

    clinician = register(client, "CLINICIAN")
    ref = _referral(client, clinician, patient["id"], assessment_id)

    upd = client.patch(
        f"/referrals/{ref['id']}/outcome",
        headers=clinician["headers"],
        json={"outcome": "ATTENDED_CONFIRMED", "confirmed_hba1c_percent": 7.4},
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["outcome_hba1c_percent"] == 7.4

    case = _find_case_by_hba1c(client, clinician, 7.4)
    assert case is not None, "a research case should have been seeded"
    # HbA1c 7.4% → diabetes (ADA ≥ 6.5%). This is the confirmed ground truth the
    # non-invasive model never had.
    assert case["diabetes_label"] == "HIGH_RISK"
    # Obesity/hypertension were derived deterministically from the assessment.
    assert case["hypertension_label"] in {"HIGH_RISK", "VERY_HIGH_RISK"}


def test_without_research_consent_no_case_is_seeded(client: Any) -> None:
    patient = register(client, "PATIENT")
    grant_consent(client, patient["headers"], "TRIAGE")  # NOT research consent
    assessment_id = _assess_with_bp(client, patient["headers"])

    clinician = register(client, "CLINICIAN")
    ref = _referral(client, clinician, patient["id"], assessment_id)

    upd = client.patch(
        f"/referrals/{ref['id']}/outcome",
        headers=clinician["headers"],
        json={"outcome": "ATTENDED_CONFIRMED", "confirmed_hba1c_percent": 8.1},
    )
    assert upd.status_code == 200, upd.text
    # 8.1 is unique to this test — no case should carry it without consent.
    assert _find_case_by_hba1c(client, clinician, 8.1) is None


def test_outcome_without_glycaemia_does_not_seed(client: Any) -> None:
    patient = register(client, "PATIENT")
    grant_consent(client, patient["headers"], "TRIAGE")
    grant_consent(client, patient["headers"], "DATA_SHARING_RESEARCH")
    assessment_id = _assess_with_bp(client, patient["headers"])

    clinician = register(client, "CLINICIAN")
    ref = _referral(client, clinician, patient["id"], assessment_id)

    # Attended + consent, but no facility glycaemia → nothing to label diabetes.
    upd = client.patch(
        f"/referrals/{ref['id']}/outcome",
        headers=clinician["headers"],
        json={"outcome": "ATTENDED_INCONCLUSIVE"},
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["outcome_hba1c_percent"] is None
