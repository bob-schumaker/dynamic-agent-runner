from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from dynamic_agent_runner import (
    CancellationHandle,
    DARExternalAdapterProtocol,
    DARExternalRequestContext,
    ExternalAdapterError,
    ExternalModelAdapterDescriptor,
    ExternalModelAdapterHealth,
    ModelResponse,
    ModelToolCall,
    OpenAIModelRequest,
)
from dynamic_agent_runner.errors import WorkflowExecutionError
from dynamic_agent_runner.external_adapter import (
    ExternalModelAdapterFacade,
    canonical_descriptor_digest,
)
from dynamic_agent_runner.executor import (
    _normalize_model_adapters,
    _select_model_and_adapter,
)


class FakeCancellation:
    def __init__(self, cancelled: bool = False) -> None:
        self._cancelled = cancelled

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise asyncio.CancelledError


def descriptor(**overrides: object) -> ExternalModelAdapterDescriptor:
    values: dict[str, object] = {
        "adapter_id": "test.external",
        "provider_id": "test",
        "protocol_id": "dar.external-model.v1",
        "protocol_version": "1.0",
        "model_alias": "test-model",
        "canonical_model_id": "test-canonical",
        "execution_location": "local",
        "execution_modes": frozenset({"sync", "async"}),
        "input_modalities": frozenset({"text"}),
        "output_modalities": frozenset({"text"}),
        "response_formats": frozenset({"text", "json_schema"}),
        "capabilities": frozenset({"text_generation", "structured_output"}),
        "limits": {"max_context_tokens": 4096, "max_output_tokens": 512},
        "contract_digest": "",
    }
    values.update(overrides)
    provisional = object.__new__(ExternalModelAdapterDescriptor)
    for key, value in values.items():
        object.__setattr__(provisional, key, value)
    values["contract_digest"] = canonical_descriptor_digest(provisional)
    return ExternalModelAdapterDescriptor(**values)


class FakeExternalAdapter:
    adapter_id = "test.external"
    protocol_id = "dar.external-model.v1"
    protocol_version = "1.0"

    def __init__(self, response: ModelResponse | None = None) -> None:
        self.descriptor = descriptor()
        self.response = response or ModelResponse(content="ok")
        self.requests: list[OpenAIModelRequest] = []

    def describe(self) -> ExternalModelAdapterDescriptor:
        return self.descriptor

    def health(self) -> ExternalModelAdapterHealth:
        return ExternalModelAdapterHealth(status="ready")

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        self.requests.append(request)
        return self.response


class AsyncExternalAdapter(FakeExternalAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.adapter_id = "test.async"
        self.descriptor = descriptor(
            adapter_id="test.async",
            model_alias="test-async",
            canonical_model_id="test-async-canonical",
            execution_modes=frozenset({"async"}),
        )

    async def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        self.requests.append(request)
        await asyncio.sleep(0)
        return self.response


def test_public_protocol_and_descriptor_are_exported() -> None:
    assert DARExternalAdapterProtocol is not None
    assert CancellationHandle is not None
    assert DARExternalRequestContext is not None
    assert ExternalModelAdapterHealth(status="ready").status == "ready"


def test_descriptor_digest_is_deterministic_and_excludes_digest_field() -> None:
    first = descriptor()
    second = object.__new__(ExternalModelAdapterDescriptor)
    for field_name, value in first.__dict__.items():
        object.__setattr__(second, field_name, value)
    object.__setattr__(second, "contract_digest", "different")
    assert canonical_descriptor_digest(first) == canonical_descriptor_digest(second)
    assert first.contract_digest == canonical_descriptor_digest(first)


def test_descriptor_freezes_limits() -> None:
    limits = {"max_output_tokens": 512}
    value = descriptor(limits=limits)
    limits["max_output_tokens"] = 1
    assert value.limits["max_output_tokens"] == 512
    with pytest.raises(TypeError):
        value.limits["max_output_tokens"] = 1  # type: ignore[index]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocol_id", "wrong.protocol"),
        ("protocol_version", "2.0"),
        ("input_modalities", frozenset({"image"})),
        ("output_modalities", frozenset({"audio"})),
        ("execution_modes", frozenset()),
        ("limits", {"max_output_tokens": -1}),
    ],
)
def test_descriptor_rejects_invalid_v1_values(field: str, value: object) -> None:
    values = descriptor().__dict__
    values[field] = value
    values["contract_digest"] = "invalid"
    with pytest.raises(ExternalAdapterError):
        ExternalModelAdapterDescriptor(**values)


def test_facade_injects_only_dar_context_and_normalizes_response() -> None:
    adapter = FakeExternalAdapter(
        ModelResponse(
            content='{"answer": "ok"}',
            raw={"secret": "must disappear"},
            metadata={"safe": "yes", "secret": "no"},
        )
    )
    facade = ExternalModelAdapterFacade(adapter)
    request = OpenAIModelRequest(
        model="test-model",
        messages=({"role": "user", "content": "hello"},),
    )

    result = facade.create_response(request)

    assert result.raw is None
    assert result.metadata == {"safe": "yes"}
    assert adapter.requests[0].adapter_context is not None
    assert isinstance(adapter.requests[0].adapter_context, DARExternalRequestContext)
    assert not hasattr(adapter.requests[0].adapter_context, "tool_registry")
    assert not hasattr(adapter.requests[0].adapter_context, "approval")


def test_facade_rejects_model_mismatch_before_external_dispatch() -> None:
    adapter = FakeExternalAdapter()
    facade = ExternalModelAdapterFacade(adapter)
    request = OpenAIModelRequest(
        model="other-model",
        messages=({"role": "user", "content": "hello"},),
    )
    with pytest.raises(ExternalAdapterError):
        facade.create_response(request)
    assert adapter.requests == []


def test_facade_rejects_streaming_and_persistent_modes() -> None:
    facade = ExternalModelAdapterFacade(FakeExternalAdapter())
    for key in ("stream", "persistent_session", "native_callback"):
        request = OpenAIModelRequest(
            model="test-model",
            messages=({"role": "user", "content": "hello"},),
            extra={key: True},
        )
        with pytest.raises(ExternalAdapterError):
            facade.create_response(request)


def test_structured_response_is_validated_and_canonicalized() -> None:
    adapter = FakeExternalAdapter(ModelResponse(content='{"b": 2, "a": 1}'))
    facade = ExternalModelAdapterFacade(adapter)
    request = OpenAIModelRequest(
        model="test-model",
        messages=({"role": "user", "content": "hello"},),
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "answer",
                "schema": {
                    "type": "object",
                    "required": ["a", "b"],
                },
            },
        },
    )
    result = facade.create_response(request)
    assert result.content == '{"a":1,"b":2}'


def test_tool_call_is_preserved_without_handler_access() -> None:
    call = ModelToolCall(id="call-1", name="tool", arguments=json.dumps({}))
    adapter = FakeExternalAdapter(ModelResponse(content=None, tool_calls=(call,)))
    adapter.descriptor = descriptor(
        capabilities=frozenset({"text_generation", "structured_output", "tool_calling"})
    )
    facade = ExternalModelAdapterFacade(adapter)
    result = facade.create_response(
        OpenAIModelRequest(
            model="test-model",
            messages=({"role": "user", "content": "hello"},),
            tools=({"type": "function", "name": "tool"},),
        )
    )
    assert result.tool_calls == (call,)
    assert not hasattr(adapter.requests[0].adapter_context, "handler")


def test_raw_external_adapter_is_normalized_elementwise() -> None:
    adapter = FakeExternalAdapter()
    legacy = object()
    normalized = _normalize_model_adapters((adapter,))
    assert isinstance(normalized[0], ExternalModelAdapterFacade)
    assert normalized[0].models == ("test-model",)
    second = FakeExternalAdapter()
    second.adapter_id = "test.external.2"
    second.descriptor = descriptor(
        adapter_id="test.external.2",
        model_alias="test-model-2",
        canonical_model_id="test-canonical-2",
    )
    mixed = _normalize_model_adapters((adapter, second))
    assert len(mixed) == 2
    with pytest.raises(WorkflowExecutionError):
        _normalize_model_adapters((legacy,))


def test_async_only_adapter_stays_async_and_rejects_sync_facade_calls() -> None:
    adapter = AsyncExternalAdapter()
    facade = ExternalModelAdapterFacade(adapter)
    request = OpenAIModelRequest(
        model="test-async",
        messages=({"role": "user", "content": "hello"},),
    )
    with pytest.raises(ExternalAdapterError):
        facade.create_response(request)
    result = asyncio.run(facade.create_response_async(request))
    assert result.content == "ok"


def test_external_selection_resolves_omitted_model_and_never_falls_back() -> None:
    adapter = FakeExternalAdapter()
    facade = ExternalModelAdapterFacade(adapter)
    omitted = SimpleNamespace(id="node-1", model=None, model_requirements={}, raw={})
    selected_model, selected_adapter = _select_model_and_adapter(
        omitted, (facade,), {}, model_adapter_coverage="augmented"
    )
    assert selected_model == "test-model"
    assert selected_adapter is facade

    mismatched = SimpleNamespace(
        id="node-2", model="gpt-5", model_requirements={}, raw={}
    )
    with pytest.raises(WorkflowExecutionError):
        _select_model_and_adapter(
            mismatched, (facade,), {}, model_adapter_coverage="augmented"
        )


def test_dispatch_tokens_are_private_single_use_and_reject_replay() -> None:
    facade = ExternalModelAdapterFacade(FakeExternalAdapter())
    request = OpenAIModelRequest(
        model="test-model",
        messages=({"role": "user", "content": "hello"},),
    )
    prepared = facade._prepare_request(request)  # type: ignore[attr-defined]
    token = facade._issue_dispatch_token(prepared, "sync")  # type: ignore[attr-defined]
    facade._consume_dispatch_token(token.token_id, prepared, "sync")  # type: ignore[attr-defined]
    with pytest.raises(ExternalAdapterError):
        facade._consume_dispatch_token(token.token_id, prepared, "sync")  # type: ignore[attr-defined]
