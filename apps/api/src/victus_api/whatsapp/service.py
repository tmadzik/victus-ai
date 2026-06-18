"""WhatsApp service: persist conversation state, dedupe, drive the engine.

Maps the :class:`WhatsAppSession` row ⇄ the pure :class:`SessionData`, runs the
conversation engine for one inbound message, persists the new state, and — when
the video arrives — enqueues a :class:`ProcessingJob` for the worker. Returns the
bot replies for the router to send *after* the transaction commits.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.core.logging import get_logger
from victus_api.db.models import WhatsAppSession
from victus_api.whatsapp.conversation import ConvState, SessionData, advance
from victus_api.whatsapp.meta import InboundMessage
from victus_api.worker.jobs import enqueue, scrub_phone

log = get_logger(__name__)


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


async def process_inbound(
    db: AsyncSession, msg: InboundMessage
) -> list[str]:
    """Advance one message; persist state; enqueue on video. Returns replies.

    Idempotent on ``message_id``: Meta re-delivers, so a message already applied
    to this session is a no-op (returns no replies).
    """
    row = await _get_or_create(db, msg.from_phone)

    if row.last_message_id is not None and row.last_message_id == msg.message_id:
        log.info("whatsapp_duplicate_ignored", message_id=msg.message_id)
        return []

    data = _to_data(row)
    turn = advance(
        data,
        text=msg.text,
        has_video=(msg.type == "video"),
        media_id=msg.media_id,
    )

    # STOP/DELETE — erase the session row and scrub this phone's jobs, so the
    # "reply STOP to delete your information" promise actually holds.
    if turn.purge:
        scrubbed = await scrub_phone(db, msg.from_phone)
        await db.delete(row)
        log.info("whatsapp_session_purged", phone=msg.from_phone, jobs_scrubbed=scrubbed)
        return turn.replies

    _apply(row, data)
    row.last_message_id = msg.message_id

    if turn.action is not None:
        await enqueue(
            db,
            media_id=turn.action.media_id,
            wa_phone=msg.from_phone,
            wa_message_id=msg.message_id,
            language=turn.action.language,
            intake=turn.action.intake,
        )
        log.info("whatsapp_capture_enqueued", phone=msg.from_phone)

    return turn.replies
