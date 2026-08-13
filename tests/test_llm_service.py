import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.llm_service import LLMService


class LLMServiceProviderTests(unittest.TestCase):
    def test_routerai_is_preferred_and_existing_env_name_is_supported_by_config(self):
        fake_settings = SimpleNamespace(
            routerai_api_key="router-key",
            routerai_model="google/gemini-2.5-flash-lite",
            routerai_base_url="https://routerai.ru/api/v1",
            openai_api_key="openai-key",
            openai_model="gpt-4o-mini",
        )
        with patch("services.llm_service.settings", fake_settings):
            provider, key, model, endpoint = LLMService._provider_config()

        self.assertEqual(provider, "RouterAI")
        self.assertEqual(key, "router-key")
        self.assertEqual(model, "google/gemini-2.5-flash-lite")
        self.assertEqual(endpoint, "https://routerai.ru/api/v1/chat/completions")

    def test_direct_openai_remains_a_fallback(self):
        fake_settings = SimpleNamespace(
            routerai_api_key="",
            routerai_model="google/gemini-2.5-flash-lite",
            routerai_base_url="https://routerai.ru/api/v1",
            openai_api_key="openai-key",
            openai_model="gpt-4o-mini",
        )
        with patch("services.llm_service.settings", fake_settings):
            provider, key, model, endpoint = LLMService._provider_config()

        self.assertEqual(provider, "OpenAI")
        self.assertEqual(key, "openai-key")
        self.assertEqual(model, "gpt-4o-mini")
        self.assertEqual(endpoint, "https://api.openai.com/v1/chat/completions")


if __name__ == "__main__":
    unittest.main()
