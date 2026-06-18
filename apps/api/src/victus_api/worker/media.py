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


class WhatsAppCloudMediaFetcher:
    """Production fetcher for the Meta WhatsApp Cloud API.

    Stubbed until Meta business verification completes (plan Phase 0). The
    implementation is intentionally documented here so wiring it later is
    mechanical:

        1. GET https://graph.facebook.com/{ver}/{media_id}  (Bearer token)
           → JSON ``{"url": "...", "mime_type": "...", ...}``
        2. GET that url with the same Bearer token → raw bytes
        3. write bytes to ``dest_dir`` and return the path

    Use the already-vendored ``httpx`` (an existing API dependency).
    """

    def __init__(self, *, access_token: str, api_version: str = "v21.0") -> None:
        self._token = access_token
        self._api_version = api_version

    async def fetch(self, *, media_id: str, dest_dir: str) -> str:
        raise NotImplementedError(
            "WhatsAppCloudMediaFetcher is pending Meta verification "
            "(Demonstrator plan Phase 0). Use LocalFileMediaFetcher for now."
        )
