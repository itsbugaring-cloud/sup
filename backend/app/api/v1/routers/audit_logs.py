"""
app/api/v1/routers/audit_logs.py
──────────────────────────────────────────────────────────────────────────────
FastAPI router for Audit Log read operations (admin only).

Endpoints:
  GET /api/v1/audit-logs                          → paginated list
  GET /api/v1/audit-logs/{entity_type}/{entity_id} → entity change history
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.dependencies import AdminUser, AuditRepo
from app.models.audit_log import AuditAction, AuditActorType
from app.schemas.audit_log import AuditLogFilter, AuditLogRead
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get(
    "",
    summary="List audit logs (admin only)",
    response_model=PaginatedResponse[AuditLogRead],
)
async def list_audit_logs(
    current_user: AdminUser,
    audit_repo: AuditRepo,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    action: AuditAction | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    actor_type: AuditActorType | None = Query(default=None),
) -> PaginatedResponse[AuditLogRead]:
    filters = AuditLogFilter(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        actor_type=actor_type,
    )

    logs, total = await audit_repo.list_audit_logs(filters=filters, page=page, per_page=per_page)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    return PaginatedResponse(
        data=[AuditLogRead.model_validate(log) for log in logs],
        meta=PaginationMeta(
            page=page,
            per_page=per_page,
            total_items=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


@router.get(
    "/{entity_type}/{entity_id}",
    summary="Get change history for a specific record (admin only)",
    response_model=SuccessResponse[list[AuditLogRead]],
)
async def get_entity_history(
    entity_type: str,
    entity_id: str,
    current_user: AdminUser,
    audit_repo: AuditRepo,
    limit: int = Query(default=100, ge=1, le=500),
) -> SuccessResponse[list[AuditLogRead]]:
    logs = await audit_repo.get_entity_history(
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )
    return SuccessResponse(
        data=[AuditLogRead.model_validate(log) for log in logs],
        message=f"{len(logs)} audit events found for {entity_type}:{entity_id}",
    )
