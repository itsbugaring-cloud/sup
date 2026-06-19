"""
app/schemas/audit_log.py
──────────────────────────────────────────────────────────────────────────────
Pydantic schemas for AuditLog — read-only (audit logs are never created via API).
Internal writes use the AuditLogCreate schema in the repository layer only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.audit_log import AuditAction, AuditActorType
from app.schemas.common import CRMBaseModel


class AuditLogRead(CRMBaseModel):
    """
    Full audit log response schema.
    Used by: GET /api/v1/audit-logs
    """

    id: uuid.UUID
    action: AuditAction
    entity_type: str
    entity_id: str | None
    changes_before: dict[str, Any] | None
    changes_after: dict[str, Any] | None
    actor_type: AuditActorType
    actor_id: str
    actor_display_name: str | None
    request_id: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class AuditLogCreate(CRMBaseModel):
    """
    Internal schema for writing audit log entries.
    NEVER exposed via API — used only by the AuditLogRepository.
    """

    action: AuditAction
    entity_type: str
    entity_id: str | None = None
    changes_before: dict[str, Any] | None = None
    changes_after: dict[str, Any] | None = None
    actor_type: AuditActorType
    actor_id: str
    actor_display_name: str | None = None
    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None


class AuditLogFilter(CRMBaseModel):
    """Query parameters for filtering audit logs."""

    entity_type: str | None = Field(default=None, max_length=100)
    entity_id: str | None = Field(default=None, max_length=255)
    action: AuditAction | None = None
    actor_id: str | None = Field(default=None, max_length=255)
    actor_type: AuditActorType | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
