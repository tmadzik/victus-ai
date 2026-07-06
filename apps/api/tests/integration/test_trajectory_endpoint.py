"""Integration: the longitudinal trajectory endpoint aggregates a participant's
assessments and is role-gated."""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration._helpers import grant_consent, register

pytestmark = pytest.mark.integration

_A = {
    "inputs": {
        "height_cm": 175,
        "weight_kg": 68,
        "waist_cm": 82,
        "age_years": 30,
        "sex": "MALE",
        "systolic_bp_mmhg": 118,
        "diastolic_bp_mmhg": 76,
    },
    "symptoms": {"safety_triggers": [], "contextual": []},
}
_B = {
    "inputs": {
        "height_cm": 170,
        "weight_kg": 95,
        "waist_cm": 108,
        "age_years": 58,
        "sex": "MALE",
        "systolic_bp_mmhg": 152,
        "diastolic_bp_mmhg": 96,
    },
    "symptoms": {"safety_triggers": [], "contextual": []},
}

_DIRECTIONS = {"RISING", "STABLE", "FALLING"}


def _patient_with_two(client: Any) -> dict[str, Any]:
    patient = register(client, "PATIENT")
    grant_consent(client, patient["headers"], "TRIAGE")
    for body in (_A, _B):
        r = client.post(
            "/pathways/triage/assess", headers=patient["headers"], json=body
        )
        assert r.status_code == 200, r.text
    return patient


def test_my_trajectory_aggregates_assessments(client: Any) -> None:
    patient = _patient_with_two(client)
    r = client.get(
        "/pathways/triage/trajectory/me", headers=patient["headers"]
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == patient["id"]
    assert "claims_mode" in body
    diseases = {t["disease"] for t in body["trajectories"]}
    assert {"OBESITY", "HYPERTENSION", "DIABETES"} <= diseases

    for t in body["trajectories"]:
        assert len(t["points"]) == 2  # both assessments trended
        assert t["direction"] in _DIRECTIONS
        assert isinstance(t["change_is_significant"], bool)
        assert 0.0 <= t["latest_index"] <= 1.0


def test_clinician_can_read_participant_trajectory(client: Any) -> None:
    patient = _patient_with_two(client)
    clinician = register(client, "CLINICIAN")
    r = client.get(
        f"/pathways/triage/trajectory/participant/{patient['id']}",
        headers=clinician["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == patient["id"]


def test_patient_cannot_read_others_trajectory(client: Any) -> None:
    patient = register(client, "PATIENT")
    grant_consent(client, patient["headers"], "TRIAGE")
    r = client.get(
        f"/pathways/triage/trajectory/participant/{patient['id']}",
        headers=patient["headers"],
    )
    assert r.status_code == 403, r.text
