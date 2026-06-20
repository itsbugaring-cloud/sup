"""
app/schemas/supplier.py
──────────────────────────────────────────────────────────────────────────────
Pydantic schemas for Supplier CRUD operations.

Strict layering:
  - SupplierCreate  : Validated input for POST /suppliers
  - SupplierUpdate  : Partial update for PATCH /suppliers/{id}
  - SupplierRead    : Full response schema (ORM → JSON)
  - SupplierListRead: Compact schema for list views (no documents)
  - SupplierFilter  : Query parameters for filtering/search

Validation rules enforced here (not in the service layer):
  - NPWP must be 15 or 16 digits (numeric only).
  - Phone: Indonesian mobile format validation.
  - Email: Standard email validation via Pydantic EmailStr.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import EmailStr, Field, field_validator, model_validator

from app.models.supplier import SupplierStatus
from app.schemas.common import CRMBaseModel
from app.schemas.supplier_document import SupplierDocumentRead

# ── Regex Patterns ─────────────────────────────────────────────────────────────
_NPWP_PATTERN = re.compile(r"^\d{15,16}$")
_PHONE_PATTERN = re.compile(r"^(\+62|62|0)[0-9]{8,13}$")


class SupplierCreate(CRMBaseModel):
    """
    Input schema for creating a new supplier.
    Used by: POST /api/v1/suppliers
    """

    company_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Legal company name",
        examples=["PT Maju Bersama Tbk."],
    )
    npwp_number: str | None = Field(
        default=None,
        description="NPWP: 15 or 16 numeric digits (no dashes/dots)",
        examples=["123456789012345"],
    )
    pic_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Person in charge full name",
    )
    pic_phone: str = Field(
        ...,
        description="PIC phone (Indonesian format: 08xx, +628xx, 628xx)",
        examples=["081234567890"],
    )
    pic_email: EmailStr | None = Field(
        default=None,
        description="PIC email address",
    )
    address: str | None = Field(
        default=None,
        max_length=2000,
        description="Full business address",
    )
    city: str | None = Field(
        default=None,
        max_length=100,
        description="City / Kota",
    )
    province: str | None = Field(
        default=None,
        max_length=100,
        description="Province / Provinsi",
    )
    category: str | None = Field(
        default=None,
        max_length=100,
        description="Supplier category (e.g., 'Elektronik', 'Makanan')",
    )
    status: SupplierStatus = Field(
        default=SupplierStatus.PENDING_REVIEW,
        description="Initial status (defaults to pending_review)",
    )
    notes: str | None = Field(
        default=None,
        max_length=5000,
        description="Internal notes",
    )
    metadata_: dict[str, Any] | None = Field(
        default=None,
        alias="metadata",
        description="Extra flexible attributes as key-value pairs",
    )
    # Telegram context (set by bot middleware, not by user directly)
    submitted_by_telegram_id: int | None = Field(default=None, exclude=True)
    submitted_by_telegram_username: str | None = Field(default=None, exclude=True)

    @field_validator("npwp_number")
    @classmethod
    def validate_npwp(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Strip common NPWP formatting characters
        cleaned = re.sub(r"[-.\s]", "", v)
        if not _NPWP_PATTERN.match(cleaned):
            raise ValueError(
                "NPWP must be 15 or 16 numeric digits (no dashes or dots)"
            )
        return cleaned

    @field_validator("pic_phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-()]", "", v)
        if not _PHONE_PATTERN.match(cleaned):
            raise ValueError(
                "Phone must be in Indonesian format: 08xx, +628xx, or 628xx"
            )
        return cleaned


class SupplierUpdate(CRMBaseModel):
    """
    Input schema for partially updating a supplier.
    Used by: PATCH /api/v1/suppliers/{id}

    All fields are optional — only provided fields are updated.
    """

    company_name: str | None = Field(default=None, min_length=2, max_length=255)
    npwp_number: str | None = Field(default=None)
    pic_name: str | None = Field(default=None, min_length=2, max_length=255)
    pic_phone: str | None = Field(default=None)
    pic_email: EmailStr | None = Field(default=None)
    address: str | None = Field(default=None, max_length=2000)
    city: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    status: SupplierStatus | None = Field(default=None)
    notes: str | None = Field(default=None, max_length=5000)
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")

    @field_validator("npwp_number")
    @classmethod
    def validate_npwp(cls, v: str | None) -> str | None:
        if v is None:
            return v
        cleaned = re.sub(r"[-.\s]", "", v)
        if not _NPWP_PATTERN.match(cleaned):
            raise ValueError("NPWP must be 15 or 16 numeric digits")
        return cleaned

    @field_validator("pic_phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        cleaned = re.sub(r"[\s\-()]", "", v)
        if not _PHONE_PATTERN.match(cleaned):
            raise ValueError("Phone must be in Indonesian format")
        return cleaned

    def to_update_dict(self) -> dict[str, Any]:
        """
        Returns a dict of only the fields that were explicitly set.
        Used by the repository to build partial UPDATE queries.
        """
        return self.model_dump(
            exclude_none=True,
            exclude_unset=True,
            by_alias=False,
        )


class SupplierDocumentEmbedded(CRMBaseModel):
    """Minimal document schema embedded within supplier responses."""

    id: uuid.UUID
    document_type: str
    original_filename: str
    mime_type: str | None
    file_size_bytes: int | None
    is_verified: bool
    created_at: datetime


class SupplierRead(CRMBaseModel):
    """
    Full supplier response schema.
    Used by: GET /api/v1/suppliers/{id}
    """

    id: uuid.UUID
    company_name: str
    npwp_number: str | None
    pic_name: str
    pic_phone: str
    pic_email: str | None
    address: str | None
    city: str | None
    province: str | None
    category: str | None
    status: SupplierStatus
    notes: str | None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")
    submitted_by_telegram_id: int | None
    submitted_by_telegram_username: str | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    documents: list[SupplierDocumentEmbedded] = Field(default_factory=list)

    model_config = CRMBaseModel.model_config.copy()


class SupplierListRead(CRMBaseModel):
    """
    Compact supplier schema for list/table views.
    Omits documents and heavy fields for performance.
    Used by: GET /api/v1/suppliers (paginated list)
    """

    id: uuid.UUID
    company_name: str
    npwp_number: str | None
    pic_name: str
    pic_phone: str
    pic_email: str | None
    city: str | None
    province: str | None
    category: str | None
    status: SupplierStatus
    document_count: int = 0    # Computed by repository query
    submitted_by_telegram_username: str | None = None
    created_at: datetime
    updated_at: datetime


class SupplierFilter(CRMBaseModel):
    """
    Query parameters for filtering the supplier list.
    All fields are optional and combinable.
    """

    search: str | None = Field(
        default=None,
        description="Full-text search across company_name and pic_name (trigram)",
        max_length=200,
    )
    status: SupplierStatus | None = Field(
        default=None,
        description="Filter by status",
    )
    city: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    include_deleted: bool = Field(
        default=False,
        description="Include soft-deleted suppliers (admin only)",
    )
    created_after: datetime | None = Field(
        default=None,
        description="Filter suppliers created after this timestamp",
    )
    created_before: datetime | None = Field(
        default=None,
        description="Filter suppliers created before this timestamp",
    )


class SupplierStatusUpdate(CRMBaseModel):
    """Minimal schema for status-only updates (quick action in dashboard)."""

    status: SupplierStatus
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for status change",
    )
