"""Meta WhatsApp Cloud API payload parsing + webhook signature verification.

Pure functions, no I/O — so the router stays thin and these are unit-testable
against captured Meta payloads. The inbound JSON shape is the documented Cloud
API webhook envelope:

    {"object":"whatsapp_business_account",
     "entry":[{"changes":[{"value":{
        "messages":[{"from":"2637...","id":"wamid...","type":"text",
                     "text":{"body":"hi"}}],
        "contacts":[{"wa_id":"2637...","profile":{"name":"..."}}]}}]}]}

Media messages carry ``{"type":"video","video":{"id":"<media_id>", ...}}``.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InboundMessage:
    """A single normalized inbound WhatsApp message."""

    from_phone: str        # E.164 wa_id of the sender
    message_id: str        # wamid… — used for idempotency
    type: str              # "text" | "video" | "image" | "audio" | …
    text: str | None = None
    media_id: str | None = None
    profile_name: str | None = None


def verify_signature(
    *, app_secret: str, raw_body: bytes, signature_header: str | None
) -> bool:
    """Validate Meta's ``X-Hub-Signature-256: sha256=<hexdigest>`` header.

    HMAC-SHA256 of the *raw* request body keyed with the app secret. Uses a
    constant-time compare. Returns False on any malformed/missing header.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    provided = signature_header.split("=", 1)[1].strip()
    expected = hmac.new(
        app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(provided, expected)


def parse_verification(params: dict[str, str]) -> tuple[bool, str]:
    """Parse the GET verification handshake query params.

    Returns ``(is_subscribe, challenge)``. The router compares the token and,
    if it matches, echoes ``challenge`` back as plain text.
    """
    mode = params.get("hub.mode", "")
    challenge = params.get("hub.challenge", "")
    return mode == "subscribe", challenge


def verification_token(params: dict[str, str]) -> str:
    return params.get("hub.verify_token", "")


def parse_inbound(payload: dict[str, Any]) -> list[InboundMessage]:
    """Extract inbound messages from a Cloud API webhook payload.

    Tolerant by design: status callbacks (delivery/read receipts) and any
    unexpected shapes yield an empty list rather than raising, so the webhook
    can always return 200 quickly.
    """
    out: list[InboundMessage] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            # Map wa_id → profile name from the contacts block, if present.
            names: dict[str, str] = {}
            for contact in value.get("contacts", []) or []:
                wa_id = contact.get("wa_id")
                name = (contact.get("profile") or {}).get("name")
                if wa_id and name:
                    names[wa_id] = name

            for msg in value.get("messages", []) or []:
                from_phone = msg.get("from")
                message_id = msg.get("id")
                mtype = msg.get("type")
                if not (from_phone and message_id and mtype):
                    continue
                text = None
                media_id = None
                if mtype == "text":
                    text = (msg.get("text") or {}).get("body")
                elif mtype in ("video", "image", "audio", "document"):
                    media_id = (msg.get(mtype) or {}).get("id")
                # Interactive replies (buttons/lists) surface as their own type;
                # normalise the selected id/title into text for the engine.
                elif mtype == "interactive":
                    interactive = msg.get("interactive") or {}
                    for key in ("button_reply", "list_reply"):
                        if key in interactive:
                            text = (interactive[key] or {}).get("title") or (
                                interactive[key] or {}
                            ).get("id")
                            break
                out.append(
                    InboundMessage(
                        from_phone=from_phone,
                        message_id=message_id,
                        type=mtype,
                        text=text,
                        media_id=media_id,
                        profile_name=names.get(from_phone),
                    )
                )
    return out
