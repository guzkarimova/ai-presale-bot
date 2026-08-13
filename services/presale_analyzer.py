import json
import logging
from typing import Any

from pydantic import ValidationError

from database.models import Application
from schemas.presale import PresaleAnalysis
from services.llm_service import LLMService
from services.pricing_service import pricing_catalog_for_prompt
from services.service_catalog import catalog_for_prompt


SYSTEM_PROMPT = """Ты — AI-пресейл аналитик. Анализируй заявку только в пределах переданного каталога услуг.
Правила:
- не рассчитывай и не возвращай цену или срок: это делает отдельный pricing engine;
- selected_services должен быть массивом строк и содержать только ID из pricing_service_ids;
- обязательно выбирай deployment для проекта, который нужно развернуть;
- testing и documentation не выбирай: они включены в разработку автоматически;
- неизвестные CRM, 1С, телефонию, маркетплейсы и другие внешние системы отмечай needs_check;
- если API или конфигурация не проверены, добавляй ограничение и при необходимости вопрос для уточнения;
- не обещай полную замену сотрудников или гарантированный бизнес-результат;
- clarifications_needed содержит максимум 3 коротких вопроса, отсортированных по важности;
- включай туда только вопросы, ответ на которые действительно влияет на стоимость, срок, архитектуру или возможность интеграции;
- не спрашивай очевидные, второстепенные или уже раскрытые в заявке сведения;
- ответ должен строго соответствовать переданной JSON Schema и быть на русском языке.
"""


def _application_payload(application: Application) -> dict[str, Any]:
    transcript = []
    if application.additional_answers_json:
        try:
            transcript = json.loads(application.additional_answers_json)
        except (json.JSONDecodeError, TypeError):
            logging.warning("Application %s has invalid transcript JSON", application.id)
    additional = [
        item.get("text", "")
        for item in transcript
        if item.get("sender") == "user" and item.get("event_type") == "message"
    ]
    return {
        "lead_id": application.id,
        "telegram_user_id": application.telegram_user_id,
        "answers": {
            "company_and_task": application.business_task,
            "current_process": application.current_process,
            "channels_and_integrations": application.integrations,
            "ai_scope": application.ai_actions,
            "expected_result": application.expected_result,
        },
        "additional_messages": additional,
    }


class PresaleAnalyzer:
    async def analyze(self, application: Application) -> PresaleAnalysis:
        logging.info("Starting AI analysis for application %s", application.id)
        payload = {
            "application": _application_payload(application),
            "service_catalog": json.loads(catalog_for_prompt()),
            "pricing_service_ids": pricing_catalog_for_prompt(),
        }
        last_error: Exception | None = None
        correction = ""
        for attempt in range(2):
            try:
                raw = await LLMService().generate_structured_json(
                    SYSTEM_PROMPT, payload, PresaleAnalysis.model_json_schema(), correction
                )
                analysis = PresaleAnalysis.model_validate_json(raw)
                analysis = self._apply_catalog_guardrails(analysis)
                logging.info("AI analysis completed for application %s", application.id)
                return analysis
            except (json.JSONDecodeError, ValidationError, KeyError, TypeError, ValueError) as exc:
                last_error = exc
                logging.warning("Invalid AI JSON for application %s, attempt %s: %s", application.id, attempt + 1, exc)
                correction = "Предыдущий ответ не прошёл валидацию. Верни только корректный JSON строго по схеме."
        raise RuntimeError(f"AI response validation failed: {last_error}")

    @staticmethod
    def _apply_catalog_guardrails(analysis: PresaleAnalysis) -> PresaleAnalysis:
        analysis.selected_services = list(dict.fromkeys(analysis.selected_services))
        return analysis
