"""Unit tests for the Meta WhatsApp Cloud clients + the worker's rail gating.

No live network: every HTTP call is served by an ``httpx.MockTransport`` so we
assert on the exact request the clients would send Meta, and on the failure
model, without ever leaving the process. The gating tests lock down that the
worker never constructs a live client while the rail is off.
"""

from __future__ import annotations

import argparse
import json

import httpx
import pytest

from victus_api.worker.__main__ import (
    _build_io,
    _DisabledMediaFetcher,
    _StdoutReplier,
)
from victus_api.worker.config import WorkerConfig
from victus_api.worker.media import (
    LocalFileMediaFetcher,
    WhatsAppCloudMediaFetcher,
    _ext_for_mime,
)
from victus_api.worker.reply import WhatsAppCloudReplier
from victus_api.worker.whatsapp_client import (
    WhatsAppApiError,
    WhatsAppNotConfiguredError,
)

# --- replier -----------------------------------------------------------------


async def test_replier_posts_expected_request() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.OUT"}]})

    replier = WhatsAppCloudReplier(
        access_token="TESTTOKEN",
        phone_number_id="PN123",
        base_url="https://graph.example.test",
        transport=httpx.MockTransport(handler),
    )
    await replier.send_text(to="263771234567", text="Your results are ready.")

    assert seen["url"] == "https://graph.example.test/v21.0/PN123/messages"
    assert seen["auth"] == "Bearer TESTTOKEN"
    assert seen["body"] == {
        "messaging_product": "whatsapp",
        "to": "263771234567",
        "type": "text",
        "text": {"body": "Your results are ready."},
    }


async def test_replier_raises_on_non_2xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad token"}})

    replier = WhatsAppCloudReplier(
        access_token="x",
        phone_number_id="PN",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(WhatsAppApiError) as ei:
        await replier.send_text(to="1", text="hi")
    assert ei.value.status_code == 401


async def test_replier_requires_credentials() -> None:
    replier = WhatsAppCloudReplier(access_token="", phone_number_id="")
    with pytest.raises(WhatsAppNotConfiguredError):
        await replier.send_text(to="1", text="hi")


# --- media fetcher -----------------------------------------------------------


def _media_handler(
    *, media_bytes: bytes, mime: str = "video/mp4", file_size: int | None = None
):
    """A two-endpoint handler: /{id} resolves to a CDN url, then the CDN url
    serves the bytes."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "cdn.example.test":
            assert request.headers.get("authorization") == "Bearer TESTTOKEN"
            return httpx.Response(200, content=media_bytes)
        if request.url.path.endswith("/MEDIA42"):
            body = {"url": "https://cdn.example.test/blob/download", "mime_type": mime}
            if file_size is not None:
                body["file_size"] = file_size
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    return handler


async def test_media_fetch_two_step_writes_file(tmp_path) -> None:
    payload = b"\x00\x01fake-mp4-bytes"
    fetcher = WhatsAppCloudMediaFetcher(
        access_token="TESTTOKEN",
        base_url="https://graph.example.test",
        transport=httpx.MockTransport(_media_handler(media_bytes=payload)),
    )
    path = await fetcher.fetch(media_id="MEDIA42", dest_dir=str(tmp_path))
    assert path.endswith("MEDIA42.mp4")
    with open(path, "rb") as fh:
        assert fh.read() == payload


async def test_media_fetch_extension_from_mime(tmp_path) -> None:
    fetcher = WhatsAppCloudMediaFetcher(
        access_token="TESTTOKEN",
        base_url="https://graph.example.test",
        transport=httpx.MockTransport(
            _media_handler(media_bytes=b"x", mime="video/quicktime")
        ),
    )
    path = await fetcher.fetch(media_id="MEDIA42", dest_dir=str(tmp_path))
    assert path.endswith(".mov")


async def test_media_fetch_rejects_oversized_from_metadata(tmp_path) -> None:
    fetcher = WhatsAppCloudMediaFetcher(
        access_token="TESTTOKEN",
        base_url="https://graph.example.test",
        max_bytes=1024,
        transport=httpx.MockTransport(
            _media_handler(media_bytes=b"x" * 10, file_size=2048)
        ),
    )
    with pytest.raises(WhatsAppApiError) as ei:
        await fetcher.fetch(media_id="MEDIA42", dest_dir=str(tmp_path))
    assert ei.value.status_code == 413


async def test_media_fetch_raises_on_resolve_error(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "unknown media"}})

    fetcher = WhatsAppCloudMediaFetcher(
        access_token="TESTTOKEN",
        base_url="https://graph.example.test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(WhatsAppApiError):
        await fetcher.fetch(media_id="MEDIA42", dest_dir=str(tmp_path))


async def test_media_fetch_requires_token(tmp_path) -> None:
    fetcher = WhatsAppCloudMediaFetcher(access_token="")
    with pytest.raises(WhatsAppNotConfiguredError):
        await fetcher.fetch(media_id="MEDIA42", dest_dir=str(tmp_path))


def test_ext_for_mime() -> None:
    assert _ext_for_mime("video/mp4") == ".mp4"
    assert _ext_for_mime("video/mp4; codecs=avc1") == ".mp4"
    assert _ext_for_mime("video/quicktime") == ".mov"
    assert _ext_for_mime(None) == ".mp4"
    assert _ext_for_mime("application/weird") == ".mp4"


# --- rail gating in the worker composition root ------------------------------


def _args(*, local_media: bool = False) -> argparse.Namespace:
    return argparse.Namespace(once=True, loop=False, local_media=local_media)


def test_build_io_disabled_uses_safe_fakes() -> None:
    cfg = WorkerConfig(whatsapp_enabled=False)
    fetcher, replier = _build_io(_args(), cfg)
    assert isinstance(fetcher, _DisabledMediaFetcher)
    assert isinstance(replier, _StdoutReplier)


def test_build_io_enabled_but_missing_creds_stays_disabled() -> None:
    cfg = WorkerConfig(whatsapp_enabled=True, whatsapp_access_token="")
    fetcher, replier = _build_io(_args(), cfg)
    assert isinstance(fetcher, _DisabledMediaFetcher)
    assert isinstance(replier, _StdoutReplier)


def test_build_io_enabled_and_configured_uses_cloud_clients() -> None:
    cfg = WorkerConfig(
        whatsapp_enabled=True,
        whatsapp_access_token="TOK",
        whatsapp_phone_number_id="PN",
    )
    fetcher, replier = _build_io(_args(), cfg)
    assert isinstance(fetcher, WhatsAppCloudMediaFetcher)
    assert isinstance(replier, WhatsAppCloudReplier)


def test_build_io_local_media_flag_wins() -> None:
    cfg = WorkerConfig(
        whatsapp_enabled=True,
        whatsapp_access_token="TOK",
        whatsapp_phone_number_id="PN",
    )
    fetcher, replier = _build_io(_args(local_media=True), cfg)
    assert isinstance(fetcher, LocalFileMediaFetcher)
    assert isinstance(replier, _StdoutReplier)


async def test_disabled_media_fetcher_raises() -> None:
    with pytest.raises(RuntimeError):
        await _DisabledMediaFetcher().fetch(media_id="x", dest_dir="/tmp")


def test_config_reads_rail_env(monkeypatch) -> None:
    monkeypatch.setenv("WHATSAPP_SEND_ENABLED", "true")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "abc")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "999")
    monkeypatch.setenv("WHATSAPP_API_VERSION", "v22.0")
    cfg = WorkerConfig.from_env()
    assert cfg.whatsapp_enabled is True
    assert cfg.whatsapp_access_token == "abc"
    assert cfg.whatsapp_phone_number_id == "999"
    assert cfg.whatsapp_api_version == "v22.0"
