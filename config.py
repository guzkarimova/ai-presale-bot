from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    routerai_api_key: str
    routerai_model: str
    routerai_base_url: str
    openai_api_key: str
    openai_model: str
    admin_telegram_id: str
    manager_telegram_id: str
    google_service_account_json: str
    google_service_account_file: str
    google_sheet_id: str
    google_sheet_gid: str


settings = Settings(
    telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
    # Keep compatibility with the variable name already used in the deployed .env.
    routerai_api_key=os.getenv("routerai_API_KEY", os.getenv("ROUTERAI_API_KEY", "")).strip(),
    routerai_model=os.getenv("ROUTERAI_MODEL", "google/gemini-2.5-flash-lite").strip(),
    routerai_base_url=os.getenv("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1").strip().rstrip("/"),
    openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
    openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
    admin_telegram_id=os.getenv("ADMIN_TELEGRAM_ID", "").strip(),
    manager_telegram_id=os.getenv("MANAGER_TELEGRAM_ID", os.getenv("ADMIN_TELEGRAM_ID", "")).strip(),
    google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip(),
    google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip(),
    google_sheet_id=os.getenv("GOOGLE_SHEET_ID", "").strip(),
    google_sheet_gid=os.getenv("GOOGLE_SHEET_GID", "").strip(),
)
