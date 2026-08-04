"""Shared plumbing for the Meta WhatsApp Cloud API clients.

The replier (outbound text) and the media fetcher (inbound video download) both
talk to ``graph.facebook.com`` with the same bearer auth and the same failure
model, so the small pieces they share — the base URL, the auth header, and the
error types — live here. Each client owns only its own endpoint shape.

Network use is gated one level up (``WorkerConfig.whatsapp_enabled`` +
``__main__._build_io``): these clients are constructed only when the rail is
switched on, so importing this module never implies a live call.
"""

from __future__ import annotations

import httpx

# Meta versions the Graph API in the path (``/v21.0/...``). Pin a known-good
# default; override per host with WHATSAPP_API_VERSION when Meta deprecates it.
DEFAULT_API_VERSION = "v21.0"
DEFAULT_GRAPH_BASE_URL = "https://graph.facebook.com"
DEFAULT_TIMEOUT_S = 30.0


class WhatsAppNotConfiguredError(RuntimeError):
    """A Cloud client was used without the credentials it needs.

    Raised eagerly (before any network call) so a half-configured deployment
    fails loudly instead of silently POSTing an empty bearer token.
    """


class WhatsAppApiError(RuntimeError):
    """Meta returned a non-2xx response. Carries the status + a truncated body
    for the logs (never the bearer token, which is only ever in the header)."""

    def __init__(self, *, operation: str, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"WhatsApp {operation} failed: HTTP {status_code} — {body[:300]}")


def auth_headers(token: str) -> dict[str, str]:
    """The bearer header every Cloud API call carries (including the media CDN
    download, which also requires the token)."""
    return {"Authorization": f"Bearer {token}"}


def build_async_client(
    *, timeout_s: float, transport: httpx.AsyncBaseTransport | None
) -> httpx.AsyncClient:
    """One place to construct the client so ``transport`` injection (an
    ``httpx.MockTransport`` in tests) works identically for both clients."""
    return httpx.AsyncClient(timeout=timeout_s, transport=transport)
