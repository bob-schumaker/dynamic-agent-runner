from __future__ import annotations

import asyncio
from dataclasses import replace
import time

import pytest

from dynamic_agent_runner.external_adapter import (
    ExternalAdapterUnavailableError,
    ExternalAdapterValidationError,
    ExternalModelAdapterFacade,
)
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.executor import execute_workflow
from dynamic_agent_runner.models import LoadedAgentWorkflow, ToolDefinition
from dynamic_agent_runner.openai_client import (
    ModelResponse,
    ModelToolCall,
    OpenAIModelRequest,
)
from dynamic_agent_runner.openai_compatible_external import (
    OpenAICompatibleExternalConfig,
    OpenAICompatibleExternalAdapter,
    create_async_openai_compatible_external_adapter,
    create_openai_compatible_external_adapter,
    validate_external_base_url,
)
from dynamic_agent_runner.registry import InMemoryToolRegistry, RegisteredTool
import dynamic_agent_runner.openai_compatible_external as external_module


def _config(**overrides: object) -> OpenAICompatibleExternalConfig:
    values: dict[str, object] = {
        "adapter_id": "external.test",
        "base_url": "http://127.0.0.1:8080/v1",
        "model_alias": "friendly-model",
        "service_model_id": "service-model",
        "canonical_model_id": "provider/service-model",
    }
    values.update(overrides)
    return OpenAICompatibleExternalConfig(**values)


def _request(**overrides: object) -> OpenAIModelRequest:
    request = OpenAIModelRequest(
        model="friendly-model",
        messages=({"role": "user", "content": "hello"},),
    )
    return replace(request, **overrides)


class SyncTransport:
    def __init__(self, inventory: tuple[str, ...] = ("service-model",)) -> None:
        self.inventory = inventory
        self.requests: list[OpenAIModelRequest] = []

    def list_models(self, *, timeout_seconds: float) -> tuple[str, ...]:
        assert timeout_seconds == 30
        return self.inventory

    def create_response(
        self, request: OpenAIModelRequest, **_: object
    ) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(content='{"ok":true}')


class BlockingHealthTransport(SyncTransport):
    def list_models(self, *, timeout_seconds: float) -> tuple[str, ...]:
        del timeout_seconds
        time.sleep(0.2)
        return self.inventory


class AsyncTransport:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def create_response(
        self, request: OpenAIModelRequest, **_: object
    ) -> ModelResponse:
        del request
        self.started.set()
        await asyncio.sleep(10)
        return ModelResponse(content="late")


def test_config_hides_key_and_rejects_invalid_timeout() -> None:
    config = _config()
    assert "secret" not in repr(config)
    with pytest.raises(ExternalAdapterValidationError):
        _config(timeout_seconds=0)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "ftp://127.0.0.1/v1",
        "http://127.0.0.1/v1?x=1",
        "http://user:pass@127.0.0.1/v1",
    ],
)
def test_url_policy_rejects_unsafe_endpoints(url: str) -> None:
    with pytest.raises(ExternalAdapterValidationError):
        validate_external_base_url(url)


def test_url_policy_accepts_https_and_loopback_http() -> None:
    assert (
        validate_external_base_url("https://example.com/v1/")
        == "https://example.com/v1"
    )
    assert validate_external_base_url("http://[::1]:8080/v1") == "http://[::1]:8080/v1"


def test_health_requires_exact_service_model_and_generation_uses_service_id() -> None:
    transport = SyncTransport()
    adapter = OpenAICompatibleExternalAdapter(_config(), None, transport)
    facade = ExternalModelAdapterFacade(adapter)
    assert facade.create_response(_request()).content == '{"ok":true}'
    assert transport.requests[0].model == "service-model"

    unavailable = OpenAICompatibleExternalAdapter(
        _config(), None, SyncTransport(("other-model",))
    )
    with pytest.raises(ExternalAdapterUnavailableError):
        ExternalModelAdapterFacade(unavailable).create_response(_request())


def test_default_factory_uses_explicit_transport_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configs: list[object] = []

    def make_client(config: object) -> object:
        configs.append(config)
        return object()

    monkeypatch.setattr(external_module, "create_official_openai_client", make_client)
    create_openai_compatible_external_adapter(_config(), api_key=None)
    assert len(configs) == 1
    config = configs[0]
    assert config.discover_default_auth is False
    assert config.trust_env is False
    assert config.follow_redirects is False
    assert config.suppress_auth_header is True
    assert config.timeout_seconds == 30


def test_service_wire_request_preserves_order_and_tool_choice() -> None:
    transport = SyncTransport()
    adapter = OpenAICompatibleExternalAdapter(
        _config(tool_calling=True), None, transport
    )
    request = _request(
        messages=(
            {"role": "system", "content": "one"},
            {"role": "user", "content": "two"},
        ),
        tools=({"type": "function", "function": {"name": "search_repo"}},),
        tool_choice="auto",
    )
    ExternalModelAdapterFacade(adapter).create_response(request)
    sent = transport.requests[0]
    assert sent.model == "service-model"
    assert sent.messages == request.messages
    assert sent.tool_choice == "auto"
    assert sent.tools == request.tools


def test_malformed_transport_response_fails_closed() -> None:
    class BadTransport(SyncTransport):
        def create_response(self, request: OpenAIModelRequest, **_: object) -> object:
            del request
            return object()

    with pytest.raises(ExternalAdapterValidationError):
        ExternalModelAdapterFacade(
            OpenAICompatibleExternalAdapter(_config(), None, BadTransport())
        ).create_response(_request())


def test_health_timeout_discards_late_blocking_probe() -> None:
    adapter = OpenAICompatibleExternalAdapter(
        _config(timeout_seconds=0.05), None, BlockingHealthTransport()
    )
    started = time.monotonic()
    with pytest.raises(ExternalAdapterUnavailableError):
        ExternalModelAdapterFacade(adapter).create_response(_request())
    assert time.monotonic() - started < 0.15


def test_async_adapter_cancellation_uses_separate_sync_health_probe() -> None:
    async def run() -> None:
        transport = AsyncTransport()
        health = SyncTransport()
        adapter = create_async_openai_compatible_external_adapter(
            _config(), transport=transport, health_transport=health
        )
        facade = ExternalModelAdapterFacade(adapter)
        task = asyncio.create_task(facade.create_response_async(_request()))
        await transport.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())


def test_external_adapter_tool_call_reenters_executor_once() -> None:
    class LoopTransport(SyncTransport):
        def __init__(self) -> None:
            super().__init__()
            self.responses = [
                ModelResponse(
                    content=None,
                    tool_calls=(
                        ModelToolCall("call-1", "search_repo", '{"query":"agents"}'),
                    ),
                ),
                ModelResponse(content="final answer"),
            ]

        def create_response(
            self, request: OpenAIModelRequest, **_: object
        ) -> ModelResponse:
            self.requests.append(request)
            return self.responses.pop(0)

    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "external-tool-loop",
                "entrypoint": "analyze",
                "packaging": {"mode": "hybrid_bundle"},
                "runtime": {
                    "execution_policy": {
                        "model": "friendly-model",
                        "tool_use_completion": {
                            "run_again": "required",
                            "stop_on_tool": "disabled",
                            "final_output": "default",
                        },
                    }
                },
                "nodes": [
                    {
                        "id": "analyze",
                        "kind": "llm_step",
                        "prompt": {"user_template": "Question: {prompt}"},
                        "available_tools": ["search_repo"],
                    }
                ],
                "edges": [],
                "tools": [{"id": "search_repo"}],
            }
        )
    )
    calls: list[object] = []
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {
                        "id": "search_repo",
                        "description_for_llm": "Search",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    }
                ),
                lambda arguments: calls.append(arguments) or {"answer": "42"},
            )
        ]
    )
    transport = LoopTransport()
    adapter = OpenAICompatibleExternalAdapter(
        _config(tool_calling=True), None, transport
    )
    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )
    assert result.final_result == "final answer"
    assert calls == [{"query": "agents"}]
    assert len(transport.requests) == 2
