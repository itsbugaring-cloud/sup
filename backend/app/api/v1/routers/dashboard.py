from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import AdminUser, AuditRepo, BotConfigRepo, SupplierRepo
from app.schemas.audit_log import AuditLogFilter, AuditLogRead
from app.schemas.common import SuccessResponse
from app.schemas.supplier import SupplierFilter, SupplierListRead
from app.models.supplier import SupplierStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/overview",
    summary="Admin dashboard overview",
    response_model=SuccessResponse[dict],
)
async def get_dashboard_overview(
    current_user: AdminUser,
    supplier_repo: SupplierRepo,
    audit_repo: AuditRepo,
    bot_repo: BotConfigRepo,
) -> SuccessResponse[dict]:
    pending_suppliers, _ = await supplier_repo.list_suppliers(
        SupplierFilter(status=SupplierStatus.PENDING_REVIEW),
        page=1,
        per_page=5,
    )
    recent_logs, _ = await audit_repo.list_audit_logs(
        AuditLogFilter(),
        page=1,
        per_page=8,
    )
    stats = {
        "total_active": await supplier_repo.get_total_active(),
        "by_status": {
            key.value if hasattr(key, "value") else key: value
            for key, value in (await supplier_repo.get_status_counts()).items()
        },
    }
    bot_config = await bot_repo.get_default()

    data = {
        "stats": stats,
        "pending_suppliers": [
            SupplierListRead.model_validate(item).model_dump(mode="json")
            for item in pending_suppliers
        ],
        "recent_activity": [
            AuditLogRead.model_validate(item).model_dump(mode="json")
            for item in recent_logs
        ],
        "telegram": {
            "is_active": bot_config.is_active,
            "has_token": bool(bot_config.bot_token_encrypted),
            "bot_username": bot_config.bot_username,
            "webhook_is_set": bot_config.webhook_is_set,
            "notifications_enabled": bot_config.notifications_enabled,
            "chat_count": len(bot_config.chat_ids or []),
            "last_error": bot_config.last_error,
            "last_verified_at": bot_config.last_verified_at,
        },
    }
    return SuccessResponse(data=data)
