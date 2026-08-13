import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from schemas.pricing import AppliedPricingRule, ExcludedPricingItem, PricingItem, PricingResult


PRICING_PATH = Path(__file__).resolve().parents[1] / "data" / "pricing.json"


@lru_cache(maxsize=1)
def load_pricing() -> dict[str, Any]:
    data = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    if not isinstance(data.get("services"), dict) or not data["services"]:
        raise ValueError("Pricing config must contain services")
    return data


def pricing_catalog_for_prompt() -> list[dict[str, Any]]:
    pricing = load_pricing()
    return [
        {
            "id": service_id,
            "name": item["name"],
            "selection_hint": item.get("manual_reason", ""),
        }
        for service_id, item in pricing["services"].items()
        if service_id not in {"testing", "documentation"}
    ]


class PricingService:
    def calculate(
        self,
        selected_services: Iterable[str],
        unchecked_integrations: Iterable[str] = (),
    ) -> PricingResult:
        config = load_pricing()
        services: dict[str, dict[str, Any]] = config["services"]
        selected = list(dict.fromkeys(str(item).strip() for item in selected_services if str(item).strip()))
        working: list[str] = []
        excluded: list[ExcludedPricingItem] = []
        applied_rules: list[AppliedPricingRule] = []
        manual_reasons: list[str] = []
        manual_items: list[str] = []
        timeline_manual = False

        for service_id in selected:
            if service_id not in services:
                logging.warning("Unknown service returned by AI: %s", service_id)
                excluded.append(ExcludedPricingItem(id=service_id, reason="Неизвестный ID услуги; требуется ручная проверка."))
                manual_reasons.append(f"Неизвестная услуга: {service_id}")
                timeline_manual = True
                continue
            working.append(service_id)

        for rule in config.get("bundle_rules", []):
            required = rule["requires"]
            if all(item in working for item in required):
                for item in required:
                    working.remove(item)
                    excluded.append(ExcludedPricingItem(id=item, reason=f"Заменено пакетным правилом {rule['id']}"))
                replacement = rule["replace_with"]
                if replacement not in working:
                    working.append(replacement)
                applied_rules.append(AppliedPricingRule(
                    id=rule["id"],
                    description=rule["description"],
                    removed_services=required,
                    added_service=replacement,
                ))

        for parent_id in list(working):
            for included_id in services[parent_id].get("includes", []):
                if included_id in working:
                    working.remove(included_id)
                    excluded.append(ExcludedPricingItem(
                        id=included_id,
                        reason=f"Включено в услугу {parent_id}; двойное начисление исключено.",
                    ))
                    applied_rules.append(AppliedPricingRule(
                        id=f"includes:{parent_id}:{included_id}",
                        description=f"{parent_id} включает {included_id}",
                        removed_services=[included_id],
                        added_service=None,
                    ))

        billable: list[PricingItem] = []
        for service_id in working:
            item = services[service_id]
            fixed_price = item.get("price")
            price_from = item.get("price_from")
            price = fixed_price if fixed_price is not None else price_from
            if price is not None:
                billable.append(PricingItem(
                    id=service_id,
                    name=item["name"],
                    price=int(price),
                    price_type="fixed" if fixed_price is not None else "from",
                    manual_check=bool(item.get("manual_check", False)),
                ))
            if item.get("manual_check"):
                manual_items.append(service_id)
                manual_reasons.append(item.get("manual_reason") or f"Услуга {item['name']} требует ручной проверки.")
            if item.get("timeline_manual_check"):
                timeline_manual = True

        for integration in dict.fromkeys(str(item).strip() for item in unchecked_integrations if str(item).strip()):
            manual_reasons.append(f"Требуется проверка технической возможности интеграции: {integration}.")
            timeline_manual = True

        calculated = sum(item.price for item in billable)
        minimum = int(config["minimum_project_price"])
        has_safe_lower_bound = calculated > 0
        minimum_applied = has_safe_lower_bound and calculated < minimum
        final_price = max(calculated, minimum) if has_safe_lower_bound else None
        manual_required = bool(manual_reasons)

        project_level = "CUSTOM"
        from_days = to_days = None
        if final_price is not None:
            for tier in config["timeline_tiers"]:
                max_price = tier["max_price"]
                if max_price is None or final_price <= max_price:
                    project_level = tier["project_level"]
                    from_days = tier["from_days"]
                    to_days = tier["to_days"]
                    break
        if final_price is None or final_price > 200000 or timeline_manual:
            project_level = "CUSTOM"
            from_days = to_days = None
            timeline_manual = True

        return PricingResult(
            selected_services=selected,
            billable_services=billable,
            excluded_services=excluded,
            applied_rules=applied_rules,
            calculated_price=calculated,
            minimum_price_applied=minimum_applied,
            final_price=final_price,
            currency=config.get("currency", "RUB"),
            manual_check_required=manual_required,
            manual_check_reasons=list(dict.fromkeys(manual_reasons)),
            manual_items=list(dict.fromkeys(manual_items)),
            project_level=project_level,
            timeline_from_days=from_days,
            timeline_to_days=to_days,
            timeline_manual_check=timeline_manual,
        )
