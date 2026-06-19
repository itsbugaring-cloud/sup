"""
app/models/supplier_document.py
──────────────────────────────────────────────────────────────────────────────
SQLAlchemy ORM model for the `supplier_documents` table.

Files are NEVER stored in PostgreSQL as BLOBs.
Only the MinIO object key and metadata are persisted here.
"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.supplier import Supplier


class DocumentType(str, enum.Enum):
    """
    Supported document types for supplier verification.
    Must match the PostgreSQL `document_type` enum type.
    """

    NPWP = "npwp"
    PHOTO = "photo"
    SIUP = "siup"
    NIB = "nib"
    CONTRACT = "contract"
    OTHER = "other"


class SupplierDocument(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Documents (NPWP, photos, contracts) linked to suppliers.

    Table: supplier_documents
    File data lives in MinIO — only the object key is stored here.
    """

    __tablename__ = "supplier_documents"

    # ── Foreign Key ───────────────────────────────────────────────────────────
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE", name="fk_supplier_documents_suppliers_supplier_id"),
        nullable=False,
        index=True,
        comment="FK to suppliers.id",
    )

    # ── Document Classification ───────────────────────────────────────────────
    document_type: Mapped[DocumentType] = mapped_column(
        # Use native Enum — type already created in migration
        nullable=False,
        comment="Type/category of the document",
    )

    # ── File Identity ─────────────────────────────────────────────────────────
    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Original filename as uploaded by the user",
    )
    stored_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="UUID-based filename as stored in MinIO",
    )

    # ── MinIO Storage Location ────────────────────────────────────────────────
    minio_bucket: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="MinIO bucket where the file is stored",
    )
    minio_object_key: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        unique=True,
        comment="Full object key / path within the MinIO bucket",
    )

    # ── File Metadata ─────────────────────────────────────────────────────────
    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="File size in bytes",
    )
    mime_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="MIME type verified from magic bytes (NOT file extension)",
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 checksum for file integrity verification",
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Whether the document has been reviewed and verified by admin",
    )

    # ── Uploader Context ──────────────────────────────────────────────────────
    uploaded_by_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Telegram user ID who uploaded (bot flow)",
    )
    uploaded_by_web_user: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Web dashboard user email who uploaded",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    supplier: Mapped["Supplier"] = relationship(
        "Supplier",
        back_populates="documents",
    )

    def __repr__(self) -> str:
        return (
            f"<SupplierDocument id={self.id} type={self.document_type.value} "
            f"supplier_id={self.supplier_id}>"
        )
