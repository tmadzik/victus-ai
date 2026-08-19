"""WhatsApp Cloud API webhook endpoints.

GET  /whatsapp/webhook  — Meta verification handshake (echo the challenge).
POST /whatsapp/webhook  — inbound messages: verify signature, advance the
                          conversation, enqueue captures, reply.

The POST handler returns 200 quickly and never raises to Meta (a 5xx triggers
aggressive re-delivery of a turn we have already committed). Reply sending
happens after the DB transaction commits so we never message a user about state
that did not persist; send failures are logged at ERROR and never surfaced to
Meta. Heavy work (video) is deferred to the worker via the queue.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import PlainTextResponse

from victus_api.config import get_settings
from victus_api.core.logging import get_logger, redact_phone
from victus_api.db.session import session_scope
from victus_api.whatsapp.config import WhatsAppConfig
from victus_api.whatsapp.meta import (
    parse_inbound,
    parse_verification,
    verification_token,
    verify_signature,
)
from victus_api.whatsapp.reply_factory import build_replier
from victus_api.whatsapp.service import process_inbound
from victus_api.worker.reply import Replier

log = get_logger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

_config = WhatsAppConfig.from_env()


@router.get("/webhook", include_in_schema=False)
async def verify(request: Request) -> Response:
    """Meta GET verification: echo ``hub.challenge`` iff the token matches."""
    params = dict(request.query_params)
    is_subscribe, challenge = parse_verification(params)
    if is_subscribe and verification_token(params) == _config.verify_token:
        return PlainTextResponse(challenge, status_code=status.HTTP_200_OK)
    return PlainTextResponse(
        "verification failed", status_code=status.HTTP_403_FORBIDDEN
    )


async def _send_replies(
    replier: Replier, *, to: str, replies: Sequence[str], message_id: str
) -> None:
    """Deliver one turn's replies, stopping at the first failure.

    A send failure must not propagate: raising here would 500 the webhook, and
    Meta answers a 5xx by re-delivering the message — replaying a conversation
    turn whose state has already been committed. But it must not be silent
    either. The state *is* committed by the time we send, so a swallowed
    failure leaves a participant waiting for a message the database believes
    they received, with nothing anywhere recording the discrepancy. That is a
    WhatsApp rail that is entirely dead while every dashboard reads healthy.

    Stopping at the first failure is deliberate rather than lazy. The causes
    that matter in production — an expired token, a lapsed 24-hour customer
    service window, a 429 — apply to every reply in the turn, so continuing
    only adds doomed requests to a rail that is already refusing them, and
    under a 429 that is actively counterproductive.
    """
    for index, text in enumerate(replies):
        try:
            await replier.send_text(to=to, text=text)
        except Exception as exc:
            log.error(
                "whatsapp_reply_send_failed",
                message_id=message_id,
                to=redact_phone(to),
                reply_index=index,
                undelivered=len(replies) - index,
                # Present on WhatsAppApiError; the status is what separates a
                # dead token (401) from a closed window (4xx) from throttling
                # (429) without reading the body.
                status_code=getattr(exc, "status_code", None),
                exc_info=True,
            )
            return


@router.post("/webhook")
async def inbound(request: Request) -> Response:
    """Inbound messages from Meta. Always 200 (unless signature fails)."""
    raw = await request.body()

    if _config.require_signature:
        sig = request.headers.get("X-Hub-Signature-256")
        if not verify_signature(
            app_secret=_config.app_secret, raw_body=raw, signature_header=sig
        ):
            log.warning("whatsapp_signature_invalid")
            return Response(status_code=status.HTTP_403_FORBIDDEN)

    try:
        payload = await request.json()
    except Exception:
        # Malformed body — ack so Meta does not hammer us; nothing to do.
        return Response(status_code=status.HTTP_200_OK)

    messages = parse_inbound(payload)
    replier = build_replier(_config)
    site_code = get_settings().site_code

    for msg in messages:
        try:
            async with session_scope() as db:
                replies = await process_inbound(db, msg, site_code=site_code)
            # Send only after commit — never announce unpersisted state.
            await _send_replies(
                replier,
                to=msg.from_phone,
                replies=replies,
                message_id=msg.message_id,
            )
        except Exception:
            # One bad message must not fail the batch or trigger Meta retries.
            log.warning(
                "whatsapp_inbound_failed",
                message_id=msg.message_id,
                exc_info=True,
            )

    return Response(status_code=status.HTTP_200_OK)
