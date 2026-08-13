from typing import Literal

from pydantic import BaseModel, Field


class PricingItem(BaseModel):
    id: str
    name: str
    price: int
    price_type: Literal["fixed", "from"] = "fixed"
    manual_check: bool = False


class ExcludedPricingItem(BaseModel):
    id: str
    reason: str


class AppliedPricingRule(BaseModel):
    id: str
    description: str
    removed_services: list[str] = Field(default_factory=list)
    added_service: str | None = None


class PricingResult(BaseModel):
    selected_services: list[str]
    billable_services: list[PricingItem]
    excluded_services: list[ExcludedPricingItem]
    applied_rules: list[AppliedPricingRule]
    calculated_price: int
    minimum_price_applied: bool
    final_price: int | None
    currency: str
    manual_check_required: bool
    manual_check_reasons: list[str]
    manual_items: list[str]
    project_level: Literal["SMALL", "MEDIUM", "COMPLEX", "CUSTOM"]
    timeline_from_days: int | None
    timeline_to_days: int | None
    timeline_manual_check: bool

    @property
    def timeline_text(self) -> str:
        if self.timeline_manual_check or self.timeline_from_days is None or self.timeline_to_days is None:
            return "Срок определяется после технической оценки"
        return f"{self.timeline_from_days}–{self.timeline_to_days} рабочих дней"

    @property
    def price_text(self) -> str:
        if self.final_price is None:
            return "Стоимость определяется после технической оценки"
        prefix = "от " if self.manual_check_required else ""
        return f"{prefix}{self.final_price:,} ₽".replace(",", " ")
