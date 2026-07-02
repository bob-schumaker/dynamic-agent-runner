from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner import (
    create_litellm_adapter as exported_create_litellm_adapter,
)
from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request
from dynamic_agent_runner.openai_client import create_default_openai_provider
from dynamic_agent_runner.litellm_client import (
    create_async_litellm_adapter,
    create_litellm_adapter_from_provider_config,
    create_litellm_adapter,
)
from dynamic_agent_runner.openai_client import OpenAIProviderConfig


def test_litellm_adapter_translates_chat_request_and_normalizes_response() -> None:
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {
            "id": "chatcmpl_1",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "hello",
                    }
                }
            ],
        }

    adapter = create_litellm_adapter(completion=completion)
    request = build_openai_request(
        model="openai/gpt-test",
        messages=[OpenAIMessage("user", "Say hello")],
        temperature=0,
    )

    result = adapter.create_response(request)

    assert calls == [
        {
            "model": "openai/gpt-test",
            "messages": [{"role": "user", "content": "Say hello"}],
            "temperature": 0,
        }
    ]
    assert result.content == "hello"
    assert result.response_id == "chatcmpl_1"


def test_async_litellm_adapter_translates_and_normalizes_response() -> None:
    calls: list[dict[str, object]] = []

    async def acompletion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {
            "id": "chatcmpl_async",
            "choices": [{"message": {"role": "assistant", "content": "done"}}],
        }

    adapter = create_async_litellm_adapter(acompletion=acompletion)
    request = build_openai_request(
        model="openai/gpt-test",
        messages=[OpenAIMessage("user", "Finish")],
    )

    result = asyncio.run(adapter.create_response(request))

    assert calls == [
        {
            "model": "openai/gpt-test",
            "messages": [{"role": "user", "content": "Finish"}],
        }
    ]
    assert result.content == "done"
    assert result.response_id == "chatcmpl_async"


def test_litellm_adapter_rejects_responses_only_request_fields_before_dispatch() -> (
    None
):
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {}

    adapter = create_litellm_adapter(completion=completion)
    request = build_openai_request(
        model="openai/gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
        parallel_tool_calls=True,
    )

    with pytest.raises(ModelExecutionError, match="unsupported LiteLLM request field"):
        adapter.create_response(request)

    assert calls == []


def test_litellm_adapter_translates_tools_and_normalizes_tool_calls() -> None:
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {
            "id": "chatcmpl_tool",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "search_repo",
                                    "arguments": '{"query":"adapter"}',
                                },
                            }
                        ],
                    }
                }
            ],
        }

    tool = {
        "type": "function",
        "function": {
            "name": "search_repo",
            "description": "Search repository files.",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    adapter = create_litellm_adapter(completion=completion)
    request = build_openai_request(
        model="openai/gpt-test",
        messages=[OpenAIMessage("user", "Search")],
        tools=[tool],
        tool_choice="auto",
    )

    result = adapter.create_response(request)

    assert calls == [
        {
            "model": "openai/gpt-test",
            "messages": [{"role": "user", "content": "Search"}],
            "tools": [tool],
            "tool_choice": "auto",
        }
    ]
    assert result.content is None
    assert result.tool_calls[0].id == "call_1"
    assert result.tool_calls[0].name == "search_repo"
    assert result.tool_calls[0].arguments == '{"query":"adapter"}'


def test_litellm_adapter_redacts_provider_secrets() -> None:
    def completion(**kwargs: object) -> object:
        del kwargs
        raise RuntimeError("401 bearer secret-token")

    adapter = create_litellm_adapter(completion=completion)
    request = build_openai_request(
        model="openai/gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
    )

    with pytest.raises(
        ModelExecutionError, match="LiteLLM model request failed"
    ) as error:
        adapter.create_response(request)

    assert "secret-token" not in str(error.value)
    assert "REDACTED" in str(error.value)


def test_default_openai_provider_uses_litellm_for_ordinary_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")
    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(completion=lambda **kwargs: kwargs),
    )

    provider = create_default_openai_provider()

    assert provider.__class__.__name__ == "LiteLLMClientProvider"


def test_litellm_adapter_accepts_router_and_provider_config() -> None:
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "router_response", "choices": [{"message": {"content": "ok"}}]}

    router = SimpleNamespace(completion=completion)
    adapter = create_litellm_adapter_from_provider_config(
        OpenAIProviderConfig(api_key="router-key"),
        router=router,
    )
    request = build_openai_request(
        model="openai/router-model",
        messages=[OpenAIMessage("user", "Route")],
    )

    result = adapter.create_response(request)

    assert result.content == "ok"
    assert calls == [
        {
            "api_key": "router-key",
            "model": "openai/router-model",
            "messages": [{"role": "user", "content": "Route"}],
        }
    ]
    assert adapter._provider.config.api_key == "router-key"


def test_litellm_adapter_forwards_provider_credentials_and_base_url() -> None:
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "configured", "choices": [{"message": {"content": "ok"}}]}

    adapter = create_litellm_adapter(
        completion=completion,
        config=OpenAIProviderConfig(
            api_key="provider-key",
            base_url="http://localhost:4000/v1",
        ),
    )
    request = build_openai_request(
        model="openai/configured",
        messages=[OpenAIMessage("user", "Configured")],
    )

    adapter.create_response(request)

    assert calls == [
        {
            "api_key": "provider-key",
            "api_base": "http://localhost:4000/v1",
            "model": "openai/configured",
            "messages": [{"role": "user", "content": "Configured"}],
        }
    ]


def test_litellm_factory_is_public_and_model_is_metadata_only() -> None:
    def completion(**kwargs: object) -> object:
        return {"id": "metadata", "choices": [{"message": {"content": "ok"}}]}

    adapter = exported_create_litellm_adapter(
        model="metadata-model",
        completion=completion,
    )
    request = build_openai_request(
        model="request-model",
        messages=[OpenAIMessage("user", "Authoritative")],
    )

    result = adapter.create_response(request)

    assert adapter.models == ("metadata-model",)
    assert result.content == "ok"
