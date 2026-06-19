"""Integration: research-console labelled triage capture.

Covers role gating (patients refused), objective label derivation (BMI / BP /
HbA1c), the refusal to guess a label without ground truth, and the corpus
stats + training-export endpoints — against the live app + real Postgres.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import pytest
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.integration._helpers import register
from victus_api.db.models import User, UserRole

pytestmark = pytest.mark.integration

# Severely overweight (BMI 32.9) + stage-2 BP + diabetic HbA1c → all HIGH.
CASE: dict[str, Any] = {
    "age_years": 55,
    "sex": "MALE",
    "height_cm": 170,
    "weight_kg": 95,
    "waist_cm": 112,
    "systolic_bp_mmhg": 150,
    "diastolic_bp_mmhg": 96,
    "hba1c_percent": 7.2,
    "capture_domain": "CLINICAL_GRADE",
}


async def _promote(email: str, role: UserRole) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as s:
            await s.execute(
                update(User)
                .where(func.lower(User.email) == email.lower())
                .values(role=role)
            )
            await s.commit()
    finally:
        await engine.dispose()


def test_patient_cannot_record_research_case(client: Any) -> None:
    user = register(client, "PATIENT")
    r = client.post("/research/triage-cases", headers=user["headers"], json=CASE)
    assert r.status_code == 403, r.text


def test_clinician_records_with_derived_labels(client: Any) -> None:
    user = register(client, "PATIENT")
    asyncio.run(_promote(user["email"], UserRole.CLINICIAN))

    r = client.post("/research/triage-cases", headers=user["headers"], json=CASE)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["bmi"] == 32.9
    assert d["obesity_label"] == "HIGH_RISK"
    assert d["hypertension_label"] == "HIGH_RISK"
    assert d["diabetes_label"] == "HIGH_RISK"
    assert "HbA1c 7.2" in d["label_basis"]["diabetes"]

    # Refuses to guess diabetes/hypertension without a marker.
    bad = {"age_years": 40, "sex": "MALE", "height_cm": 170, "weight_kg": 80, "waist_cm": 90}
    rb = client.post("/research/triage-cases", headers=user["headers"], json=bad)
    assert rb.status_code == 422, rb.text

    # A clinician override supplies labels when objective data is absent.
    override = {**bad, "diabetes_label": "ELEVATED_RISK", "hypertension_label": "LOW_RISK"}
    ro = client.post("/research/triage-cases", headers=user["headers"], json=override)
    assert ro.status_code == 201, ro.text
    assert ro.json()["label_basis"]["diabetes"] == "clinician-set"


def test_corpus_stats_and_export(client: Any) -> None:
    user = register(client, "PATIENT")
    asyncio.run(_promote(user["email"], UserRole.CLINICIAN))
    client.post("/research/triage-cases", headers=user["headers"], json=CASE)

    st = client.get("/research/triage-cases/stats", headers=user["headers"])
    assert st.status_code == 200, st.text
    body = st.json()
    assert body["total"] >= 1
    assert body["with_diabetes_marker"] >= 1
    assert set(body["label_distribution"]) == {"obesity", "hypertension", "diabetes"}

    ex = client.get("/research/triage-cases/export", headers=user["headers"])
    assert ex.status_code == 200, ex.text
    lines = [ln for ln in ex.text.splitlines() if ln.strip()]
    assert len(lines) >= 1
    row = json.loads(lines[0])
    assert {
        "obesity_label",
        "hypertension_label",
        "diabetes_label",
        "domain",
    } <= set(row)
