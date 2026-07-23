#!/usr/bin/env python3
"""Drive the Mobile Clinic Gateway end-to-end on localhost, no Meta account.

Walks the real walk-up journey against the real endpoints:

    kiosk opens a session  →  QR / wa.me deep link
    participant "messages" WhatsApp with the code   (simulated webhook)
    participant consents                            (simulated "YES")
    kiosk captures                                  (synthetic rPPG signal)
    worker runs the pipeline, seals the result, mints a one-time OTP
    → secure portal link + OTP, which you open in a browser

Nothing here is a mock of the platform: the kiosk, webhook, worker, encryption
and OTP gate are all the production code paths. The only stand-in is Meta —
the API skips webhook signature checks when no app secret is configured, and
the worker's --local-media mode prints outbound messages to its log instead of
sending them to a phone.

    python3 infra/demo-gateway.py
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "http://localhost:8000"
APP = "http://localhost:3000"
KIOSK_ID = "demo-kiosk-1"
KIOSK_TOKEN = "demo-kiosk-token"

# A FRESH participant phone per run. The WhatsApp rail keeps one conversation
# per phone number, so reusing a fixed number means the previous run's state
# (still bound to that run's kiosk session, mid-consent) hijacks the next one —
# the new nonce links, but the "YES" consents the OLD session and the terminal
# never advances. A real walk-up is a different phone every time; this mirrors
# that and makes the demo re-runnable. Override with DEMO_PHONE to replay one.
PHONE = os.environ.get("DEMO_PHONE") or f"26377{int(time.time()) % 10_000_000:07d}"

BOLD, DIM, GREEN, OFF = "\033[1m", "\033[2m", "\033[32m", "\033[0m"
COMPOSE = ["docker", "compose",
           "-f", "infra/docker-compose.prod.yml",
           "-f", "infra/docker-compose.local.yml",
           "--env-file", "infra/.env.local", "--profile", "whatsapp"]


def call(method: str, path: str, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"\n{method} {path} failed → HTTP {exc.code}: {detail[:400]}")
    return json.loads(raw) if raw else {}


def whatsapp_says(text: str):
    """POST a synthetic inbound WhatsApp message in Meta's webhook envelope."""
    return call("POST", "/whatsapp/webhook", {
        "entry": [{"changes": [{"value": {"messages": [{
            "from": PHONE,
            "id": f"wamid.demo{int(time.time()*1000)}",
            "type": "text",
            "text": {"body": text},
        }]}}]}]
    })


def synth_signal(n: int = 450, fps: float = 30.0, hr_bpm: float = 74.0, rr_bpm: float = 15.0):
    hr_hz, rr_hz = hr_bpm / 60.0, rr_bpm / 60.0
    frames = []
    for i in range(n):
        t = i / fps
        pulse, resp = math.sin(2 * math.pi * hr_hz * t), math.sin(2 * math.pi * rr_hz * t)
        jit = 0.03 * math.sin(2 * math.pi * 7.3 * t + 1.1)
        frames.append({"t_ms": round(i * 1000.0 / fps),
                       "r": round(180.0 + 0.4 * pulse + 0.8 * resp + jit, 4),
                       "g": round(120.0 + 2.2 * pulse + 0.5 * resp + jit, 4),
                       "b": round(110.0 + 0.9 * pulse + 0.4 * resp + jit, 4)})
    return {"frames": frames, "sample_rate_hz": fps, "duration_s": n / fps}


def worker_log() -> str:
    try:
        done = subprocess.run([*COMPOSE, "logs", "--no-log-prefix", "worker"],
                              capture_output=True, text=True, timeout=30)
        return done.stdout + done.stderr
    except Exception:
        return ""


def step(n: int, title: str) -> None:
    print(f"\n{BOLD}{n}. {title}{OFF}")


def open_session_on_screen() -> tuple[str, str] | None:
    """Find the session the kiosk terminal is currently displaying.

    The QR deep-links to a WhatsApp number that doesn't exist in a demo, so
    scanning it dead-ends. Instead we adopt that exact session and drive it —
    the kiosk polls its own status, so the SCREEN advances by itself.
    """
    sql = ("SELECT id, verification_nonce FROM kiosk_sessions "
           "WHERE status IN ('INITIATED','LINKED') AND expires_at > now() "
           "ORDER BY created_at DESC LIMIT 1;")
    try:
        done = subprocess.run(
            [*COMPOSE, "exec", "-T", "postgres", "psql", "-tAF,", "-U", "victus",
             "-d", "victus", "-c", sql],
            capture_output=True, text=True, timeout=30)
        line = next((ln for ln in done.stdout.strip().splitlines() if "," in ln), "")
        sid, _, nonce = line.partition(",")
        return (sid.strip(), nonce.strip()) if sid.strip() and nonce.strip() else None
    except Exception:
        return None


def main() -> int:
    kiosk_auth = {"X-Kiosk-Id": KIOSK_ID, "X-Kiosk-Token": KIOSK_TOKEN}
    on_screen = any(a in sys.argv[1:] for a in ("--on-screen", "--scan"))

    print(f"\n{BOLD}Mobile Clinic Gateway — end-to-end walk-up demo{OFF}")
    print(f"{DIM}Real kiosk, webhook, worker, encryption and OTP gate. "
          f"Meta is stood in for locally.{OFF}")

    if on_screen:
        step(1, "Adopting the session already on the kiosk screen")
        found = open_session_on_screen()
        if not found:
            print("   No session is waiting. Open http://localhost:3000/kiosk and")
            print("   start a check-up so the QR screen is showing, then re-run.")
            return 1
        sid, nonce = found
        session = {"id": sid, "verification_nonce": nonce,
                   "qr_text": f"VICTUS-KIOSK {nonce}"}
        print(f"   session  {sid}")
        print(f"   code     {GREEN}{nonce}{OFF} {DIM}— should match the screen{OFF}")
        print(f"\n   {BOLD}Watch the kiosk screen. It will move on its own.{OFF}")
        time.sleep(2)
    else:
        step(1, "A participant walks up — the terminal opens a session")
        # The terminal identifies itself by header; the endpoint takes no body.
        session = call("POST", "/kiosk/sessions", {}, kiosk_auth)
        sid, nonce = session["id"], session["verification_nonce"]
        print(f"   session   {sid}")
        print(f"   QR text   {GREEN}{session['qr_text']}{OFF}")
        print(f"   deep link {session.get('whatsapp_deep_link') or '(no number configured)'}")
        print(f"   {DIM}On a real terminal this is a QR code on screen.{OFF}")

    step(2, "They scan it — WhatsApp opens pre-filled, they hit send")
    whatsapp_says(session["qr_text"])
    st = call("GET", f"/kiosk/sessions/{sid}", None, kiosk_auth)
    print(f"   status → {GREEN}{st['status']}{OFF}   linked={st['linked']}")
    print(f"   {DIM}The phone is now bound to the terminal by a single-use nonce.{OFF}")

    step(3, "Consent is taken in the chat, not on the kiosk")
    whatsapp_says("YES")
    st = call("GET", f"/kiosk/sessions/{sid}", None, kiosk_auth)
    print(f"   status → {GREEN}{st['status']}{OFF}   consented={st['consented']}")
    if not st["consented"]:
        print(f"   {DIM}(conversation asked something else first — replying YES again){OFF}")
        whatsapp_says("YES")
        st = call("GET", f"/kiosk/sessions/{sid}", None, kiosk_auth)
        print(f"   status → {GREEN}{st['status']}{OFF}   consented={st['consented']}")

    step(4, "The camera capture — only derived signals leave the terminal")
    if on_screen:
        # The terminal owns the capture in this mode. Posting one here would
        # hijack the session out from under the screen.
        print(f"   {BOLD}Do the capture on the kiosk screen now.{OFF}")
        print("   Sit in front of it, or press “Use demo capture” to submit a")
        print("   synthetic signal if the lighting won't cooperate.")
        print(f"   {DIM}Waiting for the terminal to submit…{OFF}")
    else:
        call("POST", f"/kiosk/sessions/{sid}/capture", {
            "signal_quality_index": 0.91, "illumination_score": 0.88,
            "face_bbox_ratio": 0.34, "frame_count": 450, "error_flags": [],
            "rppg_signal": synth_signal(),
        }, kiosk_auth)
        print("   captured → queued for the worker")
        print(f"   {DIM}No frames are stored — quality scalars persist, traces ride the job.{OFF}")

    step(5, "The worker runs the pipeline, seals the result, mints a one-time OTP")
    for _ in range(150 if on_screen else 45):
        st = call("GET", f"/kiosk/sessions/{sid}", None, kiosk_auth)
        if st["result_ready"] or st["status"] in ("COMPLETE", "ABORTED"):
            break
        time.sleep(2)
    print(f"   status → {GREEN}{st['status']}{OFF}   result_ready={st['result_ready']}")
    if not st["result_ready"]:
        print("\n   The worker didn't finish. Check:  "
              f"{' '.join(COMPOSE)} logs worker")
        return 1

    step(6, "What the participant receives on WhatsApp")
    log = worker_log()
    url = next(iter(re.findall(r"https?://\S+/v/[A-Za-z0-9_\-]+", log)[-1:]), None)
    # Anchor on the asterisks the OTP message wraps the code in ("code is *0755*").
    # A bare \d{4} also matches the year in a log timestamp.
    otp = next(iter(re.findall(r"code is \*(\d{4})\*", log)[-1:]), None)
    if url:
        print(f"   secure link  {GREEN}{url}{OFF}")
        print(f"   one-time code {GREEN}{otp or '(see worker log)'}{OFF}")
    else:
        print("   (couldn't parse the log — read it directly:)")
        print(f"     {' '.join(COMPOSE)} logs worker")

    print(f"""
{BOLD}Open that link in a browser and enter the code.{OFF}
  · The result is AES-256-GCM encrypted at rest; the link is single-use and
    expires in 24h; wrong codes lock the token out after 5 tries.
  · The clinician-facing record lands in the app independently — sign in as
    clinician@demo.victusdata.com and search the participant.

{DIM}In production the two messages above are delivered to the participant's
WhatsApp by the Cloud API. Here the worker prints them instead of sending.{OFF}
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
