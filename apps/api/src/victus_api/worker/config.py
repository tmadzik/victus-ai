"""Worker runtime configuration, read from the environment.

Kept separate from the validated app ``Settings`` so the worker can run as its
own cPanel process (cron or persistent Python app) without pulling in the full
web/API settings surface. Fold into ``Settings`` later if the worker is hosted
in-process with the API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerConfig:
    batch_size: int = 5          # max jobs claimed per poll
    max_attempts: int = 3        # transient-failure retries before FAILED
    retry_backoff_s: int = 60    # base backoff; multiplied by attempt number
    poll_interval_s: float = 5.0  # loop mode sleep between empty polls
    # App-relative scratch dir for the downloaded video; override per host with
    # WORKER_MEDIA_DIR (e.g. an absolute path under the cPanel account home).
    media_dir: str = "var/whatsapp-media"
    purge_media_on_done: bool = True  # data-minimisation: delete raw video

    @classmethod
    def from_env(cls) -> WorkerConfig:
        def _int(name: str, default: int) -> int:
            raw = os.environ.get(name)
            return int(raw) if raw not in (None, "") else default

        def _float(name: str, default: float) -> float:
            raw = os.environ.get(name)
            return float(raw) if raw not in (None, "") else default

        def _bool(name: str, default: bool) -> bool:
            raw = os.environ.get(name)
            if raw in (None, ""):
                return default
            return raw.strip().lower() in ("1", "true", "yes", "on")

        return cls(
            batch_size=_int("WORKER_BATCH_SIZE", cls.batch_size),
            max_attempts=_int("WORKER_MAX_ATTEMPTS", cls.max_attempts),
            retry_backoff_s=_int("WORKER_RETRY_BACKOFF_S", cls.retry_backoff_s),
            poll_interval_s=_float("WORKER_POLL_INTERVAL_S", cls.poll_interval_s),
            media_dir=os.environ.get("WORKER_MEDIA_DIR", cls.media_dir),
            purge_media_on_done=_bool(
                "WORKER_PURGE_MEDIA", cls.purge_media_on_done
            ),
        )
