"""
app/models/audit_log.py
──────────────────────────────────────────────────────────────────────────────
SQLAlchemy ORM model for the `audit_logs` table.

Audit logs are IMMUTABLE — no rows are ever updated or deleted.
This is enforced at the repository level; there is no update/delete method.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class AuditAction(str, enum.Enum):
    """
    Audit event action type.
    Must match the PostgreSQL `audit_action` enum.
    """

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    RESTORE = "RESTORE"
    EXPORT = "EXPORT"
    LOGIN = "LOGIN"


class AuditActorType(str, enum.Enum):
    """
    Type of actor who performed the action.
    Must match the PostgreSQL `audit_actor_type` enum.
    """

    WEB_USER = "web_user"
    TELEGRAM_BOT = "telegram_bot"
    SYSTEM = "system"


class AuditLog(TenantMixin, Base):
    """
    Immutable audit trail record.

    Table: audit_logs
    NO soft delete — audit logs can never be deleted.
    NO updated_at — audit logs are created once, never modified.
    """

    __tablename__ = "audit_logs"

    # ── Identity ──────────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="UUID v4 primary key",
    )

    # ── What was done ─────────────────────────────────────────────────────────
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action", create_type=False),
        nullable=False,
        index=True,
        comment="Type of action performed",
    )

    # ── What was affected ─────────────────────────────────────────────────────
    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Name of the affected model/table (e.g., 'suppliers')",
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Primary key of affected record (as string for flexibility)",
    )

    # ── Change Payload ────────────────────────────────────────────────────────
    changes_before: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Snapshot BEFORE the change (UPDATE/DELETE)",
    )
    changes_after: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Snapshot AFTER the change (CREATE/UPDATE)",
    )

    # ── Who did it ────────────────────────────────────────────────────────────
    actor_type: Mapped[AuditActorType] = mapped_column(
        Enum(AuditActorType, name="audit_actor_type", create_type=False),
        nullable=False,
        comment="Type of actor",
    )
    actor_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="ID of the actor (email, telegram ID, or 'system')",
    )
    actor_display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Human-readable display name of the actor",
    )

    # ── Request Context ───────────────────────────────────────────────────────
    request_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
        comment="API request UUID for log correlation",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address (IPv4 or IPv6)",
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Client user-agent string",
    )

    # ── Immutable Timestamp ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="UTC timestamp of the audit event (immutable)",
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action.value} "
            f"entity={self.entity_type}:{self.entity_id} actor={self.actor_id}>"
        )
