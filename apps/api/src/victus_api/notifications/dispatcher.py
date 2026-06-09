"""Best-effort webhook delivery (Slack-compatible incoming webhook).

The dispatcher is deliberately fire-and-forget within the request: it awaits
the POST with a short timeout and swallows ALL exceptions, because a
notification-delivery failure must never roll back or fail the originating
governance action. The reliable channel is the persisted in-app notification;
the webhook is a convenience ping on top.
"""

from __future__ import annotations

from typing import Any

import httpx

from victus_api.core.logging import get_logger

log = get_logger(__name__)


def build_slack_payload(
    *,
    title: str,
    body: str,
    link_url: str | None,
    fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a Slack-compatible message using Block Kit.

    Slack ignores unknown top-level keys, and other webhook receivers
    (Mattermost, Discord-with-shim) accept the same ``text`` fallback, so this
    payload degrades gracefully across providers.
    """
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title[:150], "emoji": True},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
    ]
    if fields:
        blocks.append(
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*{k}*\n{v}"}
                    for k, v in fields.items()
                ],
            }
        )
    if link_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Open approval queue",
                            "emoji": True,
                        },
                        "url": link_url,
                        "style": "primary",
                    }
                ],
            }
        )
    return {"text": f"{title} — {body}", "blocks": blocks}


async def dispatch_webhook(
    *,
    webhook_url: str | None,
    payload: dict[str, Any],
    timeout_s: float,
) -> bool:
    """POST ``payload`` to ``webhook_url``. Returns True on 2xx, else False.

    Never raises — all failures are logged and converted to a ``False``
    return so callers can ignore the outcome.
    """
    if not webhook_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(webhook_url, json=payload)
        if 200 <= resp.status_code < 300:
            return True
        log.warning(
            "notify_webhook_non_2xx",
            status_code=resp.status_code,
            body=resp.text[:300],
        )
        return False
    except Exception:
        log.warning("notify_webhook_failed", exc_info=True)
        return False
