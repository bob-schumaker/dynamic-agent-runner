"""Helpers for caller-provided local OpenAI-compatible model endpoints."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    OpenAIClientAdapter,
    OpenAIProviderConfig,
    create_default_async_openai_provider,
    create_default_openai_provider,
)


@dataclass(frozen=True)
class LocalOpenAIEndpointConfig:
    """Configuration for a caller-owned local OpenAI-compatible endpoint."""

    base_url: str
    model_aliases: tuple[str, ...]
    api_key: str | None = None
    provider_name: str | None = None
    expected_model_id: str | None = None

    def __init__(
        self,
        *,
        base_url: str,
        model_aliases: Sequence[str],
        api_key: str | None = None,
        provider_name: str | None = None,
        expected_model_id: str | None = None,
    ) -> None:
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(
            self,
            "model_aliases",
            tuple(str(model_alias) for model_alias in model_aliases),
        )
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "provider_name", provider_name)
        object.__setattr__(self, "expected_model_id", expected_model_id)


def create_local_openai_adapter(
    config: LocalOpenAIEndpointConfig,
) -> OpenAIClientAdapter:
    """Build a sync local adapter through the existing provider seam."""

    return OpenAIClientAdapter(
        provider=create_default_openai_provider(
            _provider_config_from_local_endpoint(config)
        ),
        models=config.model_aliases,
        is_local=True,
    )


def create_local_async_openai_adapter(
    config: LocalOpenAIEndpointConfig,
) -> AsyncOpenAIClientAdapter:
    """Build an async local adapter through the existing provider seam."""

    return AsyncOpenAIClientAdapter(
        provider=create_default_async_openai_provider(
            _provider_config_from_local_endpoint(config)
        ),
        models=config.model_aliases,
        is_local=True,
    )


def _provider_config_from_local_endpoint(
    config: LocalOpenAIEndpointConfig,
) -> OpenAIProviderConfig:
    return OpenAIProviderConfig(
        base_url=config.base_url,
        api_key=config.api_key,
        provider_name=config.provider_name,
    )
