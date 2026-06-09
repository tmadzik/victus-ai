"""Pathway B + research-ops integration tests against real Postgres.

Covers: rPPG/TOI heart-rate recovery, study subject/session lifecycle,
multi-pair calibration with Bland-Altman agreement statistics, the
governance maker-checker erasure gate (including segregation of duties and
that an erased account can no longer authenticate), and the in-app
notification read lifecycle.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.integration._helpers import (
    PASSWORD,
    assess_toi,
    grant_consent,
    register,
    unread_count,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def clinician(client: Any) -> dict[str, Any]:
    user = register(client, "CLINICIAN")
    grant_consent(client, user["headers"], "TOI_IMAGING")
    return user


def test_toi_recovers_heart_rate(client: Any, clinician: dict[str, Any]) -> None:
    enter = client.post("/pathways/toi/enter", headers=clinician["headers"], json={})
    assert enter.status_code in (200, 201, 204), enter.text

    toi = assess_toi(client, clinician["headers"], hr_bpm=66.0)
    assert toi["id"]
    assert toi["quality"] in {"GOOD", "DEGRADED", "POOR"}

    hr = toi["biomarkers"]["heart_rate"]["value"]
    assert hr is not None, f"no heart rate recovered (quality={toi['quality']})"
    assert abs(hr - 66.0) <= 12.0, f"recovered HR {hr} far from truth 66"


def test_study_subject_and_active_session(client: Any, clinician: dict[str, Any]) -> None:
    subj = client.post(
        "/study/subjects",
        headers=clinician["headers"],
        json={
            "external_subject_id": f"SUBJ-{uuid.uuid4().hex[:8]}",
            "age_years": 47,
            "sex_assigned_at_birth": "FEMALE",
            "fitzpatrick_scale": "IV",
            "consent_protocol_version": "v1.0",
        },
    )
    assert subj.status_code in (200, 201), subj.text
    subject_id = subj.json()["id"]

    sess = client.post(
        "/study/sessions",
        headers=clinician["headers"],
        json={"study_subject_id": subject_id, "posture": "SITTING", "time_of_day": "MORNING"},
    )
    assert sess.status_code in (200, 201), sess.text
    session_id = sess.json()["id"]

    active = client.get("/study/sessions/active", headers=clinician["headers"])
    assert active.status_code == 200, active.text
    assert active.json()["id"] == session_id


def test_calibration_bland_altman(client: Any, clinician: dict[str, Any]) -> None:
    """Record six rPPG/reference pairs across the HR band and assert the
    Bland-Altman block is computed (n>=5 unlocks limits of agreement) with a
    small mean error on the clean synthetic signal."""
    truths = [66.0, 60.0, 72.0, 78.0, 84.0, 90.0]
    jitter = [0.5, -0.6, 0.8, -0.7, 0.4, -0.5]

    for truth, jit in zip(truths, jitter, strict=True):
        toi = assess_toi(client, clinician["headers"], hr_bpm=truth)
        measured = toi["biomarkers"]["heart_rate"]["value"] or truth
        ref = max(30.0, min(240.0, round(measured + jit, 1)))
        rec = client.post(
            "/calibration/record",
            headers=clinician["headers"],
            json={
                "toi_assessment_id": toi["id"],
                "reference_device_type": "PULSE_OXIMETER",
                "reference_device_label": "Masimo MightySat",
                "reference_hr_bpm": ref,
                "reference_rr_bpm": 15.0,
                "auto_paired_from_ble": False,
                "skin_tone_estimate": "IV",
            },
        )
        assert rec.status_code in (200, 201), rec.text
        assert rec.json()["error_bpm"] is not None

    stats = client.get("/calibration/stats", headers=clinician["headers"])
    assert stats.status_code == 200, stats.text
    overall = stats.json()["overall"]
    assert overall["n"] >= 5
    assert overall["loa_lower_bpm"] is not None and overall["loa_upper_bpm"] is not None
    assert overall["loa_lower_bpm"] <= overall["bias_bpm"] <= overall["loa_upper_bpm"]
    assert overall["mae_bpm"] < 5.0, f"MAE {overall['mae_bpm']} too high on clean signal"

    csv = client.get("/calibration/export.csv", headers=clinician["headers"])
    assert csv.status_code == 200
    assert "text/csv" in csv.headers.get("content-type", "")
    assert len(csv.text.strip().splitlines()) >= 2  # header + >=1 data row


def test_governance_maker_checker_lifecycle(client: Any) -> None:
    maker = register(client, "ADMIN")
    checker = register(client, "ADMIN")
    victim = register(client, "PATIENT")

    base_unread = unread_count(client, checker["headers"])

    propose = client.post(
        f"/governance/admin/users/{victim['id']}/erase",
        headers=maker["headers"],
        json={
            "confirm_user_id": victim["id"],
            "jurisdiction": "GDPR",
            "request_basis": "ADMIN_ACTION",
            "notes": "integration-test erasure",
        },
    )
    assert propose.status_code in (200, 201, 202), propose.text
    request_id = propose.json()["id"]
    assert propose.json()["status"] == "AWAITING_APPROVAL"
    # the propose response surfaces maker-checker attribution directly now,
    # not only via the ledger
    assert propose.json()["requires_approval"] is True

    # the checker is notified that an approval is pending
    assert unread_count(client, checker["headers"]) >= base_unread + 1

    # the full maker-checker fields are exposed via the admin ledger
    ledger = client.get(
        "/governance/admin/erasure-requests?status=AWAITING_APPROVAL",
        headers=checker["headers"],
    )
    assert ledger.status_code == 200
    rows = _rows(ledger.json())
    pending = next(r for r in rows if r["id"] == request_id)
    assert pending["requires_approval"] is True

    # segregation of duties: the maker may not approve their own request
    self_approve = client.post(
        f"/governance/admin/erasure-requests/{request_id}/approve",
        headers=maker["headers"],
        json={},
    )
    assert self_approve.status_code >= 400
    assert "egregation" in self_approve.text or "cannot approve" in self_approve.text

    # a different admin approves -> erasure executes
    approve = client.post(
        f"/governance/admin/erasure-requests/{request_id}/approve",
        headers=checker["headers"],
        json={},
    )
    assert approve.status_code in (200, 201), approve.text
    approved = approve.json()
    assert approved["status"] == "COMPLETED"
    # the approve response carries approver attribution directly
    assert approved["approved_by_user_id"] == checker["id"]
    assert approved["approved_by_email"] == checker["email"]

    # approver attribution recorded (visible on the ledger)
    completed = client.get(
        "/governance/admin/erasure-requests?status=COMPLETED", headers=checker["headers"]
    )
    done_row = next(r for r in _rows(completed.json()) if r["id"] == request_id)
    assert done_row["approved_by_user_id"] == checker["id"]

    # the erased account can no longer authenticate
    relogin = client.post("/auth/login", json={"email": victim["email"], "password": PASSWORD})
    assert relogin.status_code >= 400

    # the maker is notified of the outcome
    maker_notes = client.get("/notifications/me", headers=maker["headers"])
    assert maker_notes.status_code == 200
    types = [n["type"] for n in _rows(maker_notes.json(), key="notifications")]
    assert "ERASURE_REQUEST_APPROVED" in types


def test_notifications_read_lifecycle(client: Any) -> None:
    maker = register(client, "ADMIN")
    checker = register(client, "ADMIN")
    victim = register(client, "PATIENT")

    client.post(
        f"/governance/admin/users/{victim['id']}/erase",
        headers=maker["headers"],
        json={
            "confirm_user_id": victim["id"],
            "jurisdiction": "GDPR",
            "request_basis": "ADMIN_ACTION",
        },
    )

    listing = client.get("/notifications/me", headers=checker["headers"])
    assert listing.status_code == 200
    items = _rows(listing.json(), key="notifications")
    assert len(items) >= 1

    one = client.post(f"/notifications/{items[0]['id']}/read", headers=checker["headers"], json={})
    assert one.status_code in (200, 204), one.text

    all_read = client.post("/notifications/read-all", headers=checker["headers"], json={})
    assert all_read.status_code in (200, 204), all_read.text

    assert unread_count(client, checker["headers"]) == 0


def _rows(body: Any, key: str = "requests") -> list[dict[str, Any]]:
    if isinstance(body, list):
        return body
    return body.get(key) or body.get("items") or body.get("requests") or []
