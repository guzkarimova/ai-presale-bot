from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ServiceDefinition(BaseModel):
    id: str
    name: str
    category: str
    description: str
    client_pain_signals: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    possible_integrations: list[str] = Field(default_factory=list)
    required_client_data: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    complexity: Literal["basic", "medium", "complex", "custom"]
    price_from: int | None = None
    price_to: int | None = None
    timeline_from_days: int | None = None
    timeline_to_days: int | None = None
    requires_manual_estimation: bool = False


class ServiceCatalog(BaseModel):
    version: int
    currency: str = "RUB"
    services: list[ServiceDefinition]


class Integration(BaseModel):
    name: str
    purpose: str
    status: Literal["confirmed", "needs_check"]


class PresaleAnalysis(BaseModel):
    client_summary: str
    business_problem: str
    current_process: str
    desired_result: str
    recommended_solution_name: str
    selected_services: list[str]
    solution_description: str
    proposed_workflow: list[str]
    integrations: list[Integration]
    required_from_client: list[str]
    expected_business_effect: list[str]
    risks_and_limitations: list[str]
    clarifications_needed: list[str]
    complexity: Literal["basic", "medium", "complex", "custom"]
    manager_comment: str

    @field_validator("clarifications_needed", mode="after")
    @classmethod
    def limit_clarifications(cls, value: list[str]) -> list[str]:
        """Keep only the three highest-priority questions returned by the AI."""
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))[:3]

    @field_validator("selected_services", mode="before")
    @classmethod
    def normalize_legacy_selected_services(cls, value):
        """Read historical analyses while new AI output stays a plain list of pricing IDs."""
        legacy_map = {
            "ai_assistants": "ai_assistant",
            "telegram_max_bots": "telegram_bot_basic",
            "ai_presale": "ai_assistant",
            "ai_sales_assistant": "ai_assistant",
            "ai_support": "ai_assistant",
            "rag_knowledge_base": "rag",
            "document_processing": "ai_analytics",
            "document_generation": "document_generation",
            "crm_integrations": "crm",
            "onec_integration": "1c",
            "google_sheets": "google_sheets",
            "google_docs": "google_docs",
            "api_integrations": "external_api",
            "business_process_automation": "complex_business_logic",
            "analytics": "dashboard",
            "ai_analytics": "ai_analytics",
            "automatic_reporting": "automatic_reports",
            "marketplaces": "marketplaces_wb_ozon",
            "ai_content": "ai_basic",
            "notifications": "notifications",
            "voice_ai": "custom",
            "parsing": "parsing",
            "custom_automation": "custom",
        }
        result = []
        for item in value or []:
            service_id = item.get("service_id") if isinstance(item, dict) else str(item)
            result.append(legacy_map.get(service_id, service_id))
        return list(dict.fromkeys(result))
