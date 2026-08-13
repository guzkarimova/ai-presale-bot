import json
import logging
import ssl
from typing import Any

import aiohttp
import certifi

from config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """OpenAI-compatible gateway used by domain services."""

    @staticmethod
    def _provider_config() -> tuple[str, str, str, str]:
        if settings.routerai_api_key:
            return (
                "RouterAI",
                settings.routerai_api_key,
                settings.routerai_model,
                f"{settings.routerai_base_url}/chat/completions",
            )
        if settings.openai_api_key:
            return (
                "OpenAI",
                settings.openai_api_key,
                settings.openai_model,
                "https://api.openai.com/v1/chat/completions",
            )
        raise RuntimeError("ROUTERAI_API_KEY or OPENAI_API_KEY is not configured")

    async def generate_structured_json(
        self,
        system_prompt: str,
        payload: dict[str, Any],
        json_schema: dict[str, Any],
        correction: str = "",
    ) -> str:
        provider, api_key, model, endpoint = self._provider_config()
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        correction
                        + "\nJSON Schema результата:\n"
                        + json.dumps(json_schema, ensure_ascii=False)
                        + "\nДанные для анализа:\n"
                        + json.dumps(payload, ensure_ascii=False)
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        timeout = aiohttp.ClientTimeout(total=90)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        logger.info("Sending structured AI request via %s, model=%s", provider, model)
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            async with session.post(endpoint, headers=headers, json=body) as response:
                response_body = await response.text()
                if response.status >= 400:
                    raise RuntimeError(f"{provider} API returned HTTP {response.status}: {response_body[:300]}")
                data = json.loads(response_body)
                return data["choices"][0]["message"]["content"]

    async def check_information_complete(self, *args, **kwargs):
        raise NotImplementedError("Use PresaleAnalysis.clarifications_needed")

    async def build_specification(self, *args, **kwargs):
        raise NotImplementedError("Use PresaleAnalyzer.analyze")
