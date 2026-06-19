"""
app/core/config.py
──────────────────────────────────────────────────────────────────────────────
Centralised application configuration loaded from environment variables.

Uses pydantic-settings v2 for:
  - Strong typing and validation of all env vars at startup.
  - Automatic reading from .env file (dev) or injected env vars (Docker/prod).
  - Computed DSNs constructed from individual parts to avoid secret duplication.

NEVER import settings from this module at module-level in services/models —
  always inject via dependency injection (app.core.dependencies).
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import (
    AnyHttpUrl,
    Field,
    PostgresDsn,
    RedisDsn,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL hostname")
    POSTGRES_PORT: int = Field(default=5432, ge=1, le=65535)
    POSTGRES_USER: str = Field(..., description="PostgreSQL username")
    POSTGRES_PASSWORD: str = Field(..., description="PostgreSQL password")
    POSTGRES_DB: str = Field(default="supplier_crm")

    # Connection pool settings
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    DB_POOL_TIMEOUT: int = Field(default=30, ge=5)
    DB_POOL_RECYCLE: int = Field(default=1800)  # 30 min — prevents stale connections
    DB_ECHO_SQL: bool = Field(default=False, description="Log all SQL statements")

    @computed_field  # type: ignore[misc]
    @property
    def DATABASE_URL(self) -> str:
        """Async PostgreSQL DSN for SQLAlchemy (asyncpg driver)."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Sync PostgreSQL DSN for Alembic migrations (psycopg2 driver)."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


class RedisSettings(BaseSettings):
    """Redis connection settings used by both API cache and Bot FSM."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379, ge=1, le=65535)
    REDIS_PASSWORD: str = Field(..., description="Redis AUTH password")
    REDIS_DB: int = Field(default=0, ge=0, le=15, description="Redis DB for API cache")
    REDIS_BOT_FSM_DB: int = Field(
        default=1, ge=0, le=15, description="Redis DB for Aiogram FSM"
    )

    REDIS_POOL_MAX_CONNECTIONS: int = Field(default=50)
    REDIS_SOCKET_TIMEOUT: float = Field(default=5.0)
    REDIS_SOCKET_CONNECT_TIMEOUT: float = Field(default=3.0)

    @computed_field  # type: ignore[misc]
    @property
    def REDIS_URL(self) -> str:
        """Redis DSN for API cache and ARQ worker."""
        return (
            f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}"
            f":{self.REDIS_PORT}/{self.REDIS_DB}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def REDIS_FSM_URL(self) -> str:
        """Redis DSN dedicated to Aiogram FSM state storage."""
        return (
            f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}"
            f":{self.REDIS_PORT}/{self.REDIS_BOT_FSM_DB}"
        )


class MinIOSettings(BaseSettings):
    """MinIO / S3-compatible object storage settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    MINIO_HOST: str = Field(default="localhost")
    MINIO_PORT: int = Field(default=9000)
    MINIO_ROOT_USER: str = Field(..., description="MinIO access key / root user")
    MINIO_ROOT_PASSWORD: str = Field(..., description="MinIO secret key / root password")
    MINIO_BUCKET_DOCUMENTS: str = Field(default="supplier-documents")
    MINIO_BUCKET_EXPORTS: str = Field(default="crm-exports")
    MINIO_USE_SSL: bool = Field(default=False)
    MINIO_PUBLIC_URL: str = Field(
        default="http://localhost:9000",
        description="Externally reachable base URL for presigned URLs",
    )

    # Pre-signed URL expiry
    PRESIGNED_URL_EXPIRY_SECONDS: int = Field(
        default=3600, description="1 hour default for document access URLs"
    )
    EXPORT_PRESIGNED_URL_EXPIRY_SECONDS: int = Field(
        default=86400, description="24 hours for export download URLs"
    )

    @computed_field  # type: ignore[misc]
    @property
    def MINIO_ENDPOINT(self) -> str:
        """Internal MinIO endpoint for SDK connection."""
        return f"{self.MINIO_HOST}:{self.MINIO_PORT}"


class TelegramSettings(BaseSettings):
    """Telegram Bot configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    TELEGRAM_BOT_TOKEN: str = Field(..., description="Token from @BotFather")
    TELEGRAM_WEBHOOK_SECRET: str = Field(
        ..., description="Secret token for Telegram webhook verification (X-Telegram-Bot-Api-Secret-Token)"
    )
    TELEGRAM_WEBHOOK_URL: str = Field(
        ..., description="Full HTTPS URL for the webhook endpoint"
    )
    # Comma-separated list of allowed Telegram user IDs
    TELEGRAM_ALLOWED_USER_IDS: str = Field(
        default="",
        description="Comma-separated Telegram user IDs allowed to use the bot",
    )

    @computed_field  # type: ignore[misc]
    @property
    def ALLOWED_USER_IDS(self) -> list[int]:
        """Parsed list of whitelisted Telegram user IDs."""
        if not self.TELEGRAM_ALLOWED_USER_IDS:
            return []
        return [
            int(uid.strip())
            for uid in self.TELEGRAM_ALLOWED_USER_IDS.split(",")
            if uid.strip().isdigit()
        ]


class JWTSettings(BaseSettings):
    """JWT Authentication configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    JWT_SECRET_KEY: str = Field(..., min_length=32, description="Must be at least 32 chars")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1)


class RateLimitSettings(BaseSettings):
    """Rate limiting configuration for SlowAPI."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    RATE_LIMIT_DEFAULT: str = Field(default="100/minute")
    RATE_LIMIT_LOGIN: str = Field(default="5/minute")
    RATE_LIMIT_EXPORT: str = Field(default="3/minute")
    RATE_LIMIT_WEBHOOK: str = Field(default="30/second")


class ARQSettings(BaseSettings):
    """ARQ background worker settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    ARQ_MAX_JOBS: int = Field(default=10, ge=1)
    ARQ_JOB_TIMEOUT: int = Field(default=3600, ge=60)


class LoggingSettings(BaseSettings):
    """Structured logging configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json", description="json | text")

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return v.upper()

    @field_validator("LOG_FORMAT")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        if v.lower() not in {"json", "text"}:
            raise ValueError("LOG_FORMAT must be 'json' or 'text'")
        return v.lower()


class AppSettings(BaseSettings):
    """Top-level application settings — composes all sub-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ── App Identity ──────────────────────────────────────────────────────────
    APP_ENV: str = Field(default="development", description="development|staging|production")
    APP_NAME: str = Field(default="Supplier CRM")
    APP_VERSION: str = Field(default="1.0.0")
    APP_SECRET_KEY: str = Field(..., min_length=32)
    APP_DEBUG: bool = Field(default=False)
    APP_DOMAIN: str = Field(default="localhost")
    APP_PORT: int = Field(default=8000)
    API_V1_PREFIX: str = Field(default="/api/v1")

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = Field(
        default='["http://localhost:3000"]',
        description="JSON-encoded list of allowed origins",
    )

    @computed_field  # type: ignore[misc]
    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        """Parsed CORS origins list."""
        try:
            return json.loads(self.CORS_ORIGINS)
        except (json.JSONDecodeError, TypeError):
            return [self.CORS_ORIGINS]

    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v.lower() not in allowed:
            raise ValueError(f"APP_ENV must be one of {allowed}")
        return v.lower()

    @computed_field  # type: ignore[misc]
    @property
    def IS_PRODUCTION(self) -> bool:
        return self.APP_ENV == "production"

    @computed_field  # type: ignore[misc]
    @property
    def IS_DEVELOPMENT(self) -> bool:
        return self.APP_ENV == "development"

    # ── Composed sub-settings ─────────────────────────────────────────────────
    # Each is instantiated independently to allow granular injection.
    # Access via: settings.db.DATABASE_URL, settings.redis.REDIS_URL, etc.
    @computed_field  # type: ignore[misc]
    @property
    def db(self) -> DatabaseSettings:
        return DatabaseSettings()

    @computed_field  # type: ignore[misc]
    @property
    def redis(self) -> RedisSettings:
        return RedisSettings()

    @computed_field  # type: ignore[misc]
    @property
    def minio(self) -> MinIOSettings:
        return MinIOSettings()

    @computed_field  # type: ignore[misc]
    @property
    def telegram(self) -> TelegramSettings:
        return TelegramSettings()

    @computed_field  # type: ignore[misc]
    @property
    def jwt(self) -> JWTSettings:
        return JWTSettings()

    @computed_field  # type: ignore[misc]
    @property
    def rate_limit(self) -> RateLimitSettings:
        return RateLimitSettings()

    @computed_field  # type: ignore[misc]
    @property
    def arq(self) -> ARQSettings:
        return ARQSettings()

    @computed_field  # type: ignore[misc]
    @property
    def logging(self) -> LoggingSettings:
        return LoggingSettings()


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """
    Returns a cached singleton of AppSettings.

    Usage:
        from app.core.config import get_settings
        settings = get_settings()

    FastAPI Dependency Injection:
        from fastapi import Depends
        from app.core.config import get_settings, AppSettings

        async def my_endpoint(settings: AppSettings = Depends(get_settings)):
            ...
    """
    return AppSettings()


# Module-level singleton for use outside of FastAPI DI context
# (e.g., Alembic env.py, ARQ worker startup)
settings: AppSettings = get_settings()
