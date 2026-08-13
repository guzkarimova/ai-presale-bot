import json
from functools import lru_cache
from pathlib import Path

from schemas.presale import ServiceCatalog


CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "services_catalog.json"


@lru_cache(maxsize=1)
def load_service_catalog() -> ServiceCatalog:
    return ServiceCatalog.model_validate_json(CATALOG_PATH.read_text(encoding="utf-8"))


def catalog_for_prompt() -> str:
    catalog = load_service_catalog()
    data = catalog.model_dump()
    for service in data["services"]:
        for field in ("price_from", "price_to", "timeline_from_days", "timeline_to_days", "requires_manual_estimation"):
            service.pop(field, None)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
