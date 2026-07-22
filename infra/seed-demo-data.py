#!/usr/bin/env python3
"""Seed a synthetic demo cohort so the platform demonstrates well.

An empty install shows nothing: no trajectories, no rising-risk nudges, no
acquisition worklist, no care-loop analytics. This creates a small cohort with
deliberate *storylines* — one participant whose risk climbs, one whose risk
falls after intervention, one urgent referral, one contactless-capture trend —
so every part of the platform has something real to show.

Everything is created through the public API, so it exercises the same code
paths (and writes the same audit trail) as real use. Assessment timestamps are
then spread backwards over a few months so trajectories look longitudinal.

ALL DATA IS SYNTHETIC. These are not real people and not real measurements.

    API_URL=http://localhost:8000 python3 infra/seed-demo-data.py
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
PASSWORD = os.environ.get("DEMO_PASSWORD", "VictusDemo!2026")
DOMAIN = "demo.victusdata.com"

BOLD, DIM, OFF = "\033[1m", "\033[2m", "\033[0m"


# --------------------------------------------------------------------------- #
# tiny HTTP helpers (stdlib only)
# --------------------------------------------------------------------------- #
class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, detail: str):
        super().__init__(f"{method} {path} → HTTP {status}: {detail[:300]}")
        self.status = status


def _call(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        raise ApiError(method, path, exc.code, exc.read().decode(errors="replace")) from None
    return json.loads(raw) if raw else {}


def register(email: str, role: str, name: str) -> str | None:
    """Returns an access token, or None when the account already exists."""
    try:
        out = _call("POST", "/auth/register",
                    {"email": email, "password": PASSWORD, "full_name": name, "role": role})
        return out["tokens"]["access_token"]
    except ApiError as exc:
        if exc.status == 409:      # already registered — fall back to logging in
            return None
        raise


def login(email: str) -> str:
    out = _call("POST", "/auth/login", {"email": email, "password": PASSWORD})
    return out["tokens"]["access_token"]


def account(email: str, role: str, name: str) -> tuple[str, bool]:
    """Idempotent: create if missing, else log in. Returns (token, created)."""
    created = register(email, role, name) is not None
    # Always continue with a freshly minted login token rather than the one the
    # register response returned — one less thing to go stale mid-seed.
    return login(email), created


def consent(token: str) -> None:
    _call("PATCH", "/users/me/consents",
          {"grants": ["TRIAGE", "TOI_IMAGING"], "revokes": []}, token=token)


def already_assessed(token: str) -> bool:
    """True when this participant already has assessments.

    Assessment endpoints are append-only, so without this guard a second run
    would stack a *second* history on top of the first and every trajectory
    would double back on itself.
    """
    triage_rows = _call("GET", "/pathways/triage/assessments/me?limit=1", token=token)
    toi_rows = _call("GET", "/pathways/toi/assessments/me?limit=1", token=token)
    return bool(triage_rows) or bool(toi_rows)


def triage(token: str, *, height, weight, waist, hip, age, sex, sbp, dbp, triggers=()) -> dict:
    return _call("POST", "/pathways/triage/assess", {
        "inputs": {
            "height_cm": height, "weight_kg": weight, "waist_cm": waist, "hip_cm": hip,
            "age_years": age, "sex": sex,
            "systolic_bp_mmhg": sbp, "diastolic_bp_mmhg": dbp,
        },
        "symptoms": {"safety_triggers": list(triggers), "contextual": []},
    }, token=token)


def synth_frames(n: int = 450, fps: float = 30.0, hr_bpm: float = 66.0, rr_bpm: float = 15.0):
    """A clean synthetic ROI-mean RGB trace with a green-dominant pulsatile AC —
    the same generator the integration tests use, so the rPPG pipeline recovers
    a stable heart rate near ``hr_bpm``."""
    hr_hz, rr_hz = hr_bpm / 60.0, rr_bpm / 60.0
    frames = []
    for i in range(n):
        t = i / fps
        pulse = math.sin(2 * math.pi * hr_hz * t)
        resp = math.sin(2 * math.pi * rr_hz * t)
        jit = 0.03 * math.sin(2 * math.pi * 7.3 * t + 1.1)
        frames.append({
            "t_ms": round(i * 1000.0 / fps),
            "r": round(180.0 + 0.4 * pulse + 0.8 * resp + jit, 4),
            "g": round(120.0 + 2.2 * pulse + 0.5 * resp + jit, 4),
            "b": round(110.0 + 0.9 * pulse + 0.4 * resp + jit, 4),
        })
    return frames


def toi(token: str, hr_bpm: float) -> dict:
    frames = synth_frames(hr_bpm=hr_bpm)
    return _call("POST", "/pathways/toi/assess", {
        "frames": frames, "sample_rate_hz": 30.0, "duration_s": len(frames) / 30.0,
        "skin_tone_estimate": "IV", "motion_score": 1.0,
        "lighting_score": 0.9, "face_presence_ratio": 1.0,
    }, token=token)


# --------------------------------------------------------------------------- #
# the cohort — each participant exists to demonstrate one thing
# --------------------------------------------------------------------------- #
# (key, display name, age, sex, storyline, [triage measurement series])
COHORT = [
    ("tendai", "Tendai Moyo", 47, "MALE",
     "Risk RISING — fires the clinician nudge and an upward trajectory",
     [dict(height=172, weight=70, waist=82,  hip=96,  sbp=118, dbp=76),
      dict(height=172, weight=84, waist=96,  hip=102, sbp=134, dbp=86),
      dict(height=172, weight=97, waist=110, hip=108, sbp=156, dbp=98)]),

    ("chipo", "Chipo Nyathi", 52, "FEMALE",
     "Risk FALLING — the intervention bent the curve",
     [dict(height=163, weight=92, waist=104, hip=112, sbp=152, dbp=96),
      dict(height=163, weight=83, waist=94,  hip=106, sbp=138, dbp=88),
      dict(height=163, weight=71, waist=84,  hip=99,  sbp=122, dbp=78)]),

    ("farai", "Farai Kanengoni", 39, "MALE",
     "STABLE — change stays inside measurement noise, so nothing is flagged",
     [dict(height=178, weight=79, waist=88, hip=99, sbp=124, dbp=80),
      dict(height=178, weight=80, waist=89, hip=99, sbp=126, dbp=81)]),

    ("blessing", "Blessing Sibanda", 44, "MALE",
     "Borderline — the kind of uncertain case the worklist asks you to confirm",
     [dict(height=170, weight=86, waist=97, hip=103, sbp=136, dbp=87),
      dict(height=170, weight=88, waist=99, hip=104, sbp=140, dbp=89)]),

    ("kudzai", "Kudzai Tafara", 50, "FEMALE",
     "Contactless (rPPG) capture — rising vital-sign trend fires the TOI nudge",
     [dict(height=166, weight=78, waist=91, hip=103, sbp=130, dbp=84)]),
]

URGENT = ("adaeze", "Adaeze Okonkwo", 58, "FEMALE",
          "RED — a red-flag symptom bypasses the model and escalates immediately",
          dict(height=161, weight=88, waist=101, hip=109, sbp=148, dbp=92))


def backdate() -> bool:
    """Spread assessment timestamps backwards so trajectories span months.

    Runs inside the compose Postgres. Returns False (non-fatal) if unavailable —
    the demo still works, the points just share a date.
    """
    sql = """
    WITH r AS (
      SELECT id, row_number() OVER (PARTITION BY user_id ORDER BY created_at) AS rn,
             count(*)   OVER (PARTITION BY user_id)                           AS total
      FROM triage_assessments)
    UPDATE triage_assessments t SET created_at = now() - ((r.total - r.rn) * interval '28 days')
    FROM r WHERE t.id = r.id;
    WITH r AS (
      SELECT id, row_number() OVER (PARTITION BY user_id ORDER BY created_at) AS rn,
             count(*)   OVER (PARTITION BY user_id)                           AS total
      FROM toi_assessments)
    UPDATE toi_assessments t SET created_at = now() - ((r.total - r.rn) * interval '21 days')
    FROM r WHERE t.id = r.id;
    """
    cmd = ["docker", "compose",
           "-f", "infra/docker-compose.prod.yml", "-f", "infra/docker-compose.local.yml",
           "--env-file", "infra/.env.local",
           "exec", "-T", "postgres", "psql", "-q",
           "-U", os.environ.get("POSTGRES_USER", "victus"),
           "-d", os.environ.get("POSTGRES_DB", "victus"), "-c", sql]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return done.returncode == 0
    except Exception:
        return False


def main() -> int:
    print(f"\n{BOLD}Seeding the Victus demo cohort → {API}{OFF}")
    print(f"{DIM}All data is synthetic — not real people, not real measurements.{OFF}\n")

    # Staff first, so they exist to receive the nudges the assessments fire.
    _, made = account(f"admin@{DOMAIN}", "ADMIN", "Demo Administrator")
    print(f"  {'created' if made else 'exists '}  admin@{DOMAIN}      (ADMIN)")
    _, made = account(f"clinician@{DOMAIN}", "CLINICIAN", "Dr. Demo Clinician")
    print(f"  {'created' if made else 'exists '}  clinician@{DOMAIN}  (CLINICIAN)")

    print()
    for key, name, age, sex, story, series in COHORT:
        email = f"{key}@{DOMAIN}"
        token, made = account(email, "PATIENT", name)
        consent(token)
        if already_assessed(token):
            print(f"  skipped  {email:<34} {DIM}already has a history{OFF}")
            continue
        states = []
        for m in series:
            out = triage(token, age=age, sex=sex, **m)
            states.append(out["overall_state"])
        if key == "kudzai":
            for hr in (62.0, 98.0):  # a clear upward move between two checks
                toi(token, hr)
            states.append("TOI×2")
        print(f"  {'created' if made else 'exists '}  {email:<34} {'→'.join(states)}")
        print(f"           {DIM}{story}{OFF}")

    # The urgent-referral case.
    key, name, age, sex, story, m = URGENT
    email = f"{key}@{DOMAIN}"
    token, made = account(email, "PATIENT", name)
    consent(token)
    if already_assessed(token):
        print(f"  skipped  {email:<34} {DIM}already has a history{OFF}")
    else:
        out = triage(token, age=age, sex=sex, triggers=["chest_pain_radiating"], **m)
        print(f"  {'created' if made else 'exists '}  {email:<34} {out['overall_state']}"
              f" (safety override: {out['safety_override_triggered']})")
        print(f"           {DIM}{story}{OFF}")

    print(f"\n{BOLD}Spreading assessment dates so trajectories look longitudinal{OFF}")
    print("  " + ("done — assessments now span several months."
                  if backdate() else
                  "skipped (couldn't reach the database container); demo still works."))

    print(f"""
{BOLD}Demo accounts — password for all: {PASSWORD}{OFF}

  Clinician   clinician@{DOMAIN}   ← start here; sees the whole cohort
  Admin       admin@{DOMAIN}       ← governance, audit, approvals
  Participant tendai@{DOMAIN}      ← the rising-risk story, from the member side

Open the clinical app at http://localhost:3000 and see DEMO.md for the walkthrough.
""")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ApiError as exc:
        print(f"\nSeeding failed — {exc}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"\nCould not reach the API at {API}: {exc}\n"
              f"Is the stack up? Try ./infra/demo-up.sh", file=sys.stderr)
        sys.exit(1)
