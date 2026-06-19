"""
app/repositories/audit_log_repository.py
──────────────────────────────────────────────────────────────────────────────
Repository for the `audit_logs` table.

IMPORTANT RULES:
  - Audit logs are IMMUTABLE — no update or delete methods exist.
  - This repository only provides: create + read/filter.
  - `log_action()` is a convenience method called by the service layer.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditActorType, AuditLog
from app.repositories.base import BaseRepository
from app.schemas.audit_log import AuditLogCreate, AuditLogFilter


class AuditLogRepository(BaseRepository[AuditLog]):
    """Async repository for the immutable `audit_logs` table."""

    model = AuditLog

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # ── Write (Create Only — no update/delete) ────────────────────────────────

    async def log_action(self, data: AuditLogCreate) -> AuditLog:
        """
        Write a single audit log entry.

        This is the ONLY write method — audit logs are never modified.
        Call this from the service layer after every state-changing operation.
        """
        return await self.create(**data.model_dump())

    async def log_action_bulk(self, entries: list[AuditLogCreate]) -> list[AuditLog]:
        """
        Bulk-insert multiple audit log entries (e.g., batch operations).
        """
        logs = []
        for entry in entries:
            instance = AuditLog(**entry.model_dump())
            self._session.add(instance)
            logs.append(instance)
        await self._session.flush()
        return logs

    # ── Read ──────────────────────────────────────────────────────────────────

    async def list_audit_logs(
        self,
        filters: AuditLogFilter,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """
        Paginated, filtered audit log list.

        Returns:
            Tuple of (list of AuditLog instances, total count).
        """
        from sqlalchemy import func

        base_stmt = self._build_filter_stmt(filters)

        # Total count
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        # Paginated data
        offset = (page - 1) * per_page
        data_stmt = (
            base_stmt
            .order_by(AuditLog.created_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        data_result = await self._session.execute(data_stmt)
        logs = list(data_result.scalars().all())

        return logs, total

    async def get_entity_history(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100,
    ) -> list[AuditLog]:
        """
        Fetch the full change history for a specific record.

        Usage:
            history = await repo.get_entity_history("suppliers", str(supplier_id))
        """
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def _build_filter_stmt(self, filters: AuditLogFilter):
        """Build the filtered SELECT statement for audit log queries."""
        stmt = select(AuditLog)
        conditions = []

        if filters.entity_type:
            conditions.append(AuditLog.entity_type == filters.entity_type)

        if filters.entity_id:
            conditions.append(AuditLog.entity_id == filters.entity_id)

        if filters.action:
            conditions.append(AuditLog.action == filters.action)

        if filters.actor_id:
            conditions.append(AuditLog.actor_id == filters.actor_id)

        if filters.actor_type:
            conditions.append(AuditLog.actor_type == filters.actor_type)

        if filters.from_date:
            conditions.append(AuditLog.created_at >= filters.from_date)

        if filters.to_date:
            conditions.append(AuditLog.created_at <= filters.to_date)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        return stmt
