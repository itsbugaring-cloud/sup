"""
app/api/v1/routers/suppliers.py
──────────────────────────────────────────────────────────────────────────────
FastAPI router for Supplier CRUD operations.

Endpoints follow kebab-case convention per project spec:
  GET    /api/v1/suppliers              → list (paginated + filtered)
  POST   /api/v1/suppliers              → create
  GET    /api/v1/suppliers/{id}         → get single
  PATCH  /api/v1/suppliers/{id}         → partial update
  DELETE /api/v1/suppliers/{id}         → soft delete
  POST   /api/v1/suppliers/{id}/restore → restore soft-deleted
  PATCH  /api/v1/suppliers/{id}/status  → quick status update
  GET    /api/v1/suppliers/stats        → dashboard KPI stats

All endpoints require JWT auth. Delete/restore require admin role.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.dependencies import (
    AdminUser,
    AuditRepo,
    BotConfigRepo,
    CurrentUser,
    DbSession,
    DocRepo,
    SupplierRepo,
    get_client_ip,
    get_request_id,
)
from app.models.audit_log import AuditActorType
from app.schemas.common import PaginatedResponse, SuccessResponse
from app.schemas.supplier import (
    SupplierCreate,
    SupplierFilter,
    SupplierListRead,
    SupplierRead,
    SupplierStatusUpdate,
    SupplierUpdate,
)
from app.services.minio_service import MinIOService
from app.services.supplier_service import SupplierService
from app.services.telegram_notifier import TelegramNotifier

from fastapi_cache.decorator import cache

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


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


# ── GET /suppliers/stats ──────────────────────────────────────────────────────
@router.get(
    "/stats",
    summary="Get supplier KPI statistics",
    response_model=SuccessResponse[dict],
)
@cache(expire=30)
async def get_stats(
    current_user: CurrentUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    doc_repo: DocRepo,
) -> SuccessResponse[dict]:
    svc = _get_service(supplier_repo, audit_repo, doc_repo)
    data = await svc.get_dashboard_stats()
    return SuccessResponse(data=data, message="Stats retrieved")


# ── GET /suppliers ────────────────────────────────────────────────────────────
@router.get(
    "",
    summary="List suppliers (paginated, filtered)",
    response_model=PaginatedResponse[SupplierListRead],
)
@cache(expire=15)
async def list_suppliers(
    current_user: CurrentUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    doc_repo: DocRepo,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=200),
    search: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    city: str | None = Query(default=None),
    province: str | None = Query(default=None),
    category: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
) -> PaginatedResponse[SupplierListRead]:
    from app.models.supplier import SupplierStatus

    filters = SupplierFilter(
        search=search,
        status=SupplierStatus(status_filter) if status_filter else None,
        city=city,
        province=province,
        category=category,
        include_deleted=include_deleted and current_user.role == "admin",
    )

    svc = _get_service(supplier_repo, audit_repo, doc_repo)
    return await svc.list_suppliers(filters=filters, page=page, per_page=per_page)


# ── POST /suppliers ───────────────────────────────────────────────────────────
@router.post(
    "",
    summary="Create a new supplier",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[SupplierRead],
)
async def create_supplier(
    body: SupplierCreate,
    request: Request,
    current_user: CurrentUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    bot_repo: BotConfigRepo,
    doc_repo: DocRepo,
) -> SuccessResponse[SupplierRead]:
    svc = _get_service(supplier_repo, audit_repo, doc_repo)
    result = await svc.create_supplier(
        data=body,
        actor_id=current_user.id,
        actor_display_name=current_user.display_name,
        actor_type=AuditActorType.WEB_USER,
        request_id=get_request_id(request),
        ip_address=get_client_ip(request),
    )
    await TelegramNotifier(bot_repo).send_supplier_created(result)
    return SuccessResponse(data=result, message="Supplier created successfully")


# ── GET /suppliers/{id} ───────────────────────────────────────────────────────
@router.get(
    "/{supplier_id}",
    summary="Get a single supplier by ID",
    response_model=SuccessResponse[SupplierRead],
)
async def get_supplier(
    supplier_id: uuid.UUID,
    current_user: CurrentUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    doc_repo: DocRepo,
) -> SuccessResponse[SupplierRead]:
    svc = _get_service(supplier_repo, audit_repo, doc_repo)
    result = await svc.get_supplier(supplier_id)
    return SuccessResponse(data=result)


# ── PATCH /suppliers/{id} ─────────────────────────────────────────────────────
@router.patch(
    "/{supplier_id}",
    summary="Partially update a supplier",
    response_model=SuccessResponse[SupplierRead],
)
async def update_supplier(
    supplier_id: uuid.UUID,
    body: SupplierUpdate,
    request: Request,
    current_user: CurrentUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    doc_repo: DocRepo,
) -> SuccessResponse[SupplierRead]:
    svc = _get_service(supplier_repo, audit_repo, doc_repo)
    result = await svc.update_supplier(
        supplier_id=supplier_id,
        data=body,
        actor_id=current_user.id,
        actor_display_name=current_user.display_name,
        request_id=get_request_id(request),
        ip_address=get_client_ip(request),
    )
    return SuccessResponse(data=result, message="Supplier updated")


# ── PATCH /suppliers/{id}/status ──────────────────────────────────────────────
@router.patch(
    "/{supplier_id}/status",
    summary="Update supplier status only",
    response_model=SuccessResponse[SupplierRead],
)
async def update_status(
    supplier_id: uuid.UUID,
    body: SupplierStatusUpdate,
    request: Request,
    current_user: CurrentUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    bot_repo: BotConfigRepo,
    doc_repo: DocRepo,
) -> SuccessResponse[SupplierRead]:
    svc = _get_service(supplier_repo, audit_repo, doc_repo)
    result = await svc.update_status(
        supplier_id=supplier_id,
        data=body,
        actor_id=current_user.id,
        actor_display_name=current_user.display_name,
        actor_type=AuditActorType.WEB_USER,
        request_id=get_request_id(request),
        ip_address=get_client_ip(request),
    )
    await TelegramNotifier(bot_repo).send_status_change(
        result,
        actor_display_name=current_user.display_name or current_user.email,
        source="Dashboard",
    )
    return SuccessResponse(data=result, message="Status updated")


# ── DELETE /suppliers/{id} ────────────────────────────────────────────────────
@router.delete(
    "/{supplier_id}",
    summary="Soft-delete a supplier (admin only)",
    status_code=status.HTTP_200_OK,
    response_model=SuccessResponse[None],
)
async def delete_supplier(
    supplier_id: uuid.UUID,
    request: Request,
    current_user: AdminUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    doc_repo: DocRepo,
) -> None:
    svc = _get_service(supplier_repo, audit_repo, doc_repo)
    await svc.delete_supplier(
        supplier_id=supplier_id,
        actor_id=current_user.id,
        actor_display_name=current_user.display_name,
        request_id=get_request_id(request),
        ip_address=get_client_ip(request),
    )
    return SuccessResponse(data=None, message="Supplier deleted successfully")


# ── POST /suppliers/{id}/restore ──────────────────────────────────────────────
@router.post(
    "/{supplier_id}/restore",
    summary="Restore a soft-deleted supplier (admin only)",
    response_model=SuccessResponse[SupplierRead],
)
async def restore_supplier(
    supplier_id: uuid.UUID,
    request: Request,
    current_user: AdminUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    doc_repo: DocRepo,
) -> SuccessResponse[SupplierRead]:
    svc = _get_service(supplier_repo, audit_repo, doc_repo)
    result = await svc.restore_supplier(
        supplier_id=supplier_id,
        actor_id=current_user.id,
        request_id=get_request_id(request),
    )
    return SuccessResponse(data=result, message="Supplier restored")
