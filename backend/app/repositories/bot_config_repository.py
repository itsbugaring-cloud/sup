"""
app/repositories/bot_config_repository.py
──────────────────────────────────────────────────────────────────────────────
Repository for the `bot_configs` table.

Single-row pattern: there is always exactly one row (config_name='default').
The `get_default()` method always returns it (upsert on first call).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot_config import BotConfig
from app.repositories.base import BaseRepository


class BotConfigRepository(BaseRepository[BotConfig]):
    """Async repository for the single-row `bot_configs` table."""

    model = BotConfig
    DEFAULT_NAME = "default"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_default(self) -> BotConfig:
        """
        Return the default bot config row.
        If somehow missing, recreate it (idempotent).
        """
        stmt = select(BotConfig).where(BotConfig.config_name == self.DEFAULT_NAME)
        result = await self._session.execute(stmt)
        config = result.scalar_one_or_none()

        if config is None:
            config = await self.create(config_name=self.DEFAULT_NAME)

        return config

    async def update_config(self, config: BotConfig, **kwargs) -> BotConfig:
        """Update bot config fields."""
        return await self.update(config, **kwargs)

    async def set_verified(
        self,
        config: BotConfig,
        bot_username: str,
        bot_display_name: str,
    ) -> BotConfig:
        """Mark config as verified after a successful Telegram API call."""
        return await self.update(
            config,
            bot_username=bot_username,
            bot_display_name=bot_display_name,
            last_verified_at=datetime.now(tz=timezone.utc),
            last_error=None,
        )

    async def set_error(self, config: BotConfig, error: str) -> BotConfig:
        """Record a Telegram API error for debugging."""
        return await self.update(config, last_error=error)

    async def set_webhook_status(
        self, config: BotConfig, is_set: bool
    ) -> BotConfig:
        return await self.update(config, webhook_is_set=is_set)
