"""Pathway A (NCD triage) integration tests against real Postgres.

Covers: registration, login, JWT refresh rotation, the evidential (EDL) risk
assessment, the deterministic clinical-safety override that short-circuits to
RED, input-plausibility flagging, and assessment history persistence.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration._helpers import PASSWORD, grant_consent, register

pytestmark = pytest.mark.integration

NORMAL_INPUTS: dict[str, Any] = {
    "height_cm": 170.0,
    "weight_kg": 72.0,
    "waist_cm": 84.0,
    "hip_cm": 98.0,
    "age_years": 41,
    "sex": "MALE",
    "systolic_bp_mmhg": 128.0,
    "diastolic_bp_mmhg": 82.0,
}

IMPLAUSIBLE_INPUTS: dict[str, Any] = {
    "height_cm": 150.0,
    "weight_kg": 200.0,
    "waist_cm": 200.0,  # waist > height
    "hip_cm": 60.0,
    "age_years": 30,
    "sex": "FEMALE",
    "systolic_bp_mmhg": 100.0,
    "diastolic_bp_mmhg": 95.0,
}


@pytest.fixture
def patient(client: Any) -> dict[str, Any]:
    user = register(client, "PATIENT")
    grant_consent(client, user["headers"], "TRIAGE")
    return user


def _assess(
    client: Any, headers: dict[str, str], inputs: dict[str, Any], triggers: list[str]
) -> dict[str, Any]:
    resp = client.post(
        "/pathways/triage/assess",
        headers=headers,
        json={"inputs": inputs, "symptoms": {"safety_triggers": triggers, "contextual": []}},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_register_login_refresh_rotation(client: Any) -> None:
    user = register(client, "PATIENT")

    login = client.post("/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert login.status_code == 200, login.text
    tokens = login.json()["tokens"]
    assert tokens["access_token"] and tokens["refresh_token"]

    refreshed = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    rotated = refreshed.json()["tokens"]
    assert rotated["access_token"] != tokens["access_token"], "access token must rotate"

    me = client.get("/users/me", headers={"Authorization": f"Bearer {rotated['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == user["email"]


def test_triage_requires_consent(client: Any) -> None:
    """Without TRIAGE consent the assessment must be refused, not silently run."""
    user = register(client, "PATIENT")
    resp = client.post(
        "/pathways/triage/assess",
        headers=user["headers"],
        json={"inputs": NORMAL_INPUTS, "symptoms": {"safety_triggers": [], "contextual": []}},
    )
    assert resp.status_code in (403, 409), resp.text


@pytest.mark.usefixtures("require_triage_model")
def test_edl_normal_assessment(client: Any, patient: dict[str, Any]) -> None:
    result = _assess(client, patient["headers"], NORMAL_INPUTS, [])

    assert result["safety_override_triggered"] is False
    assert result["state"] in {"GREEN", "YELLOW", "RED"}

    probs = result["class_probabilities"]
    assert abs(sum(probs.values()) - 1.0) < 1e-3, "Dirichlet mean must be a distribution"

    unc = result["uncertainty"]
    assert 0.0 <= unc["vacuity"] <= 1.0
    assert unc["epistemic"] >= 0.0 and unc["aleatoric"] >= 0.0


def test_safety_override_forces_red(client: Any, patient: dict[str, Any]) -> None:
    """A red-flag symptom short-circuits to RED before the model is consulted —
    so this holds even without the EDL checkpoint present."""
    result = _assess(client, patient["headers"], NORMAL_INPUTS, ["chest_pain_radiating"])

    assert result["safety_override_triggered"] is True
    assert result["state"] == "RED"
    assert "chest_pain_radiating" in result["override_reasons"]


@pytest.mark.usefixtures("require_triage_model")
def test_implausible_inputs_are_flagged(client: Any, patient: dict[str, Any]) -> None:
    result = _assess(client, patient["headers"], IMPLAUSIBLE_INPUTS, [])
    flags = result["plausibility_flags"]
    assert len(flags) > 0
    assert "WAIST_GT_HEIGHT" in flags


@pytest.mark.usefixtures("require_triage_model")
def test_history_records_assessments(client: Any, patient: dict[str, Any]) -> None:
    _assess(client, patient["headers"], NORMAL_INPUTS, [])
    _assess(client, patient["headers"], NORMAL_INPUTS, ["chest_pain_radiating"])

    resp = client.get("/pathways/triage/assessments/me", headers=patient["headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("items") or body.get("assessments")
    assert items is not None and len(items) >= 2
