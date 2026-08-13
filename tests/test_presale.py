import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.database import Base
from database.models import Application
from schemas.presale import PresaleAnalysis
from services.presale_analyzer import PresaleAnalyzer
from services.presale_pipeline import process_presale
from services.proposal_generator import ProposalGenerator
from services.pricing_service import PricingService
from services.service_catalog import load_service_catalog
from services.application_service import claim_presale_processing


def sample_analysis(**overrides) -> PresaleAnalysis:
    data = {
        "client_summary": "Интернет-магазин с большим потоком обращений.",
        "business_problem": "Менеджеры вручную отвечают на типовые вопросы.",
        "current_process": "Обращения обрабатываются менеджерами вручную.",
        "desired_result": "Снизить нагрузку и ускорить ответы.",
        "recommended_solution_name": "AI-ассистент поддержки",
        "selected_services": ["ai_assistant", "1c", "deployment"],
        "solution_description": "AI-ассистент отвечает по базе знаний и передаёт сложные вопросы менеджеру.",
        "proposed_workflow": ["Обращение поступает в Telegram", "AI ищет ответ", "Сложный вопрос передаётся менеджеру"],
        "integrations": [{"name": "Неизвестная CRM", "purpose": "Создание лида", "status": "needs_check"}],
        "required_from_client": ["FAQ", "Описание конфигурации 1С", "Документация API"],
        "expected_business_effect": ["Сокращение ручных операций", "Ускорение обработки обращений"],
        "risks_and_limitations": ["Интеграция требует проверки API"],
        "clarifications_needed": ["Какой API доступен у CRM?"],
        "complexity": "complex",
        "manager_comment": "Нужна ручная техническая оценка.",
    }
    data.update(overrides)
    return PresaleAnalysis.model_validate(data)


class PresaleTests(unittest.TestCase):
    def test_catalog_contains_all_initial_directions(self):
        catalog = load_service_catalog()
        self.assertEqual(len(catalog.services), 23)
        self.assertEqual(len({item.id for item in catalog.services}), 23)

    def test_ai_schema_does_not_contain_price_or_timeline(self):
        schema = PresaleAnalysis.model_json_schema()
        properties = schema["properties"]
        self.assertNotIn("estimated_price", properties)
        self.assertNotIn("estimated_timeline", properties)
        self.assertNotIn("can_auto_estimate", properties)
        self.assertEqual(properties["selected_services"]["items"]["type"], "string")

    def test_guardrails_deduplicate_service_ids(self):
        result = PresaleAnalyzer._apply_catalog_guardrails(
            sample_analysis(selected_services=["ai_assistant", "ai_assistant"])
        )
        self.assertEqual(result.selected_services, ["ai_assistant"])
        self.assertEqual(result.integrations[0].status, "needs_check")
        self.assertTrue(result.clarifications_needed)

    def test_clarifications_are_limited_to_three_unique_questions(self):
        result = sample_analysis(clarifications_needed=["Первый?", "Второй?", "Первый?", "Третий?", "Четвёртый?"])
        self.assertEqual(result.clarifications_needed, ["Первый?", "Второй?", "Третий?"])

    def test_unknown_service_is_left_for_pricing_validation(self):
        analysis = PresaleAnalyzer._apply_catalog_guardrails(sample_analysis(selected_services=["invented"]))
        pricing = PricingService().calculate(analysis.selected_services)
        self.assertTrue(pricing.manual_check_required)
        self.assertIsNone(pricing.final_price)

    def test_invalid_ai_json_is_retried(self):
        app = Application(id=8100, telegram_user_id="8100", status="QUALIFIED", business_task="Тест")
        valid_json = sample_analysis().model_dump_json(by_alias=True)
        with patch(
            "services.presale_analyzer.LLMService.generate_structured_json",
            new=AsyncMock(side_effect=["not-json", valid_json]),
        ) as request:
            result = asyncio.run(PresaleAnalyzer().analyze(app))
        self.assertEqual(request.await_count, 2)
        self.assertIn("ai_assistant", result.selected_services)

    def test_insufficient_data_is_kept_as_clarification(self):
        result = PresaleAnalyzer._apply_catalog_guardrails(
            sample_analysis(clarifications_needed=["Уточнить объём обращений и доступность API."])
        )
        self.assertIn("Уточнить объём обращений", result.clarifications_needed[0])
        self.assertTrue(result.clarifications_needed)

    def test_pdf_generation_failure_does_not_prevent_manager_text(self):
        app = Application(id=7001, telegram_user_id="1", username="test", status="QUALIFIED")
        analysis = PresaleAnalyzer._apply_catalog_guardrails(sample_analysis())
        bot = AsyncMock()
        with (
            patch("services.presale_pipeline.get_application", return_value=app),
            patch("services.presale_pipeline.PresaleAnalyzer.analyze", new=AsyncMock(return_value=analysis)),
            patch("services.presale_pipeline.save_presale_analysis"),
            patch("services.presale_pipeline.save_pricing_result"),
            patch("services.presale_pipeline.ProposalGenerator.generate", side_effect=RuntimeError("pdf test error")),
            patch("services.presale_pipeline.mark_processing_error"),
            patch("services.presale_pipeline.GoogleDocsService.sync_presale_result"),
            patch("services.presale_pipeline.ManagerNotifier.send_new_lead", new=AsyncMock()) as notify,
            patch("services.presale_pipeline.ManagerNotifier.configured", return_value=False),
        ):
            asyncio.run(process_presale(bot, app.id))
        notify.assert_awaited_once()

    def test_processing_claim_is_idempotent(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        test_session = sessionmaker(bind=engine, expire_on_commit=False)
        with test_session() as session:
            session.add(Application(id=8001, telegram_user_id="8001", status="ready"))
            session.commit()
        with patch("services.application_service.SessionLocal", test_session):
            self.assertTrue(claim_presale_processing(8001, 12345))
            self.assertFalse(claim_presale_processing(8001, 12345))

    def test_successful_pipeline_saves_and_notifies_once(self):
        app = Application(id=8002, telegram_user_id="2", username="test", status="QUALIFIED")
        analysis = PresaleAnalyzer._apply_catalog_guardrails(sample_analysis())
        bot = AsyncMock()
        fake_pdf = Path(tempfile.gettempdir()) / "proposal-test.pdf"
        fake_pdf.write_bytes(b"%PDF-test")
        with (
            patch("services.presale_pipeline.get_application", return_value=app),
            patch("services.presale_pipeline.PresaleAnalyzer.analyze", new=AsyncMock(return_value=analysis)),
            patch("services.presale_pipeline.save_presale_analysis") as save_analysis,
            patch("services.presale_pipeline.save_pricing_result") as save_pricing,
            patch("services.presale_pipeline.ProposalGenerator.generate", return_value=fake_pdf),
            patch("services.presale_pipeline.save_proposal") as save_pdf,
            patch("services.presale_pipeline.GoogleDocsService.sync_presale_result") as google_sync,
            patch("services.presale_pipeline.ManagerNotifier.send_new_lead", new=AsyncMock()) as notify,
            patch("services.presale_pipeline.ManagerNotifier.configured", return_value=False),
        ):
            asyncio.run(process_presale(bot, app.id))
        save_analysis.assert_called_once()
        save_pricing.assert_called_once()
        save_pdf.assert_called_once()
        google_sync.assert_called_once()
        notify.assert_awaited_once()


class PdfSmokeTest(unittest.TestCase):
    def test_pdf_with_cyrillic_is_generated(self):
        app = Application(id=9999, telegram_user_id="1", username="Тестовая компания", status="AI_ANALYZED")
        analysis = PresaleAnalyzer._apply_catalog_guardrails(sample_analysis(
            recommended_solution_name="AI-система аналитики Wildberries и Ozon",
            selected_services=[
                "telegram_bot_basic", "ai_analytics", "google_sheets", "wildberries_api",
                "ozon_api", "automatic_reports", "scheduler", "deployment",
            ],
            solution_description="Единая система сбора данных маркетплейсов, AI-анализа и ежедневной отчётности.",
            proposed_workflow=[
                "Система получает данные Wildberries и Ozon",
                "Объединяет данные в Google Sheets",
                "AI анализирует показатели и формирует рекомендации",
                "Отчёт по расписанию поступает менеджеру в Telegram",
            ],
            integrations=[
                {"name": "Wildberries API", "purpose": "Получение показателей", "status": "confirmed"},
                {"name": "Ozon API", "purpose": "Получение показателей", "status": "confirmed"},
                {"name": "Google Sheets", "purpose": "Хранение сводных данных", "status": "confirmed"},
            ],
            required_from_client=["API-ключи кабинетов Wildberries и Ozon", "Перечень нужных показателей", "Расписание отчётов"],
            risks_and_limitations=["Состав доступных данных зависит от прав API кабинетов"],
            clarifications_needed=["Какие показатели и периоды должны входить в ежедневный отчёт?"],
        ))
        pricing = PricingService().calculate(analysis.selected_services)
        self.assertEqual(pricing.final_price, 122000)
        path = ProposalGenerator().generate(app, analysis, pricing)
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
