"""Kiosk credential generation + hashing.

Three short-lived secrets back the gateway, none stored in the clear:

* **verification nonce** — the code embedded in the QR-prefilled WhatsApp text.
  Bound to one ``kiosk_sessions`` row; stored as-is (it is meaningless without
  also passing the consent gate from a real MSISDN) but single-use.
* **result token** — the opaque credential in the portal URL. Only its SHA-256
  is persisted, so a DB read cannot reconstruct a working link.
* **OTP** — the 4-digit second factor, argon2-hashed (reusing the auth hasher)
  and protected by a bounded attempt counter so the 10k space is not brute-able.
"""

from __future__ import annotations

import hashlib
import secrets

from victus_api.auth.security import hash_password, verify_password

# Leading token of the QR-prefilled WhatsApp message. The webhook matches this
# to route an inbound message into the kiosk-linking flow instead of the normal
# conversation FSM.
KIOSK_VERIFICATION_PREFIX = "VICTUS-KIOSK"

# Verification nonce: url-safe, comfortably inside the String(32) column.
_NONCE_BYTES = 12  # ~16 url-safe chars
# Result token: 256-bit opaque random, like the refresh-token design.
_RESULT_TOKEN_BYTES = 48


def generate_verification_nonce() -> str:
    """Short, single-use code for the QR deep link (<= 32 chars)."""
    return secrets.token_urlsafe(_NONCE_BYTES)


def build_verification_text(nonce: str) -> str:
    """The exact WhatsApp message the QR pre-fills (prefix + nonce)."""
    return f"{KIOSK_VERIFICATION_PREFIX} {nonce}"


def parse_verification_nonce(text: str | None) -> str | None:
    """Extract a kiosk nonce from an inbound message, or None if it isn't one.

    Matches ``VICTUS-KIOSK <nonce>`` case-insensitively on the prefix; the nonce
    itself is returned verbatim (it is looked up exactly).
    """
    if not text:
        return None
    parts = text.strip().split()
    if len(parts) >= 2 and parts[0].upper() == KIOSK_VERIFICATION_PREFIX:
        return parts[1]
    return None


def generate_result_token() -> str:
    """Opaque, high-entropy token for the secure-result portal URL."""
    return secrets.token_urlsafe(_RESULT_TOKEN_BYTES)


def hash_result_token(token: str) -> str:
    """SHA-256 hex of a result token — what we persist and look up by."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_otp() -> str:
    """A zero-padded 4-digit one-time PIN (uniform over 0000-9999)."""
    return f"{secrets.randbelow(10_000):04d}"


def hash_otp(otp: str) -> str:
    """argon2id hash of the OTP (defence-in-depth atop the attempt limit)."""
    return hash_password(otp)


def verify_otp(otp: str, hashed: str) -> bool:
    """Constant-time argon2 verify of a submitted OTP."""
    return verify_password(otp, hashed)
