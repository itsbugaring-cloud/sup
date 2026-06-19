"""
app/schemas/bot_config.py
──────────────────────────────────────────────────────────────────────────────
Pydantic schemas for Bot Configuration API.

Security note:
  - `BotConfigRead` NEVER returns the raw token or the encrypted blob.
  - Only `bot_token_hint` (e.g., "...xAb3f") is returned for display.
  - The token is accepted as input on save and immediately encrypted in service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import CRMBaseModel


class ChatIdEntry(CRMBaseModel):
    """A single Telegram chat target (group, channel, or user)."""

    chat_id: str = Field(
        ...,
        description="Telegram chat ID (numeric, may be negative for groups)",
        examples=["-1001234567890", "987654321"],
    )
    label: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable label for this chat",
        examples=["Ops Team", "Management", "Field Staff"],
    )
    is_active: bool = Field(
        default=True,
        description="Whether notifications should be sent to this chat",
    )

    @field_validator("chat_id")
    @classmethod
    def validate_chat_id(cls, v: str) -> str:
        """Chat IDs must be numeric (possibly prefixed with -)."""
        cleaned = v.strip()
        try:
            int(cleaned)
        except ValueError:
            raise ValueError(
                "Chat ID must be a numeric value (e.g., -1001234567890)"
            )
        return cleaned


class BotConfigUpdate(CRMBaseModel):
    """
    Input schema for updating bot configuration.
    Only provided fields are updated (PATCH semantics).

    The `bot_token` field is write-only — it is accepted here,
    encrypted in the service layer, and NEVER returned.
    """

    bot_token: str | None = Field(
        default=None,
        min_length=20,
        description="Telegram bot token from @BotFather (write-only, stored encrypted)",
        examples=["7123456789:AAH..."],
    )
    webhook_url: str | None = Field(
        default=None,
        max_length=500,
        description="Full HTTPS URL for the webhook endpoint",
    )
    webhook_secret: str | None = Field(
        default=None,
        max_length=255,
        description="Secret token for webhook header verification",
    )
    chat_ids: list[ChatIdEntry] | None = Field(
        default=None,
        description="Array of target chat IDs with labels",
    )
    notifications_enabled: bool | None = Field(default=None)
    notify_on_create: bool | None = Field(default=None)
    notify_on_status_change: bool | None = Field(default=None)
    notify_on_document_upload: bool | None = Field(default=None)
    notify_on_export: bool | None = Field(default=None)
    is_active: bool | None = Field(default=None)


class BotConfigRead(CRMBaseModel):
    """
    Bot configuration response schema.
    NEVER includes raw token or encrypted blob.
    """

    id: uuid.UUID
    config_name: str
    # ── Token display (hint only) ─────────────────────────────────────────────
    has_token: bool = Field(description="Whether a token has been configured")
    bot_token_hint: str | None = Field(
        None, description="Last 6 chars for display (e.g., '...Ab3fX')"
    )
    # ── Bot identity ──────────────────────────────────────────────────────────
    bot_username: str | None
    bot_display_name: str | None
    # ── Webhook ───────────────────────────────────────────────────────────────
    webhook_url: str | None
    webhook_is_set: bool
    # ── Chat IDs ──────────────────────────────────────────────────────────────
    chat_ids: list[ChatIdEntry]
    # ── Notification settings ─────────────────────────────────────────────────
    notifications_enabled: bool
    notify_on_create: bool
    notify_on_status_change: bool
    notify_on_document_upload: bool
    notify_on_export: bool
    # ── Status ────────────────────────────────────────────────────────────────
    is_active: bool
    last_verified_at: datetime | None
    last_error: str | None
    # ── Audit ─────────────────────────────────────────────────────────────────
    updated_by: str | None
    created_at: datetime
    updated_at: datetime


class BotTestRequest(CRMBaseModel):
    """Request body for the test-connection endpoint."""

    chat_id: str | None = Field(
        default=None,
        description="Specific chat ID to test; uses first active chat if omitted",
    )


class BotTestResult(CRMBaseModel):
    """Result of a bot connection test."""

    success: bool
    message: str
    bot_username: str | None = None
    bot_display_name: str | None = None
    chat_id_tested: str | None = None
    error_code: int | None = None
