import json
from abc import ABC, abstractmethod

import httpx

from app.models.domain import MaintenanceInsight


class LLMProvider(ABC):
    @abstractmethod
    async def synthesize(self, system: str, evidence: str) -> MaintenanceInsight:
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4.1-mini") -> None:
        self.api_key, self.model = api_key, model

    async def synthesize(self, system: str, evidence: str) -> MaintenanceInsight:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": evidence},
            ],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return MaintenanceInsight.model_validate_json(content)


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-latest") -> None:
        self.api_key, self.model = api_key, model

    async def synthesize(self, system: str, evidence: str) -> MaintenanceInsight:
        payload = {
            "model": self.model,
            "max_tokens": 1800,
            "system": system,
            "messages": [{"role": "user", "content": evidence}],
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages", headers=headers, json=payload
            )
            response.raise_for_status()
        return MaintenanceInsight.model_validate_json(response.json()["content"][0]["text"])


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str = "llama3.2") -> None:
        self.base_url, self.model = base_url.rstrip("/"), model

    async def synthesize(self, system: str, evidence: str) -> MaintenanceInsight:
        payload = {
            "model": self.model,
            "prompt": f"{system}\n\n{evidence}",
            "format": "json",
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
        content = json.loads(response.json()["response"])
        return MaintenanceInsight.model_validate(content)
