"""FastAPI ASGI app factory."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import text

from victus_api import __version__
from victus_api.auth.router import router as auth_router
from victus_api.calibration.router import router as calibration_router
from victus_api.config import Settings, get_settings
from victus_api.core.exceptions import register_exception_handlers
from victus_api.core.logging import configure_logging, get_logger, request_id_var
from victus_api.db.session import dispose_engine, get_engine
from victus_api.governance.admin_router import router as governance_admin_router
from victus_api.governance.router import router as governance_router
from victus_api.notifications.router import router as notifications_router
from victus_api.pathways.router import router as pathways_router
from victus_api.study.router import router as study_router
from victus_api.toi.router import router as toi_router
from victus_api.triage.router import router as triage_router
from victus_api.users.router import router as users_router

log = get_logger(__name__)


limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    configure_logging(settings)
    log.info("api_startup", env=settings.api_env, version=__version__)
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        log.info("db_connection_ok")
    except Exception:
        log.exception("db_connection_failed")
    yield
    await dispose_engine()
    log.info("api_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="Victus AI API",
        version=__version__,
        description="Dual-pathway NCD risk + TOI biomarker platform backend.",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    app.state.limiter = limiter

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Internal-Token", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
        max_age=600,
    )
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def _request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(RateLimitExceeded)
    async def _ratelimit_handler(_: Request, exc: RateLimitExceeded) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limited",
                    "message": f"Rate limit exceeded: {exc.detail}",
                }
            },
        )

    register_exception_handlers(app)

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(pathways_router)
    app.include_router(triage_router)
    app.include_router(toi_router)
    app.include_router(calibration_router)
    app.include_router(study_router)
    app.include_router(governance_router)
    app.include_router(governance_admin_router)
    app.include_router(notifications_router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/readyz", tags=["meta"])
    async def readyz() -> dict[str, str]:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


app = create_app()
