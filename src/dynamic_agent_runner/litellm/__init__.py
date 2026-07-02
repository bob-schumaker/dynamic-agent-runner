"""Small OpenAI-compatible LiteLLM transport bundled with DAR.

This is intentionally limited to the completion surfaces used by DAR.  It
keeps the package usable when the full upstream LiteLLM distribution is not
available from the configured package index.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def completion(**kwargs: Any) -> Any:
    """Dispatch a synchronous Chat Completions request through OpenAI."""
    from openai import OpenAI

    client_kwargs = _client_kwargs(kwargs)
    request_kwargs = _request_kwargs(kwargs)
    return OpenAI(**client_kwargs).chat.completions.create(**request_kwargs)


async def acompletion(**kwargs: Any) -> Any:
    """Dispatch an asynchronous Chat Completions request through OpenAI."""
    from openai import AsyncOpenAI

    client_kwargs = _client_kwargs(kwargs)
    request_kwargs = _request_kwargs(kwargs)
    return await AsyncOpenAI(**client_kwargs).chat.completions.create(**request_kwargs)


def _client_kwargs(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if kwargs.get("api_key") is not None:
        result["api_key"] = kwargs["api_key"]
    base_url = kwargs.get("base_url", kwargs.get("api_base"))
    if base_url is not None:
        result["base_url"] = base_url
    return result


def _request_kwargs(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    excluded = {"api_key", "api_base", "base_url", "custom_llm_provider"}
    return {key: value for key, value in kwargs.items() if key not in excluded}


__all__ = ["acompletion", "completion"]
