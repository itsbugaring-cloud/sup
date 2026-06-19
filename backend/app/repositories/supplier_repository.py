"""
app/repositories/supplier_repository.py
──────────────────────────────────────────────────────────────────────────────
Repository for all database operations on the `suppliers` table.

Responsibilities:
  - All SQL queries for Supplier CRUD.
  - Soft delete / restore logic.
  - Paginated, filtered list queries.
  - Export query (no pagination, used by ARQ worker).

Rules:
  - NO business logic here — only DB I/O.
  - All queries default to `deleted_at IS NULL` (active records only).
  - Use `include_deleted=True` only for admin/audit endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier, SupplierStatus
from app.models.supplier_document import SupplierDocument
from app.repositories.base import BaseRepository
from app.schemas.supplier import SupplierCreate, SupplierFilter, SupplierUpdate


class SupplierRepository(BaseRepository[Supplier]):
    """
    Async repository for the `suppliers` table.

    Inject via FastAPI DI:
        repo = SupplierRepository(db)
    """

    model = Supplier

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_supplier(
        self,
        data: SupplierCreate,
        telegram_id: int | None = None,
        telegram_username: str | None = None,
    ) -> Supplier:
        """Create a new supplier record."""
        payload = data.model_dump(
            exclude_none=False,
            exclude={"submitted_by_telegram_id", "submitted_by_telegram_username"},
        )
        # Handle metadata alias
        if "metadata_" in payload:
            payload["metadata_"] = payload.pop("metadata_")

        return await self.create(
            **payload,
            submitted_by_telegram_id=telegram_id,
            submitted_by_telegram_username=telegram_username,
        )

    # ── Read: Single ──────────────────────────────────────────────────────────

    async def get_active_by_id(self, supplier_id: uuid.UUID) -> Supplier | None:
        """Fetch a single active (non-deleted) supplier by ID."""
        stmt = (
            select(Supplier)
            .where(
                Supplier.id == supplier_id,
                Supplier.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_including_deleted(
        self, supplier_id: uuid.UUID
    ) -> Supplier | None:
        """Fetch a supplier by ID regardless of soft-delete status (admin use)."""
        return await self.get_by_id(supplier_id)

    async def get_by_npwp(self, npwp_number: str) -> Supplier | None:
        """Find an active supplier by NPWP number."""
        stmt = select(Supplier).where(
            Supplier.npwp_number == npwp_number,
            Supplier.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Read: List (Paginated) ────────────────────────────────────────────────

    async def list_suppliers(
        self,
        filters: SupplierFilter,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Supplier], int]:
        """
        Paginated, filtered supplier list.

        Returns:
            Tuple of (list of Supplier instances, total count).
        """
        base_stmt = self._build_filter_stmt(filters)

        # Total count (before pagination)
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        # Paginated data
        offset = (page - 1) * per_page
        data_stmt = (
            base_stmt
            .order_by(Supplier.created_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        data_result = await self._session.execute(data_stmt)
        suppliers = list(data_result.scalars().unique().all())

        return suppliers, total

    async def list_for_export(self, filters: SupplierFilter) -> list[Supplier]:
        """
        Fetch ALL matching suppliers for export (no pagination).
        Used only by the ARQ background worker — never in the API directly.
        """
        stmt = (
            self._build_filter_stmt(filters)
            .order_by(Supplier.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    def _build_filter_stmt(self, filters: SupplierFilter):
        """Build the base SELECT statement with all filter conditions applied."""
        stmt = select(Supplier)

        conditions = []

        # Soft delete filter (always applied unless explicitly overridden)
        if not filters.include_deleted:
            conditions.append(Supplier.deleted_at.is_(None))

        # Trigram full-text search on company_name and pic_name
        if filters.search:
            search_term = f"%{filters.search}%"
            conditions.append(
                or_(
                    Supplier.company_name.ilike(search_term),
                    Supplier.pic_name.ilike(search_term),
                    Supplier.pic_phone.ilike(search_term),
                )
            )

        if filters.status:
            conditions.append(Supplier.status == filters.status)

        if filters.city:
            conditions.append(Supplier.city.ilike(f"%{filters.city}%"))

        if filters.province:
            conditions.append(Supplier.province.ilike(f"%{filters.province}%"))

        if filters.category:
            conditions.append(Supplier.category.ilike(f"%{filters.category}%"))

        if filters.created_after:
            conditions.append(Supplier.created_at >= filters.created_after)

        if filters.created_before:
            conditions.append(Supplier.created_at <= filters.created_before)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        return stmt

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_supplier(
        self, supplier: Supplier, data: SupplierUpdate
    ) -> Supplier:
        """Apply a partial update to a supplier."""
        update_data = data.to_update_dict()
        return await self.update(supplier, **update_data)

    async def update_status(
        self, supplier: Supplier, status: SupplierStatus, notes: str | None = None
    ) -> Supplier:
        """Quick status-only update."""
        kwargs: dict[str, Any] = {"status": status}
        if notes is not None:
            kwargs["notes"] = notes
        return await self.update(supplier, **kwargs)

    # ── Soft Delete / Restore ─────────────────────────────────────────────────

    async def soft_delete(
        self, supplier: Supplier, deleted_by: str
    ) -> Supplier:
        """
        Soft-delete a supplier.

        Sets `deleted_at = NOW()` and records `deleted_by`.
        The record remains in the DB for audit purposes.
        """
        return await self.update(
            supplier,
            deleted_at=datetime.now(tz=timezone.utc),
            deleted_by=deleted_by,
        )

    async def restore(self, supplier: Supplier) -> Supplier:
        """Restore a soft-deleted supplier."""
        return await self.update(
            supplier,
            deleted_at=None,
            deleted_by=None,
        )

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def get_status_counts(self) -> dict[str, int]:
        """
        Returns a dict of status → count for dashboard KPI cards.
        Only counts active (non-deleted) suppliers.
        """
        stmt = (
            select(Supplier.status, func.count(Supplier.id).label("count"))
            .where(Supplier.deleted_at.is_(None))
            .group_by(Supplier.status)
        )
        result = await self._session.execute(stmt)
        return {row.status: row.count for row in result}

    async def get_total_active(self) -> int:
        """Count of non-deleted suppliers."""
        stmt = (
            select(func.count(Supplier.id))
            .where(Supplier.deleted_at.is_(None))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
