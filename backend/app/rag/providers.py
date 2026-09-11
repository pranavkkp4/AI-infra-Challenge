import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from hashlib import sha256
from typing import Any

import httpx

from app.data.pii import redact_external_identifiers
from app.models.domain import MaintenanceInsight
from app.rag.grounding import enforce_grounding


class LLMProvider(ABC):
    provider_name = "external"
    generated_by = "external_llm"

    async def synthesize(self, system: str, evidence: str) -> MaintenanceInsight:
        # The system prompt is application-controlled; screen only retrieved evidence.
        evidence_ids = set(re.findall(r"^WORK ORDER:\s*(\S+)\s*$", evidence, re.M))
        allowed_identifiers = evidence_ids | _asset_identifiers(evidence)
        if _screen_external_text(evidence, allowed_identifiers).was_redacted:
            raise ValueError(
                "Detectable PII or location identifiers must be redacted before model invocation"
            )
        if not evidence_ids:
            raise ValueError("External synthesis requires explicit WorkOrderId evidence blocks")
        raw_insight = await self._synthesize(system, evidence)
        insight = (
            raw_insight
            if isinstance(raw_insight, MaintenanceInsight)
            else MaintenanceInsight.model_validate(raw_insight)
        )
        enforce_grounding(insight, evidence_ids)
        output_scan = _screen_external_text(insight.model_dump_json(), allowed_identifiers)
        if output_scan.was_redacted:
            raise ValueError("Provider output contained PII or location identifiers")
        provenance = {
            **insight.provenance,
            "contract_version": "rag.v1",
            "provider": self.provider_name,
            "generated_by": self.generated_by,
            "prompt_sha256": sha256(f"{system}\n{evidence}".encode()).hexdigest(),
            "evidence_work_order_ids": sorted(evidence_ids),
            "evidence_count": len(evidence_ids),
            "pii_screened": True,
        }
        return insight.model_copy(
            update={"generated_by": self.generated_by, "provenance": provenance}
        )

    @abstractmethod
    async def _synthesize(self, system: str, evidence: str) -> MaintenanceInsight | dict[str, Any]:
        raise NotImplementedError


class DeterministicProvider(LLMProvider):
    provider_name = "deterministic"
    generated_by = "deterministic_alp"

    def __init__(self, fallback: Callable[[], MaintenanceInsight] | None = None) -> None:
        self.fallback = fallback

    async def _synthesize(self, system: str, evidence: str) -> MaintenanceInsight:
        if self.fallback is None:
            raise ValueError("Deterministic provider requires an ALP fallback")
        return self.fallback()


class OpenAIProvider(LLMProvider):
    provider_name = "openai"
    generated_by = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini") -> None:
        self.api_key, self.model = api_key, model

    async def _synthesize(self, system: str, evidence: str) -> MaintenanceInsight:
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
    provider_name = "anthropic"
    generated_by = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-latest") -> None:
        self.api_key, self.model = api_key, model

    async def _synthesize(self, system: str, evidence: str) -> MaintenanceInsight:
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
    provider_name = "ollama"
    generated_by = "ollama"

    def __init__(self, base_url: str, model: str = "llama3.2") -> None:
        self.base_url, self.model = base_url.rstrip("/"), model

    async def _synthesize(self, system: str, evidence: str) -> MaintenanceInsight:
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


def create_provider(
    settings: object | str | None = None,
    *,
    provider: str | None = None,
    deterministic_fallback: Callable[[], MaintenanceInsight] | None = None,
) -> LLMProvider:
    """Build the configured adapter, failing before any network call if misconfigured."""

    if isinstance(settings, str) and provider is None:
        provider = settings
        settings = None
    name = (provider or getattr(settings, "llm_provider", "deterministic")).strip().lower()
    if name == "deterministic":
        return DeterministicProvider(deterministic_fallback)
    if name == "openai":
        api_key = getattr(settings, "openai_api_key", None)
        if not api_key:
            raise ValueError("OpenAI provider requires CIVICOPS_OPENAI_API_KEY")
        return OpenAIProvider(api_key, getattr(settings, "openai_model", "gpt-4.1-mini"))
    if name == "anthropic":
        api_key = getattr(settings, "anthropic_api_key", None)
        if not api_key:
            raise ValueError("Anthropic provider requires CIVICOPS_ANTHROPIC_API_KEY")
        return AnthropicProvider(
            api_key, getattr(settings, "anthropic_model", "claude-3-5-haiku-latest")
        )
    if name == "ollama":
        return OllamaProvider(
            getattr(settings, "ollama_base_url", "http://localhost:11434"),
            getattr(settings, "ollama_model", "llama3.2"),
        )
    raise ValueError(f"Unsupported LLM provider: {name}")


provider_factory = create_provider
get_provider = create_provider


def _asset_identifiers(evidence: str) -> set[str]:
    return {
        asset.strip()
        for line in evidence.splitlines()
        if line.startswith("ASSET:")
        for asset in line.removeprefix("ASSET:").split(",")
        if asset.strip()
    }


def _screen_external_text(text: str, allowed_identifiers: set[str]):
    scrubbed = text
    for identifier in sorted(allowed_identifiers, key=len, reverse=True):
        scrubbed = scrubbed.replace(identifier, "[OPERATIONAL_IDENTIFIER]")
    return redact_external_identifiers(scrubbed)
