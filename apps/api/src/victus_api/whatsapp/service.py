"""WhatsApp service: persist conversation state, dedupe, drive the engine.

Maps the :class:`WhatsAppSession` row ⇄ the pure :class:`SessionData`, runs the
conversation engine for one inbound message, persists the new state, and — when
the video arrives — enqueues a :class:`ProcessingJob` for the worker. Returns the
bot replies for the router to send *after* the transaction commits.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.audit.service import write_audit
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    AuditAction,
    ConsentRecord,
    ConsentType,
    User,
    UserRole,
    WhatsAppSession,
)
from victus_api.kiosk import service as kiosk_service
from victus_api.kiosk.security import parse_verification_nonce
from victus_api.whatsapp.conversation import (
    PURGE_COMMANDS,
    ConvState,
    SessionData,
    _parse_yes_no,
    _t,
    advance,
)
from victus_api.whatsapp.meta import InboundMessage
from victus_api.worker.jobs import enqueue, scrub_phone

log = get_logger(__name__)

# Kiosk-linking copy (English; localisation tracks the conversation module).
_KIOSK_LINK_INVALID = (
    "⚠️ That kiosk link is invalid or has expired. Please tap *Start* on the "
    "kiosk screen to get a fresh code."
)
_KIOSK_CONSENT_PROMPT = (
    "👋 You're connecting to a *Victus* kiosk for a free, contactless wellness "
    "check-up. This is a *wellness screening, not a medical diagnosis*. The "
    "kiosk will take a brief face scan to estimate your vitals; no photo or "
    "video is kept. Reply STOP at any time to delete your information.\n\n"
    "Do you consent to continue? (reply YES or NO)"
)
_KIOSK_VERIFIED = (
    "✅ You're verified. Please return to the kiosk screen — it's ready to begin "
    "your check-up. Your results will arrive here when they're ready."
)
_KIOSK_DECLINED = (
    "No problem — nothing will be collected. You can start again at the kiosk "
    "any time. Stay well."
)

# Versioned consent recorded when a WhatsApp participant replies YES — captured
# as formal ConsentRecord rows (not just the session bool) so the consent is
# auditable and the participant falls under the standard consent/erasure model.
WHATSAPP_CONSENT_VERSION = "whatsapp-v1"
WHATSAPP_CONSENT_TYPES: tuple[ConsentType, ...] = (
    ConsentType.TRIAGE,
    ConsentType.TOI_IMAGING,
)


async def _anchor_participant(
    db: AsyncSession, row: WhatsAppSession, *, site_code: str
) -> User:
    """Create a pseudonymous User + versioned consents the first time a phone
    grants consent, and link it to the session.

    The User holds NO PII (email / full_name / phone stay null) — it is purely
    an identity anchor so captures persist to the clinician app and the
    participant is reachable by the standard account-erasure flow. The phone
    lives only on the session (deleted on STOP/erasure) and jobs (scrubbed).

    ``site_code`` is the deployment's configured site (e.g. "NG"), stamped onto
    the anchor exactly as web registration does — so a WhatsApp participant
    resolves to the same data-protection jurisdiction (NG → NDPA) as everyone
    else on that instance, rather than the column default.
    """
    user = User(role=UserRole.PATIENT, is_active=True, site_code=site_code)
    db.add(user)
    await db.flush()
    row.user_id = user.id
    for consent_type in WHATSAPP_CONSENT_TYPES:
        db.add(
            ConsentRecord(
                user_id=user.id,
                consent_type=consent_type,
                version=WHATSAPP_CONSENT_VERSION,
            )
        )
        await write_audit(
            db,
            action=AuditAction.CONSENT_GRANTED,
            actor_id=user.id,
            ip_address=None,
            user_agent="whatsapp",
            resource=f"whatsapp:consent:{user.id}",
            metadata={
                "consent_type": consent_type.value,
                "version": WHATSAPP_CONSENT_VERSION,
                "channel": "WHATSAPP",
            },
        )
    log.info("whatsapp_participant_anchored", user_id=str(user.id))
    return user


def _to_data(row: WhatsAppSession) -> SessionData:
    return SessionData(
        phone=row.phone,
        state=ConvState(row.state),
        language=row.language,
        consent=row.consent,
        intake=dict(row.intake or {}),
        audit_index=row.audit_index,
        safety_triggers=list(row.safety_triggers or []),
        contextual=list(row.contextual or []),
    )


def _apply(row: WhatsAppSession, data: SessionData) -> None:
    row.state = data.state.value
    row.language = data.language
    row.consent = data.consent
    row.intake = dict(data.intake)
    row.audit_index = data.audit_index
    row.safety_triggers = list(data.safety_triggers)
    row.contextual = list(data.contextual)


async def _get_or_create(db: AsyncSession, phone: str) -> WhatsAppSession:
    row = (
        await db.execute(
            select(WhatsAppSession).where(WhatsAppSession.phone == phone)
        )
    ).scalar_one_or_none()
    if row is None:
        row = WhatsAppSession(phone=phone, state=ConvState.LANGUAGE.value)
        db.add(row)
        await db.flush()
    return row


async def _link_kiosk(
    db: AsyncSession,
    row: WhatsAppSession,
    msg: InboundMessage,
    *,
    nonce: str,
) -> list[str]:
    """An inbound ``VICTUS-KIOSK <nonce>`` — bind this phone to that session."""
    row.last_message_id = msg.message_id
    kiosk_row = await kiosk_service.link_session_by_nonce(
        db, nonce=nonce, whatsapp_session=row
    )
    if kiosk_row is None:
        return [_KIOSK_LINK_INVALID]
    row.state = ConvState.KIOSK_CONSENT.value
    row.intake = {**dict(row.intake or {}), "kiosk_session_id": str(kiosk_row.id)}
    log.info("whatsapp_kiosk_linked", phone=msg.from_phone)
    return [_KIOSK_CONSENT_PROMPT]


async def _kiosk_consent(
    db: AsyncSession,
    row: WhatsAppSession,
    msg: InboundMessage,
    *,
    site_code: str,
) -> list[str]:
    """Drive the short consent exchange for a kiosk-linked conversation."""
    row.last_message_id = msg.message_id
    text = msg.text
    ksid = (row.intake or {}).get("kiosk_session_id")
    kiosk_uuid = uuid.UUID(ksid) if ksid else None

    # STOP/DELETE is honoured here too: delete the kiosk session (cascades its
    # biometric/result/token rows), scrub jobs, drop the conversation row.
    if text and text.strip().lower() in PURGE_COMMANDS:
        await kiosk_service.purge_for_whatsapp_session(db, whatsapp_session_id=row.id)
        scrubbed = await scrub_phone(db, msg.from_phone)
        await db.delete(row)
        log.info("whatsapp_session_purged", phone=msg.from_phone, jobs_scrubbed=scrubbed)
        return [_t("purged", row.language)]

    yn = _parse_yes_no(text)
    if yn is None:
        return [_t("retry_yesno", row.language, q=_KIOSK_CONSENT_PROMPT)]
    if not yn:
        if kiosk_uuid is not None:
            await kiosk_service.abort_session(db, session_id=kiosk_uuid)
        row.state = ConvState.DECLINED.value
        return [_KIOSK_DECLINED]

    # Consent granted — anchor the pseudonymous participant (once) and stamp the
    # kiosk session CONSENTED so the terminal can begin capture.
    if row.user_id is None:
        user = await _anchor_participant(db, row, site_code=site_code)
    else:
        user = await db.get(User, row.user_id)
    row.consent = True
    if kiosk_uuid is not None and user is not None:
        await kiosk_service.grant_consent(db, session_id=kiosk_uuid, user=user)
    row.state = ConvState.COMPLETE.value
    return [_KIOSK_VERIFIED]


async def process_inbound(
    db: AsyncSession, msg: InboundMessage, *, site_code: str
) -> list[str]:
    """Advance one message; persist state; enqueue on video. Returns replies.

    Idempotent on ``message_id``: Meta re-delivers, so a message already applied
    to this session is a no-op (returns no replies).

    ``site_code`` is the deployment's configured site, stamped onto the
    pseudonymous participant anchored on first consent.
    """
    row = await _get_or_create(db, msg.from_phone)

    if row.last_message_id is not None and row.last_message_id == msg.message_id:
        log.info("whatsapp_duplicate_ignored", message_id=msg.message_id)
        return []

    # Kiosk rail: a QR-prefilled "VICTUS-KIOSK <nonce>" starts the linking flow
    # from any state; once linked we run a short consent-only exchange (the
    # capture happens at the terminal, not over WhatsApp).
    nonce = parse_verification_nonce(msg.text)
    if nonce is not None:
        return await _link_kiosk(db, row, msg, nonce=nonce)
    if row.state == ConvState.KIOSK_CONSENT.value:
        return await _kiosk_consent(db, row, msg, site_code=site_code)

    data = _to_data(row)
    turn = advance(
        data,
        text=msg.text,
        has_video=(msg.type == "video"),
        media_id=msg.media_id,
        site_code=site_code,
    )

    # STOP/DELETE — erase the session row, scrub this phone's jobs, and delete
    # any linked kiosk session (cascading its biometric/result/token rows), so
    # the "reply STOP to delete your information" promise actually holds.
    if turn.purge:
        await kiosk_service.purge_for_whatsapp_session(db, whatsapp_session_id=row.id)
        scrubbed = await scrub_phone(db, msg.from_phone)
        await db.delete(row)
        log.info("whatsapp_session_purged", phone=msg.from_phone, jobs_scrubbed=scrubbed)
        return turn.replies

    _apply(row, data)
    row.last_message_id = msg.message_id

    # The moment consent is granted, anchor a pseudonymous account + versioned
    # consents (once per participant) so the eventual capture persists and the
    # participant is governable.
    if row.consent and row.user_id is None:
        await _anchor_participant(db, row, site_code=site_code)

    if turn.action is not None:
        await enqueue(
            db,
            media_id=turn.action.media_id,
            wa_phone=msg.from_phone,
            wa_message_id=msg.message_id,
            language=turn.action.language,
            user_id=row.user_id,
            intake=turn.action.intake,
        )
        log.info("whatsapp_capture_enqueued", phone=msg.from_phone)

    return turn.replies
