"""
app/api/v1/routers/webhook.py
──────────────────────────────────────────────────────────────────────────────
Dynamic Telegram Webhook Router.
Receives updates from Telegram for multiple tenant bots.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.bot_config_repository import BotConfigRepository
from app.services.bot_config_service import _decrypt_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/{tenant_id}", include_in_schema=False)
async def telegram_webhook(
    tenant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Receive Telegram updates for a specific tenant.
    We lookup the bot token for the tenant, decrypt it, and pass it to aiogram.
    """
    repo = BotConfigRepository(db, tenant_id=tenant_id)
    config = await repo.get_default()

    if not config or not config.bot_token_encrypted:
        logger.warning(f"Webhook received for tenant {tenant_id} but no bot configured.")
        return {"ok": True}  # Return 200 so Telegram stops retrying

    try:
        token = _decrypt_token(config.bot_token_encrypted)
    except Exception as e:
        logger.error(f"Failed to decrypt token for tenant {tenant_id}: {e}")
        return {"ok": True}

    update_data = await request.json()
    
    # In a full Aiogram implementation, we would feed `update_data` to a `Dispatcher`.
    # For now, we acknowledge receipt.
    logger.info(f"Received webhook update for tenant {tenant_id}: {update_data.get('update_id')}")

    return {"ok": True}
