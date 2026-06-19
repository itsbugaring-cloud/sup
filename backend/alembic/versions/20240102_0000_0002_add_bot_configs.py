"""
alembic/versions/20240102_0000_0002_add_bot_configs.py
──────────────────────────────────────────────────────────────────────────────
MIGRATION: Add bot_configs table
Revision: 0002
Description: Stores Telegram bot configuration (token, chat IDs, webhook, etc.)
             Sensitive fields (bot_token) are encrypted at the application level
             before being persisted — only the encrypted blob is stored here.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Table: bot_configs ────────────────────────────────────────────────────
    op.create_table(
        "bot_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            comment="UUID v4 primary key",
        ),
        sa.Column(
            "config_name",
            sa.String(100),
            nullable=False,
            server_default="default",
            unique=True,
            comment="Configuration slot name (supports multi-bot in future)",
        ),
        # ── Bot Token (stored encrypted by app layer) ─────────────────────────
        sa.Column(
            "bot_token_encrypted",
            sa.Text,
            nullable=True,
            comment="Telegram bot token encrypted with APP_SECRET_KEY (Fernet)",
        ),
        sa.Column(
            "bot_token_hint",
            sa.String(20),
            nullable=True,
            comment="Last 6 chars of bot token for display only (e.g., '...xAb3f')",
        ),
        sa.Column(
            "bot_username",
            sa.String(100),
            nullable=True,
            comment="Bot @username fetched from Telegram API on save",
        ),
        sa.Column(
            "bot_display_name",
            sa.String(255),
            nullable=True,
            comment="Bot display name fetched from Telegram API on save",
        ),
        # ── Webhook ───────────────────────────────────────────────────────────
        sa.Column(
            "webhook_url",
            sa.String(500),
            nullable=True,
            comment="Full HTTPS URL for the Telegram webhook endpoint",
        ),
        sa.Column(
            "webhook_secret",
            sa.String(255),
            nullable=True,
            comment="Secret token sent in X-Telegram-Bot-Api-Secret-Token header",
        ),
        sa.Column(
            "webhook_is_set",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="Whether the webhook has been successfully registered with Telegram",
        ),
        # ── Notification Chat IDs ─────────────────────────────────────────────
        sa.Column(
            "chat_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
            comment=(
                "Array of chat targets: "
                "[{\"chat_id\": \"-1001234567\", \"label\": \"Ops Team\", \"is_active\": true}]"
            ),
        ),
        # ── Notification Settings ─────────────────────────────────────────────
        sa.Column(
            "notifications_enabled",
            sa.Boolean,
            nullable=False,
            server_default="true",
            comment="Master switch for all bot notifications",
        ),
        sa.Column(
            "notify_on_create",
            sa.Boolean,
            nullable=False,
            server_default="true",
            comment="Send notification when a new supplier is created",
        ),
        sa.Column(
            "notify_on_status_change",
            sa.Boolean,
            nullable=False,
            server_default="true",
            comment="Send notification when a supplier status changes",
        ),
        sa.Column(
            "notify_on_document_upload",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="Send notification when a document is uploaded",
        ),
        sa.Column(
            "notify_on_export",
            sa.Boolean,
            nullable=False,
            server_default="true",
            comment="Notify when an async export completes",
        ),
        # ── Status ────────────────────────────────────────────────────────────
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="Whether this bot config is currently active",
        ),
        sa.Column(
            "last_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the token was last verified as valid",
        ),
        sa.Column(
            "last_error",
            sa.Text,
            nullable=True,
            comment="Last error message from Telegram API (for debugging)",
        ),
        # ── Audit ─────────────────────────────────────────────────────────────
        sa.Column(
            "created_by",
            sa.String(255),
            nullable=True,
            comment="Web user who created this config",
        ),
        sa.Column(
            "updated_by",
            sa.String(255),
            nullable=True,
            comment="Web user who last updated this config",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        comment="Telegram bot configuration. One active config per deployment.",
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    op.create_index("idx_bot_configs_config_name", "bot_configs", ["config_name"])
    op.create_index("idx_bot_configs_is_active", "bot_configs", ["is_active"])

    # ── updated_at trigger ────────────────────────────────────────────────────
    op.execute("""
        CREATE TRIGGER trg_bot_configs_updated_at
        BEFORE UPDATE ON bot_configs
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """)

    # ── Insert default empty config ────────────────────────────────────────────
    op.execute("""
        INSERT INTO bot_configs (config_name, is_active, notifications_enabled)
        VALUES ('default', false, true);
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_bot_configs_updated_at ON bot_configs;")
    op.drop_table("bot_configs")
