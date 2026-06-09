"""In-app + webhook notifications.

Two backends:

1. In-app — a persisted ``notifications`` row per recipient. Transactional
   (commits with the originating action), so delivery is reliable. Surfaced
   as a header bell + unread count + ``/notifications`` page in the web app.

2. Webhook — an optional Slack-compatible incoming-webhook POST. Best-effort:
   a failed POST is logged and swallowed so it never blocks the originating
   flow (e.g. an erasure proposal still succeeds even if Slack is down).
"""

NOTIFICATIONS_VERSION = "1.0.0"
