"""
app/models/bot_config.py
──────────────────────────────────────────────────────────────────────────────
SQLAlchemy ORM model for the `bot_configs` table.

The actual bot token is stored encrypted (Fernet symmetric encryption).
Only `bot_token_hint` (last 6 chars) is stored in plaintext for display.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, TenantMixin


class BotConfig(TimestampMixin, TenantMixin, Base):
    """
    Telegram bot configuration entity.

    Table: bot_configs
    Token stored encrypted — decrypted only in memory by the service layer.
    """

    __tablename__ = "bot_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    config_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        server_default="default",
        comment="Config slot name",
    )

    # ── Encrypted token ───────────────────────────────────────────────────────
    bot_token_encrypted: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Fernet-encrypted bot token"
    )
    bot_token_hint: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="Last 6 chars for display"
    )

    # ── Bot info (populated on verify) ───────────────────────────────────────
    bot_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bot_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Webhook ───────────────────────────────────────────────────────────────
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    webhook_is_set: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # ── Chat IDs (JSONB array) ────────────────────────────────────────────────
    # Format: [{"chat_id": "-1001234567", "label": "Ops Team", "is_active": true}]
    chat_ids: Mapped[list | None] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    # ── Notification toggles ──────────────────────────────────────────────────
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    notify_on_create: Mapped[bool] = mapped_column(Boolean, server_default="true")
    notify_on_status_change: Mapped[bool] = mapped_column(Boolean, server_default="true")
    notify_on_document_upload: Mapped[bool] = mapped_column(Boolean, server_default="false")
    notify_on_export: Mapped[bool] = mapped_column(Boolean, server_default="true")

    # ── Status ────────────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="false")
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<BotConfig name={self.config_name!r} "
            f"active={self.is_active} username={self.bot_username!r}>"
        )
