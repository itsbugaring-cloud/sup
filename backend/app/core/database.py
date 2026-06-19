"""
app/core/database.py
──────────────────────────────────────────────────────────────────────────────
Async SQLAlchemy engine and session factory.

Architecture:
  - Single async engine per process (connection pool shared).
  - `AsyncSessionFactory` creates scoped sessions per request.
  - `get_db_session` is the FastAPI dependency for DI.
  - `get_db_session_context` is an async context manager for non-DI usage
    (e.g., ARQ worker, startup tasks).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ── Async Engine ───────────────────────────────────────────────────────────────
# Created once at module import time.
# Pool is shared across all requests for the lifetime of the process.
engine = create_async_engine(
    settings.db.DATABASE_URL,
    pool_size=settings.db.DB_POOL_SIZE,
    max_overflow=settings.db.DB_MAX_OVERFLOW,
    pool_timeout=settings.db.DB_POOL_TIMEOUT,
    pool_recycle=settings.db.DB_POOL_RECYCLE,
    pool_pre_ping=True,       # Verify connections are alive before using them
    echo=settings.db.DB_ECHO_SQL,
    future=True,              # Use SQLAlchemy 2.0 style
)

# ── Session Factory ────────────────────────────────────────────────────────────
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # Don't expire objects after commit (needed for async)
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session per request.

    Usage:
        from fastapi import Depends
        from app.core.database import get_db_session

        async def my_endpoint(db: AsyncSession = Depends(get_db_session)):
            ...

    The session is automatically committed on success and rolled back on error.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions outside FastAPI DI.

    Usage (ARQ worker, startup scripts):
        async with get_db_session_context() as db:
            result = await db.execute(...)
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
