"""
app/api/v1/routers/supplier_documents.py
──────────────────────────────────────────────────────────────────────────────
FastAPI router for Supplier Document operations.

Endpoints:
  POST   /api/v1/supplier-documents/{supplier_id}/upload  → upload document
  GET    /api/v1/supplier-documents/{supplier_id}          → list documents
  DELETE /api/v1/supplier-documents/{document_id}          → soft delete
  PATCH  /api/v1/supplier-documents/{document_id}/verify   → toggle verify
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, Request, UploadFile, status

from app.core.rate_limit import limiter

from app.core.dependencies import (
    AdminUser,
    AuditRepo,
    BotConfigRepo,
    CurrentUser,
    DocRepo,
    SupplierRepo,
    get_client_ip,
    get_request_id,
)
from app.models.audit_log import AuditActorType
from app.models.supplier_document import DocumentType
from app.schemas.common import SuccessResponse
from app.schemas.supplier_document import DocumentVerifyUpdate, SupplierDocumentRead
from app.services.minio_service import MinIOService
from app.services.supplier_service import SupplierService
from app.services.telegram_notifier import TelegramNotifier

router = APIRouter(prefix="/supplier-documents", tags=["supplier-documents"])


def _get_service(
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    doc_repo: DocRepo,
) -> SupplierService:
    return SupplierService(
        supplier_repo=supplier_repo,
        audit_repo=audit_repo,
        doc_repo=doc_repo,
        minio=MinIOService(),
    )


# ── POST /supplier-documents/{supplier_id}/upload ─────────────────────────────
@router.post(
    "/{supplier_id}/upload",
    summary="Upload a document for a supplier",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[SupplierDocumentRead],
)
@limiter.limit("20/minute")
async def upload_document(
    supplier_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    bot_repo: BotConfigRepo,
    doc_repo: DocRepo,
    file: UploadFile = File(..., description="Document file (PDF, JPG, PNG, DOCX, XLSX)"),
    document_type: DocumentType = Form(..., description="Type of document"),
) -> SuccessResponse[SupplierDocumentRead]:
    svc = _get_service(supplier_repo, audit_repo, doc_repo)
    result = await svc.upload_document(
        supplier_id=supplier_id,
        document_type=document_type,
        file=file,
        actor_id=current_user.id,
        actor_type=AuditActorType.WEB_USER,
        request_id=get_request_id(request),
        ip_address=get_client_ip(request),
    )
    supplier = await supplier_repo.get_active_by_id(supplier_id)
    if supplier:
        await TelegramNotifier(bot_repo).send_document_uploaded(
            supplier,
            document_type.value,
            current_user.display_name or current_user.email,
        )
    return SuccessResponse(data=result, message="Document uploaded successfully")


# ── GET /supplier-documents/{supplier_id} ─────────────────────────────────────
@router.get(
    "/{supplier_id}",
    summary="List all documents for a supplier",
    response_model=SuccessResponse[list[SupplierDocumentRead]],
)
async def list_documents(
    supplier_id: uuid.UUID,
    current_user: CurrentUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    doc_repo: DocRepo,
) -> SuccessResponse[list[SupplierDocumentRead]]:
    # Verify supplier exists
    supplier = await supplier_repo.get_active_by_id(supplier_id)
    if not supplier:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Supplier not found")

    docs = await doc_repo.list_by_supplier(supplier_id)
    minio = MinIOService()

    results = []
    for doc in docs:
        schema = SupplierDocumentRead.model_validate(doc)
        schema.download_url = minio.generate_presigned_url(
            bucket=doc.minio_bucket,
            object_key=doc.minio_object_key,
        )
        results.append(schema)

    return SuccessResponse(data=results)


# ── PATCH /supplier-documents/{document_id}/verify ────────────────────────────
@router.patch(
    "/{document_id}/verify",
    summary="Toggle document verification status (admin only)",
    response_model=SuccessResponse[SupplierDocumentRead],
)
async def verify_document(
    document_id: uuid.UUID,
    body: DocumentVerifyUpdate,
    current_user: AdminUser,
    doc_repo: DocRepo,
) -> SuccessResponse[SupplierDocumentRead]:
    doc = await doc_repo.get_active_by_id(document_id)
    if not doc:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Document not found")

    updated = await doc_repo.mark_verified(doc, body.is_verified)
    return SuccessResponse(
        data=SupplierDocumentRead.model_validate(updated),
        message="Document verification status updated",
    )


# ── DELETE /supplier-documents/{document_id} ──────────────────────────────────
@router.delete(
    "/{document_id}",
    summary="Soft-delete a supplier document (admin only)",
    status_code=status.HTTP_200_OK,
    response_model=SuccessResponse[None],
)
async def delete_document(
    document_id: uuid.UUID,
    current_user: AdminUser,
    doc_repo: DocRepo,
) -> None:
    doc = await doc_repo.get_active_by_id(document_id)
    if not doc:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Document not found")
    await doc_repo.soft_delete(doc)
    return SuccessResponse(data=None, message="Document deleted successfully")
