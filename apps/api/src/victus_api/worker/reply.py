"""Reply abstraction: send a text message back to the user.

Same dependency-inversion rationale as ``media``: the runner depends on
``Replier`` only. Tests use ``InMemoryReplier`` to assert on what was sent; the
WhatsApp Cloud sender is the only place that knows Meta's message endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


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

    Stubbed until Meta verification completes. Wiring later is a single POST:

        POST https://graph.facebook.com/{ver}/{phone_number_id}/messages
        Authorization: Bearer {token}
        {"messaging_product":"whatsapp","to":to,
         "type":"text","text":{"body":text}}

    Within the 24-hour customer-service window (the user messaged us first) a
    free-form text reply needs no pre-approved template.
    """

    def __init__(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        api_version: str = "v21.0",
    ) -> None:
        self._token = access_token
        self._phone_number_id = phone_number_id
        self._api_version = api_version

    async def send_text(self, *, to: str, text: str) -> None:
        raise NotImplementedError(
            "WhatsAppCloudReplier is pending Meta verification "
            "(Demonstrator plan Phase 0). Use InMemoryReplier for now."
        )
