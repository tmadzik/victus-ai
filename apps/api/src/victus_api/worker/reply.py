"""Reply abstraction: send a text message back to the user.

Same dependency-inversion rationale as ``media``: the runner depends on
``Replier`` only. Tests use ``InMemoryReplier`` to assert on what was sent; the
WhatsApp Cloud sender is the only place that knows Meta's message endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from victus_api.core.logging import get_logger
from victus_api.worker.whatsapp_client import (
    DEFAULT_API_VERSION,
    DEFAULT_GRAPH_BASE_URL,
    DEFAULT_TIMEOUT_S,
    WhatsAppApiError,
    WhatsAppNotConfiguredError,
    auth_headers,
    build_async_client,
)

log = get_logger(__name__)


class Replier(Protocol):
    """Send ``text`` to the recipient identified by ``to`` (E.164 phone)."""

    async def send_text(self, *, to: str, text: str) -> None: ...


@dataclass
class InMemoryReplier:
    """Captures outbound messages for tests and local demos."""

    sent: list[tuple[str, str]] = field(default_factory=list)

    async def send_text(self, *, to: str, text: str) -> None:
        self.sent.append((to, text))


class WhatsAppCloudReplier:
    """Production sender for the Meta WhatsApp Cloud API.

    One POST per reply:

        POST {base}/{ver}/{phone_number_id}/messages
        Authorization: Bearer {token}
        {"messaging_product":"whatsapp","to":to,
         "type":"text","text":{"body":text}}

    Within the 24-hour customer-service window (the user messaged us first) a
    free-form text reply needs no pre-approved template.

    Off by default: the worker only constructs this client when
    ``WHATSAPP_SEND_ENABLED`` is set and credentials are present (see
    ``__main__._build_io``). ``transport`` exists for tests (an
    ``httpx.MockTransport``); production leaves it ``None``.
    """

    def __init__(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        api_version: str = DEFAULT_API_VERSION,
        base_url: str = DEFAULT_GRAPH_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = access_token
        self._phone_number_id = phone_number_id
        self._api_version = api_version
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._transport = transport

    async def send_text(self, *, to: str, text: str) -> None:
        if not self._token or not self._phone_number_id:
            raise WhatsAppNotConfiguredError(
                "WhatsAppCloudReplier needs WHATSAPP_ACCESS_TOKEN and "
                "WHATSAPP_PHONE_NUMBER_ID."
            )
        url = f"{self._base_url}/{self._api_version}/{self._phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        async with build_async_client(
            timeout_s=self._timeout_s, transport=self._transport
        ) as client:
            resp = await client.post(
                url, json=payload, headers=auth_headers(self._token)
            )
        if not resp.is_success:
            raise WhatsAppApiError(
                operation="send_text", status_code=resp.status_code, body=resp.text
            )
        log.info("whatsapp_reply_sent", to=to, chars=len(text))
