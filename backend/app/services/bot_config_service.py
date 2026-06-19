"""
app/services/bot_config_service.py
──────────────────────────────────────────────────────────────────────────────
Business logic for bot configuration management.

Security:
  - Bot tokens are encrypted with Fernet (AES-128-CBC) before storage.
  - The encryption key is derived from APP_SECRET_KEY.
  - Raw tokens are NEVER logged.

Telegram API calls:
  - `verify_token()` calls GET /bot{token}/getMe to validate the token.
  - `send_test_message()` calls POST /bot{token}/sendMessage.
  - Uses httpx for async HTTP.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import get_logger
from app.models.bot_config import BotConfig
from app.repositories.bot_config_repository import BotConfigRepository
from app.schemas.bot_config import (
    BotConfigRead,
    BotConfigUpdate,
    BotTestResult,
    ChatIdEntry,
)

logger = get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def _get_fernet() -> Fernet:
    """
    Derive a Fernet key from APP_SECRET_KEY.
    Fernet requires exactly 32 URL-safe base64-encoded bytes.
    """
    key_bytes = settings.APP_SECRET_KEY.encode()[:32].ljust(32, b"0")
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def _encrypt_token(token: str) -> str:
    """Encrypt a bot token with Fernet."""
    return _get_fernet().encrypt(token.encode()).decode()


def _decrypt_token(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted bot token."""
    return _get_fernet().decrypt(encrypted.encode()).decode()


def _mask_token(token: str) -> str:
    """Return hint: last 6 chars prefixed with '...' (e.g., '...xAb3fX')."""
    if len(token) <= 6:
        return "..." + token
    return "..." + token[-6:]


class BotConfigService:
    """Service for Telegram bot configuration management."""

    def __init__(self, repo: BotConfigRepository) -> None:
        self._repo = repo

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_config(self) -> BotConfigRead:
        """Return the current bot configuration (safe — no token in response)."""
        config = await self._repo.get_default()
        return self._to_read_schema(config)

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_config(
        self,
        data: BotConfigUpdate,
        actor_id: str,
    ) -> BotConfigRead:
        """
        Save bot configuration updates.

        If a new bot_token is provided:
          1. Validate it against Telegram API (getMe).
          2. Encrypt and store it.
          3. Store hint (last 6 chars) for display.
        """
        config = await self._repo.get_default()
        update_kwargs: dict[str, Any] = {"updated_by": actor_id}

        # ── New token provided → validate + encrypt ───────────────────────────
        if data.bot_token:
            bot_info = await self._call_get_me(data.bot_token)
            if not bot_info["ok"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid bot token: {bot_info.get('description', 'Unknown error')}",
                )

            bot_result = bot_info["result"]
            update_kwargs["bot_token_encrypted"] = _encrypt_token(data.bot_token)
            update_kwargs["bot_token_hint"] = _mask_token(data.bot_token)
            update_kwargs["bot_username"] = bot_result.get("username")
            update_kwargs["bot_display_name"] = bot_result.get("first_name")
            update_kwargs["last_verified_at"] = datetime.now(tz=timezone.utc)
            update_kwargs["last_error"] = None
            logger.info("bot_token_updated", username=bot_result.get("username"))

        # ── Other fields ──────────────────────────────────────────────────────
        if data.webhook_url is not None:
            update_kwargs["webhook_url"] = data.webhook_url
            update_kwargs["webhook_is_set"] = False  # Must re-register

        if data.webhook_secret is not None:
            update_kwargs["webhook_secret"] = data.webhook_secret

        if data.chat_ids is not None:
            update_kwargs["chat_ids"] = [c.model_dump() for c in data.chat_ids]

        for field in (
            "notifications_enabled",
            "notify_on_create",
            "notify_on_status_change",
            "notify_on_document_upload",
            "notify_on_export",
            "is_active",
        ):
            value = getattr(data, field, None)
            if value is not None:
                update_kwargs[field] = value

        updated = await self._repo.update_config(config, **update_kwargs)
        return self._to_read_schema(updated)

    # ── Test Connection ───────────────────────────────────────────────────────

    async def test_connection(
        self, chat_id: str | None = None
    ) -> BotTestResult:
        """
        Test the configured bot token and optionally send a test message.

        Steps:
          1. Decrypt token.
          2. Call getMe to verify bot identity.
          3. If chat_id provided, send a test message.
        """
        config = await self._repo.get_default()

        if not config.bot_token_encrypted:
            return BotTestResult(
                success=False,
                message="No bot token configured. Please save a token first.",
            )

        try:
            token = _decrypt_token(config.bot_token_encrypted)
        except InvalidToken:
            return BotTestResult(
                success=False,
                message="Token decryption failed — app secret may have changed.",
            )

        # ── Validate token ────────────────────────────────────────────────────
        bot_info = await self._call_get_me(token)
        if not bot_info["ok"]:
            await self._repo.set_error(config, bot_info.get("description", "Unknown"))
            return BotTestResult(
                success=False,
                message=f"Token validation failed: {bot_info.get('description')}",
                error_code=bot_info.get("error_code"),
            )

        bot_result = bot_info["result"]
        await self._repo.set_verified(
            config,
            bot_username=bot_result.get("username", ""),
            bot_display_name=bot_result.get("first_name", ""),
        )

        # ── Optionally send test message ──────────────────────────────────────
        target_chat_id = chat_id
        if not target_chat_id and config.chat_ids:
            active_chats = [
                c for c in config.chat_ids if c.get("is_active", True)
            ]
            if active_chats:
                target_chat_id = active_chats[0]["chat_id"]

        if target_chat_id:
            msg_result = await self._send_test_message(token, target_chat_id)
            if not msg_result["ok"]:
                return BotTestResult(
                    success=False,
                    message=f"Bot token valid ✓ but message send failed: {msg_result.get('description')}",
                    bot_username=bot_result.get("username"),
                    bot_display_name=bot_result.get("first_name"),
                    chat_id_tested=target_chat_id,
                    error_code=msg_result.get("error_code"),
                )
            return BotTestResult(
                success=True,
                message="✅ Bot token valid and test message sent successfully!",
                bot_username=bot_result.get("username"),
                bot_display_name=bot_result.get("first_name"),
                chat_id_tested=target_chat_id,
            )

        return BotTestResult(
            success=True,
            message="✅ Bot token is valid!",
            bot_username=bot_result.get("username"),
            bot_display_name=bot_result.get("first_name"),
        )

    # ── Register Webhook ──────────────────────────────────────────────────────

    async def register_webhook(self) -> dict[str, Any]:
        """Call Telegram setWebhook API to register the configured webhook URL."""
        config = await self._repo.get_default()

        if not config.bot_token_encrypted:
            raise HTTPException(status_code=400, detail="No bot token configured")
        if not config.webhook_url:
            raise HTTPException(status_code=400, detail="No webhook URL configured")

        token = _decrypt_token(config.bot_token_encrypted)

        payload: dict[str, Any] = {
            "url": config.webhook_url,
            "max_connections": 40,
            "allowed_updates": ["message", "callback_query"],
        }
        if config.webhook_secret:
            payload["secret_token"] = config.webhook_secret

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API}/bot{token}/setWebhook",
                json=payload,
            )
            result = resp.json()

        if result.get("ok"):
            await self._repo.set_webhook_status(config, is_set=True)
            logger.info("webhook_registered", url=config.webhook_url)
        else:
            await self._repo.set_error(config, result.get("description", "Unknown"))
            logger.error("webhook_registration_failed", error=result.get("description"))

        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _call_get_me(self, token: str) -> dict[str, Any]:
        """Call Telegram getMe API to validate a token."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{TELEGRAM_API}/bot{token}/getMe")
                return resp.json()
        except httpx.RequestError as e:
            return {"ok": False, "description": f"Network error: {e}"}

    async def _send_test_message(
        self, token: str, chat_id: str
    ) -> dict[str, Any]:
        """Send a test message to a Telegram chat."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{TELEGRAM_API}/bot{token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": (
                            "🤖 *Supplier CRM Bot*\n\n"
                            "✅ Koneksi berhasil dikonfigurasi\\!\n"
                            "Bot siap menerima notifikasi dari sistem CRM Supplier\\."
                        ),
                        "parse_mode": "MarkdownV2",
                    },
                )
                return resp.json()
        except httpx.RequestError as e:
            return {"ok": False, "description": f"Network error: {e}"}

    def _to_read_schema(self, config: BotConfig) -> BotConfigRead:
        """Convert ORM model to the safe read schema."""
        chat_id_entries = []
        if config.chat_ids:
            for item in config.chat_ids:
                if isinstance(item, dict):
                    try:
                        chat_id_entries.append(ChatIdEntry(**item))
                    except Exception:
                        pass

        return BotConfigRead(
            id=config.id,
            config_name=config.config_name,
            has_token=bool(config.bot_token_encrypted),
            bot_token_hint=config.bot_token_hint,
            bot_username=config.bot_username,
            bot_display_name=config.bot_display_name,
            webhook_url=config.webhook_url,
            webhook_is_set=config.webhook_is_set,
            chat_ids=chat_id_entries,
            notifications_enabled=config.notifications_enabled,
            notify_on_create=config.notify_on_create,
            notify_on_status_change=config.notify_on_status_change,
            notify_on_document_upload=config.notify_on_document_upload,
            notify_on_export=config.notify_on_export,
            is_active=config.is_active,
            last_verified_at=config.last_verified_at,
            last_error=config.last_error,
            updated_by=config.updated_by,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )
