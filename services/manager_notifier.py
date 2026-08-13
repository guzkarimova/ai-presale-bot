import html
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from config import settings
from database.models import Application
from schemas.presale import PresaleAnalysis
from schemas.pricing import PricingResult
from services.pricing_service import load_pricing


def _service_names(service_ids: list[str]) -> list[str]:
    catalog = load_pricing()["services"]
    names = [catalog[item]["name"] for item in service_ids if item in catalog]
    return list(dict.fromkeys(names))


def additional_message_affects_proposal(text: str) -> bool:
    """Treat only clearly non-informational replies as not affecting the proposal."""
    normalized = " ".join(text.casefold().strip().rstrip(".!?,").split())
    non_material_replies = {
        "спасибо", "благодарю", "понял", "поняла", "понятно", "ок", "окей",
        "хорошо", "принято", "здравствуйте", "добрый день", "добрый вечер",
    }
    return normalized not in non_material_replies


class ManagerNotifier:
    @staticmethod
    def configured() -> bool:
        return bool(settings.manager_telegram_id)

    @staticmethod
    async def _send_text(bot: Bot, text: str) -> None:
        limit = 4000
        remaining = text
        while remaining:
            if len(remaining) <= limit:
                chunk, remaining = remaining, ""
            else:
                split_at = remaining.rfind("\n", 0, limit)
                split_at = split_at if split_at > 0 else limit
                chunk, remaining = remaining[:split_at], remaining[split_at:].lstrip("\n")
            await bot.send_message(int(settings.manager_telegram_id), chunk)

    async def send_new_lead(
        self,
        bot: Bot,
        application: Application,
        analysis: PresaleAnalysis | None,
        pricing: PricingResult | None,
        pdf_path: Path | None,
        error: str | None = None,
    ) -> None:
        if not self.configured():
            logging.warning("Manager notification skipped: MANAGER_TELEGRAM_ID/ADMIN_TELEGRAM_ID is empty")
            return
        username = f"@{application.username}" if application.username else "не указан"
        if analysis is None:
            text = (
                f"🆕 <b>Новая заявка #{application.id}</b>\n\n"
                f"👤 <b>Клиент:</b> {html.escape(username)}\n"
                f"🎯 <b>Задача:</b>\n{html.escape(application.business_task or 'не указана')}\n\n"
                "⚠️ <b>Нужно уточнить:</b>\n• Требуется ручная обработка заявки."
            )
        else:
            services = "\n".join(f"• {html.escape(item)}" for item in _service_names(analysis.selected_services)) or "• не выбраны"
            integrations = ", ".join(dict.fromkeys(html.escape(item.name) for item in analysis.integrations)) or "не указаны"
            clarifications = "\n".join(f"• {html.escape(item)}" for item in analysis.clarifications_needed[:3])
            timeline = pricing.timeline_text if pricing else "Требуется ручная оценка"
            price = f"от {pricing.final_price:,} ₽".replace(",", " ") if pricing and pricing.final_price is not None else "требуется оценка"
            text = (
                f"🆕 <b>Новая заявка #{application.id}</b>\n\n"
                f"👤 <b>Клиент:</b> {html.escape(username)}\n"
                f"🏢 <b>Бизнес:</b> {html.escape(analysis.client_summary)}\n\n"
                f"🎯 <b>Задача:</b>\n{html.escape(analysis.business_problem)}\n\n"
                f"🤖 <b>Предлагаемое решение:</b>\n{html.escape(analysis.recommended_solution_name)}\n\n"
                f"<b>Что входит:</b>\n{services}\n\n"
                f"🔗 <b>Интеграции:</b> {integrations}\n\n"
                f"💰 <b>Стоимость:</b> {price}\n"
                f"⏱ <b>Срок:</b> {html.escape(timeline)}"
            )
            if clarifications:
                text += f"\n\n⚠️ <b>Нужно уточнить:</b>\n{clarifications}"
        await self._send_text(bot, text)
        logging.info("Manager text notification sent for application %s", application.id)
        if pdf_path and pdf_path.exists():
            await bot.send_document(
                int(settings.manager_telegram_id),
                FSInputFile(pdf_path),
                caption=f"📄 <b>Черновик КП по заявке #{application.id}</b>",
            )
            logging.info("Manager PDF notification sent for application %s", application.id)

    async def send_additional_message(
        self, bot: Bot, application: Application, text: str, affects_proposal: bool | None = None
    ) -> None:
        if not self.configured():
            return
        username = f"@{application.username}" if application.username else f"ID {application.telegram_user_id}"
        if affects_proposal is None:
            affects_proposal = additional_message_affects_proposal(text)
        warning = "\n\n⚠️ КП требует проверки." if affects_proposal else ""
        await bot.send_message(
            int(settings.manager_telegram_id),
            f"📝 <b>Дополнение к заявке #{application.id}</b>\n\n"
            f"👤 {html.escape(username)}\n\n"
            f"«{html.escape(text)}»{warning}",
        )
        logging.info("Additional client message sent to manager for application %s", application.id)
