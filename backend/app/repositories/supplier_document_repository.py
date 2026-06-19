"""
app/repositories/supplier_document_repository.py
──────────────────────────────────────────────────────────────────────────────
Repository for all database operations on the `supplier_documents` table.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier_document import DocumentType, SupplierDocument
from app.repositories.base import BaseRepository


class SupplierDocumentRepository(BaseRepository[SupplierDocument]):
    """Async repository for the `supplier_documents` table."""

    model = SupplierDocument

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create_document(
        self,
        supplier_id: uuid.UUID,
        document_type: DocumentType,
        original_filename: str,
        stored_filename: str,
        minio_bucket: str,
        minio_object_key: str,
        file_size_bytes: int | None = None,
        mime_type: str | None = None,
        checksum_sha256: str | None = None,
        uploaded_by_telegram_id: int | None = None,
        uploaded_by_web_user: str | None = None,
    ) -> SupplierDocument:
        """Persist document metadata after successful MinIO upload."""
        return await self.create(
            supplier_id=supplier_id,
            document_type=document_type,
            original_filename=original_filename,
            stored_filename=stored_filename,
            minio_bucket=minio_bucket,
            minio_object_key=minio_object_key,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            checksum_sha256=checksum_sha256,
            uploaded_by_telegram_id=uploaded_by_telegram_id,
            uploaded_by_web_user=uploaded_by_web_user,
        )

    async def list_by_supplier(
        self,
        supplier_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> list[SupplierDocument]:
        """Fetch all documents for a specific supplier."""
        conditions = [SupplierDocument.supplier_id == supplier_id]
        if not include_deleted:
            conditions.append(SupplierDocument.deleted_at.is_(None))

        stmt = (
            select(SupplierDocument)
            .where(and_(*conditions))
            .order_by(SupplierDocument.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_by_id(
        self, document_id: uuid.UUID
    ) -> SupplierDocument | None:
        """Fetch an active (non-deleted) document by ID."""
        stmt = select(SupplierDocument).where(
            SupplierDocument.id == document_id,
            SupplierDocument.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def soft_delete(self, document: SupplierDocument) -> SupplierDocument:
        """Soft-delete a document record (MinIO deletion is done in service layer)."""
        return await self.update(
            document,
            deleted_at=datetime.now(tz=timezone.utc),
        )

    async def mark_verified(
        self, document: SupplierDocument, is_verified: bool
    ) -> SupplierDocument:
        """Toggle verification status on a document."""
        return await self.update(document, is_verified=is_verified)
