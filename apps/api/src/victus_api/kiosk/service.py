"""Kiosk gateway service: session lifecycle, capture, secure result delivery.

Owns the state machine over ``kiosk_sessions`` and the secure-result pipeline.
Network I/O (sending the WhatsApp link) is left to the caller so this layer
stays transaction-pure and unit-testable. The WhatsApp-linking entrypoints
(:func:`link_session_by_nonce`, :func:`grant_consent`) are called from the
WhatsApp service inside its existing webhook transaction.

OTP verification deliberately does NOT raise on a wrong code: the attempt
counter must persist, and ``session_scope`` rolls back on any exception. So
:func:`unlock_result` returns a discriminated result and the router renders it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.config import Settings
from victus_api.core.exceptions import ConflictError, NotFoundError, VictusError
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    KioskBiometricMetadata,
    KioskClinicalResult,
    KioskResultToken,
    KioskSession,
    KioskSessionStatus,
    User,
    WhatsAppSession,
)
from victus_api.kiosk.config import KioskConfig
from victus_api.kiosk.crypto import KioskCipher
from victus_api.kiosk.schemas import (
    KioskCaptureRequest,
    KioskCaptureResponse,
    KioskResultGateResponse,
    KioskResultPayload,
    KioskSessionResponse,
    KioskSessionStatusResponse,
)
from victus_api.kiosk.security import (
    build_verification_text,
    generate_otp,
    generate_result_token,
    generate_verification_nonce,
    hash_otp,
    hash_result_token,
    verify_otp,
)
from victus_api.worker.jobs import enqueue

log = get_logger(__name__)

# Statuses from which a fresh capture / consent is still meaningful.
_LINKED_STATUSES = frozenset(
    {
        KioskSessionStatus.LINKED,
        KioskSessionStatus.CONSENTED,
        KioskSessionStatus.CAPTURED,
        KioskSessionStatus.PROCESSING,
        KioskSessionStatus.COMPLETE,
    }
)
_CONSENTED_STATUSES = frozenset(
    {
        KioskSessionStatus.CONSENTED,
        KioskSessionStatus.CAPTURED,
        KioskSessionStatus.PROCESSING,
        KioskSessionStatus.COMPLETE,
    }
)
# Statuses past which the session is closed to further state changes.
_TERMINAL_STATUSES = frozenset(
    {KioskSessionStatus.COMPLETE, KioskSessionStatus.EXPIRED, KioskSessionStatus.ABORTED}
)
# Pre-capture statuses safe to reap on expiry (abandoned QR / consent). A
# CAPTURED/PROCESSING session is left for the worker to finish.
_EXPIRABLE_STATUSES = frozenset(
    {
        KioskSessionStatus.INITIATED,
        KioskSessionStatus.LINKED,
        KioskSessionStatus.CONSENTED,
    }
)


class KioskSessionExpiredError(VictusError):
    status_code = 410
    error_code = "kiosk_session_expired"


def _now() -> datetime:
    return datetime.now(UTC)


# --- helpers ----------------------------------------------------------------


async def _get(db: AsyncSession, session_id: uuid.UUID) -> KioskSession:
    row = await db.get(KioskSession, session_id)
    if row is None:
        raise NotFoundError("Kiosk session not found.")
    return row


def _is_expired(row: KioskSession) -> bool:
    return row.status not in _TERMINAL_STATUSES and row.expires_at <= _now()


def _deep_link(config: KioskConfig, text: str) -> str | None:
    if not config.whatsapp_number:
        return None
    return f"https://wa.me/{config.whatsapp_number}?text={quote(text)}"


def _session_response(
    row: KioskSession, *, qr_text: str, deep_link: str | None
) -> KioskSessionResponse:
    return KioskSessionResponse(
        id=row.id,
        status=row.status.value,
        site_code=row.site_code,
        verification_nonce=row.verification_nonce,
        qr_text=qr_text,
        whatsapp_deep_link=deep_link,
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


# --- device: session lifecycle ----------------------------------------------


async def create_session(
    db: AsyncSession,
    *,
    kiosk_id: str,
    settings: Settings,
    config: KioskConfig,
) -> KioskSessionResponse:
    """Open a new kiosk session and return the QR/deep-link payload."""
    nonce = generate_verification_nonce()
    row = KioskSession(
        kiosk_id=kiosk_id,
        site_code=settings.site_code,
        status=KioskSessionStatus.INITIATED,
        verification_nonce=nonce,
        expires_at=_now() + timedelta(seconds=settings.kiosk_session_ttl_seconds),
    )
    db.add(row)
    await db.flush()
    qr_text = build_verification_text(nonce)
    log.info("kiosk_session_created", session_id=str(row.id), kiosk_id=kiosk_id)
    return _session_response(row, qr_text=qr_text, deep_link=_deep_link(config, qr_text))


async def get_status(
    db: AsyncSession, *, session_id: uuid.UUID
) -> KioskSessionStatusResponse:
    """Poll target for the terminal — drives 'begin capture' and 'result ready'."""
    row = await _get(db, session_id)
    if _is_expired(row):
        row.status = KioskSessionStatus.EXPIRED
    return KioskSessionStatusResponse(
        id=row.id,
        status=row.status.value,
        linked=row.status in _LINKED_STATUSES,
        consented=row.status in _CONSENTED_STATUSES,
        result_ready=row.status is KioskSessionStatus.COMPLETE,
        expires_at=row.expires_at,
    )


# --- WhatsApp linking (called from the WhatsApp service) --------------------


async def link_session_by_nonce(
    db: AsyncSession, *, nonce: str, whatsapp_session: WhatsAppSession
) -> KioskSession | None:
    """Bind an inbound MSISDN's conversation to a kiosk session by its nonce.

    Returns the linked session, or None when the nonce is unknown/expired/already
    consumed — the caller replies accordingly. Single-use: only an ``INITIATED``
    (or already-``LINKED``) session in date can be (re)linked.
    """
    row = (
        await db.execute(
            select(KioskSession).where(KioskSession.verification_nonce == nonce)
        )
    ).scalar_one_or_none()
    if row is None or _is_expired(row):
        return None
    if row.status not in (KioskSessionStatus.INITIATED, KioskSessionStatus.LINKED):
        return None
    row.whatsapp_session_id = whatsapp_session.id
    if row.status is KioskSessionStatus.INITIATED:
        row.status = KioskSessionStatus.LINKED
        row.linked_at = _now()
    log.info("kiosk_session_linked", session_id=str(row.id))
    return row


async def grant_consent(
    db: AsyncSession, *, session_id: uuid.UUID, user: User
) -> KioskSession:
    """Mark a linked session CONSENTED and anchor it to the participant."""
    row = await _get(db, session_id)
    row.user_id = user.id
    row.status = KioskSessionStatus.CONSENTED
    row.consent_at = _now()
    log.info("kiosk_session_consented", session_id=str(row.id), user_id=str(user.id))
    return row


async def abort_session(db: AsyncSession, *, session_id: uuid.UUID) -> None:
    """Tear a session down (participant declined / kiosk purge)."""
    row = await db.get(KioskSession, session_id)
    if row is not None and row.status not in _TERMINAL_STATUSES:
        row.status = KioskSessionStatus.ABORTED


# --- device: capture finalisation -------------------------------------------


async def finalize_capture(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    payload: KioskCaptureRequest,
    settings: Settings,
) -> KioskCaptureResponse:
    """Persist derived capture metadata and enqueue the processing job.

    Requires a CONSENTED session in date. Stores only the quality scalars +
    error flags (no frames); the rPPG traces ride in the job ``intake`` for the
    worker, which the standard scrub clears on completion/erasure.
    """
    row = await _get(db, session_id)
    if _is_expired(row):
        row.status = KioskSessionStatus.EXPIRED
        raise KioskSessionExpiredError("Kiosk session expired before capture.")
    if row.status is not KioskSessionStatus.CONSENTED:
        raise ConflictError(
            "Capture requires a consented session.",
            details={"status": row.status.value},
        )

    db.add(
        KioskBiometricMetadata(
            session_id=row.id,
            signal_quality_index=payload.signal_quality_index,
            illumination_score=payload.illumination_score,
            face_bbox_ratio=payload.face_bbox_ratio,
            frame_count=payload.frame_count,
            error_flags=list(payload.error_flags),
        )
    )

    job = await enqueue(
        db,
        channel="KIOSK",
        user_id=row.user_id,
        intake={
            "kiosk_session_id": str(row.id),
            "rppg_signal": payload.rppg_signal or {},
        },
    )
    row.processing_job_id = job.id
    row.status = KioskSessionStatus.PROCESSING
    row.captured_at = _now()
    log.info(
        "kiosk_capture_finalized",
        session_id=str(row.id),
        processing_job_id=str(job.id),
    )
    return KioskCaptureResponse(
        id=row.id, status=row.status.value, processing_job_id=job.id
    )


# --- secure result delivery -------------------------------------------------


@dataclass(frozen=True)
class ResultDelivery:
    """Everything the caller needs to send the secure-portal link (no PHI)."""

    session_id: uuid.UUID
    portal_url: str
    otp: str
    phone: str | None
    message: str


def _portal_url(settings: Settings, token: str) -> str:
    return f"{settings.web_app_base_url.rstrip('/')}/v/{token}"


def build_result_message(portal_url: str) -> str:
    """The templated, PHI-free notification body (link only, no diagnostics)."""
    return (
        "Your Victus wellness check-up summary is ready. Open your secure "
        f"portal here: {portal_url}\nYou'll need the 4-digit code we sent you."
    )


async def deliver_result(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    payload: KioskResultPayload,
    settings: Settings,
) -> ResultDelivery:
    """Seal the summary, mint a single-use OTP token, mark the session COMPLETE.

    Returns the cleartext token (inside the URL) + OTP exactly once for the
    caller to deliver out-of-band; neither is ever stored in the clear.
    """
    row = await _get(db, session_id)

    cipher = KioskCipher.from_settings(settings)
    aad = str(row.id).encode("utf-8")
    envelope = cipher.encrypt(payload.model_dump_json().encode("utf-8"), aad=aad)
    result = KioskClinicalResult(
        session_id=row.id,
        encrypted_payload=envelope.ciphertext,
        encryption_nonce=envelope.nonce,
        key_id=envelope.key_id,
    )
    db.add(result)
    await db.flush()

    token = generate_result_token()
    otp = generate_otp()
    db.add(
        KioskResultToken(
            session_id=row.id,
            result_id=result.id,
            token_hash=hash_result_token(token),
            otp_hash=hash_otp(otp),
            max_otp_attempts=settings.kiosk_otp_max_attempts,
            expires_at=_now()
            + timedelta(seconds=settings.kiosk_result_token_ttl_seconds),
        )
    )
    row.status = KioskSessionStatus.COMPLETE
    row.completed_at = _now()

    phone: str | None = None
    if row.whatsapp_session_id is not None:
        wa = await db.get(WhatsAppSession, row.whatsapp_session_id)
        phone = wa.phone if wa is not None else None

    portal_url = _portal_url(settings, token)
    log.info("kiosk_result_delivered", session_id=str(row.id))
    return ResultDelivery(
        session_id=row.id,
        portal_url=portal_url,
        otp=otp,
        phone=phone,
        message=build_result_message(portal_url),
    )


# --- public: OTP-gated portal -----------------------------------------------


@dataclass(frozen=True)
class UnlockSuccess:
    payload: KioskResultPayload


@dataclass(frozen=True)
class UnlockFailure:
    # "not_found" | "expired" | "consumed" | "locked" | "invalid_otp"
    reason: str
    attempts_remaining: int | None = None


UnlockResult = UnlockSuccess | UnlockFailure


async def _get_token(db: AsyncSession, token: str) -> KioskResultToken | None:
    return (
        await db.execute(
            select(KioskResultToken).where(
                KioskResultToken.token_hash == hash_result_token(token)
            )
        )
    ).scalar_one_or_none()


async def get_result_gate(
    db: AsyncSession, *, token: str
) -> KioskResultGateResponse:
    """Pre-unlock probe for the portal form — no data, no state change."""
    tok = await _get_token(db, token)
    if tok is None or tok.expires_at <= _now():
        raise NotFoundError("This result link is invalid or has expired.")
    if tok.consumed_at is not None:
        raise ConflictError("This result has already been viewed.")
    remaining = max(0, tok.max_otp_attempts - tok.otp_attempts)
    return KioskResultGateResponse(
        expires_at=tok.expires_at,
        locked=remaining == 0,
        attempts_remaining=remaining,
    )


async def unlock_result(
    db: AsyncSession, *, token: str, otp: str, settings: Settings
) -> UnlockResult:
    """Verify the OTP and, on success, decrypt + consume the result (single use).

    A wrong OTP increments the attempt counter and returns a failure (never
    raises) so the increment commits — the bounded counter is the real defence.
    """
    tok = await _get_token(db, token)
    if tok is None or tok.expires_at <= _now():
        return UnlockFailure(reason="expired")
    if tok.consumed_at is not None:
        return UnlockFailure(reason="consumed")
    if tok.otp_hash is None or tok.otp_attempts >= tok.max_otp_attempts:
        return UnlockFailure(reason="locked", attempts_remaining=0)

    if not verify_otp(otp, tok.otp_hash):
        tok.otp_attempts += 1
        remaining = max(0, tok.max_otp_attempts - tok.otp_attempts)
        log.info("kiosk_otp_failed", session_id=str(tok.session_id), remaining=remaining)
        return UnlockFailure(
            reason="locked" if remaining == 0 else "invalid_otp",
            attempts_remaining=remaining,
        )

    # Correct OTP — consume (single use) and decrypt.
    tok.consumed_at = _now()
    result = await db.get(KioskClinicalResult, tok.result_id)
    if result is None:
        raise NotFoundError("Result payload is no longer available.")
    cipher = KioskCipher.from_settings(settings)
    plaintext = cipher.decrypt(
        ciphertext=result.encrypted_payload,
        nonce=result.encryption_nonce,
        key_id=result.key_id,
        aad=str(tok.session_id).encode("utf-8"),
    )
    log.info("kiosk_result_unlocked", session_id=str(tok.session_id))
    return UnlockSuccess(payload=KioskResultPayload.model_validate_json(plaintext))


# --- erasure / data-minimisation reapers ------------------------------------


async def purge_for_whatsapp_session(
    db: AsyncSession, *, whatsapp_session_id: uuid.UUID
) -> int:
    """Delete kiosk sessions linked to a WhatsApp conversation (STOP/erasure).

    Cascades to biometric metadata, encrypted results and tokens. Returns the
    number of kiosk sessions removed.
    """
    result = await db.execute(
        delete(KioskSession).where(
            KioskSession.whatsapp_session_id == whatsapp_session_id
        )
    )
    return result.rowcount or 0


async def expire_stale_sessions(db: AsyncSession) -> int:
    """Mark abandoned pre-capture sessions EXPIRED once past their TTL."""
    result = await db.execute(
        update(KioskSession)
        .where(
            KioskSession.status.in_(list(_EXPIRABLE_STATUSES)),
            KioskSession.expires_at <= _now(),
        )
        .values(status=KioskSessionStatus.EXPIRED)
    )
    return result.rowcount or 0


async def purge_spent_results(db: AsyncSession) -> int:
    """Delete encrypted result payloads once their token is consumed or expired.

    The portal is single-use and 24h-bounded, so a viewed-or-lapsed result has
    no further purpose — dropping the ciphertext shrinks the at-rest health-data
    footprint. The clinician-facing record lives separately on ``toi_assessments``
    and is untouched. Cascades the spent tokens. Returns rows removed.
    """
    spent_result_ids = select(KioskResultToken.result_id).where(
        or_(
            KioskResultToken.consumed_at.is_not(None),
            KioskResultToken.expires_at <= _now(),
        )
    )
    result = await db.execute(
        delete(KioskClinicalResult).where(
            KioskClinicalResult.id.in_(spent_result_ids)
        )
    )
    return result.rowcount or 0
