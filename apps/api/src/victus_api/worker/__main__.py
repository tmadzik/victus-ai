"""Worker CLI entrypoint.

cPanel cron (every minute):
    * * * * * cd /home/victus/api && /home/victus/venv/bin/python -m victus_api.worker --once

cPanel "Setup Python App" (persistent):
    python -m victus_api.worker --loop

Both default to the WhatsApp Cloud fetcher/replier (stubbed until Meta
verification). For local end-to-end testing without WhatsApp, pass
``--local-media`` to treat ``media_id`` as a local file path and print replies
to stdout instead of sending them.
"""

from __future__ import annotations

import argparse
import asyncio

from victus_api.core.logging import get_logger
from victus_api.worker.config import WorkerConfig
from victus_api.worker.media import LocalFileMediaFetcher, WhatsAppCloudMediaFetcher
from victus_api.worker.reply import Replier, WhatsAppCloudReplier
from victus_api.worker.runner import run_loop, run_once

log = get_logger(__name__)


class _StdoutReplier:
    """Prints replies instead of sending them (local demo)."""

    async def send_text(self, *, to: str, text: str) -> None:
        print(f"\n--- reply to {to} ---\n{text}\n")


def _build_io(args: argparse.Namespace):  # noqa: ANN202 - simple CLI helper
    import os

    if args.local_media:
        return LocalFileMediaFetcher(), _StdoutReplier()
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    fetcher = WhatsAppCloudMediaFetcher(access_token=token)
    replier: Replier = WhatsAppCloudReplier(
        access_token=token, phone_number_id=phone_id
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
    fetcher, replier = _build_io(args)

    if args.once:
        handled = asyncio.run(run_once(cfg, fetcher=fetcher, replier=replier))
        log.info("worker_run_once_complete", handled=handled)
        return 0

    asyncio.run(run_loop(cfg, fetcher=fetcher, replier=replier))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
