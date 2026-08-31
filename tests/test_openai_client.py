"""Tests for the OpenAI client adapter boundary."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.errors import ModelExecutionError, WorkflowExecutionError
from dynamic_agent_runner.executor import execute_workflow, execute_workflow_async
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    OpenAIClientAdapter,
    OpenAIMessage,
    OpenAIProviderConfig,
    build_openai_request,
    create_default_async_openai_provider,
    create_async_openai_adapter_from_provider_config,
    create_async_openai_response,
    create_default_async_openai_client,
    create_default_openai_client,
    create_default_openai_provider,
    create_official_async_openai_client,
    create_official_openai_client,
    create_openai_adapter_from_provider_config,
    create_openai_response,
    is_context_overflow_error,
    normalize_openai_response,
)
from dynamic_agent_runner.registry import openai_tool_schema
from dynamic_agent_runner.models import ToolDefinition
from dynamic_agent_runner.tracing import InMemoryTraceSink
from parity_support import (
    install_parity_io_blocker,
    parity_exposed_schemas,
    parity_loop_workflow,
    parity_no_tool_workflow,
    parity_contract_projection,
    parity_record,
    parity_registry,
)


@pytest.fixture(autouse=True)
def isolate_ambient_auth(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))


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


class SequencedResponses:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses: FakeResponses, models: object | None = None):
        self.responses = responses
        if models is not None:
            self.models = models


class FakeModels:
    def __init__(self, models: object):
        self.models = models
        self.calls: list[dict[str, object]] = []

    def list(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        return self.models


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


class SequencedAsyncResponses(SequencedResponses):
    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeAsyncClient:
    def __init__(self, responses: FakeAsyncResponses, models: object | None = None):
        self.responses = responses
        if models is not None:
            self.models = models


class FakeAsyncModels:
    def __init__(self, models: object):
        self.models = models
        self.calls: list[dict[str, object]] = []

    async def list(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        return self.models


class FakeProvider:
    def __init__(
        self,
        responses: FakeResponses,
        config: OpenAIProviderConfig | None = None,
        models: object | None = None,
    ):
        self.responses = responses
        self.config = config or OpenAIProviderConfig()
        self.calls = 0
        self.client = FakeClient(responses, models=models)

    def get_client(self) -> FakeClient:
        self.calls += 1
        return self.client


class FakeAsyncProvider:
    def __init__(
        self,
        responses: FakeAsyncResponses,
        config: OpenAIProviderConfig | None = None,
        models: object | None = None,
    ):
        self.responses = responses
        self.config = config or OpenAIProviderConfig()
        self.calls = 0
        self.client = FakeAsyncClient(responses, models=models)

    def get_client(self) -> FakeAsyncClient:
        self.calls += 1
        return self.client


@pytest.mark.parametrize("asynchronous", [False, True])
def test_model_interface_parity_openai_s1_uses_normalized_native_call(
    asynchronous: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_parity_io_blocker(monkeypatch)
    result, record, error, _ = _run_openai_parity(
        "S1",
        [
            _openai_tool_response(
                "create_record", '{"title":"DAR","body":"controlled"}'
            ),
            {"id": "response-text", "output_text": "created"},
        ],
        asynchronous=asynchronous,
    )

    assert error is None
    assert result is not None
    assert result.final_result == "created"
    assert record.normalized_calls == (
        ("create_record", '{"title":"DAR","body":"controlled"}'),
    )
    if not asynchronous:
        _, async_record, _, _ = _run_openai_parity(
            "S1",
            [
                _openai_tool_response(
                    "create_record", '{"title":"DAR","body":"controlled"}'
                ),
                {"id": "response-text", "output_text": "created"},
            ],
            asynchronous=True,
        )
        assert parity_contract_projection(record) == parity_contract_projection(
            async_record
        )


def _openai_tool_response(name: str, arguments: str) -> dict[str, object]:
    return {
        "id": "response-tool",
        "output": [
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": name,
                "arguments": arguments,
            }
        ],
    }


def _run_openai_parity(
    scenario: str, native_responses: list[object], *, asynchronous: bool
):
    observed = []

    def record_response(_request, response) -> None:
        observed.extend(response.tool_calls)

    registry, invocations, results = parity_registry()
    sink = InMemoryTraceSink()
    error = None
    try:
        if asynchronous:
            responses = SequencedAsyncResponses(native_responses)
            adapter = AsyncOpenAIClientAdapter(
                FakeAsyncClient(responses),
                models=["gpt-test"],
                response_validator=record_response,
            )
            result = asyncio.run(
                execute_workflow_async(
                    parity_no_tool_workflow()
                    if scenario == "S5"
                    else parity_loop_workflow(),
                    prompt="controlled parity",
                    tool_registry=registry,
                    model_adapter=adapter,
                    trace_sink=sink,
                )
            )
        else:
            responses = SequencedResponses(native_responses)
            adapter = OpenAIClientAdapter(
                FakeClient(responses),
                models=["gpt-test"],
                response_validator=record_response,
            )
            result = execute_workflow(
                parity_no_tool_workflow()
                if scenario == "S5"
                else parity_loop_workflow(),
                prompt="controlled parity",
                tool_registry=registry,
                model_adapter=adapter,
                trace_sink=sink,
            )
    except Exception as caught:
        result = None
        error = caught
    return (
        result,
        parity_record(
            interface="openai_scripted_client",
            scenario=scenario,
            asynchronous=asynchronous,
            normalized_calls=tuple((call.name, call.arguments) for call in observed),
            exposed_schemas=parity_exposed_schemas(responses.calls[0]["tools"]),
            invocations=invocations,
            results=results,
            result=result,
            error=error,
            sink=sink,
        ),
        error,
        responses.calls,
    )


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    ("scenario", "responses", "invoked", "fails"),
    [
        ("S5", [{"id": "response-text", "output_text": "no tool"}], (), False),
        (
            "S2",
            [
                _openai_tool_response(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase"}',
                ),
                {"output_text": "transformed"},
            ],
            ("transform_record",),
            False,
        ),
        (
            "S2-invalid",
            [_openai_tool_response("transform_record", '{"record_id":"record-seed"}')],
            (),
            True,
        ),
        (
            "S2-wrong-type",
            [
                _openai_tool_response(
                    "transform_record", '{"record_id":1,"operation":"uppercase"}'
                )
            ],
            (),
            True,
        ),
        (
            "S2-invalid-enum",
            [
                _openai_tool_response(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"lowercase"}',
                )
            ],
            (),
            True,
        ),
        (
            "S2-unknown",
            [
                _openai_tool_response(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase","unknown":true}',
                )
            ],
            (),
            True,
        ),
        (
            "S2-malformed",
            [_openai_tool_response("transform_record", "not-json")],
            (),
            True,
        ),
        (
            "S3",
            [
                _openai_tool_response("lookup_record", '{"key":"seed"}'),
                _openai_tool_response(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase"}',
                ),
                {"output_text": "SEED"},
            ],
            ("lookup_record", "transform_record"),
            False,
        ),
        (
            "S4",
            [_openai_tool_response("fail_controlled", '{"code":"planned"}')],
            ("fail_controlled",),
            True,
        ),
        ("S6", [_openai_tool_response("lookup_record", "not-json")], (), True),
    ],
)
def test_model_interface_parity_openai_native_scenarios(
    scenario: str,
    responses: list[object],
    invoked: tuple[str, ...],
    fails: bool,
    asynchronous: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_parity_io_blocker(monkeypatch)
    result, record, error, calls = _run_openai_parity(
        scenario, responses, asynchronous=asynchronous
    )
    assert tuple(name for name, _ in record.invocations) == invoked
    assert (error is not None) is fails
    assert (result is None) is fails
    if fails:
        assert isinstance(error, WorkflowExecutionError)
        assert record.error_class == "WorkflowExecutionError"
    if scenario == "S4":
        assert record.stop_reasons == ("tool_failure",)
        assert len(calls) == 1
        assert isinstance(error, WorkflowExecutionError)
        assert "planned controlled failure" in str(error)
        assert record.trace_event_types.count("model_tool_loop_tool_call") == 1
    if scenario == "S6":
        assert "tool_started" not in record.trace_event_types
        assert "model_tool_loop_tool_call" not in record.trace_event_types
        assert len(calls) == 1
    if scenario == "S3":
        assert len(calls) == 3
        assert "record-seed" in str(calls[1])
    if not asynchronous:
        _, async_record, _, _ = _run_openai_parity(
            scenario, responses, asynchronous=True
        )
        assert parity_contract_projection(record) == parity_contract_projection(
            async_record
        )


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


def test_local_openai_endpoint_config_preserves_aliases_and_expected_identity() -> None:
    from dynamic_agent_runner.local_models import LocalOpenAIEndpointConfig

    config = LocalOpenAIEndpointConfig(
        base_url="http://localhost:11434/v1",
        api_key="local-key",
        model_aliases=["qwen-local", "chat-default"],
        provider_name="llama.cpp",
        expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
    )

    assert config.base_url == "http://localhost:11434/v1"
    assert config.api_key == "local-key"
    assert config.model_aliases == ("qwen-local", "chat-default")
    assert config.provider_name == "llama.cpp"
    assert config.expected_model_id == "Qwen/Qwen3-4B-Instruct-2507"


def test_create_local_openai_adapter_builds_local_provider_backed_adapter() -> None:
    from dynamic_agent_runner.local_models import (
        LocalOpenAIEndpointConfig,
        create_local_openai_adapter,
    )

    config = LocalOpenAIEndpointConfig(
        base_url="http://localhost:11434/v1",
        api_key="local-key",
        model_aliases=["qwen-local", "chat-default"],
        provider_name="llama.cpp",
        expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
    )

    adapter = create_local_openai_adapter(config)

    assert isinstance(adapter, OpenAIClientAdapter)
    assert adapter.models == ("qwen-local", "chat-default")
    assert adapter.is_local is True
    assert adapter._provider is not None
    assert adapter._provider.config == OpenAIProviderConfig(
        base_url="http://localhost:11434/v1",
        api_key="local-key",
        provider_name="llama.cpp",
        discover_default_auth=False,
    )


def test_create_local_async_openai_adapter_builds_local_provider_backed_adapter() -> (
    None
):
    from dynamic_agent_runner.local_models import (
        LocalOpenAIEndpointConfig,
        create_local_async_openai_adapter,
    )

    config = LocalOpenAIEndpointConfig(
        base_url="http://localhost:11434/v1",
        api_key="local-key",
        model_aliases=["qwen-local", "chat-default"],
        provider_name="llama.cpp",
        expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
    )

    adapter = create_local_async_openai_adapter(config)

    assert isinstance(adapter, AsyncOpenAIClientAdapter)
    assert adapter.models == ("qwen-local", "chat-default")
    assert adapter.is_local is True
    assert adapter._provider is not None
    assert adapter._provider.config == OpenAIProviderConfig(
        base_url="http://localhost:11434/v1",
        api_key="local-key",
        provider_name="llama.cpp",
        discover_default_auth=False,
    )


def test_create_openai_adapter_from_provider_config_uses_default_provider_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider(
        FakeResponses({"id": "resp_provider_factory", "output_text": "factory"}),
        OpenAIProviderConfig(
            base_url="http://localhost:11434/v1",
            api_key="local-key",
            provider_name="llama.cpp",
        ),
    )
    observed: dict[str, object] = {}

    def fake_default_provider(config: OpenAIProviderConfig):
        observed["config"] = config
        return provider

    monkeypatch.setattr(
        "dynamic_agent_runner.openai_client.create_default_openai_provider",
        fake_default_provider,
    )

    adapter = create_openai_adapter_from_provider_config(
        OpenAIProviderConfig(
            base_url="http://localhost:11434/v1",
            api_key="local-key",
            provider_name="llama.cpp",
        ),
        models=["qwen-local", "chat-default"],
        is_local=True,
    )

    assert isinstance(adapter, OpenAIClientAdapter)
    assert adapter._provider is provider
    assert adapter.models == ("qwen-local", "chat-default")
    assert adapter.is_local is True
    assert observed["config"] == OpenAIProviderConfig(
        base_url="http://localhost:11434/v1",
        api_key="local-key",
        provider_name="llama.cpp",
    )


def test_create_async_openai_adapter_from_provider_config_uses_default_provider_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeAsyncProvider(
        FakeAsyncResponses(
            {"id": "resp_async_provider_factory", "output_text": "factory async"}
        ),
        OpenAIProviderConfig(
            base_url="http://localhost:11434/v1",
            api_key="local-key",
            provider_name="llama.cpp",
        ),
    )
    observed: dict[str, object] = {}

    def fake_default_provider(config: OpenAIProviderConfig):
        observed["config"] = config
        return provider

    monkeypatch.setattr(
        "dynamic_agent_runner.openai_client.create_default_async_openai_provider",
        fake_default_provider,
    )

    adapter = create_async_openai_adapter_from_provider_config(
        OpenAIProviderConfig(
            base_url="http://localhost:11434/v1",
            api_key="local-key",
            provider_name="llama.cpp",
        ),
        models=["qwen-local", "chat-default"],
        is_local=True,
    )

    assert isinstance(adapter, AsyncOpenAIClientAdapter)
    assert adapter._provider is provider
    assert adapter.models == ("qwen-local", "chat-default")
    assert adapter.is_local is True
    assert observed["config"] == OpenAIProviderConfig(
        base_url="http://localhost:11434/v1",
        api_key="local-key",
        provider_name="llama.cpp",
    )


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


def test_adapter_lists_supported_models_from_configured_models() -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    adapter = OpenAIClientAdapter(
        FakeClient(responses),
        models=["local-chat", "fallback-chat"],
    )

    assert adapter.list_supported_models() == ("local-chat", "fallback-chat")


def test_adapter_lists_supported_models_from_authenticated_client() -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    models = FakeModels({"data": [{"id": "gpt-a"}, {"id": "gpt-b"}]})
    adapter = OpenAIClientAdapter(FakeClient(responses, models=models))

    first = adapter.list_supported_models()
    second = adapter.list_supported_models()

    assert first == ("gpt-a", "gpt-b")
    assert second == ("gpt-a", "gpt-b")
    assert models.calls == [{}]


def test_adapter_lists_lowest_version_supported_model_first() -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    models = FakeModels(
        {
            "data": [
                {"id": "gpt-5.5"},
                {"id": "gpt-5.4"},
                {"id": "gpt-5.4-mini"},
                {"id": "codex-auto-review"},
            ]
        }
    )
    adapter = OpenAIClientAdapter(FakeClient(responses, models=models))

    assert adapter.list_supported_models() == (
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.5",
        "codex-auto-review",
    )
    assert adapter.default_model() == "gpt-5.4"


def test_generic_provider_catalog_keeps_id_only_sorting_behavior() -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    models = FakeModels(
        {
            "data": [
                {"id": "gpt-5.5", "priority": 1, "visibility": "hide"},
                {"id": "gpt-5.4", "priority": 20, "visibility": "public"},
            ]
        }
    )
    adapter = OpenAIClientAdapter(FakeClient(responses, models=models))

    assert adapter.list_supported_models() == ("gpt-5.4", "gpt-5.5")


def test_adapter_refreshes_supported_models_when_requested() -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    models = FakeModels({"data": [{"id": "gpt-a"}]})
    adapter = OpenAIClientAdapter(FakeClient(responses, models=models))

    assert adapter.list_supported_models() == ("gpt-a",)
    models.models = {"data": [{"id": "gpt-b"}]}

    assert adapter.list_supported_models(refresh=True) == ("gpt-b",)
    assert models.calls == [{}, {}]


def test_chatgpt_codex_adapter_lists_models_before_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    models = FakeModels({"models": [{"slug": "codex-mini-latest"}]})
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "version.json").write_text(
        '{"latest_version": "9.8.7-beta.1"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    provider = FakeProvider(
        responses,
        OpenAIProviderConfig(provider_name="chatgpt-codex"),
        models=models,
    )
    adapter = OpenAIClientAdapter(provider=provider)
    request = build_openai_request(
        model="codex-mini-latest",
        messages=[OpenAIMessage("user", "Hello")],
    )

    result = adapter.create_response(request)

    assert models.calls == [{"extra_query": {"client_version": "9.8.7"}}]
    assert responses.calls == [
        {
            "model": "codex-mini-latest",
            "input": [{"role": "user", "content": "Hello"}],
            "instructions": "You are a helpful assistant.",
            "store": False,
            "stream": True,
        }
    ]
    assert result.content == "via provider"


def test_chatgpt_codex_adapter_exposes_supported_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    models = FakeModels({"models": [{"slug": "codex-mini-latest"}]})
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "version.json").write_text(
        '{"latest_version": "9.8.7"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    provider = FakeProvider(
        responses,
        OpenAIProviderConfig(provider_name="chatgpt-codex"),
        models=models,
    )
    adapter = OpenAIClientAdapter(provider=provider)

    assert adapter.list_supported_models() == ("codex-mini-latest",)
    assert adapter.list_supported_models() == ("codex-mini-latest",)
    assert models.calls == [{"extra_query": {"client_version": "9.8.7"}}]


def test_chatgpt_codex_catalog_preserves_priority_hides_models_and_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    models = FakeModels(
        {
            "models": [
                {"slug": "gpt-5.4", "priority": 20, "visibility": "public"},
                {"slug": "gpt-5.6-sol", "priority": 1, "visibility": "public"},
                {"slug": "gpt-5.6-hidden", "priority": 0, "visibility": "hide"},
            ]
        }
    )
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "version.json").write_text(
        '{"latest_version": "9.8.7"}', encoding="utf-8"
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    provider = FakeProvider(
        responses,
        OpenAIProviderConfig(provider_name="chatgpt-codex"),
        models=models,
    )
    adapter = OpenAIClientAdapter(provider=provider)

    assert adapter.list_supported_models() == ("gpt-5.6-sol", "gpt-5.4")
    assert adapter.default_model() == "gpt-5.6-sol"


def test_chatgpt_codex_auth_forwards_account_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        '{"auth_mode":"chatgpt","tokens":'
        '{"access_token":"secret-token","account_id":"account-123"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    created_kwargs: list[dict[str, object]] = []

    class FakeOfficialOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules, "openai", SimpleNamespace(OpenAI=FakeOfficialOpenAI)
    )

    create_default_openai_client()

    assert created_kwargs == [
        {
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": "secret-token",
            "default_headers": {"ChatGPT-Account-ID": "account-123"},
        }
    ]


def test_chatgpt_codex_adapter_moves_prompt_messages_to_instructions() -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    models = FakeModels({"models": [{"slug": "codex-mini-latest"}]})
    provider = FakeProvider(
        responses,
        OpenAIProviderConfig(provider_name="chatgpt-codex"),
        models=models,
    )
    adapter = OpenAIClientAdapter(provider=provider)
    request = build_openai_request(
        model="codex-mini-latest",
        messages=[
            OpenAIMessage("system", "System rules."),
            OpenAIMessage("developer", "Developer rules."),
            OpenAIMessage("user", "Hello"),
        ],
    )

    result = adapter.create_response(request)

    assert responses.calls == [
        {
            "model": "codex-mini-latest",
            "input": [{"role": "user", "content": "Hello"}],
            "instructions": "System rules.\n\nDeveloper rules.",
            "store": False,
            "stream": True,
        }
    ]
    assert result.content == "via provider"


def test_chatgpt_codex_adapter_converts_structured_tool_loop_transcript() -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    models = FakeModels({"models": [{"slug": "codex-mini-latest"}]})
    provider = FakeProvider(
        responses,
        OpenAIProviderConfig(provider_name="chatgpt-codex"),
        models=models,
    )
    adapter = OpenAIClientAdapter(provider=provider)
    request = build_openai_request(
        model="codex-mini-latest",
        messages=[
            OpenAIMessage("system", "System rules."),
            OpenAIMessage("user", "Find agents."),
            {
                "role": "assistant",
                "content": "Tool call call_1: search_repo",
                "_dar_transcript_type": "model_tool_call",
                "call_id": "call_1",
                "name": "search_repo",
                "arguments": '{"query":"agents"}',
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "name": "search_repo",
                "content": '{"summary":"agents found"}',
                "_dar_transcript_type": "model_tool_result",
                "call_id": "call_1",
                "output": '{"summary":"agents found"}',
            },
        ],
    )

    result = adapter.create_response(request)

    assert result.content == "via provider"
    assert responses.calls == [
        {
            "model": "codex-mini-latest",
            "input": [
                {"role": "user", "content": "Find agents."},
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "search_repo",
                    "arguments": '{"query":"agents"}',
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": '{"summary":"agents found"}',
                },
            ],
            "instructions": "System rules.",
            "store": False,
            "stream": True,
        }
    ]


def test_chatgpt_codex_adapter_rejects_unlisted_model_before_request() -> None:
    responses = FakeResponses({"id": "resp_provider", "output_text": "via provider"})
    models = FakeModels({"data": [{"id": "codex-mini-latest"}]})
    provider = FakeProvider(
        responses,
        OpenAIProviderConfig(provider_name="chatgpt-codex"),
        models=models,
    )
    adapter = OpenAIClientAdapter(provider=provider)
    request = build_openai_request(
        model="gpt-4.1",
        messages=[OpenAIMessage("user", "Hello")],
    )

    with pytest.raises(ModelExecutionError) as exc_info:
        adapter.create_response(request)

    message = str(exc_info.value)
    assert "gpt-4.1" in message
    assert "codex-mini-latest" in message
    assert "ChatGPT/Codex" in message
    assert len(models.calls) == 1
    assert responses.calls == []


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


def test_async_adapter_lists_supported_models_from_configured_models() -> None:
    responses = FakeAsyncResponses(
        {"id": "resp_async_provider", "output_text": "via async provider"}
    )
    adapter = AsyncOpenAIClientAdapter(
        FakeAsyncClient(responses),
        models=["local-chat", "fallback-chat"],
    )

    assert asyncio.run(adapter.list_supported_models()) == (
        "local-chat",
        "fallback-chat",
    )


def test_async_adapter_lists_supported_models_from_authenticated_client() -> None:
    responses = FakeAsyncResponses(
        {"id": "resp_async_provider", "output_text": "via async provider"}
    )
    models = FakeAsyncModels({"data": [{"id": "gpt-a"}, {"id": "gpt-b"}]})
    adapter = AsyncOpenAIClientAdapter(FakeAsyncClient(responses, models=models))

    first = asyncio.run(adapter.list_supported_models())
    second = asyncio.run(adapter.list_supported_models())

    assert first == ("gpt-a", "gpt-b")
    assert second == ("gpt-a", "gpt-b")
    assert models.calls == [{}]


def test_async_adapter_uses_lowest_version_default_model() -> None:
    responses = FakeAsyncResponses(
        {"id": "resp_async_provider", "output_text": "via async provider"}
    )
    models = FakeAsyncModels(
        {
            "data": [
                {"id": "gpt-5.5"},
                {"id": "gpt-5.4"},
                {"id": "codex-auto-review"},
            ]
        }
    )
    adapter = AsyncOpenAIClientAdapter(FakeAsyncClient(responses, models=models))

    assert asyncio.run(adapter.default_model()) == "gpt-5.4"


def test_async_chatgpt_codex_adapter_rejects_unlisted_model_before_request() -> None:
    responses = FakeAsyncResponses(
        {"id": "resp_async_provider", "output_text": "via async provider"}
    )
    models = FakeAsyncModels({"data": [{"id": "codex-mini-latest"}]})
    provider = FakeAsyncProvider(
        responses,
        OpenAIProviderConfig(provider_name="chatgpt-codex"),
        models=models,
    )
    adapter = AsyncOpenAIClientAdapter(provider=provider)
    request = build_openai_request(
        model="gpt-4.1",
        messages=[OpenAIMessage("user", "Hello async")],
    )

    with pytest.raises(ModelExecutionError) as exc_info:
        asyncio.run(adapter.create_response(request))

    message = str(exc_info.value)
    assert "gpt-4.1" in message
    assert "codex-mini-latest" in message
    assert "ChatGPT/Codex" in message
    assert len(models.calls) == 1
    assert responses.calls == []


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


def test_create_openai_response_normalizes_streaming_text() -> None:
    responses = FakeResponses(
        [
            SimpleNamespace(type="response.created", response={"id": "resp_stream"}),
            SimpleNamespace(type="response.output_text.delta", delta="hel"),
            SimpleNamespace(type="response.output_text.delta", delta="lo"),
            SimpleNamespace(type="response.completed", response={"id": "resp_stream"}),
        ]
    )
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
        stream=True,
    )

    result = create_openai_response(FakeClient(responses), request)

    assert responses.calls == [
        {
            "model": "gpt-test",
            "input": [{"role": "user", "content": "Hello"}],
            "stream": True,
        }
    ]
    assert result.response_id == "resp_stream"
    assert result.content == "hello"


def test_create_openai_response_preserves_streamed_function_call_output_item() -> None:
    responses = FakeResponses(
        [
            SimpleNamespace(type="response.created", response={"id": "resp_stream"}),
            SimpleNamespace(
                type="response.output_item.done",
                item={
                    "type": "function_call",
                    "call_id": "call_stream",
                    "name": "search_repo",
                    "arguments": '{"query":"adapter"}',
                },
            ),
            SimpleNamespace(
                type="response.completed",
                response={"id": "resp_stream", "output": []},
            ),
        ]
    )
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
        stream=True,
    )

    result = create_openai_response(FakeClient(responses), request)

    assert result.response_id == "resp_stream"
    assert result.content is None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call_stream"
    assert result.tool_calls[0].name == "search_repo"
    assert result.tool_calls[0].arguments == '{"query":"adapter"}'


def test_create_openai_response_prefers_completed_output_over_streamed_items() -> None:
    responses = FakeResponses(
        [
            SimpleNamespace(type="response.created", response={"id": "resp_stream"}),
            SimpleNamespace(
                type="response.output_item.done",
                item={
                    "type": "function_call",
                    "call_id": "call_stream",
                    "name": "stream_tool",
                    "arguments": '{"source":"stream"}',
                },
            ),
            SimpleNamespace(
                type="response.completed",
                response={
                    "id": "resp_stream",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_completed",
                            "name": "completed_tool",
                            "arguments": '{"source":"completed"}',
                        }
                    ],
                },
            ),
        ]
    )
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
        stream=True,
    )

    result = create_openai_response(FakeClient(responses), request)

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call_completed"
    assert result.tool_calls[0].name == "completed_tool"
    assert result.tool_calls[0].arguments == '{"source":"completed"}'


def test_create_async_openai_response_normalizes_streaming_text() -> None:
    class FakeAsyncStream:
        def __aiter__(self):
            return self

        async def __anext__(self) -> object:
            if not events:
                raise StopAsyncIteration
            return events.pop(0)

    events = [
        SimpleNamespace(type="response.created", response={"id": "resp_stream"}),
        SimpleNamespace(type="response.output_text.delta", delta="hel"),
        SimpleNamespace(type="response.output_text.delta", delta="lo"),
        SimpleNamespace(type="response.completed", response={"id": "resp_stream"}),
    ]
    responses = FakeAsyncResponses(FakeAsyncStream())
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
        stream=True,
    )

    result = asyncio.run(
        create_async_openai_response(FakeAsyncClient(responses), request)
    )

    assert responses.calls == [
        {
            "model": "gpt-test",
            "input": [{"role": "user", "content": "Hello"}],
            "stream": True,
        }
    ]
    assert result.response_id == "resp_stream"
    assert result.content == "hello"


def test_create_async_openai_response_preserves_streamed_function_call_output_item() -> (
    None
):
    class FakeAsyncStream:
        def __aiter__(self):
            return self

        async def __anext__(self) -> object:
            if not events:
                raise StopAsyncIteration
            return events.pop(0)

    events = [
        SimpleNamespace(type="response.created", response={"id": "resp_stream"}),
        SimpleNamespace(
            type="response.output_item.done",
            item={
                "type": "function_call",
                "call_id": "call_async_stream",
                "name": "search_repo",
                "arguments": '{"query":"async"}',
            },
        ),
        SimpleNamespace(
            type="response.completed",
            response={"id": "resp_stream", "output": []},
        ),
    ]
    responses = FakeAsyncResponses(FakeAsyncStream())
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
        stream=True,
    )

    result = asyncio.run(
        create_async_openai_response(FakeAsyncClient(responses), request)
    )

    assert result.response_id == "resp_stream"
    assert result.content is None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call_async_stream"
    assert result.tool_calls[0].name == "search_repo"
    assert result.tool_calls[0].arguments == '{"query":"async"}'


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


@pytest.mark.parametrize(
    "message",
    [
        "context_length_exceeded: too many tokens",
        "invalid_request_error: prompt is longer than the maximum context window",
        "400 Bad Request: token limit exceeded for this model",
    ],
)
def test_context_overflow_error_classification(message: str) -> None:
    assert is_context_overflow_error(ModelExecutionError(message)) is True


def test_context_overflow_error_classification_ignores_unrelated_errors() -> None:
    assert is_context_overflow_error(ModelExecutionError("network timeout")) is False


def test_create_default_openai_client_uses_official_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []
    created_kwargs: list[dict[str, object]] = []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeOfficialOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created.append(self)
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules, "openai", SimpleNamespace(OpenAI=FakeOfficialOpenAI)
    )

    client = create_official_openai_client()

    assert client is created[0]
    assert created_kwargs == [{}]


def test_create_default_openai_provider_resolves_discovered_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")

    provider = create_default_openai_provider()

    assert provider.config.api_key == "ambient-key"


def test_create_default_openai_provider_uses_chatgpt_codex_auth_when_only_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        '{"auth_mode": "chatgpt", "tokens": {"access_token": "secret-token"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    provider = create_default_openai_provider()

    assert provider.config.provider_name == "chatgpt-codex"
    assert provider.config.api_key is None
    assert "secret-token" not in repr(provider)


def test_create_default_async_openai_provider_resolves_discovered_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")

    provider = create_default_async_openai_provider()

    assert provider.config.api_key == "ambient-key"


def test_create_default_async_openai_provider_uses_chatgpt_codex_auth_when_preferred(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        '{"OPENAI_API_KEY": "codex-key", "tokens": {"access_token": "secret-token"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    provider = create_default_async_openai_provider(
        OpenAIProviderConfig(codex_auth_preference="chatgpt_first")
    )

    assert provider.config.provider_name == "chatgpt-codex"
    assert provider.config.api_key is None
    assert "secret-token" not in repr(provider)


def test_create_default_openai_provider_discovery_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")

    provider = create_default_openai_provider(
        OpenAIProviderConfig(discover_default_auth=False)
    )

    assert provider.config.api_key is None


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

    client = create_official_openai_client(
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


def test_adapter_lazy_default_provider_uses_discovered_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")
    monkeypatch.setitem(
        sys.modules, "litellm", SimpleNamespace(completion=lambda **kwargs: kwargs)
    )

    adapter = OpenAIClientAdapter()

    assert adapter.client is not None
    assert adapter._provider.config.api_key == "ambient-key"


def test_adapter_lazy_default_provider_uses_discovered_chatgpt_codex_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    created_kwargs: list[dict[str, object]] = []
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        '{"auth_mode": "chatgpt", "tokens": {"access_token": "secret-token"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    class FakeOfficialOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules, "openai", SimpleNamespace(OpenAI=FakeOfficialOpenAI)
    )

    adapter = OpenAIClientAdapter()

    assert adapter.client is not None
    assert created_kwargs == [
        {
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": "secret-token",
        }
    ]


def test_create_default_openai_client_omits_api_key_when_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_kwargs: list[dict[str, object]] = []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeOfficialOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules, "openai", SimpleNamespace(OpenAI=FakeOfficialOpenAI)
    )

    create_official_openai_client(
        OpenAIProviderConfig(base_url="http://localhost:11434/v1", api_key=None)
    )

    assert created_kwargs == [{"base_url": "http://localhost:11434/v1"}]


def test_create_default_async_openai_client_uses_official_async_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeOfficialAsyncOpenAI:
        def __init__(self) -> None:
            created.append(self)

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(AsyncOpenAI=FakeOfficialAsyncOpenAI),
    )

    client = create_official_async_openai_client()

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

    client = create_official_async_openai_client(
        OpenAIProviderConfig(base_url="http://localhost:11434/v1", api_key="test-key")
    )

    assert created_kwargs == [
        {"base_url": "http://localhost:11434/v1", "api_key": "test-key"}
    ]
    assert client is not None


def test_async_adapter_lazy_default_provider_uses_discovered_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")

    async def acompletion(**kwargs: object) -> object:
        return kwargs

    monkeypatch.setitem(
        sys.modules, "litellm", SimpleNamespace(acompletion=acompletion)
    )

    adapter = AsyncOpenAIClientAdapter()

    assert adapter.client is not None
    assert adapter._provider.config.api_key == "ambient-key"


def test_async_adapter_lazy_default_provider_uses_discovered_chatgpt_codex_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    created_kwargs: list[dict[str, object]] = []
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        '{"auth_mode": "chatgpt", "tokens": {"access_token": "secret-token"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    class FakeOfficialAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(AsyncOpenAI=FakeOfficialAsyncOpenAI),
    )

    adapter = AsyncOpenAIClientAdapter()

    assert adapter.client is not None
    assert created_kwargs == [
        {
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": "secret-token",
        }
    ]


def test_create_default_async_openai_client_omits_api_key_when_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_kwargs: list[dict[str, object]] = []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeOfficialAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(AsyncOpenAI=FakeOfficialAsyncOpenAI),
    )

    create_official_async_openai_client(
        OpenAIProviderConfig(base_url="http://localhost:11434/v1", api_key=None)
    )

    assert created_kwargs == [{"base_url": "http://localhost:11434/v1"}]


def test_create_default_openai_client_uses_litellm_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sys.modules, "litellm", SimpleNamespace(completion=lambda: None)
    )

    client = create_default_openai_client()

    assert hasattr(client, "responses")


def test_create_default_async_openai_client_uses_litellm_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sys.modules, "litellm", SimpleNamespace(acompletion=lambda: None)
    )

    client = create_default_async_openai_client()

    assert hasattr(client, "responses")


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


def test_build_openai_request_keeps_adapter_context_out_of_extra() -> None:
    """Adapter-only context must not be model request extra data."""

    context = object()

    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
        adapter_context=context,
    )

    assert request.adapter_context is context
    assert "adapter_context" not in request.extra
    assert request.to_kwargs() == {
        "model": "gpt-test",
        "input": [{"role": "user", "content": "Hello"}],
    }
