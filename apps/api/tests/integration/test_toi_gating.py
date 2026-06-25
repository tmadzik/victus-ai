"""Integration: experimental TOI biomarkers are gated out of API responses."""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration._helpers import assess_toi, grant_consent, register

pytestmark = pytest.mark.integration


def test_experimental_biomarkers_gated_by_default(client: Any) -> None:
    user = register(client, "CLINICIAN")
    grant_consent(client, user["headers"], "TOI_IMAGING")
    client.post("/pathways/toi/enter", headers=user["headers"], json={})

    toi = assess_toi(client, user["headers"], hr_bpm=66.0)
    biomarkers = toi["biomarkers"]

    # Validated outputs still flow through.
    assert "heart_rate" in biomarkers
    # Experimental ones are withheld by default.
    assert "hrv_rmssd" not in biomarkers
    assert "hrv_sdnn" not in biomarkers
    assert "stress_index" not in biomarkers
    # Nothing surfaced is flagged experimental.
    assert all(v.get("experimental") is False for v in biomarkers.values())
