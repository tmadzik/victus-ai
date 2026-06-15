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

# Severely obese with an unambiguously NORMAL blood pressure — exercises
# independent per-disease weighting (obesity must be elevated while
# hypertension stays no worse than obesity).
OBESE_NORMAL_BP_INPUTS: dict[str, Any] = {
    "height_cm": 170.0,
    "weight_kg": 112.0,
    "waist_cm": 120.0,
    "hip_cm": 120.0,
    "age_years": 50,
    "sex": "MALE",
    "systolic_bp_mmhg": 116.0,
    "diastolic_bp_mmhg": 74.0,
}

_DISEASES = ("OBESITY", "HYPERTENSION", "DIABETES")
_STATE_SEVERITY = {"GREEN": 0, "YELLOW": 1, "RED": 2}


def _by_disease(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["disease"]: entry for entry in result["per_disease"]}


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
    assert result["overall_state"] in {"GREEN", "YELLOW", "RED"}

    # Every disease is weighted independently — one entry per NCD, each a
    # well-formed Dirichlet with its own uncertainty decomposition and state.
    by_disease = _by_disease(result)
    assert set(by_disease) == set(_DISEASES)
    for disease, entry in by_disease.items():
        assert entry["state"] in {"GREEN", "YELLOW", "RED"}, disease
        probs = entry["class_probabilities"]
        assert abs(sum(probs.values()) - 1.0) < 1e-3, f"{disease} mean must be a distribution"
        unc = entry["uncertainty"]
        assert 0.0 <= unc["vacuity"] <= 1.0
        assert unc["epistemic"] >= 0.0 and unc["aleatoric"] >= 0.0

    # The overall state is exactly the worst of the per-disease states.
    worst = max(_STATE_SEVERITY[e["state"]] for e in result["per_disease"])
    assert _STATE_SEVERITY[result["overall_state"]] == worst


@pytest.mark.usefixtures("require_triage_model")
def test_per_disease_independent_weighting(client: Any, patient: dict[str, Any]) -> None:
    """A severely obese subject with a normal cuff reading must NOT let obesity
    drag hypertension up — the diseases are scored independently."""
    result = _assess(client, patient["headers"], OBESE_NORMAL_BP_INPUTS, [])
    by_disease = _by_disease(result)

    obesity = by_disease["OBESITY"]
    hypertension = by_disease["HYPERTENSION"]

    # Obesity is clearly elevated from BMI ~38.8 / WHtR ~0.71.
    assert obesity["top_class"] in {"HIGH_RISK", "VERY_HIGH_RISK"}
    assert obesity["state"] in {"YELLOW", "RED"}
    # The adiposity signal must NOT bleed into hypertension: with a normal cuff
    # reading, hypertension is never escalated to RED and stays no worse than
    # the obesity head.
    assert hypertension["state"] != "RED"
    assert (
        _STATE_SEVERITY[hypertension["state"]] <= _STATE_SEVERITY[obesity["state"]]
    )
    # The overall state tracks the worst disease (obesity or the diabetes proxy).
    worst = max(_STATE_SEVERITY[e["state"]] for e in result["per_disease"])
    assert _STATE_SEVERITY[result["overall_state"]] == worst


def test_safety_override_forces_red(client: Any, patient: dict[str, Any]) -> None:
    """A red-flag symptom forces overall RED and routes the implicated disease
    to RED — deterministic, so it holds even without the EDL checkpoint."""
    result = _assess(client, patient["headers"], NORMAL_INPUTS, ["chest_pain_radiating"])

    assert result["safety_override_triggered"] is True
    assert result["overall_state"] == "RED"
    assert "chest_pain_radiating" in result["override_reasons"]

    # chest_pain_radiating is routed to HYPERTENSION → that disease is RED with
    # the red-flag surfaced as a contributing factor.
    hypertension = _by_disease(result)["HYPERTENSION"]
    assert hypertension["state"] == "RED"
    assert any("chest pain" in f.lower() for f in hypertension["contributing_factors"])


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


def test_consent_regrant_after_revoke(client: Any) -> None:
    """Re-granting a previously-revoked consent must reactivate the record, not
    fail on the (user, consent_type, version) unique constraint."""
    user = register(client, "PATIENT")
    headers = user["headers"]

    def current() -> list[str]:
        r = client.get("/users/me", headers=headers)
        assert r.status_code == 200, r.text
        return r.json()["consents"]

    g = client.patch("/users/me/consents", headers=headers,
                     json={"grants": ["TRIAGE"], "revokes": []})
    assert g.status_code == 200, g.text
    assert "TRIAGE" in current()

    rv = client.patch("/users/me/consents", headers=headers,
                      json={"grants": [], "revokes": ["TRIAGE"]})
    assert rv.status_code == 200, rv.text
    assert "TRIAGE" not in current()

    # Previously raised "A database constraint was violated."
    rg = client.patch("/users/me/consents", headers=headers,
                      json={"grants": ["TRIAGE"], "revokes": []})
    assert rg.status_code == 200, rg.text
    assert "TRIAGE" in current()
