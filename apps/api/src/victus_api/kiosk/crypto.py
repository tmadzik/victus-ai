"""AES-256-GCM envelope for kiosk clinical-result payloads.

The triage summary is encrypted at rest with a key supplied *externally* (host
env / secrets file, surfaced via ``Settings.kiosk_encryption_key``) — the
database only ever sees ciphertext + nonce + a key-version label. GCM gives
confidentiality and integrity (a tampered ciphertext fails the auth tag), so a
read of the table alone reveals nothing and a write cannot forge a result.

Key material accepts either 64 hex chars or base64 decoding to exactly 32 bytes,
so operators can paste whatever ``openssl rand`` produced. ``key_id`` is stamped
on each row so a rotation can keep older rows decryptable by resolving the right
key version (the keyring is currently single-entry; rotation extends it).
"""

from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from victus_api.config import Settings

# GCM standard nonce size. 96 bits is the AES-GCM sweet spot (no rehashing).
_NONCE_BYTES = 12
_KEY_BYTES = 32  # AES-256


class KioskCryptoError(RuntimeError):
    """Key misconfiguration or a failed authenticated decryption."""


def _resolve_key_bytes(raw: str) -> bytes:
    """Decode a configured key string (hex or base64) to exactly 32 bytes."""
    raw = raw.strip()
    # Try hex first (64 chars), then base64 — both unambiguous at 32 bytes.
    if len(raw) == _KEY_BYTES * 2:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise KioskCryptoError(
            "KIOSK_ENCRYPTION_KEY must be 64 hex chars or base64 of 32 bytes."
        ) from exc
    if len(decoded) != _KEY_BYTES:
        raise KioskCryptoError(
            f"KIOSK_ENCRYPTION_KEY must decode to {_KEY_BYTES} bytes, "
            f"got {len(decoded)}."
        )
    return decoded


@dataclass(frozen=True)
class Envelope:
    """A sealed payload, ready to persist on ``kiosk_clinical_results``."""

    ciphertext: bytes
    nonce: bytes
    key_id: str


class KioskCipher:
    """Stateless AES-256-GCM sealer bound to the active key version."""

    def __init__(self, *, key: bytes, key_id: str) -> None:
        if len(key) != _KEY_BYTES:
            raise KioskCryptoError("Kiosk AES key must be 32 bytes (AES-256).")
        self._aes = AESGCM(key)
        self._key_id = key_id

    @classmethod
    def from_settings(cls, settings: Settings) -> KioskCipher:
        key = _resolve_key_bytes(settings.kiosk_encryption_key.get_secret_value())
        return cls(key=key, key_id=settings.kiosk_key_id)

    def encrypt(self, plaintext: bytes, *, aad: bytes | None = None) -> Envelope:
        """Seal ``plaintext``; ``aad`` (e.g. the session id) is bound but not stored."""
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._aes.encrypt(nonce, plaintext, aad)
        return Envelope(ciphertext=ciphertext, nonce=nonce, key_id=self._key_id)

    def decrypt(
        self,
        *,
        ciphertext: bytes,
        nonce: bytes,
        key_id: str,
        aad: bytes | None = None,
    ) -> bytes:
        """Open a sealed payload, verifying the auth tag and key version."""
        if key_id != self._key_id:
            raise KioskCryptoError(
                f"No key available for key_id '{key_id}' (active: '{self._key_id}')."
            )
        try:
            return self._aes.decrypt(nonce, ciphertext, aad)
        except InvalidTag as exc:
            raise KioskCryptoError(
                "Kiosk result decryption failed: ciphertext failed authentication."
            ) from exc
