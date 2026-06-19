"""
app/models/supplier.py
──────────────────────────────────────────────────────────────────────────────
SQLAlchemy ORM model for the `suppliers` table.

Mirrors the schema created in migration 0001_initial_schema.
All columns must match 1:1 with the migration — Alembic is the source of truth.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.supplier_document import SupplierDocument
    from app.models.audit_log import AuditLog


class SupplierStatus(str, enum.Enum):
    """
    Supplier operational status.
    String enum so values serialize directly to/from JSON and DB.
    Must match the PostgreSQL `supplier_status` enum type exactly.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING_REVIEW = "pending_review"
    BLACKLISTED = "blacklisted"


class Supplier(TimestampMixin, SoftDeleteMixin, UUIDPrimaryKeyMixin, TenantMixin, Base):
    """
    Core supplier entity.

    Table: suppliers
    Soft-deletable: filter `deleted_at IS NULL` in all queries.
    """

    __tablename__ = "suppliers"

    # ── Core Business Fields ──────────────────────────────────────────────────
    company_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Legal company name of the supplier",
    )
    npwp_number: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        unique=True,
        comment="Nomor Pokok Wajib Pajak (tax ID)",
    )
    pic_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Person in charge full name",
    )
    pic_phone: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="PIC phone number",
    )
    pic_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="PIC email address",
    )
    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Full business address",
    )
    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="City / Kota",
    )
    province: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Province / Provinsi",
    )
    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Supplier category / type of goods or services",
    )
    status: Mapped[SupplierStatus] = mapped_column(
        Enum(SupplierStatus, name="supplier_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default="pending_review",
        index=True,
        comment="Current operational status",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Internal notes",
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",   # DB column name is `metadata` (underscore avoids Python builtin clash)
        JSONB,
        nullable=True,
        server_default="{}",
        comment="Flexible extra attributes (JSONB)",
    )

    # ── Telegram Submitter Tracking ───────────────────────────────────────────
    submitted_by_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="Telegram user ID of the field staff who submitted",
    )
    submitted_by_telegram_username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Telegram username of the submitting field staff",
    )

    # ── Soft Delete Metadata ─────────────────────────────────────────────────
    deleted_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Actor who performed the soft delete",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    documents: Mapped[list["SupplierDocument"]] = relationship(
        "SupplierDocument",
        back_populates="supplier",
        cascade="all, delete-orphan",
        lazy="selectin",  # Eagerly load documents when supplier is fetched
        order_by="SupplierDocument.created_at.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<Supplier id={self.id} company_name={self.company_name!r} "
            f"status={self.status.value}>"
        )
