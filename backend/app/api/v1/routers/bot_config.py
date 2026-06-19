"""
app/api/v1/routers/bot_config.py
──────────────────────────────────────────────────────────────────────────────
FastAPI router for bot configuration (admin-only).

Endpoints:
  GET  /api/v1/bot-config           → get current config (no token returned)
  PUT  /api/v1/bot-config           → save config (token encrypted on save)
  POST /api/v1/bot-config/test      → test connection + optional test message
  POST /api/v1/bot-config/webhook   → register webhook with Telegram
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from app.core.dependencies import AdminUser, BotConfigRepo
from app.schemas.bot_config import (
    BotConfigRead,
    BotConfigUpdate,
    BotTestRequest,
    BotTestResult,
)
from app.schemas.common import SuccessResponse
from app.services.bot_config_service import BotConfigService

router = APIRouter(prefix="/bot-config", tags=["bot-config"])


def _get_service(repo: BotConfigRepo) -> BotConfigService:
    return BotConfigService(repo=repo)


# ── GET /bot-config ───────────────────────────────────────────────────────────
@router.get(
    "",
    summary="Get current bot configuration (admin only)",
    response_model=SuccessResponse[BotConfigRead],
)
async def get_bot_config(
    current_user: AdminUser,
    svc: BotConfigService = Depends(_get_service),
) -> SuccessResponse[BotConfigRead]:
    result = await svc.get_config()
    return SuccessResponse(data=result)


# ── PUT /bot-config ───────────────────────────────────────────────────────────
@router.put(
    "",
    summary="Update bot configuration (admin only)",
    response_model=SuccessResponse[BotConfigRead],
)
async def update_bot_config(
    body: BotConfigUpdate,
    current_user: AdminUser,
    svc: BotConfigService = Depends(_get_service),
) -> SuccessResponse[BotConfigRead]:
    result = await svc.update_config(data=body, actor_id=current_user.id)
    return SuccessResponse(data=result, message="Bot configuration saved")


# ── POST /bot-config/test ─────────────────────────────────────────────────────
@router.post(
    "/test",
    summary="Test bot token and send a test message (admin only)",
    response_model=SuccessResponse[BotTestResult],
)
async def test_bot_connection(
    body: BotTestRequest,
    current_user: AdminUser,
    svc: BotConfigService = Depends(_get_service),
) -> SuccessResponse[BotTestResult]:
    result = await svc.test_connection(chat_id=body.chat_id)
    return SuccessResponse(
        data=result,
        message="Test completed" if result.success else "Test failed",
    )


# ── POST /bot-config/webhook ──────────────────────────────────────────────────
@router.post(
    "/webhook",
    summary="Register webhook URL with Telegram (admin only)",
    response_model=SuccessResponse[dict],
)
async def register_webhook(
    current_user: AdminUser,
    svc: BotConfigService = Depends(_get_service),
) -> SuccessResponse[dict]:
    result = await svc.register_webhook()
    return SuccessResponse(
        data=result,
        message="Webhook registered successfully" if result.get("ok") else "Webhook registration failed",
    )
