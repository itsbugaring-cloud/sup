"""
app/repositories/base.py
──────────────────────────────────────────────────────────────────────────────
Abstract generic repository base class.

Provides a standard CRUD interface that concrete repositories override or extend.
Type-parameterised on the SQLAlchemy model to enable IDE autocomplete.

Pattern: Repository pattern isolates all DB queries from business logic.
         Service layer never imports SQLAlchemy directly.
"""

from __future__ import annotations

import uuid
from abc import ABC
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(ABC, Generic[ModelT]):
    """
    Generic async repository providing standard CRUD operations.

    Concrete repositories inherit from this and add domain-specific queries.
    """

    model: type[ModelT]  # Must be set by subclass

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────────────────────

    async def create(self, **kwargs: Any) -> ModelT:
        """
        Create and persist a new record.

        Args:
            **kwargs: Column values matching the model's fields.

        Returns:
            The newly created and refreshed ORM instance.
        """
        instance = self.model(**kwargs)
        self._session.add(instance)
        await self._session.flush()     # Get DB-generated values (id, created_at)
        await self._session.refresh(instance)
        return instance

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_by_id(self, record_id: uuid.UUID) -> ModelT | None:
        """Fetch a single record by primary key UUID."""
        stmt = select(self.model).where(self.model.id == record_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Fetch all records with pagination. Does NOT filter deleted."""
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── Update ────────────────────────────────────────────────────────────────

    async def update(self, instance: ModelT, **kwargs: Any) -> ModelT:
        """
        Update an existing ORM instance in-place.

        Args:
            instance: The ORM instance to update.
            **kwargs: Fields to update with new values.

        Returns:
            The updated ORM instance.
        """
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    # ── Delete ────────────────────────────────────────────────────────────────

    async def hard_delete(self, instance: ModelT) -> None:
        """Permanently delete a record. Use with caution in production."""
        await self._session.delete(instance)
        await self._session.flush()

    # ── Count ─────────────────────────────────────────────────────────────────

    async def count(self, stmt: Select | None = None) -> int:
        """Count records matching an optional statement."""
        if stmt is None:
            count_stmt = select(func.count()).select_from(self.model)
        else:
            count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await self._session.execute(count_stmt)
        return result.scalar_one()
