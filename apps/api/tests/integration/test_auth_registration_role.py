"""Public registration must never let a caller choose its own role.

CLINICIAN reads identified participant records and ADMIN reaches governance and
erasure, so a self-assignable role on the public endpoint would let anyone
provision access to other people's health data.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration._helpers import PASSWORD

pytestmark = pytest.mark.integration


def _payload(**extra: object) -> dict[str, object]:
    return {
        "email": f"role_probe_{uuid.uuid4().hex[:10]}@example.com",
        "password": PASSWORD,
        "full_name": "Role Probe",
        **extra,
    }


@pytest.mark.parametrize("role", ["ADMIN", "CLINICIAN", "CHW"])
def test_register_rejects_caller_supplied_role(client, role: str) -> None:
    """A request that tries to claim an elevated role is refused outright."""
    resp = client.post("/auth/register", json=_payload(role=role))

    # `extra="forbid"` on the DTO means the field is rejected, not ignored —
    # a caller gets a loud 422 instead of quietly receiving a PATIENT account.
    assert resp.status_code == 422, resp.text


def test_register_creates_a_patient(client) -> None:
    """The happy path still works and always yields a PATIENT."""
    resp = client.post("/auth/register", json=_payload())

    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["user"]["role"] == "PATIENT"
