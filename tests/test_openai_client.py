"""Tests for the OpenAI client adapter boundary."""

from __future__ import annotations

import asyncio
import builtins
import sys
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    OpenAIClientAdapter,
    OpenAIMessage,
    OpenAIProviderConfig,
    build_openai_request,
    create_default_async_openai_client,
    create_default_openai_client,
    normalize_openai_response,
)
from dynamic_agent_runner.registry import openai_tool_schema
from dynamic_agent_runner.models import ToolDefinition


class FakeResponses:
    def __init__(self, response: object | None = None, error: Exception | None = None):
        self.response = response or {"id": "resp_1", "output_text": "hello"}
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, responses: FakeResponses):
        self.responses = responses


class FakeAsyncResponses:
    def __init__(self, response: object | None = None, error: Exception | None = None):
        self.response = response or {"id": "resp_async", "output_text": "hello async"}
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeAsyncClient:
    def __init__(self, responses: FakeAsyncResponses):
        self.responses = responses


class FakeProvider:
    def __init__(
        self,
        responses: FakeResponses,
        config: OpenAIProviderConfig | None = None,
    ):
        self.responses = responses
        self.config = config or OpenAIProviderConfig()
        self.calls = 0
        self.client = FakeClient(responses)

    def get_client(self) -> FakeClient:
        self.calls += 1
        return self.client


class FakeAsyncProvider:
    def __init__(
        self,
        responses: FakeAsyncResponses,
        config: OpenAIProviderConfig | None = None,
    ):
        self.responses = responses
        self.config = config or OpenAIProviderConfig()
        self.calls = 0
        self.client = FakeAsyncClient(responses)

    def get_client(self) -> FakeAsyncClient:
        self.calls += 1
        return self.client


def test_build_openai_request_includes_messages_tools_and_options() -> None:
    tool_schema = openai_tool_schema(
        ToolDefinition.from_mapping(
            {
                "id": "search_repo",
                "description_for_llm": "Search repository files.",
                "input_schema": {"type": "object", "properties": {}},
            }
        )
    )

    request = build_openai_request(
        model="gpt-test",
        messages=[
            OpenAIMessage("system", "Be concise."),
            {"role": "user", "content": "Search for adapters."},
        ],
        tools=[tool_schema],
        tool_choice="auto",
        response_format={"type": "json_object"},
        temperature=0,
        unused=None,
    )

    assert request.to_kwargs() == {
        "model": "gpt-test",
        "input": [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Search for adapters."},
        ],
        "tools": [tool_schema],
        "tool_choice": "auto",
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }


def test_adapter_uses_injected_client_and_normalizes_response() -> None:
    responses = FakeResponses({"id": "resp_123", "output_text": "final answer"})
    adapter = OpenAIClientAdapter(FakeClient(responses))
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
    )

    result = adapter.create_response(request)

    assert responses.calls == [
        {"model": "gpt-test", "input": [{"role": "user", "content": "Hello"}]}
    ]
    assert result.response_id == "resp_123"
    assert result.content == "final answer"
    assert result.tool_calls == ()


def test_openai_provider_config_preserves_endpoint_settings() -> None:
    config = OpenAIProviderConfig(
        base_url="http://localhost:11434/v1",
        api_key=None,
        provider_name="local-llm",
    )

    assert config.base_url == "http://localhost:11434/v1"
    assert config.api_key is None
    assert config.provider_name == "local-llm"


def test_adapter_can_use_repository_owned_provider_facade() -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    provider = FakeProvider(
        responses,
        OpenAIProviderConfig(base_url="http://localhost:11434/v1"),
    )
    adapter = OpenAIClientAdapter(provider=provider)
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
    )

    first_client = adapter.client
    second_client = adapter.client

    assert first_client is second_client is provider.client
    result = adapter.create_response(request)

    assert provider.calls == 1
    assert provider.config.base_url == "http://localhost:11434/v1"
    assert result.response_id == "resp_provider"
    assert result.content == "via provider"


def test_adapter_default_path_constructs_through_default_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = FakeResponses(
        {"id": "resp_default_provider", "output_text": "via default provider"}
    )
    provider = FakeProvider(responses)

    def fake_default_provider() -> FakeProvider:
        return provider

    def fail_default_client() -> object:
        raise AssertionError("default client factory should not be used directly")

    monkeypatch.setattr(
        "dynamic_agent_runner.openai_client.create_default_openai_provider",
        fake_default_provider,
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.openai_client.create_default_openai_client",
        fail_default_client,
    )

    adapter = OpenAIClientAdapter()
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
    )

    first_client = adapter.client
    second_client = adapter.client
    result = adapter.create_response(request)

    assert first_client is second_client is provider.client
    assert provider.calls == 1
    assert result.response_id == "resp_default_provider"
    assert result.content == "via default provider"


def test_adapter_create_response_uses_repository_owned_dispatch_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = FakeResponses({"id": "resp_123", "output_text": "final answer"})
    adapter = OpenAIClientAdapter(FakeClient(responses))
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
    )
    sentinel = object()
    observed: dict[str, object] = {}

    def fake_create_openai_response(client: object, req: object) -> object:
        observed["client"] = client
        observed["request"] = req
        return sentinel

    monkeypatch.setattr(
        "dynamic_agent_runner.openai_client.create_openai_response",
        fake_create_openai_response,
        raising=False,
    )

    result = adapter.create_response(request)

    assert result is sentinel
    assert observed == {"client": adapter.client, "request": request}
    assert responses.calls == []


def test_async_adapter_awaits_injected_client_and_normalizes_response() -> None:
    responses = FakeAsyncResponses(
        {"id": "resp_async_123", "output_text": "async final"}
    )
    adapter = AsyncOpenAIClientAdapter(FakeAsyncClient(responses))
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello async")],
    )

    result = asyncio.run(adapter.create_response(request))

    assert responses.calls == [
        {"model": "gpt-test", "input": [{"role": "user", "content": "Hello async"}]}
    ]
    assert result.response_id == "resp_async_123"
    assert result.content == "async final"
    assert result.tool_calls == ()


def test_async_adapter_can_use_repository_owned_provider_facade() -> None:
    responses = FakeAsyncResponses(
        {"id": "resp_async_provider", "output_text": "via async provider"}
    )
    provider = FakeAsyncProvider(
        responses,
        OpenAIProviderConfig(base_url="http://localhost:11434/v1"),
    )
    adapter = AsyncOpenAIClientAdapter(provider=provider)
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello async")],
    )

    first_client = adapter.client
    second_client = adapter.client

    assert first_client is second_client is provider.client
    result = asyncio.run(adapter.create_response(request))

    assert provider.calls == 1
    assert provider.config.base_url == "http://localhost:11434/v1"
    assert result.response_id == "resp_async_provider"
    assert result.content == "via async provider"


def test_async_adapter_default_path_constructs_through_default_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = FakeAsyncResponses(
        {
            "id": "resp_async_default_provider",
            "output_text": "via async default provider",
        }
    )
    provider = FakeAsyncProvider(responses)

    def fake_default_provider() -> FakeAsyncProvider:
        return provider

    def fail_default_client() -> object:
        raise AssertionError("default async client factory should not be used directly")

    monkeypatch.setattr(
        "dynamic_agent_runner.openai_client.create_default_async_openai_provider",
        fake_default_provider,
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.openai_client.create_default_async_openai_client",
        fail_default_client,
    )

    adapter = AsyncOpenAIClientAdapter()
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello async")],
    )

    first_client = adapter.client
    second_client = adapter.client
    result = asyncio.run(adapter.create_response(request))

    assert first_client is second_client is provider.client
    assert provider.calls == 1
    assert result.response_id == "resp_async_default_provider"
    assert result.content == "via async default provider"


def test_async_adapter_create_response_uses_repository_owned_dispatch_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = FakeAsyncResponses(
        {"id": "resp_async_123", "output_text": "async final"}
    )
    adapter = AsyncOpenAIClientAdapter(FakeAsyncClient(responses))
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello async")],
    )
    sentinel = object()
    observed: dict[str, object] = {}

    async def fake_create_async_openai_response(client: object, req: object) -> object:
        observed["client"] = client
        observed["request"] = req
        return sentinel

    monkeypatch.setattr(
        "dynamic_agent_runner.openai_client.create_async_openai_response",
        fake_create_async_openai_response,
        raising=False,
    )

    result = asyncio.run(adapter.create_response(request))

    assert result is sentinel
    assert observed == {"client": adapter.client, "request": request}
    assert responses.calls == []


def test_normalize_openai_response_extracts_message_text_and_tool_calls() -> None:
    raw_response = {
        "id": "resp_tools",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Need a tool."},
                ],
            },
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "search_repo",
                "arguments": '{"query":"adapter"}',
            },
        ],
    }

    response = normalize_openai_response(raw_response)

    assert response.response_id == "resp_tools"
    assert response.content == "Need a tool."
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "call_1"
    assert response.tool_calls[0].name == "search_repo"
    assert response.tool_calls[0].arguments == '{"query":"adapter"}'


def test_adapter_wraps_model_failures() -> None:
    responses = FakeResponses(error=RuntimeError("network unavailable"))
    adapter = OpenAIClientAdapter(FakeClient(responses))
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
    )

    with pytest.raises(ModelExecutionError, match="OpenAI model request failed"):
        adapter.create_response(request)


def test_async_adapter_wraps_model_failures() -> None:
    responses = FakeAsyncResponses(error=RuntimeError("network unavailable"))
    adapter = AsyncOpenAIClientAdapter(FakeAsyncClient(responses))
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
    )

    with pytest.raises(ModelExecutionError, match="OpenAI model request failed"):
        asyncio.run(adapter.create_response(request))


def test_create_default_openai_client_uses_official_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []
    created_kwargs: list[dict[str, object]] = []

    class FakeOfficialOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created.append(self)
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules, "openai", SimpleNamespace(OpenAI=FakeOfficialOpenAI)
    )

    client = create_default_openai_client()

    assert client is created[0]
    assert created_kwargs == [{}]


def test_create_default_openai_client_applies_provider_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_kwargs: list[dict[str, object]] = []

    class FakeOfficialOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules, "openai", SimpleNamespace(OpenAI=FakeOfficialOpenAI)
    )

    client = create_default_openai_client(
        OpenAIProviderConfig(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            provider_name="local-llm",
        )
    )

    assert created_kwargs == [
        {"base_url": "http://localhost:11434/v1", "api_key": "test-key"}
    ]
    assert client is not None


def test_create_default_openai_client_omits_api_key_when_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_kwargs: list[dict[str, object]] = []

    class FakeOfficialOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules, "openai", SimpleNamespace(OpenAI=FakeOfficialOpenAI)
    )

    create_default_openai_client(
        OpenAIProviderConfig(base_url="http://localhost:11434/v1", api_key=None)
    )

    assert created_kwargs == [{"base_url": "http://localhost:11434/v1"}]


def test_create_default_async_openai_client_uses_official_async_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []

    class FakeOfficialAsyncOpenAI:
        def __init__(self) -> None:
            created.append(self)

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(AsyncOpenAI=FakeOfficialAsyncOpenAI),
    )

    client = create_default_async_openai_client()

    assert client is created[0]


def test_create_default_async_openai_client_applies_provider_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_kwargs: list[dict[str, object]] = []

    class FakeOfficialAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(AsyncOpenAI=FakeOfficialAsyncOpenAI),
    )

    client = create_default_async_openai_client(
        OpenAIProviderConfig(base_url="http://localhost:11434/v1", api_key="test-key")
    )

    assert created_kwargs == [
        {"base_url": "http://localhost:11434/v1", "api_key": "test-key"}
    ]
    assert client is not None


def test_create_default_async_openai_client_omits_api_key_when_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_kwargs: list[dict[str, object]] = []

    class FakeOfficialAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(AsyncOpenAI=FakeOfficialAsyncOpenAI),
    )

    create_default_async_openai_client(
        OpenAIProviderConfig(base_url="http://localhost:11434/v1", api_key=None)
    )

    assert created_kwargs == [{"base_url": "http://localhost:11434/v1"}]


def test_create_default_openai_client_wraps_import_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def fake_import(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "openai":
            raise ImportError("openai unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, "openai", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(
        ModelExecutionError, match="official openai package is not available"
    ):
        create_default_openai_client()


def test_create_default_async_openai_client_wraps_import_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def fake_import(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "openai":
            raise ImportError("openai unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, "openai", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(
        ModelExecutionError, match="official openai package is not available"
    ):
        create_default_async_openai_client()


@pytest.mark.parametrize(
    ("model", "messages", "message"),
    [
        ("", [OpenAIMessage("user", "hi")], "requires a model"),
        ("gpt-test", [], "requires at least one message"),
        ("gpt-test", [{"role": "user"}], "requires role and content"),
    ],
)
def test_build_openai_request_validates_required_inputs(
    model: str,
    messages: list[object],
    message: str,
) -> None:
    with pytest.raises(ModelExecutionError, match=message):
        build_openai_request(model=model, messages=messages)
