from __future__ import annotations

import html
import uuid
from typing import Any

from app.core.logging import get_logger
from app.repositories.bot_config_repository import BotConfigRepository
from app.services.telegram_client import TelegramClient

logger = get_logger(__name__)


def _status_label(status: str) -> str:
    return status.replace("_", " ").title()


def _supplier_markup(supplier_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Review", "callback_data": f"review:{supplier_id}"},
                {"text": "Activate", "callback_data": f"set:{supplier_id}:active"},
            ],
            [
                {"text": "Mark Inactive", "callback_data": f"set:{supplier_id}:inactive"},
                {"text": "Blacklist", "callback_data": f"set:{supplier_id}:blacklisted"},
            ],
        ]
    }


class TelegramNotifier:
    def __init__(self, repo: BotConfigRepository) -> None:
        self._repo = repo

    async def _get_client_and_chats(
        self,
        *,
        require_toggle: bool = True,
    ) -> tuple[TelegramClient, list[dict[str, Any]]] | None:
        from app.services.bot_config_service import _decrypt_token

        config = await self._repo.get_default()
        if not config.bot_token_encrypted or not config.is_active:
            return None
        if require_toggle and not config.notifications_enabled:
            return None

        active_chats = [
            chat for chat in (config.chat_ids or []) if chat.get("is_active", True)
        ]
        if not active_chats:
            return None

        try:
            token = _decrypt_token(config.bot_token_encrypted)
        except Exception as exc:
            logger.error("telegram_token_decrypt_failed", error=str(exc))
            return None

        return TelegramClient(token), active_chats

    async def send_plain(
        self,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        *,
        require_toggle: bool = True,
    ) -> None:
        context = await self._get_client_and_chats(require_toggle=require_toggle)
        if not context:
            return

        client, chats = context
        for chat in chats:
            try:
                await client.send_message(
                    str(chat["chat_id"]),
                    text,
                    reply_markup=reply_markup,
                )
            except Exception as exc:
                logger.error(
                    "telegram_send_failed",
                    chat_id=str(chat.get("chat_id")),
                    error=str(exc),
                )

    async def send_supplier_created(self, supplier: Any) -> None:
        source = (
            f"@{supplier.submitted_by_telegram_username}"
            if getattr(supplier, "submitted_by_telegram_username", None)
            else "Dashboard"
        )
        text = (
            "🆕 <b>New supplier submitted</b>\n"
            f"<b>{html.escape(supplier.company_name)}</b>\n"
            f"Status: <b>{html.escape(_status_label(str(supplier.status)))}</b>\n"
            f"PIC: {html.escape(supplier.pic_name)}\n"
            f"Source: {html.escape(source)}"
        )
        markup = None
        if str(supplier.status) == "pending_review":
            markup = _supplier_markup(str(supplier.id))
        await self.send_plain(text, markup)

    async def send_status_change(
        self,
        supplier: Any,
        actor_display_name: str,
        source: str,
    ) -> None:
        text = (
            "📌 <b>Supplier status updated</b>\n"
            f"<b>{html.escape(supplier.company_name)}</b>\n"
            f"New status: <b>{html.escape(_status_label(str(supplier.status)))}</b>\n"
            f"Updated by: {html.escape(actor_display_name)} via {html.escape(source)}"
        )
        await self.send_plain(text)

    async def send_document_uploaded(
        self,
        supplier: Any,
        document_type: str,
        actor_display_name: str,
    ) -> None:
        text = (
            "📎 <b>Document uploaded</b>\n"
            f"<b>{html.escape(supplier.company_name)}</b>\n"
            f"Document: <b>{html.escape(document_type.replace('_', ' ').title())}</b>\n"
            f"Uploaded by: {html.escape(actor_display_name)}"
        )
        await self.send_plain(text)

    async def send_export_event(
        self,
        *,
        total_rows: int,
        actor_display_name: str,
        mode: str,
        task_id: str | None = None,
        download_url: str | None = None,
    ) -> None:
        lines = [
            "📊 <b>Export update</b>",
            f"Rows: <b>{total_rows}</b>",
            f"Requested by: {html.escape(actor_display_name)}",
        ]
        if mode == "queued":
            lines.append(f"Status: <b>Queued</b>")
            if task_id:
                lines.append(f"Task ID: <code>{html.escape(task_id)}</code>")
        elif mode == "completed":
            lines.append("Status: <b>Ready</b>")
            if download_url:
                lines.append(f"<a href=\"{html.escape(download_url)}\">Download export</a>")
        else:
            lines.append(f"Status: <b>{html.escape(mode.title())}</b>")
        await self.send_plain("\n".join(lines))

    async def send_bot_summary(
        self,
        *,
        total: int,
        pending: int,
        active: int,
        blacklisted: int,
    ) -> None:
        text = (
            "🧭 <b>Workspace summary</b>\n"
            f"Total suppliers: <b>{total}</b>\n"
            f"Pending review: <b>{pending}</b>\n"
            f"Active: <b>{active}</b>\n"
            f"Blacklisted: <b>{blacklisted}</b>"
        )
        await self.send_plain(text, require_toggle=False)

    async def send_pending_supplier_cards(self, suppliers: list[Any]) -> None:
        if not suppliers:
            await self.send_plain(
                "✅ <b>No pending suppliers</b>\nAll submissions have been reviewed.",
                require_toggle=False,
            )
            return

        for supplier in suppliers:
            text = (
                "🕒 <b>Pending review</b>\n"
                f"<b>{html.escape(supplier.company_name)}</b>\n"
                f"PIC: {html.escape(supplier.pic_name)}\n"
                f"City: {html.escape(supplier.city or '-')}\n"
                f"Status: <b>{html.escape(_status_label(str(supplier.status)))}</b>"
            )
            await self.send_plain(
                text,
                _supplier_markup(str(supplier.id)),
                require_toggle=False,
            )
