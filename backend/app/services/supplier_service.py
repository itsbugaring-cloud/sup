"""
app/services/supplier_service.py
──────────────────────────────────────────────────────────────────────────────
Business logic layer for Supplier operations.

This layer:
  - Orchestrates between repositories, MinIO, and audit logging.
  - Enforces business rules (e.g., NPWP uniqueness, status transitions).
  - Raises HTTPException for user-facing errors.
  - NEVER touches SQLAlchemy or SQL directly — delegates to repositories.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.core.logging import get_logger
from app.models.audit_log import AuditAction, AuditActorType
from app.models.supplier import Supplier, SupplierStatus
from app.models.supplier_document import DocumentType, SupplierDocument
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.supplier_document_repository import SupplierDocumentRepository
from app.repositories.supplier_repository import SupplierRepository
from app.schemas.audit_log import AuditLogCreate
from app.schemas.supplier import (
    SupplierCreate,
    SupplierFilter,
    SupplierListRead,
    SupplierRead,
    SupplierStatusUpdate,
    SupplierUpdate,
)
from app.schemas.supplier_document import SupplierDocumentRead
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.services.minio_service import MinIOService

logger = get_logger(__name__)


class SupplierService:
    """
    Business logic orchestrator for Supplier CRUD and document management.

    Instantiated per-request via FastAPI DI (stateless per call).
    """

    def __init__(
        self,
        supplier_repo: SupplierRepository,
        audit_repo: AuditLogRepository,
        doc_repo: SupplierDocumentRepository,
        minio: MinIOService,
    ) -> None:
        self._repo = supplier_repo
        self._audit = audit_repo
        self._doc_repo = doc_repo
        self._minio = minio

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _supplier_to_dict(self, supplier: Supplier) -> dict[str, Any]:
        """Snapshot a supplier to a plain dict for audit log storage."""
        return {
            "id": str(supplier.id),
            "company_name": supplier.company_name,
            "npwp_number": supplier.npwp_number,
            "pic_name": supplier.pic_name,
            "pic_phone": supplier.pic_phone,
            "pic_email": supplier.pic_email,
            "status": supplier.status.value if supplier.status else None,
            "city": supplier.city,
            "province": supplier.province,
            "category": supplier.category,
        }

    async def _write_audit(
        self,
        action: AuditAction,
        entity_id: str,
        actor_type: AuditActorType,
        actor_id: str,
        actor_display_name: str | None = None,
        before: dict | None = None,
        after: dict | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Write an audit log entry — fire and forget (errors are logged but not raised)."""
        try:
            await self._audit.log_action(
                AuditLogCreate(
                    action=action,
                    entity_type="suppliers",
                    entity_id=entity_id,
                    changes_before=before,
                    changes_after=after,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    actor_display_name=actor_display_name,
                    request_id=request_id,
                    ip_address=ip_address,
                )
            )
        except Exception as e:
            logger.error("audit_log_write_failed", error=str(e), entity_id=entity_id)

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_supplier(
        self,
        data: SupplierCreate,
        actor_id: str,
        actor_display_name: str | None = None,
        actor_type: AuditActorType = AuditActorType.WEB_USER,
        request_id: str | None = None,
        ip_address: str | None = None,
        telegram_id: int | None = None,
        telegram_username: str | None = None,
    ) -> SupplierRead:
        """
        Create a new supplier.

        Business rules:
          - NPWP must be unique across all non-deleted suppliers.
        """
        # ── Uniqueness check ──────────────────────────────────────────────────
        if data.npwp_number:
            existing = await self._repo.get_by_npwp(data.npwp_number)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A supplier with NPWP '{data.npwp_number}' already exists",
                )

        supplier = await self._repo.create_supplier(
            data=data,
            telegram_id=telegram_id,
            telegram_username=telegram_username,
        )

        after_snapshot = self._supplier_to_dict(supplier)
        await self._write_audit(
            action=AuditAction.CREATE,
            entity_id=str(supplier.id),
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            after=after_snapshot,
            request_id=request_id,
            ip_address=ip_address,
        )

        logger.info(
            "supplier_created",
            supplier_id=str(supplier.id),
            company_name=supplier.company_name,
            actor_id=actor_id,
        )

        return SupplierRead.model_validate(supplier)

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_supplier(self, supplier_id: uuid.UUID) -> SupplierRead:
        """Fetch a single active supplier by ID. Raises 404 if not found."""
        supplier = await self._repo.get_active_by_id(supplier_id)
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Supplier '{supplier_id}' not found",
            )

        result = SupplierRead.model_validate(supplier)

        # Inject presigned URLs for each document
        for doc in result.documents:
            doc.download_url = self._minio.generate_presigned_url(
                bucket=settings.minio.MINIO_BUCKET_DOCUMENTS,
                object_key=f"{supplier_id}/{doc.document_type}/{doc.stored_filename}",
            )

        return result

    async def list_suppliers(
        self,
        filters: SupplierFilter,
        page: int = 1,
        per_page: int = 20,
    ) -> PaginatedResponse[SupplierListRead]:
        """Paginated, filtered supplier list for the dashboard table."""
        suppliers, total = await self._repo.list_suppliers(
            filters=filters, page=page, per_page=per_page
        )

        total_pages = (total + per_page - 1) // per_page if total > 0 else 0

        return PaginatedResponse(
            data=[SupplierListRead.model_validate(s) for s in suppliers],
            meta=PaginationMeta(
                page=page,
                per_page=per_page,
                total_items=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
        )

    async def get_dashboard_stats(self) -> dict[str, Any]:
        """KPI stats for dashboard header cards."""
        status_counts = await self._repo.get_status_counts()
        total = await self._repo.get_total_active()
        return {
            "total_active": total,
            "by_status": {k.value if hasattr(k, "value") else k: v for k, v in status_counts.items()},
        }

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_supplier(
        self,
        supplier_id: uuid.UUID,
        data: SupplierUpdate,
        actor_id: str,
        actor_display_name: str | None = None,
        actor_type: AuditActorType = AuditActorType.WEB_USER,
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> SupplierRead:
        """Partial update of a supplier (PATCH semantics)."""
        supplier = await self._repo.get_active_by_id(supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

        # NPWP uniqueness check (if changing)
        if data.npwp_number and data.npwp_number != supplier.npwp_number:
            existing = await self._repo.get_by_npwp(data.npwp_number)
            if existing and existing.id != supplier_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"NPWP '{data.npwp_number}' is already assigned to another supplier",
                )

        before_snapshot = self._supplier_to_dict(supplier)
        updated = await self._repo.update_supplier(supplier, data)
        after_snapshot = self._supplier_to_dict(updated)

        await self._write_audit(
            action=AuditAction.UPDATE,
            entity_id=str(supplier_id),
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            before=before_snapshot,
            after=after_snapshot,
            request_id=request_id,
            ip_address=ip_address,
        )

        return SupplierRead.model_validate(updated)

    async def update_status(
        self,
        supplier_id: uuid.UUID,
        data: SupplierStatusUpdate,
        actor_id: str,
        actor_display_name: str | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> SupplierRead:
        """Quick status-only update (e.g., approve / blacklist from dashboard)."""
        supplier = await self._repo.get_active_by_id(supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

        before_snapshot = self._supplier_to_dict(supplier)
        updated = await self._repo.update_status(supplier, data.status, data.notes)
        after_snapshot = self._supplier_to_dict(updated)

        await self._write_audit(
            action=AuditAction.UPDATE,
            entity_id=str(supplier_id),
            actor_type=AuditActorType.WEB_USER,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            before=before_snapshot,
            after=after_snapshot,
            request_id=request_id,
            ip_address=ip_address,
        )

        return SupplierRead.model_validate(updated)

    # ── Delete / Restore ──────────────────────────────────────────────────────

    async def delete_supplier(
        self,
        supplier_id: uuid.UUID,
        actor_id: str,
        actor_display_name: str | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Soft-delete a supplier."""
        supplier = await self._repo.get_active_by_id(supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

        before_snapshot = self._supplier_to_dict(supplier)
        await self._repo.soft_delete(supplier, deleted_by=actor_id)

        await self._write_audit(
            action=AuditAction.DELETE,
            entity_id=str(supplier_id),
            actor_type=AuditActorType.WEB_USER,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            before=before_snapshot,
            request_id=request_id,
            ip_address=ip_address,
        )

        logger.info("supplier_deleted", supplier_id=str(supplier_id), actor=actor_id)

    async def restore_supplier(
        self,
        supplier_id: uuid.UUID,
        actor_id: str,
        request_id: str | None = None,
    ) -> SupplierRead:
        """Restore a soft-deleted supplier."""
        supplier = await self._repo.get_by_id_including_deleted(supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
        if not supplier.is_deleted:
            raise HTTPException(status_code=400, detail="Supplier is not deleted")

        restored = await self._repo.restore(supplier)

        await self._write_audit(
            action=AuditAction.RESTORE,
            entity_id=str(supplier_id),
            actor_type=AuditActorType.WEB_USER,
            actor_id=actor_id,
            after=self._supplier_to_dict(restored),
            request_id=request_id,
        )

        return SupplierRead.model_validate(restored)

    # ── Documents ─────────────────────────────────────────────────────────────

    async def upload_document(
        self,
        supplier_id: uuid.UUID,
        document_type: DocumentType,
        file: UploadFile,
        actor_id: str,
        actor_type: AuditActorType = AuditActorType.WEB_USER,
        telegram_id: int | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> SupplierDocumentRead:
        """
        Upload a supplier document:
          1. Verify supplier exists.
          2. Read file content, validate magic bytes.
          3. Upload to MinIO.
          4. Persist metadata in Postgres.
          5. Write audit log.
          6. Return response with presigned URL.
        """
        supplier = await self._repo.get_active_by_id(supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

        file_content = await file.read()

        try:
            stored_name, object_key, mime_type, checksum = (
                self._minio.upload_document(
                    file_content=file_content,
                    original_filename=file.filename or "unknown",
                    supplier_id=str(supplier_id),
                    document_type=document_type.value,
                )
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e),
            )

        doc = await self._doc_repo.create_document(
            supplier_id=supplier_id,
            document_type=document_type,
            original_filename=file.filename or "unknown",
            stored_filename=stored_name,
            minio_bucket=settings.minio.MINIO_BUCKET_DOCUMENTS,
            minio_object_key=object_key,
            file_size_bytes=len(file_content),
            mime_type=mime_type,
            checksum_sha256=checksum,
            uploaded_by_telegram_id=telegram_id if actor_type == AuditActorType.TELEGRAM_BOT else None,
            uploaded_by_web_user=actor_id if actor_type == AuditActorType.WEB_USER else None,
        )

        await self._audit.log_action(
            AuditLogCreate(
                action=AuditAction.CREATE,
                entity_type="supplier_documents",
                entity_id=str(doc.id),
                actor_type=actor_type,
                actor_id=actor_id,
                after={"supplier_id": str(supplier_id), "document_type": document_type.value},
                request_id=request_id,
                ip_address=ip_address,
            )
        )

        result = SupplierDocumentRead.model_validate(doc)
        result.download_url = self._minio.generate_presigned_url(
            bucket=settings.minio.MINIO_BUCKET_DOCUMENTS,
            object_key=object_key,
        )

        return result
