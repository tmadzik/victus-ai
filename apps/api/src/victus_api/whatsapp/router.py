"""WhatsApp Cloud API webhook endpoints.

GET  /whatsapp/webhook  — Meta verification handshake (echo the challenge).
POST /whatsapp/webhook  — inbound messages: verify signature, advance the
                          conversation, enqueue captures, reply.

The POST handler returns 200 quickly and never raises to Meta (a 5xx triggers
aggressive re-delivery). Reply sending happens after the DB transaction commits
so we never message a user about state that did not persist; send failures are
logged, not surfaced. Heavy work (video) is deferred to the worker via the queue.
"""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import PlainTextResponse

from victus_api.core.logging import get_logger
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

    for msg in messages:
        try:
            async with session_scope() as db:
                replies = await process_inbound(db, msg)
            # Send only after commit — never announce unpersisted state.
            for text in replies:
                with contextlib.suppress(Exception):
                    await replier.send_text(to=msg.from_phone, text=text)
        except Exception:
            # One bad message must not fail the batch or trigger Meta retries.
            log.warning(
                "whatsapp_inbound_failed",
                message_id=msg.message_id,
                exc_info=True,
            )

    return Response(status_code=status.HTTP_200_OK)
