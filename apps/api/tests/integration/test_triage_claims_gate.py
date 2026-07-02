"""Integration: the clinical-claims gate is enforced on the live triage endpoint.

The test environment sets no clinical-claims config, so the deployment defaults
to RESEARCH_DEMONSTRATOR — the assessment must come back explicitly un-authorised
for clinical use, with de-claimed actions and the research disclaimer.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration._helpers import grant_consent, register
from victus_api.core.claims import RESEARCH_NEXT_ACTION, RESEARCH_PER_DISEASE_ACTION

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


def test_triage_defaults_to_research_demonstrator(client: Any) -> None:
    patient = register(client, "PATIENT")
    grant_consent(client, patient["headers"], "TRIAGE")

    r = client.post(
        "/pathways/triage/assess", headers=patient["headers"], json=_INPUTS
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # The gate is closed by default → not authorised for clinical use.
    assert body["claims_mode"] == "RESEARCH_DEMONSTRATOR"
    assert body["clinical_claims_authorised"] is False
    assert "Research demonstrator" in body["disclaimer"]

    # The model still runs (states are present for the demonstrator) but the
    # actionable directives are de-claimed so nothing reads as clinical advice.
    assert body["next_action"] == RESEARCH_NEXT_ACTION
    assert body["per_disease"], "per-disease output should still be present"
    assert all(
        d["next_action"] == RESEARCH_PER_DISEASE_ACTION for d in body["per_disease"]
    )
