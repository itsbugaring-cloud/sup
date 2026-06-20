from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.bot_config_repository import BotConfigRepository
from app.repositories.supplier_document_repository import SupplierDocumentRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.telegram_webhook_service import TelegramWebhookService

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/{tenant_id}", include_in_schema=False)
async def telegram_webhook(
    tenant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    update_data = await request.json()
    service = TelegramWebhookService(
        supplier_repo=SupplierRepository(db, tenant_id=tenant_id),
        audit_repo=AuditLogRepository(db, tenant_id=tenant_id),
        doc_repo=SupplierDocumentRepository(db, tenant_id=tenant_id),
        bot_repo=BotConfigRepository(db, tenant_id=tenant_id),
    )
    await service.process_update(update_data)
    return {"ok": True}
