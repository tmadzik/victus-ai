"""Phusion Passenger entry point for cPanel "Setup Python App".

cPanel's Python application server (Passenger) speaks **WSGI**, but the Victus
API is an async **ASGI** app (FastAPI). ``a2wsgi.ASGIMiddleware`` bridges the
two by running the ASGI app on a fresh event loop per request.

Two things make that safe here:

1. ``DB_DISABLE_POOL=1`` (forced below) switches SQLAlchemy to ``NullPool`` so no
   asyncpg connection outlives the request's event loop.
2. ``src`` is put on ``sys.path`` so ``victus_api`` imports without an editable
   install (hatchling builds are awkward under the cPanel venv).

Passenger imports this module and serves the WSGI callable named ``application``.
For uvicorn / VPS deployments this file is unused — run
``uvicorn victus_api.main:app`` instead.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "src"))

# Must be set before victus_api.config.get_settings() is first evaluated (which
# happens on the import below), so the engine is built with NullPool.
os.environ.setdefault("DB_DISABLE_POOL", "1")

from a2wsgi import ASGIMiddleware  # noqa: E402  (after sys.path + env are set)

from victus_api.main import app  # noqa: E402

application = ASGIMiddleware(app)
