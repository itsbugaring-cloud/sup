"""
app/schemas/supplier_document.py
──────────────────────────────────────────────────────────────────────────────
Pydantic schemas for SupplierDocument upload and response.

File upload validation (magic bytes, size limits) is done in the service layer.
These schemas handle request metadata and API responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.models.supplier_document import DocumentType
from app.schemas.common import CRMBaseModel


class DocumentUploadMetadata(CRMBaseModel):
    """
    Metadata accompanying a file upload (sent as form fields alongside the file).
    Used by: POST /api/v1/suppliers/{id}/documents
    """

    document_type: DocumentType = Field(
        ...,
        description="Type of document being uploaded",
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Optional note about this document",
    )


class SupplierDocumentRead(CRMBaseModel):
    """
    Full document response schema.
    Includes presigned MinIO URL generated at request time.
    """

    id: uuid.UUID
    supplier_id: uuid.UUID
    document_type: DocumentType
    original_filename: str
    stored_filename: str
    mime_type: str | None
    file_size_bytes: int | None
    checksum_sha256: str | None
    is_verified: bool
    uploaded_by_telegram_id: int | None
    uploaded_by_web_user: str | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # Injected by the service layer after generating a presigned URL
    download_url: str | None = Field(
        default=None,
        description="Presigned MinIO URL valid for a limited time",
    )


class DocumentVerifyUpdate(CRMBaseModel):
    """Schema for verifying/unverifying a document (admin action)."""

    is_verified: bool
    notes: str | None = Field(default=None, max_length=500)
