"""Unit tests for the kiosk crypto + credential layers (no DB, no HTTP).

Locks down the security-critical pieces in isolation: the AES-256-GCM envelope
(round-trip, AAD binding, tamper + key-version rejection, key parsing), the
credential generators/hashers, the QR verification-text contract, and the
device-token check.
"""

from __future__ import annotations

import base64
import os

import pytest

from victus_api.kiosk.config import KioskConfig
from victus_api.kiosk.crypto import KioskCipher, KioskCryptoError, _resolve_key_bytes
from victus_api.kiosk.security import (
    KIOSK_VERIFICATION_PREFIX,
    build_verification_text,
    generate_otp,
    generate_result_token,
    generate_verification_nonce,
    hash_otp,
    hash_result_token,
    parse_verification_nonce,
    verify_otp,
)

# --- crypto ------------------------------------------------------------------


def _cipher(key_id: str = "k1") -> KioskCipher:
    return KioskCipher(key=os.urandom(32), key_id=key_id)


def test_encrypt_decrypt_round_trip_with_aad() -> None:
    cipher = _cipher()
    pt = b'{"triage_state":"YELLOW"}'
    env = cipher.encrypt(pt, aad=b"session-1")
    assert env.ciphertext != pt
    assert len(env.nonce) == 12
    assert env.key_id == "k1"
    out = cipher.decrypt(
        ciphertext=env.ciphertext, nonce=env.nonce, key_id=env.key_id, aad=b"session-1"
    )
    assert out == pt


def test_decrypt_rejects_wrong_aad() -> None:
    cipher = _cipher()
    env = cipher.encrypt(b"secret", aad=b"session-1")
    with pytest.raises(KioskCryptoError):
        cipher.decrypt(
            ciphertext=env.ciphertext,
            nonce=env.nonce,
            key_id=env.key_id,
            aad=b"session-2",
        )


def test_decrypt_rejects_tampered_ciphertext() -> None:
    cipher = _cipher()
    env = cipher.encrypt(b"secret")
    tampered = bytearray(env.ciphertext)
    tampered[0] ^= 0x01
    with pytest.raises(KioskCryptoError):
        cipher.decrypt(ciphertext=bytes(tampered), nonce=env.nonce, key_id=env.key_id)


def test_decrypt_rejects_unknown_key_id() -> None:
    cipher = _cipher(key_id="active")
    env = cipher.encrypt(b"secret")
    with pytest.raises(KioskCryptoError):
        cipher.decrypt(ciphertext=env.ciphertext, nonce=env.nonce, key_id="retired")


def test_nonce_is_unique_per_encryption() -> None:
    cipher = _cipher()
    assert cipher.encrypt(b"x").nonce != cipher.encrypt(b"x").nonce


def test_key_resolution_accepts_hex_and_base64() -> None:
    raw = os.urandom(32)
    assert _resolve_key_bytes(raw.hex()) == raw
    assert _resolve_key_bytes(base64.b64encode(raw).decode()) == raw


def test_key_resolution_rejects_bad_length_and_garbage() -> None:
    with pytest.raises(KioskCryptoError):
        _resolve_key_bytes(base64.b64encode(os.urandom(16)).decode())  # 16 bytes
    with pytest.raises(KioskCryptoError):
        _resolve_key_bytes("not-a-key")


def test_cipher_requires_32_byte_key() -> None:
    with pytest.raises(KioskCryptoError):
        KioskCipher(key=os.urandom(16), key_id="k")


# --- credentials -------------------------------------------------------------


def test_generate_otp_is_four_digits() -> None:
    for _ in range(50):
        otp = generate_otp()
        assert len(otp) == 4 and otp.isdigit()


def test_otp_hash_round_trip() -> None:
    otp = "0427"
    hashed = hash_otp(otp)
    assert hashed != otp
    assert verify_otp("0427", hashed)
    assert not verify_otp("0428", hashed)


def test_result_token_hash_is_stable_and_unique_tokens() -> None:
    t1, t2 = generate_result_token(), generate_result_token()
    assert t1 != t2
    assert hash_result_token(t1) == hash_result_token(t1)
    assert hash_result_token(t1) != hash_result_token(t2)


def test_verification_nonce_fits_column() -> None:
    nonce = generate_verification_nonce()
    assert 0 < len(nonce) <= 32


# --- verification text contract ---------------------------------------------


def test_verification_text_round_trip() -> None:
    nonce = generate_verification_nonce()
    text = build_verification_text(nonce)
    assert text.startswith(KIOSK_VERIFICATION_PREFIX)
    assert parse_verification_nonce(text) == nonce
    # Prefix match is case-insensitive; the nonce case is preserved verbatim.
    mixed = f"{KIOSK_VERIFICATION_PREFIX.lower()} {nonce}"
    assert parse_verification_nonce(mixed) == nonce


def test_parse_verification_nonce_negatives() -> None:
    assert parse_verification_nonce(None) is None
    assert parse_verification_nonce("hello there") is None
    assert parse_verification_nonce(KIOSK_VERIFICATION_PREFIX) is None  # no nonce


# --- device auth -------------------------------------------------------------


def test_device_verify_with_configured_tokens() -> None:
    cfg = KioskConfig(device_tokens={"kiosk-a": "tok-a"}, require_device_auth=True)
    assert cfg.verify_device("kiosk-a", "tok-a")
    assert not cfg.verify_device("kiosk-a", "wrong")
    assert not cfg.verify_device("kiosk-b", "tok-a")
    assert not cfg.verify_device(None, "tok-a")
    assert not cfg.verify_device("kiosk-a", None)


def test_device_verify_open_in_dev_when_unconfigured() -> None:
    cfg = KioskConfig(device_tokens={}, require_device_auth=False)
    assert cfg.verify_device("any-kiosk", None)
    assert not cfg.verify_device("", None)


def test_config_token_map_parsing() -> None:
    from victus_api.kiosk.config import _parse_token_map

    # Whitespace tolerated; malformed entries (no colon / empty side) skipped.
    assert _parse_token_map("a:1, b:2 ,bad,c:") == {"a": "1", "b": "2"}
    assert _parse_token_map("") == {}
