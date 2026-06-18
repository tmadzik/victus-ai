"""WhatsApp Cloud API configuration, read from the environment.

Standalone (like ``worker.config``) so it does not expand the validated app
``Settings`` surface. Populate these once Meta business verification completes
(Demonstrator plan Phase 0):

* ``WHATSAPP_VERIFY_TOKEN``     — arbitrary string you also enter in the Meta
                                  webhook setup; checked on the GET handshake.
* ``WHATSAPP_APP_SECRET``       — Meta app secret; verifies POST signatures.
* ``WHATSAPP_ACCESS_TOKEN``     — permanent token for media download + sending.
* ``WHATSAPP_PHONE_NUMBER_ID``  — the sending number's id.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WhatsAppConfig:
    verify_token: str = ""
    app_secret: str = ""
    access_token: str = ""
    phone_number_id: str = ""
    api_version: str = "v21.0"
    # When False (no app secret configured, e.g. local dev), signature checks
    # are skipped so the flow can be exercised without Meta. NEVER ship True-off
    # in production — guarded by the app secret being present.
    require_signature: bool = True

    @classmethod
    def from_env(cls) -> WhatsAppConfig:
        app_secret = os.environ.get("WHATSAPP_APP_SECRET", "")
        return cls(
            verify_token=os.environ.get("WHATSAPP_VERIFY_TOKEN", ""),
            app_secret=app_secret,
            access_token=os.environ.get("WHATSAPP_ACCESS_TOKEN", ""),
            phone_number_id=os.environ.get("WHATSAPP_PHONE_NUMBER_ID", ""),
            api_version=os.environ.get("WHATSAPP_API_VERSION", cls.api_version),
            # Only enforce signatures when we actually hold the secret.
            require_signature=bool(app_secret),
        )
