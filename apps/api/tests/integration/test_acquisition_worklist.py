"""Integration: the active-learning worklist ranks real triage assessments and
is role-gated to researchers."""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration._helpers import grant_consent, register

pytestmark = pytest.mark.integration

_INPUTS = {
    "inputs": {
        "height_cm": 170,
        "weight_kg": 92,
        "waist_cm": 104,
        "hip_cm": 100,
        "age_years": 54,
        "sex": "MALE",
        "systolic_bp_mmhg": 148,
        "diastolic_bp_mmhg": 94,
    },
    "symptoms": {"safety_triggers": [], "contextual": []},
}


def _make_assessment(client: Any) -> str:
    patient = register(client, "PATIENT")
    grant_consent(client, patient["headers"], "TRIAGE")
    r = client.post(
        "/pathways/triage/assess", headers=patient["headers"], json=_INPUTS
    )
    assert r.status_code == 200, r.text
    return patient["id"]


def test_worklist_ranks_assessment_and_targets_the_lab_head(client: Any) -> None:
    patient_id = _make_assessment(client)
    researcher = register(client, "CLINICIAN")

    r = client.get(
        "/research/acquisition-worklist", headers=researcher["headers"]
    )
    assert r.status_code == 200, r.text
    items = r.json()
    mine = [i for i in items if i["user_id"] == patient_id]
    assert mine, "the participant's assessment should be on the worklist"
    item = mine[0]
    # Acquisition targets the lab-confirmed (diabetes) head.
    assert item["driving_disease"] == "DIABETES"
    assert "HbA1c" in item["confirmatory_test"]
    assert item["priority"] in {"HIGH", "MEDIUM", "LOW"}
    assert 0.0 <= item["acquisition_score"] <= 1.0
    assert item["rationale"]


def test_worklist_is_ranked_descending_by_score(client: Any) -> None:
    for _ in range(3):
        _make_assessment(client)
    researcher = register(client, "CLINICIAN")
    r = client.get(
        "/research/acquisition-worklist", headers=researcher["headers"]
    )
    assert r.status_code == 200, r.text
    scores = [i["acquisition_score"] for i in r.json()]
    assert scores == sorted(scores, reverse=True)


def test_patient_cannot_access_worklist(client: Any) -> None:
    patient = register(client, "PATIENT")
    r = client.get("/research/acquisition-worklist", headers=patient["headers"])
    assert r.status_code == 403, r.text
