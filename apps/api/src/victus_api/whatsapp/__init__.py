"""WhatsApp Cloud API rail: webhook → conversation → enqueue capture.

Layering (each independently testable):

* ``config``       — env-sourced WhatsApp credentials/tokens.
* ``meta``         — Meta payload parsing + ``X-Hub-Signature-256`` verification.
* ``conversation`` — pure state machine (language → consent → intake → audit →
                     video) producing the triage intake and an enqueue action.
* ``service``      — DB session persistence + dedupe; turns a parsed inbound
                     message into replies and (on the video) a queued job.
* ``router``       — FastAPI GET-verify + POST-inbound endpoints.

The router never blocks: it verifies, persists, replies, and enqueues a
``ProcessingJob`` for the background worker (see worker/ package) to process.
"""
