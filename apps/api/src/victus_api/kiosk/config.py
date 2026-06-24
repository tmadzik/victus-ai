"""Kiosk device-fleet configuration, read from the environment.

Standalone (like ``whatsapp.config`` / ``worker.config``) so per-terminal
secrets do not expand the validated app ``Settings`` surface. The encryption key
and TTLs that DO want validation live on ``Settings``; this holds the device
token map and the WhatsApp deep-link number.

* ``KIOSK_DEVICE_TOKENS``    — ``kioskId:token`` pairs, comma-separated. The
                              terminal authenticates with ``X-Kiosk-Id`` +
                              ``X-Kiosk-Token``; both must match (constant-time).
* ``KIOSK_WHATSAPP_NUMBER``  — E.164 digits the QR deep-links into (wa.me/<n>).
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass


def _parse_token_map(raw: str) -> dict[str, str]:
    """Parse ``"kioskA:tokA,kioskB:tokB"`` into ``{kioskA: tokA, ...}``.

    Malformed entries (missing colon, empty id/token) are skipped rather than
    raised, so one fat-fingered pair cannot brick the whole fleet's auth.
    """
    out: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        kiosk_id, _, token = pair.partition(":")
        kiosk_id, token = kiosk_id.strip(), token.strip()
        if kiosk_id and token:
            out[kiosk_id] = token
    return out


@dataclass(frozen=True)
class KioskConfig:
    # kiosk_id -> shared device token.
    device_tokens: dict[str, str]
    # E.164 number (digits only) the kiosk QR opens in WhatsApp.
    whatsapp_number: str = ""
    # When False (no tokens configured, e.g. local dev) device auth is open so
    # the flow can be exercised without provisioning. The router refuses this in
    # production — auth there fails closed.
    require_device_auth: bool = True

    @classmethod
    def from_env(cls) -> KioskConfig:
        tokens = _parse_token_map(os.environ.get("KIOSK_DEVICE_TOKENS", ""))
        return cls(
            device_tokens=tokens,
            whatsapp_number=os.environ.get("KIOSK_WHATSAPP_NUMBER", "").strip(),
            # Only enforce when we actually hold tokens to check against.
            require_device_auth=bool(tokens),
        )

    def verify_device(self, kiosk_id: str | None, token: str | None) -> bool:
        """Constant-time check of a terminal's ``(kiosk_id, token)`` pair.

        When no tokens are configured (dev), accepts any non-empty kiosk_id.
        """
        if not self.require_device_auth:
            return bool(kiosk_id)
        if not kiosk_id or not token:
            return False
        expected = self.device_tokens.get(kiosk_id)
        if expected is None:
            return False
        return hmac.compare_digest(expected, token)
