"""Background worker for the WhatsApp/kiosk capture rail.

Layering (innermost → outermost), so each layer is testable in isolation:

* ``messages``  — localized chat copy (Shona / Ndebele / English).
* ``processor`` — DB-free core: media file → rPPG → reply text + outcome.
* ``media`` / ``reply`` — injectable WhatsApp media-fetch and send protocols.
* ``jobs``      — ``processing_jobs`` queue repository (claim / mark / retry).
* ``runner``    — ties the queue to the processor; cron + loop entrypoints.

The webhook only ever writes a QUEUED ``ProcessingJob`` and returns 200; all
heavy work happens here, off the request path (see Victus_Demonstrator_Build_Plan.md §4).
"""
