"""Integration: the care-loop analytics funnel + flywheel corpus growth."""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration._helpers import grant_consent, register

pytestmark = pytest.mark.integration

_STATS = "/referrals/analytics/care-loop"


def _stats(client: Any, clinician: dict) -> dict:
    r = client.get(_STATS, headers=clinician["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def test_care_loop_funnel_reflects_a_confirmed_outcome(client: Any) -> None:
    patient = register(client, "PATIENT")
    grant_consent(client, patient["headers"], "TRIAGE")
    grant_consent(client, patient["headers"], "DATA_SHARING_RESEARCH")
    body = {
        "inputs": {
            "height_cm": 168,
            "weight_kg": 94,
            "waist_cm": 106,
            "age_years": 60,
            "sex": "FEMALE",
            "systolic_bp_mmhg": 154,
            "diastolic_bp_mmhg": 98,
        },
        "symptoms": {"safety_triggers": [], "contextual": []},
    }
    a = client.post("/pathways/triage/assess", headers=patient["headers"], json=body)
    assert a.status_code == 200, a.text
    assessment_id = a.json()["id"]

    clinician = register(client, "CLINICIAN")
    before = _stats(client, clinician)

    ref = client.post(
        "/referrals",
        headers=clinician["headers"],
        json={
            "participant_user_id": patient["id"],
            "destination_type": "HOSPITAL",
            "destination_name": "Kano Teaching Hospital",
            "reason": "RED diabetes — confirm.",
            "urgency": "URGENT",
            "source_triage_assessment_id": assessment_id,
        },
    ).json()

    client.patch(
        f"/referrals/{ref['id']}/outcome",
        headers=clinician["headers"],
        json={"outcome": "ATTENDED_CONFIRMED", "confirmed_hba1c_percent": 7.9},
    )

    after = _stats(client, clinician)

    # The funnel moved by exactly our one referral + confirmed outcome.
    assert after["referrals_total"] == before["referrals_total"] + 1
    assert after["with_source_assessment"] == before["with_source_assessment"] + 1
    assert after["outcomes_recorded"] == before["outcomes_recorded"] + 1
    assert after["confirmed"] == before["confirmed"] + 1
    # And the flywheel produced a labelled training case.
    assert after["research_cases_seeded"] == before["research_cases_seeded"] + 1

    for rate in ("closure_rate", "attendance_rate", "confirmation_rate"):
        assert 0.0 <= after[rate] <= 1.0
    assert set(after["by_status"]) >= {"PENDING", "COMPLETED", "CANCELLED"}
    assert "ATTENDED_CONFIRMED" in after["by_outcome"]


def test_patient_cannot_read_care_loop_analytics(client: Any) -> None:
    patient = register(client, "PATIENT")
    r = client.get(_STATS, headers=patient["headers"])
    assert r.status_code == 403, r.text
