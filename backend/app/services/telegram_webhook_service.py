from __future__ import annotations

import html
import uuid
from typing import Any

from app.core.logging import get_logger
from app.models.audit_log import AuditActorType
from app.models.supplier import SupplierStatus
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.bot_config_repository import BotConfigRepository
from app.repositories.supplier_document_repository import SupplierDocumentRepository
from app.repositories.supplier_repository import SupplierRepository
from app.schemas.supplier import SupplierFilter, SupplierStatusUpdate
from app.services.minio_service import MinIOService
from app.services.supplier_service import SupplierService
from app.services.telegram_client import TelegramClient
from app.services.telegram_notifier import TelegramNotifier

logger = get_logger(__name__)


def _display_name(from_user: dict[str, Any]) -> str:
    username = from_user.get("username")
    if username:
        return f"@{username}"
    full_name = " ".join(
        part for part in [from_user.get("first_name"), from_user.get("last_name")] if part
    ).strip()
    return full_name or "Telegram"


def _review_markup(supplier_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Activate", "callback_data": f"set:{supplier_id}:active"},
                {"text": "Mark Inactive", "callback_data": f"set:{supplier_id}:inactive"},
            ],
            [
                {"text": "Blacklist", "callback_data": f"set:{supplier_id}:blacklisted"},
                {"text": "Reset Pending", "callback_data": f"set:{supplier_id}:pending_review"},
            ],
        ]
    }


def _status_text(status: str) -> str:
    return status.replace("_", " ").title()


class TelegramWebhookService:
    def __init__(
        self,
        supplier_repo: SupplierRepository,
        audit_repo: AuditLogRepository,
        doc_repo: SupplierDocumentRepository,
        bot_repo: BotConfigRepository,
    ) -> None:
        self._supplier_repo = supplier_repo
        self._audit_repo = audit_repo
        self._doc_repo = doc_repo
        self._bot_repo = bot_repo
        self._notifier = TelegramNotifier(bot_repo)

    async def process_update(self, update_data: dict[str, Any]) -> None:
        config = await self._bot_repo.get_default()
        if not config.bot_token_encrypted:
            return

        from app.services.bot_config_service import _decrypt_token

        token = _decrypt_token(config.bot_token_encrypted)
        client = TelegramClient(token)

        if update_data.get("callback_query"):
            await self._handle_callback_query(client, update_data["callback_query"])
            return
        if update_data.get("message"):
            await self._handle_message(client, update_data["message"])

    async def _handle_message(
        self,
        client: TelegramClient,
        message: dict[str, Any],
    ) -> None:
        text = (message.get("text") or "").strip()
        chat_id = str(message.get("chat", {}).get("id"))
        if not text or not chat_id:
            return

        if text in {"/start", "/help"}:
            await client.send_message(
                chat_id,
                (
                    "🤖 <b>Supplier CRM assistant</b>\n"
                    "Use /stats for workspace metrics.\n"
                    "Use /pending for suppliers waiting review."
                ),
            )
            return

        if text == "/stats":
            stats = await SupplierService(
                supplier_repo=self._supplier_repo,
                audit_repo=self._audit_repo,
                doc_repo=self._doc_repo,
                minio=MinIOService(),
            ).get_dashboard_stats()
            await client.send_message(
                chat_id,
                (
                    "🧭 <b>Workspace summary</b>\n"
                    f"Total suppliers: <b>{stats['total_active']}</b>\n"
                    f"Pending review: <b>{stats['by_status'].get('pending_review', 0)}</b>\n"
                    f"Active: <b>{stats['by_status'].get('active', 0)}</b>\n"
                    f"Blacklisted: <b>{stats['by_status'].get('blacklisted', 0)}</b>"
                ),
            )
            return

        if text == "/pending":
            suppliers, _ = await self._supplier_repo.list_suppliers(
                SupplierFilter(status=SupplierStatus.PENDING_REVIEW),
                page=1,
                per_page=5,
            )
            if not suppliers:
                await client.send_message(
                    chat_id,
                    "✅ <b>No pending suppliers</b>\nAll submissions have been reviewed.",
                )
                return

            for supplier in suppliers:
                await client.send_message(
                    chat_id,
                    (
                        "🕒 <b>Pending review</b>\n"
                        f"<b>{html.escape(supplier.company_name)}</b>\n"
                        f"PIC: {html.escape(supplier.pic_name)}\n"
                        f"City: {html.escape(supplier.city or '-')}\n"
                        f"Status: <b>{html.escape(_status_text(str(supplier.status)))}</b>"
                    ),
                    _review_markup(str(supplier.id)),
                )
            return

        await client.send_message(
            chat_id,
            "Unknown command. Use /stats or /pending.",
        )

    async def _handle_callback_query(
        self,
        client: TelegramClient,
        callback_query: dict[str, Any],
    ) -> None:
        data = callback_query.get("data", "")
        callback_query_id = callback_query.get("id")
        message = callback_query.get("message", {})
        from_user = callback_query.get("from", {})
        chat_id = str(message.get("chat", {}).get("id"))
        message_id = message.get("message_id")

        if not callback_query_id or not chat_id or not message_id:
            return

        if data.startswith("review:"):
            supplier_id = data.split(":", 1)[1]
            supplier = await self._supplier_repo.get_active_by_id(uuid.UUID(supplier_id))
            if not supplier:
                await client.answer_callback_query(callback_query_id, "Supplier not found")
                return

            await client.edit_message_text(
                chat_id,
                message_id,
                (
                    "🔎 <b>Supplier review</b>\n"
                    f"<b>{html.escape(supplier.company_name)}</b>\n"
                    f"PIC: {html.escape(supplier.pic_name)}\n"
                    f"Phone: {html.escape(supplier.pic_phone)}\n"
                    f"Location: {html.escape(supplier.city or '-')} / {html.escape(supplier.province or '-')}\n"
                    f"Status: <b>{html.escape(str(supplier.status).replace('_', ' ').title())}</b>"
                ),
                _review_markup(str(supplier.id)),
            )
            await client.answer_callback_query(callback_query_id, "Review loaded")
            return

        if data.startswith("set:"):
            _, supplier_id, next_status = data.split(":", 2)
            supplier = await self._supplier_repo.get_active_by_id(uuid.UUID(supplier_id))
            if not supplier:
                await client.answer_callback_query(callback_query_id, "Supplier not found")
                return
            if next_status not in {"active", "inactive", "blacklisted", "pending_review"}:
                await client.answer_callback_query(callback_query_id, "Invalid status")
                return

            actor_name = _display_name(from_user)
            svc = SupplierService(
                supplier_repo=self._supplier_repo,
                audit_repo=self._audit_repo,
                doc_repo=self._doc_repo,
                minio=MinIOService(),
            )
            result = await svc.update_status(
                supplier_id=supplier.id,
                data=SupplierStatusUpdate(status=SupplierStatus(next_status)),
                actor_id=str(from_user.get("id", "telegram")),
                actor_display_name=actor_name,
                actor_type=AuditActorType.TELEGRAM_BOT,
            )

            await self._notifier.send_status_change(
                result,
                actor_display_name=actor_name,
                source="Telegram Bot",
            )
            await client.edit_message_text(
                chat_id,
                message_id,
                (
                    "✅ <b>Status updated from Telegram</b>\n"
                    f"<b>{html.escape(result.company_name)}</b>\n"
                    f"New status: <b>{html.escape(_status_text(str(result.status)))}</b>\n"
                    f"Updated by: {html.escape(actor_name)}"
                ),
            )
            await client.answer_callback_query(callback_query_id, "Status updated")
