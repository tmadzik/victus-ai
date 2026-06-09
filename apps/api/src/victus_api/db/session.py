"""Async SQLAlchemy engine + session factory + post-commit callback queue."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from victus_api.config import Settings, get_settings
from victus_api.core.logging import get_logger

log = get_logger(__name__)

# Key under which deferred post-commit callbacks are stashed on a session.
_POST_COMMIT_KEY = "post_commit_callbacks"

# Strong references to in-flight fire-and-forget tasks so the event loop does
# not garbage-collect them before they finish.
_background_tasks: set[asyncio.Task[None]] = set()

PostCommitCallback = Callable[[], Awaitable[None]]


def _session_info(session: AsyncSession) -> dict:
    """Return the mutable per-session ``info`` dict.

    ``AsyncSession`` proxies ``info`` to the underlying sync ``Session``;
    we go through ``sync_session`` explicitly for robustness across versions.
    """
    return session.sync_session.info


def register_post_commit(
    session: AsyncSession, callback: PostCommitCallback
) -> None:
    """Defer ``callback`` until AFTER the session's transaction commits.

    The callback is a zero-arg coroutine factory. It runs only on a
    successful commit, and is discarded (never run) on rollback — so a
    deferred side effect can never announce data that did not persist.
    Callbacks must not depend on the session (it is closed by the time they
    run); capture any needed values in the closure.
    """
    callbacks: list[PostCommitCallback] = _session_info(session).setdefault(
        _POST_COMMIT_KEY, []
    )
    callbacks.append(callback)


def _pop_post_commit(session: AsyncSession) -> list[PostCommitCallback]:
    return _session_info(session).pop(_POST_COMMIT_KEY, [])


def _discard_post_commit(session: AsyncSession) -> None:
    _session_info(session).pop(_POST_COMMIT_KEY, None)


async def run_post_commit_callbacks(
    callbacks: list[PostCommitCallback],
) -> None:
    """Await each callback in order, best-effort (failures logged, swallowed).

    Exposed for tests; production schedules this fire-and-forget so the HTTP
    response is not blocked on slow side effects (e.g. a webhook POST).
    """
    for cb in callbacks:
        try:
            await cb()
        except Exception:
            log.warning("post_commit_callback_failed", exc_info=True)


def _spawn_post_commit(callbacks: list[PostCommitCallback]) -> None:
    if not callbacks:
        return
    task = asyncio.create_task(run_post_commit_callbacks(callbacks))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def make_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1_800,
        future=True,
    )


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = make_engine(get_settings())
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
            class_=AsyncSession,
        )
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            # Commit (or the body) failed — roll back and DISCARD any deferred
            # callbacks so a post-commit side effect never fires for data that
            # did not persist.
            _discard_post_commit(session)
            await session.rollback()
            raise
        else:
            # Commit succeeded. Drain the deferred callbacks and run them
            # fire-and-forget so the HTTP response is not blocked on slow
            # side effects (e.g. a webhook POST with a multi-second timeout).
            _spawn_post_commit(_pop_post_commit(session))


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success."""
    async with session_scope() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
