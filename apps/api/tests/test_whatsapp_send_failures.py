"""The WhatsApp rail must fail loudly.

Replies are sent *after* the conversation turn commits, so a send that fails
silently leaves a participant waiting for a message the database believes they
received. These tests pin the two properties that keep that from happening
unnoticed: the failure is recorded at ERROR with enough context to diagnose it,
and it never escapes to Meta (a 5xx would re-deliver an already-committed turn).
"""

from __future__ import annotations

import structlog

from victus_api.core.logging import redact_phone
from victus_api.whatsapp.router import _send_replies
from victus_api.worker.whatsapp_client import (
    WhatsAppApiError,
    WhatsAppNotConfiguredError,
)

PHONE = "263771234567"


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


async def test_successful_turn_sends_every_reply_and_logs_no_error() -> None:
    replier = _Replier()
    with structlog.testing.capture_logs() as logs:
        await _send_replies(
            replier, to=PHONE, replies=["one", "two"], message_id="wamid.A"
        )

    assert replier.sent == ["one", "two"]
    assert [entry for entry in logs if entry["log_level"] == "error"] == []


async def test_send_failure_is_logged_at_error_and_does_not_raise() -> None:
    # The webhook must still answer 200: raising here would make Meta
    # re-deliver a turn whose state is already committed.
    replier = _Replier(fail_from=0)

    with structlog.testing.capture_logs() as logs:
        await _send_replies(replier, to=PHONE, replies=["one"], message_id="wamid.B")

    errors = [entry for entry in logs if entry["log_level"] == "error"]
    assert len(errors) == 1
    assert errors[0]["event"] == "whatsapp_reply_send_failed"
    assert errors[0]["message_id"] == "wamid.B"
    assert errors[0]["undelivered"] == 1


async def test_remaining_replies_are_abandoned_after_a_failure() -> None:
    # An expired token or a 429 applies to the whole turn; continuing would
    # only add doomed requests to a rail already refusing them.
    replier = _Replier(fail_from=1)

    with structlog.testing.capture_logs() as logs:
        await _send_replies(
            replier, to=PHONE, replies=["one", "two", "three"], message_id="wamid.C"
        )

    assert replier.sent == ["one"]
    error = next(entry for entry in logs if entry["log_level"] == "error")
    assert error["reply_index"] == 1
    # Two of the three never went out, and the log says so rather than leaving
    # the count to be inferred from the index.
    assert error["undelivered"] == 2


async def test_api_status_code_reaches_the_log() -> None:
    # 401 (dead token) vs 429 (throttled) is the difference between "rotate the
    # credential now" and "back off"; it has to be greppable without the body.
    replier = _Replier(
        fail_from=0,
        error=WhatsAppApiError(operation="send_text", status_code=429, body="slow down"),
    )

    with structlog.testing.capture_logs() as logs:
        await _send_replies(replier, to=PHONE, replies=["one"], message_id="wamid.D")

    error = next(entry for entry in logs if entry["log_level"] == "error")
    assert error["status_code"] == 429


async def test_misconfiguration_is_reported_not_swallowed() -> None:
    # Half-configured credentials are a deployment error. Before this fix it
    # looked identical to a healthy rail.
    replier = _Replier(fail_from=0, error=WhatsAppNotConfiguredError("no token"))

    with structlog.testing.capture_logs() as logs:
        await _send_replies(replier, to=PHONE, replies=["one"], message_id="wamid.E")

    error = next(entry for entry in logs if entry["log_level"] == "error")
    assert error["event"] == "whatsapp_reply_send_failed"
    assert error["status_code"] is None  # not an API error — no status to report


async def test_failure_log_does_not_carry_the_raw_phone_number() -> None:
    replier = _Replier(fail_from=0)

    with structlog.testing.capture_logs() as logs:
        await _send_replies(replier, to=PHONE, replies=["one"], message_id="wamid.F")

    error = next(entry for entry in logs if entry["log_level"] == "error")
    assert PHONE not in str(error)
    assert error["to"] == "*********567"


def test_redact_phone_keeps_only_the_last_three_digits() -> None:
    assert redact_phone("263771234567") == "*********567"
    assert redact_phone("+2348012345678") == "***********678"
    # Length is preserved, so a malformed number still reads as malformed.
    assert len(redact_phone(PHONE)) == len(PHONE)
    assert redact_phone(None) == "<none>"
    assert redact_phone("") == "<none>"
    assert redact_phone("12") == "**"
