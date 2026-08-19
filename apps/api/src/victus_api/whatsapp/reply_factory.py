"""Select the outbound replier based on WhatsApp configuration.

* Credentials present → ``WhatsAppCloudReplier``: a real POST to Meta's Graph
  API. Failures raise, and ``router._send_replies`` logs them at ERROR without
  failing the webhook.
* No credentials      → ``LoggingReplier`` (local dev): replies are logged, not
  sent, so the full conversation is exercisable end-to-end without WhatsApp.
"""

from __future__ import annotations

from victus_api.core.logging import get_logger, redact_phone
from victus_api.whatsapp.config import WhatsAppConfig
from victus_api.worker.reply import Replier, WhatsAppCloudReplier

log = get_logger(__name__)


class LoggingReplier:
    """Logs outbound replies instead of sending (no WhatsApp credentials)."""

    async def send_text(self, *, to: str, text: str) -> None:
        log.info("whatsapp_reply_local", to=redact_phone(to), text=text)


def build_replier(config: WhatsAppConfig) -> Replier:
    if config.access_token and config.phone_number_id:
        return WhatsAppCloudReplier(
            access_token=config.access_token,
            phone_number_id=config.phone_number_id,
            api_version=config.api_version,
        )
    return LoggingReplier()
