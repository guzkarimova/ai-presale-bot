import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from database.models import Application
from services.manager_notifier import ManagerNotifier
from services.pricing_service import PricingService
from tests.test_presale import sample_analysis


class PricingServiceTests(unittest.TestCase):
    def setUp(self):
        self.pricing = PricingService()

    def test_25000_plus_10000_equals_35000(self):
        result = self.pricing.calculate(["telegram_bot_basic", "google_sheets"])
        self.assertEqual(result.calculated_price, 35000)
        self.assertEqual(result.final_price, 35000)
        self.assertFalse(result.minimum_price_applied)

    def test_minimum_project_price(self):
        result = self.pricing.calculate(["google_sheets"])
        self.assertEqual(result.calculated_price, 10000)
        self.assertEqual(result.final_price, 35000)
        self.assertTrue(result.minimum_price_applied)

    def test_wildberries_and_ozon_use_bundle(self):
        result = self.pricing.calculate(["wildberries_api", "ozon_api"])
        self.assertEqual(result.calculated_price, 35000)
        self.assertEqual([item.id for item in result.billable_services], ["marketplaces_wb_ozon"])
        self.assertEqual(result.applied_rules[0].id, "wb_ozon_bundle")

    def test_ai_assistant_includes_ai_basic(self):
        result = self.pricing.calculate(["ai_basic", "ai_assistant"])
        self.assertEqual(result.calculated_price, 25000)
        self.assertEqual([item.id for item in result.billable_services], ["ai_assistant"])

    def test_1c_requires_manual_check(self):
        result = self.pricing.calculate(["1c"])
        self.assertTrue(result.manual_check_required)
        self.assertIn("1c", result.manual_items)
        self.assertEqual(result.price_text, "от 35 000 ₽")
        self.assertTrue(result.timeline_manual_check)

    def test_unknown_service_does_not_crash(self):
        result = self.pricing.calculate(["unknown_service"])
        self.assertTrue(result.manual_check_required)
        self.assertIsNone(result.final_price)
        self.assertEqual(result.excluded_services[0].id, "unknown_service")

    def test_duplicate_id_is_not_charged_twice(self):
        result = self.pricing.calculate(["telegram_bot_basic", "telegram_bot_basic"])
        self.assertEqual(result.calculated_price, 25000)
        self.assertEqual(len(result.billable_services), 1)

    def test_marketplace_analytics_example_is_122000(self):
        selected = [
            "telegram_bot_basic",
            "ai_analytics",
            "google_sheets",
            "wildberries_api",
            "ozon_api",
            "automatic_reports",
            "scheduler",
            "deployment",
        ]
        result = self.pricing.calculate(selected)
        self.assertEqual(result.calculated_price, 122000)
        self.assertEqual(result.final_price, 122000)
        self.assertEqual(result.project_level, "COMPLEX")
        self.assertEqual(result.timeline_text, "15–25 рабочих дней")
        self.assertFalse(result.manual_check_required)

    def test_manager_receives_short_human_readable_summary(self):
        selected = [
            "telegram_bot_basic", "ai_analytics", "google_sheets", "wildberries_api",
            "ozon_api", "automatic_reports", "scheduler", "deployment",
        ]
        pricing = self.pricing.calculate(selected)
        analysis = sample_analysis(selected_services=selected)
        bot = AsyncMock()
        app = Application(id=9001, telegram_user_id="1", username="manager_test", status="PROPOSAL_GENERATED")
        with patch("services.manager_notifier.settings", SimpleNamespace(manager_telegram_id="1")):
            asyncio.run(ManagerNotifier().send_new_lead(bot, app, analysis, pricing, None))
        manager_text = "\n".join(call.args[1] for call in bot.send_message.await_args_list)
        self.assertIn("Новая заявка #9001", manager_text)
        self.assertIn("• Telegram-бот", manager_text)
        self.assertIn("Стоимость:</b> от 122 000 ₽", manager_text)
        self.assertNotIn("ai_analytics", manager_text)
        self.assertNotIn("Pricing engine", manager_text)
        self.assertNotIn("Внутренний расчёт", manager_text)

    def test_additional_message_is_one_compact_notification(self):
        bot = AsyncMock()
        app = Application(id=10, telegram_user_id="1", username="username", status="PROPOSAL_GENERATED")
        with patch("services.manager_notifier.settings", SimpleNamespace(manager_telegram_id="1")):
            asyncio.run(ManagerNotifier().send_additional_message(bot, app, "Добавьте Bitrix24"))
        bot.send_message.assert_awaited_once()
        text = bot.send_message.await_args.args[1]
        self.assertIn("Дополнение к заявке #10", text)
        self.assertIn("«Добавьте Bitrix24»", text)
        self.assertIn("КП требует проверки", text)
        self.assertNotIn("Lead ID", text)

    def test_non_material_addition_has_no_proposal_warning(self):
        bot = AsyncMock()
        app = Application(id=10, telegram_user_id="1", username="username", status="PROPOSAL_GENERATED")
        with patch("services.manager_notifier.settings", SimpleNamespace(manager_telegram_id="1")):
            asyncio.run(ManagerNotifier().send_additional_message(bot, app, "Спасибо!"))
        text = bot.send_message.await_args.args[1]
        self.assertNotIn("КП требует проверки", text)


if __name__ == "__main__":
    unittest.main()
