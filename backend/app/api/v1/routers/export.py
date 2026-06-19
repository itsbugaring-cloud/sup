"""
app/api/v1/routers/export.py
──────────────────────────────────────────────────────────────────────────────
FastAPI router for Excel export operations.

Strategy:
  - Small exports (<= 5000 rows): Generate synchronously, stream as file download.
  - Large exports (> 5000 rows): Enqueue ARQ job, return task_id for polling.

Endpoints:
  POST /api/v1/suppliers/export        → trigger export (sync or async)
  GET  /api/v1/suppliers/export/{task_id} → poll async export status
"""

from __future__ import annotations

import json
import uuid
from datetime import timezone

from arq import create_pool
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.dependencies import AuditRepo, CurrentUser, DocRepo, SupplierRepo, get_client_ip, get_request_id
from app.core.logging import get_logger
from app.models.audit_log import AuditAction, AuditActorType
from app.schemas.audit_log import AuditLogCreate
from app.schemas.common import SuccessResponse, TaskResponse
from app.schemas.supplier import SupplierFilter
from app.services.export_service import generate_supplier_excel
from app.services.minio_service import MinIOService
from app.worker import get_arq_redis_settings

logger = get_logger(__name__)

router = APIRouter(prefix="/suppliers", tags=["export"])

ASYNC_EXPORT_THRESHOLD = 5000  # Rows above this go to ARQ worker


# ── POST /suppliers/export ────────────────────────────────────────────────────
@router.post(
    "/export",
    summary="Export suppliers to Excel",
    responses={
        200: {"description": "File download (sync export <= 5000 rows)"},
        202: {"description": "Task queued (async export > 5000 rows)"},
    },
)
async def export_suppliers(
    request: Request,
    current_user: CurrentUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    doc_repo: DocRepo,
    # Accept same filters as the list endpoint
    search: str | None = None,
    status_filter: str | None = None,
    city: str | None = None,
    province: str | None = None,
    category: str | None = None,
):
    from app.models.supplier import SupplierStatus

    filters = SupplierFilter(
        search=search,
        status=SupplierStatus(status_filter) if status_filter else None,
        city=city,
        province=province,
        category=category,
    )

    # Count matching rows first
    suppliers = await supplier_repo.list_for_export(filters)
    total = len(suppliers)

    # ── Audit log: export action ──────────────────────────────────────────────
    await audit_repo.log_action(
        AuditLogCreate(
            action=AuditAction.EXPORT,
            entity_type="suppliers",
            actor_type=AuditActorType.WEB_USER,
            actor_id=current_user.id,
            actor_display_name=current_user.display_name,
            changes_after={"total_rows": total, "filters": filters.model_dump()},
            request_id=get_request_id(request),
            ip_address=get_client_ip(request),
        )
    )

    # ── Small export: synchronous ─────────────────────────────────────────────
    if total <= ASYNC_EXPORT_THRESHOLD:
        xlsx_bytes = generate_supplier_excel(suppliers)

        from datetime import datetime
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"supplier_export_{timestamp}.xlsx"

        logger.info("sync_export_completed", rows=total, actor=current_user.id)

        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Row-Count": str(total),
            },
        )

    # ── Large export: enqueue ARQ job ─────────────────────────────────────────
    task_id = str(uuid.uuid4())

    redis = await create_pool(get_arq_redis_settings())
    try:
        await redis.enqueue_job(
            "export_suppliers_job",
            filters.model_dump(mode="json"),
            current_user.id,
            task_id,
        )
    finally:
        await redis.aclose()

    logger.info(
        "async_export_queued",
        task_id=task_id,
        estimated_rows=total,
        actor=current_user.id,
    )

    return Response(
        content=json.dumps(
            TaskResponse(
                task_id=task_id,
                status="queued",
                message=f"Export of {total} rows queued. Poll /export/{task_id} for status.",
                estimated_seconds=max(30, total // 1000),
            ).model_dump()
        ),
        media_type="application/json",
        status_code=status.HTTP_202_ACCEPTED,
    )


# ── GET /suppliers/export/{task_id} ───────────────────────────────────────────
@router.get(
    "/export/{task_id}",
    summary="Poll async export task status",
    response_model=SuccessResponse[dict],
)
async def get_export_status(
    task_id: str,
    current_user: CurrentUser,
) -> SuccessResponse[dict]:
    """
    Poll the status of an async export job.

    Returns:
        - status: "queued" | "running" | "completed" | "failed"
        - download_url: presigned MinIO URL (only when completed)
    """
    import redis.asyncio as aioredis

    r = aioredis.from_url(
        settings.redis.REDIS_URL,
        decode_responses=True,
    )

    try:
        result_key = f"export_task:{task_id}"
        raw = await r.get(result_key)
    finally:
        await r.aclose()

    if raw is None:
        return SuccessResponse(
            data={"status": "not_found", "task_id": task_id},
            message="Task not found or expired",
        )

    if raw == "running":
        return SuccessResponse(
            data={"status": "running", "task_id": task_id},
            message="Export is being generated",
        )

    result = json.loads(raw)
    result["task_id"] = task_id
    return SuccessResponse(data=result)
