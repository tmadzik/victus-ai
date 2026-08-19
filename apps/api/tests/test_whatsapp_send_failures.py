"""Outbound delivery must fail loudly, and must not flood the alert channel.

Messages go out *after* the state that produced them has committed, so a send
that fails silently leaves a participant waiting for something the database
believes they received — and nothing will retry it. These tests pin the three
properties that keep that visible: the failure is recorded at ERROR with enough
context to act on, it never escapes to crash the caller, and the escalation to
the operations webhook is throttled so an outage cannot bury its own alert.
"""

from __future__ import annotations

import pytest
import structlog

from victus_api.config import Settings
from victus_api.core.logging import redact_phone
from victus_api.worker.delivery import (
    AlertThrottle,
    deliver,
    reset_alert_throttle,
)
from victus_api.worker.whatsapp_client import (
    WhatsAppApiError,
    WhatsAppNotConfiguredError,
)

PHONE = "263771234567"


@pytest.fixture(autouse=True)
def _clean_throttle() -> None:
    reset_alert_throttle()


def _settings(**overrides: object) -> Settings:
    return Settings(**{"notify_webhook_url": None, **overrides})  # type: ignore[arg-type]


class _Replier:
    """Sends fine until ``fail_from``, then raises ``error`` every time."""

    def __init__(self, *, fail_from: int | None = None, error: Exception | None = None):
        self.sent: list[str] = []
        self._fail_from = fail_from
        self._error = error or RuntimeError("boom")

    async def send_text(self, *, to: str, text: str) -> None:
        if self._fail_from is not None and len(self.sent) >= self._fail_from:
            raise self._error
        self.sent.append(text)


# --- delivery outcome --------------------------------------------------------


async def test_successful_delivery_reports_true_and_logs_no_error() -> None:
    replier = _Replier()
    with structlog.testing.capture_logs() as logs:
        ok = await deliver(
            replier,
            to=PHONE,
            messages=["one", "two"],
            kind="conversation_reply",
            settings=_settings(),
        )

    assert ok is True
    assert replier.sent == ["one", "two"]
    assert [e for e in logs if e["log_level"] == "error"] == []


async def test_failure_reports_false_rather_than_raising() -> None:
    # Callers rely on this to stop logging success they did not achieve, and
    # the webhook relies on it to still answer 200 (a 5xx makes Meta re-deliver
    # an already-committed turn).
    replier = _Replier(fail_from=0)

    with structlog.testing.capture_logs() as logs:
        ok = await deliver(
            replier,
            to=PHONE,
            messages=["one"],
            kind="kiosk_result",
            context={"session_id": "abc"},
            settings=_settings(),
        )

    assert ok is False
    error = next(e for e in logs if e["log_level"] == "error")
    assert error["event"] == "delivery_failed"
    assert error["kind"] == "kiosk_result"
    assert error["session_id"] == "abc"
    assert error["undelivered"] == 1


async def test_remaining_messages_are_abandoned_after_a_failure() -> None:
    # An expired token or a 429 applies to the whole group; continuing only
    # adds doomed requests to a rail already refusing them.
    replier = _Replier(fail_from=1)

    with structlog.testing.capture_logs() as logs:
        ok = await deliver(
            replier,
            to=PHONE,
            messages=["result", "otp"],
            kind="kiosk_result",
            settings=_settings(),
        )

    assert ok is False
    assert replier.sent == ["result"]
    error = next(e for e in logs if e["log_level"] == "error")
    # A result the participant cannot open is not a delivered result: the OTP
    # failing has to read as a failure of the whole group.
    assert error["undelivered"] == 1
    assert error["message_index"] == 1


async def test_api_status_code_reaches_the_log() -> None:
    # 401 (dead token) vs 429 (throttled) is the difference between "rotate the
    # credential now" and "back off"; it must be greppable without the body.
    replier = _Replier(
        fail_from=0,
        error=WhatsAppApiError(operation="send_text", status_code=429, body="slow"),
    )
    with structlog.testing.capture_logs() as logs:
        await deliver(
            replier, to=PHONE, messages=["one"], kind="x", settings=_settings()
        )

    assert next(e for e in logs if e["log_level"] == "error")["status_code"] == 429


async def test_misconfiguration_is_reported_not_swallowed() -> None:
    replier = _Replier(fail_from=0, error=WhatsAppNotConfiguredError("no token"))
    with structlog.testing.capture_logs() as logs:
        await deliver(
            replier, to=PHONE, messages=["one"], kind="x", settings=_settings()
        )

    error = next(e for e in logs if e["log_level"] == "error")
    assert error["status_code"] is None  # not an API error — no status to report


async def test_failure_log_does_not_carry_the_raw_phone_number() -> None:
    replier = _Replier(fail_from=0)
    with structlog.testing.capture_logs() as logs:
        await deliver(
            replier, to=PHONE, messages=["one"], kind="x", settings=_settings()
        )

    error = next(e for e in logs if e["log_level"] == "error")
    assert PHONE not in str(error)
    assert error["to"] == "*********567"


async def test_no_webhook_configured_is_not_an_error() -> None:
    # The ERROR log is the reliable record; the webhook is an escalation on top.
    replier = _Replier(fail_from=0)
    assert (
        await deliver(
            replier, to=PHONE, messages=["one"], kind="x", settings=_settings()
        )
        is False
    )


# --- alert throttling --------------------------------------------------------


def test_first_failure_alerts_immediately() -> None:
    throttle = AlertThrottle()
    assert throttle.admit(("kind", 401), now=0.0, cooldown_s=900.0) == 0


def test_repeat_failures_inside_the_window_are_counted_not_sent() -> None:
    # A dead token fails every message. Un-throttled, that is thousands of
    # webhook posts and an alert channel nobody can read.
    throttle = AlertThrottle()
    throttle.admit(("kind", 401), now=0.0, cooldown_s=900.0)
    for t in (1.0, 2.0, 3.0):
        assert throttle.admit(("kind", 401), now=t, cooldown_s=900.0) is None


def test_next_alert_after_the_cooldown_reports_what_was_suppressed() -> None:
    # The outage's volume must survive the throttling, or the alert understates
    # a rail that is down completely as if it were a single blip.
    throttle = AlertThrottle()
    throttle.admit(("kind", 401), now=0.0, cooldown_s=900.0)
    for t in (1.0, 2.0, 3.0):
        throttle.admit(("kind", 401), now=t, cooldown_s=900.0)

    assert throttle.admit(("kind", 401), now=901.0, cooldown_s=900.0) == 3
    # And the counter resets, so the following window starts clean.
    assert throttle.admit(("kind", 401), now=902.0, cooldown_s=900.0) is None


def test_distinct_failure_classes_throttle_independently() -> None:
    # A throttled 429 storm must not mask a 401 appearing beside it — they call
    # for different responses.
    throttle = AlertThrottle()
    assert throttle.admit(("reply", 429), now=0.0, cooldown_s=900.0) == 0
    assert throttle.admit(("reply", 429), now=1.0, cooldown_s=900.0) is None
    assert throttle.admit(("reply", 401), now=1.0, cooldown_s=900.0) == 0
    assert throttle.admit(("kiosk_result", 429), now=1.0, cooldown_s=900.0) == 0


async def test_alert_payload_never_carries_the_message_body_or_raw_phone() -> None:
    # These payloads are screening results and the portal OTP. The alert
    # channel is neither a clinical store nor a credential store.
    posted: dict = {}

    async def _capture(*, webhook_url: str, payload: dict, timeout_s: float) -> bool:
        posted["payload"] = payload
        return True

    import victus_api.worker.delivery as delivery_mod

    original = delivery_mod.dispatch_webhook
    delivery_mod.dispatch_webhook = _capture  # type: ignore[assignment]
    try:
        await deliver(
            _Replier(fail_from=0),
            to=PHONE,
            messages=["Your one-time access code is *4821*."],
            kind="kiosk_result",
            settings=_settings(notify_webhook_url="https://hooks.example.test/x"),
        )
    finally:
        delivery_mod.dispatch_webhook = original  # type: ignore[assignment]

    rendered = str(posted["payload"])
    assert "4821" not in rendered
    assert "one-time access code" not in rendered
    assert PHONE not in rendered
    assert "*********567" in rendered


def test_redact_phone_keeps_only_the_last_three_digits() -> None:
    assert redact_phone("263771234567") == "*********567"
    assert redact_phone("+2348012345678") == "***********678"
    # Length is preserved, so a malformed number still reads as malformed.
    assert len(redact_phone(PHONE)) == len(PHONE)
    assert redact_phone(None) == "<none>"
    assert redact_phone("") == "<none>"
    assert redact_phone("12") == "**"
