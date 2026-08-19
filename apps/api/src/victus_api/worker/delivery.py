"""Outbound delivery to participants, with alerting when it fails.

Every message Victus sends a participant — a conversation reply, a screening
result, the OTP that opens the secure portal, a re-record request — goes out
through :func:`deliver`.

It exists because each of those sites had independently wrapped its send in a
bare ``contextlib.suppress(Exception)``. Individually that reads defensive: a
send failure genuinely must not crash a worker job or 500 a webhook. Together
they meant the entire outbound rail could be dead — expired token, lapsed
24-hour window, 429 — with no participant receiving anything and no signal
anywhere. One site was worse than silent: it logged ``kiosk_result_sent``
unconditionally, *asserting* delivery of a result that had just failed to send.

So :func:`deliver` never raises (the original constraint is real), but it
returns whether delivery actually happened, logs failures at ERROR with the
HTTP status when there is one, and escalates to the operations webhook. Callers
must use the return value rather than assuming success.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

from victus_api.config import Settings, get_settings
from victus_api.core.logging import get_logger, redact_phone
from victus_api.notifications.dispatcher import build_slack_payload, dispatch_webhook
from victus_api.worker.reply import Replier

log = get_logger(__name__)


@dataclass
class _Window:
    last_alert_at: float
    suppressed: int = 0


class AlertThrottle:
    """Rate-limits alerts per failure class so an outage cannot flood the channel.

    A dead token fails *every* message. Alerting per failure would post
    thousands of times, get the webhook rate-limited, and bury the one line
    anyone needed to read — an alert channel nobody can read is worth no more
    than the silence it replaced.

    The first failure in a class alerts immediately; further failures within the
    cooldown are counted, not sent; the next alert after the cooldown carries
    that count, so the volume of the outage is still visible. Keying on
    ``(kind, status_code)`` keeps a throttled 429 storm from masking a 401
    appearing beside it — those need different responses.

    In-process and per-process by design. Several workers may each emit one
    alert, and a restart re-arms it; both are acceptable, and a restart during
    an outage is itself worth hearing about. Nothing here is a substitute for
    the ERROR logs, which are complete.
    """

    def __init__(self) -> None:
        self._windows: dict[tuple[str, int | None], _Window] = {}

    def admit(
        self, key: tuple[str, int | None], *, now: float, cooldown_s: float
    ) -> int | None:
        """Return the suppressed count to report, or ``None`` to stay quiet."""
        window = self._windows.get(key)
        if window is None:
            self._windows[key] = _Window(last_alert_at=now)
            return 0
        if now - window.last_alert_at >= cooldown_s:
            suppressed = window.suppressed
            window.last_alert_at = now
            window.suppressed = 0
            return suppressed
        window.suppressed += 1
        return None

    def reset(self) -> None:
        self._windows.clear()


_throttle = AlertThrottle()


def reset_alert_throttle() -> None:
    """Clear throttle state (tests, and any process re-arming its rail)."""
    _throttle.reset()


async def _alert(
    *,
    settings: Settings,
    kind: str,
    status_code: int | None,
    to: str,
    undelivered: int,
    context: dict[str, str],
) -> None:
    """Escalate a delivery failure to the operations webhook, if one is set."""
    if not settings.notify_webhook_url:
        return

    suppressed = _throttle.admit(
        (kind, status_code),
        now=time.monotonic(),
        cooldown_s=float(settings.delivery_alert_cooldown_seconds),
    )
    if suppressed is None:
        return

    fields = {
        "Kind": kind,
        "HTTP status": str(status_code) if status_code is not None else "n/a",
        "Recipient": redact_phone(to),
        "Undelivered in this turn": str(undelivered),
        "Site": settings.site_code,
        **context,
    }
    if suppressed:
        fields["Suppressed since last alert"] = str(suppressed)

    # Never the message body: these payloads carry screening results and the
    # portal OTP, and the alert channel is not a clinical or credential store.
    await dispatch_webhook(
        webhook_url=settings.notify_webhook_url,
        payload=build_slack_payload(
            title="WhatsApp delivery failing",
            body=(
                "Victus could not deliver a message to a participant. "
                "The conversation state is already committed, so this will not "
                "retry on its own."
            ),
            link_url=None,
            fields=fields,
        ),
        timeout_s=settings.notify_webhook_timeout_s,
    )


async def deliver(
    replier: Replier,
    *,
    to: str,
    messages: Sequence[str],
    kind: str,
    context: dict[str, str] | None = None,
    settings: Settings | None = None,
) -> bool:
    """Send ``messages`` to ``to`` in order. Returns True iff all were delivered.

    Never raises. Stops at the first failure: the causes that matter in
    production — expired token, closed 24-hour window, 429 — apply to every
    message in the group, so continuing only adds doomed requests to a rail
    already refusing them, and under a 429 that is actively counterproductive.
    """
    resolved = settings or get_settings()
    ctx = context or {}

    for index, text in enumerate(messages):
        try:
            await replier.send_text(to=to, text=text)
        except Exception as exc:
            # Present on WhatsAppApiError. The status separates a dead token
            # (401) from a closed window (4xx) from throttling (429) without
            # anyone having to read the body.
            status_code = getattr(exc, "status_code", None)
            undelivered = len(messages) - index
            log.error(
                "delivery_failed",
                kind=kind,
                to=redact_phone(to),
                message_index=index,
                undelivered=undelivered,
                status_code=status_code,
                exc_info=True,
                **ctx,
            )
            try:
                await _alert(
                    settings=resolved,
                    kind=kind,
                    status_code=status_code,
                    to=to,
                    undelivered=undelivered,
                    context=ctx,
                )
            except Exception:
                # dispatch_webhook already swallows its own failures; this guard
                # covers the payload build. Alerting must never be the reason a
                # job dies — the ERROR log above is the reliable record.
                log.warning("delivery_alert_failed", kind=kind, exc_info=True)
            return False

    return True
