"""Worker CLI entrypoint.

cPanel cron (every minute):
    * * * * * cd /home/victus/api && /home/victus/venv/bin/python -m victus_api.worker --once

cPanel "Setup Python App" (persistent):
    python -m victus_api.worker --loop

The WhatsApp Cloud rail is off by default. Set ``WHATSAPP_SEND_ENABLED=true``
(with ``WHATSAPP_ACCESS_TOKEN`` and ``WHATSAPP_PHONE_NUMBER_ID``) to send/receive
via Meta once business verification lands; until then the worker logs a warning
and never calls Meta. For local end-to-end testing, pass ``--local-media`` to
treat ``media_id`` as a local file path and print replies to stdout.
"""

from __future__ import annotations

import argparse
import asyncio

from victus_api.core.logging import get_logger
from victus_api.worker.config import WorkerConfig
from victus_api.worker.kiosk_runner import run_kiosk_loop, run_kiosk_once
from victus_api.worker.media import (
    LocalFileMediaFetcher,
    MediaFetcher,
    WhatsAppCloudMediaFetcher,
)
from victus_api.worker.reply import Replier, WhatsAppCloudReplier
from victus_api.worker.runner import run_loop, run_once

log = get_logger(__name__)


class _StdoutReplier:
    """Prints replies instead of sending them (local demo)."""

    async def send_text(self, *, to: str, text: str) -> None:
        print(f"\n--- reply to {to} ---\n{text}\n")


class _DisabledMediaFetcher:
    """Used when the WhatsApp rail is off: any attempt to download real Cloud
    media fails loudly (and the job is retried/failed) rather than silently
    doing nothing. There should be no WhatsApp media jobs while the rail is off,
    so this is a safety net, not an expected path."""

    async def fetch(self, *, media_id: str, dest_dir: str) -> str:
        raise RuntimeError(
            "WhatsApp rail is disabled (set WHATSAPP_SEND_ENABLED=true with "
            "credentials to enable Cloud API downloads)."
        )


def _build_io(
    args: argparse.Namespace, cfg: WorkerConfig
) -> tuple[MediaFetcher, Replier]:
    if args.local_media:
        return LocalFileMediaFetcher(), _StdoutReplier()
    if not cfg.whatsapp_enabled:
        log.warning(
            "whatsapp_rail_disabled",
            reason="WHATSAPP_SEND_ENABLED not set; no messages will reach Meta",
        )
        return _DisabledMediaFetcher(), _StdoutReplier()
    if not (cfg.whatsapp_access_token and cfg.whatsapp_phone_number_id):
        log.error(
            "whatsapp_rail_misconfigured",
            reason="WHATSAPP_SEND_ENABLED is on but token/phone_number_id missing",
        )
        return _DisabledMediaFetcher(), _StdoutReplier()
    log.info("whatsapp_rail_enabled", api_version=cfg.whatsapp_api_version)
    fetcher = WhatsAppCloudMediaFetcher(
        access_token=cfg.whatsapp_access_token,
        api_version=cfg.whatsapp_api_version,
        base_url=cfg.whatsapp_graph_base_url,
        timeout_s=cfg.http_timeout_s,
    )
    replier: Replier = WhatsAppCloudReplier(
        access_token=cfg.whatsapp_access_token,
        phone_number_id=cfg.whatsapp_phone_number_id,
        api_version=cfg.whatsapp_api_version,
        base_url=cfg.whatsapp_graph_base_url,
        timeout_s=cfg.http_timeout_s,
    )
    return fetcher, replier


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="victus-worker")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="drain queue and exit")
    mode.add_argument("--loop", action="store_true", help="poll forever")
    parser.add_argument(
        "--local-media",
        action="store_true",
        help="treat media_id as a local file path; print replies to stdout",
    )
    args = parser.parse_args(argv)

    cfg = WorkerConfig.from_env()
    fetcher, replier = _build_io(args, cfg)

    if args.once:

        async def _drain() -> tuple[int, int]:
            wa = await run_once(cfg, fetcher=fetcher, replier=replier)
            kiosk = await run_kiosk_once(cfg, replier=replier)
            return wa, kiosk

        whatsapp_handled, kiosk_handled = asyncio.run(_drain())
        log.info(
            "worker_run_once_complete",
            whatsapp=whatsapp_handled,
            kiosk=kiosk_handled,
        )
        return 0

    async def _loops() -> None:
        # The WhatsApp (media) and kiosk (derived-signal) queues are independent
        # channels; poll both concurrently in the persistent worker.
        await asyncio.gather(
            run_loop(cfg, fetcher=fetcher, replier=replier),
            run_kiosk_loop(cfg, replier=replier),
        )

    asyncio.run(_loops())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
