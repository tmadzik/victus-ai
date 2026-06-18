"""Select the outbound replier based on WhatsApp configuration.

* Token present  → ``WhatsAppCloudReplier`` (production send; currently stubbed
  until Meta verification — its ``send_text`` raises, and the router suppresses
  that so conversation state still advances during the pre-Meta build).
* No token       → ``LoggingReplier`` (local dev): replies are logged, not sent,
  so the full flow is exercisable end-to-end without WhatsApp.
"""

from __future__ import annotations

from victus_api.core.logging import get_logger
from victus_api.whatsapp.config import WhatsAppConfig
from victus_api.worker.reply import Replier, WhatsAppCloudReplier

log = get_logger(__name__)


class LoggingReplier:
    """Logs outbound replies instead of sending (no WhatsApp credentials)."""

    async def send_text(self, *, to: str, text: str) -> None:
        log.info("whatsapp_reply_local", to=to, text=text)


def build_replier(config: WhatsAppConfig) -> Replier:
    if config.access_token and config.phone_number_id:
        return WhatsAppCloudReplier(
            access_token=config.access_token,
            phone_number_id=config.phone_number_id,
            api_version=config.api_version,
        )
    return LoggingReplier()
