"""Async SQLAlchemy engine and session helpers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_incident_commander.config import get_settings
from ai_incident_commander.db.models import Base
from ai_incident_commander.db.url import resolve_database_url

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_session_factory_url: str | None = None


def normalize_async_database_url(database_url: str) -> str:
    """
    Ensure the URL uses the asyncpg driver for SQLAlchemy async engines.

    Args:
        database_url: Database URL from settings.

    Returns:
        URL suitable for ``create_async_engine``.
    """
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


def create_async_engine_from_url(database_url: str) -> AsyncEngine:
    """
    Build an async SQLAlchemy engine for PostgreSQL or SQLite.

    SQLite (used in integration tests via aiosqlite) does not support connection
    pooling; ``pool_size`` and ``max_overflow`` are only passed for PostgreSQL URLs.

    Args:
        database_url: Async-capable database URL.

    Returns:
        Configured ``AsyncEngine`` instance.
    """
    resolved = resolve_database_url(database_url)
    normalized = normalize_async_database_url(resolved)
    is_sqlite = normalized.startswith("sqlite")
    settings = get_settings()
    if is_sqlite:
        return create_async_engine(normalized, pool_pre_ping=False)
    return create_async_engine(
        normalized,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )


def get_async_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """
    Return a cached async session factory for the given database URL.

    Args:
        database_url: Async-capable PostgreSQL URL.

    Returns:
        Session factory bound to the shared engine.
    """
    global _engine, _session_factory, _session_factory_url

    if _session_factory is None or _session_factory_url != database_url:
        _engine = create_async_engine_from_url(database_url)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
        _session_factory_url = database_url

    return _session_factory


async def init_database(database_url: str) -> None:
    """
    Create database tables when they do not already exist.

    Args:
        database_url: Async-capable PostgreSQL URL.

    Raises:
        Exception: Propagates connection or schema initialization errors.
    """
    resolved = resolve_database_url(database_url)
    engine = create_async_engine_from_url(resolved)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@asynccontextmanager
async def session_scope(database_url: str) -> AsyncIterator[AsyncSession]:
    """
    Open a transactional async session scope.

    Args:
        database_url: Async-capable PostgreSQL URL.

    Yields:
        Active ``AsyncSession`` with commit/rollback handling.
    """
    session_factory = get_async_session_factory(database_url)
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def reset_database_runtime() -> None:
    """Clear cached engine/session factory without disposing connections."""
    global _engine, _session_factory, _session_factory_url
    _engine = None
    _session_factory = None
    _session_factory_url = None


async def dispose_database_runtime() -> None:
    """
    Dispose the cached async engine and clear session factory state.

    Call after ``asyncio.run()`` completes so asyncpg connections are not reused
    on a different event loop (Bolt investigation threads use sync bridges).
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
