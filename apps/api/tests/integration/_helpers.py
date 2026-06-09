"""Shared helpers for the integration suites: account setup, consent, and a
clean synthetic rPPG signal generator."""

from __future__ import annotations

import math
import uuid
from typing import Any

PASSWORD = "VictusTest!2026"


def register(client: Any, role: str) -> dict[str, Any]:
    """Register a uniquely-named account and return its id, email, bearer
    headers, and refresh token."""
    email = f"{role.lower()}_{uuid.uuid4().hex[:10]}@example.com"
    resp = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": f"Test {role.title()}",
            "role": role,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    return {
        "id": body["user"]["id"],
        "email": email,
        "headers": {"Authorization": f"Bearer {body['tokens']['access_token']}"},
        "refresh_token": body["tokens"]["refresh_token"],
    }


def grant_consent(client: Any, headers: dict[str, str], consent: str) -> None:
    resp = client.patch(
        "/users/me/consents",
        headers=headers,
        json={"grants": [consent], "revokes": []},
    )
    assert resp.status_code in (200, 204), resp.text


def unread_count(client: Any, headers: dict[str, str]) -> int:
    resp = client.get("/notifications/me/unread-count", headers=headers)
    assert resp.status_code == 200, resp.text
    return int(resp.json()["unread_count"])


def synth_frames(
    n: int = 450, fps: float = 30.0, hr_bpm: float = 66.0, rr_bpm: float = 15.0
) -> list[dict[str, float]]:
    """A clean synthetic ROI-mean RGB trace: a green-dominant pulsatile AC on a
    skin-tone DC, plus a slow respiratory baseline drift and a tiny
    deterministic dither. Designed to yield a high-SNR heart-rate recovery from
    the CHROM/POS pipeline so the test is stable."""
    hr_hz, rr_hz = hr_bpm / 60.0, rr_bpm / 60.0
    frames: list[dict[str, float]] = []
    for i in range(n):
        t = i / fps
        pulse = math.sin(2 * math.pi * hr_hz * t)
        resp = math.sin(2 * math.pi * rr_hz * t)
        jit = 0.03 * math.sin(2 * math.pi * 7.3 * t + 1.1)
        frames.append(
            {
                "t_ms": round(i * 1000.0 / fps),
                "r": round(180.0 + 0.4 * pulse + 0.8 * resp + jit, 4),
                "g": round(120.0 + 2.2 * pulse + 0.5 * resp + jit, 4),  # strongest
                "b": round(110.0 + 0.9 * pulse + 0.4 * resp + jit, 4),
            }
        )
    return frames


def assess_toi(client: Any, headers: dict[str, str], hr_bpm: float = 66.0) -> dict[str, Any]:
    """Run a TOI assessment from a synthetic capture at ``hr_bpm`` and return
    the response body (includes the persisted assessment id)."""
    frames = synth_frames(hr_bpm=hr_bpm)
    resp = client.post(
        "/pathways/toi/assess",
        headers=headers,
        json={
            "frames": frames,
            "sample_rate_hz": 30.0,
            "duration_s": len(frames) / 30.0,
            "skin_tone_estimate": "IV",
            "motion_score": 1.0,
            "lighting_score": 0.9,
            "face_presence_ratio": 1.0,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()
