"""Media-fetch abstraction: get a downloaded video file for a job.

The WhatsApp Cloud API hands us a *media id*, not bytes. Downloading is a
two-step authenticated call (resolve id → URL, then GET the URL with the bearer
token). We hide that behind a small protocol so:

* the runner depends only on ``MediaFetcher`` (testable with a local-file fake);
* the real Cloud API client is the only place that knows Meta's endpoints;
* the kiosk rail can supply its own fetcher later without touching the runner.
"""

from __future__ import annotations

import shutil
from pathlib import Path
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

# WhatsApp caps video at 16 MB; allow headroom, but refuse anything larger so a
# hostile/oversized media id can't exhaust the cPanel account's disk or memory.
DEFAULT_MEDIA_MAX_BYTES = 32 * 1024 * 1024

# Minimal mime → extension map for the container formats WhatsApp sends; the
# processor sniffs the real codec, so this only needs to give ffmpeg a sensible
# suffix to work with.
_MIME_EXT = {
    "video/mp4": ".mp4",
    "video/3gpp": ".3gp",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
}


class MediaFetcher(Protocol):
    """Resolve a job's media to a local file path, returning the path."""

    async def fetch(self, *, media_id: str, dest_dir: str) -> str: ...


class LocalFileMediaFetcher:
    """Test/dev fetcher: treat ``media_id`` as an existing local file path.

    Copies it into ``dest_dir`` so the purge-on-done logic has something it owns
    to delete (and never deletes the caller's original).
    """

    async def fetch(self, *, media_id: str, dest_dir: str) -> str:
        src = Path(media_id)
        if not src.is_file():
            raise FileNotFoundError(f"media not found: {media_id}")
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        dest = Path(dest_dir) / src.name
        shutil.copyfile(src, dest)
        return str(dest)


def _ext_for_mime(mime: str | None) -> str:
    """Map a mime type to a file suffix, stripping any ``; codecs=…`` params.
    Defaults to ``.mp4`` — the overwhelmingly common WhatsApp video container."""
    if not mime:
        return ".mp4"
    return _MIME_EXT.get(mime.split(";")[0].strip().lower(), ".mp4")


class WhatsAppCloudMediaFetcher:
    """Production fetcher for the Meta WhatsApp Cloud API.

    Downloading is two authenticated calls:

        1. GET {base}/{ver}/{media_id}  (Bearer token)
           → JSON ``{"url": "...", "mime_type": "...", ...}``
        2. GET that url with the same Bearer token → raw bytes
        3. write bytes to ``dest_dir`` and return the path

    Off by default: the worker constructs this only when the rail is enabled and
    credentials are present (see ``__main__._build_io``). Downloads over
    ``max_bytes`` are refused. ``transport`` is for tests (``MockTransport``).
    """

    def __init__(
        self,
        *,
        access_token: str,
        api_version: str = DEFAULT_API_VERSION,
        base_url: str = DEFAULT_GRAPH_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_bytes: int = DEFAULT_MEDIA_MAX_BYTES,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = access_token
        self._api_version = api_version
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._max_bytes = max_bytes
        self._transport = transport

    async def fetch(self, *, media_id: str, dest_dir: str) -> str:
        if not self._token:
            raise WhatsAppNotConfiguredError(
                "WhatsAppCloudMediaFetcher needs WHATSAPP_ACCESS_TOKEN."
            )
        headers = auth_headers(self._token)
        async with build_async_client(
            timeout_s=self._timeout_s, transport=self._transport
        ) as client:
            # 1. Resolve the media id to a short-lived, authenticated CDN URL.
            meta_resp = await client.get(
                f"{self._base_url}/{self._api_version}/{media_id}", headers=headers
            )
            if not meta_resp.is_success:
                raise WhatsAppApiError(
                    operation="media_resolve",
                    status_code=meta_resp.status_code,
                    body=meta_resp.text,
                )
            info = meta_resp.json()
            media_url = info.get("url")
            if not media_url:
                raise WhatsAppApiError(
                    operation="media_resolve",
                    status_code=meta_resp.status_code,
                    body="response missing 'url'",
                )
            self._guard_size(info.get("file_size"))
            # 2. Download the bytes (the CDN url also requires the bearer token).
            bin_resp = await client.get(media_url, headers=headers)
            if not bin_resp.is_success:
                raise WhatsAppApiError(
                    operation="media_download",
                    status_code=bin_resp.status_code,
                    body=bin_resp.text,
                )
            content = bin_resp.content
            self._guard_size(len(content))

        # 3. Write to the scratch dir under a name derived from the media id.
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        dest = Path(dest_dir) / f"{media_id}{_ext_for_mime(info.get('mime_type'))}"
        dest.write_bytes(content)
        log.info("whatsapp_media_fetched", media_id=media_id, bytes=len(content))
        return str(dest)

    def _guard_size(self, size: object) -> None:
        """Refuse oversized media as early as we know the size (from the resolve
        metadata, then again from the downloaded length)."""
        if isinstance(size, int) and size > self._max_bytes:
            raise WhatsAppApiError(
                operation="media_download",
                status_code=413,
                body=f"media {size} bytes exceeds cap {self._max_bytes}",
            )
