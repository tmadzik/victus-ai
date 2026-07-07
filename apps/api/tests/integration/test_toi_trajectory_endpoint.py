"""Integration: the contactless (TOI) vital-sign trajectory endpoints — content
from repeated captures and clinician/admin role gating on the participant view."""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration._helpers import assess_toi, grant_consent, register

pytestmark = pytest.mark.integration


def test_my_trajectory_trends_repeated_captures(client: Any) -> None:
    user = register(client, "CLINICIAN")
    grant_consent(client, user["headers"], "TOI_IMAGING")

    assess_toi(client, user["headers"], hr_bpm=62.0)
    assess_toi(client, user["headers"], hr_bpm=96.0)

    resp = client.get("/pathways/toi/trajectory/me", headers=user["headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()

    hr = next(
        (t for t in body["trajectories"] if t["biomarker"] == "heart_rate"), None
    )
    assert hr is not None
    assert hr["unit"] == "bpm"
    assert len(hr["points"]) == 2
    # The recovered rate rose markedly across the two captures.
    assert hr["latest_value"] > hr["baseline_value"]
    assert hr["direction"] == "RISING"
    assert hr["change_is_significant"] is True
    # Research-demonstrator by default: not presented as an authorised trend.
    assert body["clinical_claims_authorised"] is False


def test_participant_trajectory_is_clinician_only(client: Any) -> None:
    participant = register(client, "PATIENT")
    grant_consent(client, participant["headers"], "TOI_IMAGING")
    assess_toi(client, participant["headers"], hr_bpm=66.0)

    clinician = register(client, "CLINICIAN")

    # A clinician may read a participant's trajectory.
    ok = client.get(
        f"/pathways/toi/trajectory/participant/{participant['id']}",
        headers=clinician["headers"],
    )
    assert ok.status_code == 200, ok.text

    # A participant may not read someone else's (role gate).
    forbidden = client.get(
        f"/pathways/toi/trajectory/participant/{clinician['id']}",
        headers=participant["headers"],
    )
    assert forbidden.status_code == 403, forbidden.text
