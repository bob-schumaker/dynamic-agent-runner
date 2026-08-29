"""Focused tests for macOS MLX local-model adapter helpers."""

from __future__ import annotations

import asyncio
import builtins
from dataclasses import replace
from pathlib import Path

import pytest

from dynamic_agent_runner import MLXToolCallCandidate, MLXToolCodecResponse
from dynamic_agent_runner.errors import ModelExecutionError, WorkflowExecutionError
from dynamic_agent_runner.executor import (
    _model_tool_result_messages,
    execute_workflow,
    execute_workflow_async,
)
from dynamic_agent_runner.openai_client import OpenAIModelRequest
from dynamic_agent_runner.registry import ToolResult
from dynamic_agent_runner.tracing import InMemoryTraceSink
from parity_support import (
    install_parity_io_blocker,
    parity_exposed_schemas,
    parity_contract_projection,
    parity_loop_workflow,
    parity_no_tool_workflow,
    parity_record,
    parity_registry,
)


class FakeMLXBackend:
    def __init__(
        self,
        content: str = "local answer",
        *,
        model_id: str | None = None,
    ) -> None:
        self.content = content
        self.model_id = model_id
        self.requests: list[OpenAIModelRequest] = []

    def generate(self, request: OpenAIModelRequest) -> str:
        self.requests.append(request)
        return self.content


class FakeMLXBackendWithKwargs:
    def __init__(self, content: str = "local answer") -> None:
        self.content = content
        self.calls: list[tuple[OpenAIModelRequest, dict[str, object]]] = []

    def generate(self, request: OpenAIModelRequest, **kwargs: object) -> str:
        self.calls.append((request, dict(kwargs)))
        return self.content


class FakeToolCapableMLXBackend(FakeMLXBackend):
    tool_codec_versions = frozenset({"test-v1"})

    def __init__(self, generated: str) -> None:
        super().__init__()
        self.generated = generated
        self.rendered_prompts: list[str] = []

    def generate_rendered(self, prompt: str, **kwargs: object) -> str:
        self.rendered_prompts.append(prompt)
        return self.generated


class SequencedToolCapableMLXBackend(FakeToolCapableMLXBackend):
    def __init__(self, generated: list[str]) -> None:
        super().__init__("")
        self.generated = list(generated)

    def generate_rendered(self, prompt: str, **kwargs: object) -> str:
        self.rendered_prompts.append(prompt)
        return self.generated.pop(0)


class FakeMLXToolCodec:
    version = "test-v1"

    def __init__(self, *decoded: MLXToolCodecResponse) -> None:
        self.decoded = list(decoded)
        self.rendered_requests: list[OpenAIModelRequest] = []
        self.generated: list[str] = []

    def render(self, request: OpenAIModelRequest) -> str:
        self.rendered_requests.append(request)
        return "<tool-aware-prompt>"

    def decode(self, generated: str) -> MLXToolCodecResponse:
        self.generated.append(generated)
        return self.decoded.pop(0)


class _RecordingMLXAdapter:
    def __init__(self, adapter: object, observed: list[object]) -> None:
        self._adapter = adapter
        self._observed = observed
        self.requests: list[object] = []

    @property
    def models(self) -> tuple[str, ...]:
        return self._adapter.models

    def create_response(self, request: object) -> object:
        self.requests.append(request)
        response = self._adapter.create_response(request)
        self._observed.extend(response.tool_calls)
        return response


class _AsyncRecordingMLXAdapter:
    def __init__(self, adapter: object, observed: list[object]) -> None:
        self._adapter = adapter
        self._observed = observed
        self.requests: list[object] = []

    @property
    def models(self) -> tuple[str, ...]:
        return self._adapter.models

    async def create_response(self, request: object) -> object:
        self.requests.append(request)
        response = await self._adapter.create_response(request)
        self._observed.extend(response.tool_calls)
        return response


def _mlx_parity_responses(scenario: str) -> list[MLXToolCodecResponse]:
    call = MLXToolCallCandidate
    text = MLXToolCodecResponse
    scenarios = {
        "S1": [
            text(
                tool_call=call("create_record", '{"title":"DAR","body":"controlled"}')
            ),
            text(content="created"),
        ],
        "S2": [
            text(
                tool_call=call(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase"}',
                )
            ),
            text(content="transformed"),
        ],
        "S2-invalid": [
            text(tool_call=call("transform_record", '{"record_id":"record-seed"}'))
        ],
        "S2-wrong-type": [
            text(
                tool_call=call(
                    "transform_record", '{"record_id":1,"operation":"uppercase"}'
                )
            )
        ],
        "S2-invalid-enum": [
            text(
                tool_call=call(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"lowercase"}',
                )
            )
        ],
        "S2-unknown": [
            text(
                tool_call=call(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase","unknown":true}',
                )
            )
        ],
        "S2-malformed": [text(tool_call=call("transform_record", "not-json"))],
        "S3": [
            text(tool_call=call("lookup_record", '{"key":"seed"}')),
            text(
                tool_call=call(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase"}',
                )
            ),
            text(content="SEED"),
        ],
        "S4": [text(tool_call=call("fail_controlled", '{"code":"planned"}'))],
        "S5": [text(content="no tool")],
        "S6": [text(tool_call=call("lookup_record", "not-json"))],
    }
    return scenarios[scenario]


def _run_mlx_parity(
    scenario: str,
    *,
    asynchronous: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from dynamic_agent_runner import (
        MLXLocalModelConfig,
        create_mlx_local_adapter,
        create_mlx_local_async_adapter,
    )
    import dynamic_agent_runner.mlx_models as mlx_models

    model_path = tmp_path / f"inert-mlx-layout-{asynchronous}"
    write_converted_mlx_model(model_path)
    forbidden_calls: list[object] = []

    def forbidden(*args: object, **kwargs: object) -> object:
        forbidden_calls.append((args, kwargs))
        raise AssertionError("parity tests must not load or download MLX")

    real_import = builtins.__import__

    def forbid_mlx_import(
        name: str,
        globals_: object | None = None,
        locals_: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "mlx_lm":
            raise AssertionError("parity tests must not import mlx_lm")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", forbid_mlx_import)
    monkeypatch.setattr(mlx_models, "_load_default_mlx_lm_backend", forbidden)
    responses = _mlx_parity_responses(scenario)
    backend = SequencedToolCapableMLXBackend(
        [f"native-{index}" for index in range(len(responses))]
    )
    codec = FakeMLXToolCodec(*responses)
    factory = (
        create_mlx_local_async_adapter if asynchronous else create_mlx_local_adapter
    )
    adapter = factory(
        MLXLocalModelConfig(model_aliases=("gpt-test",), model_path=model_path),
        backend=backend,
        dependency_loader=forbidden,
        download_file=forbidden,
        download_snapshot=forbidden,
        tool_codec=codec,
        platform_system=lambda: "Darwin",
    )
    observed: list[object] = []
    recorder = (
        _AsyncRecordingMLXAdapter(adapter, observed)
        if asynchronous
        else _RecordingMLXAdapter(adapter, observed)
    )
    registry, invocations, results = parity_registry()
    sink = InMemoryTraceSink()
    error = None
    result = None
    try:
        workflow = (
            parity_no_tool_workflow() if scenario == "S5" else parity_loop_workflow()
        )
        if asynchronous:
            result = asyncio.run(
                execute_workflow_async(
                    workflow,
                    prompt="controlled parity",
                    tool_registry=registry,
                    model_adapter=recorder,
                    trace_sink=sink,
                )
            )
        else:
            result = execute_workflow(
                workflow,
                prompt="controlled parity",
                tool_registry=registry,
                model_adapter=recorder,
                trace_sink=sink,
            )
    except Exception as caught:
        error = caught
    assert forbidden_calls == []
    assert backend.requests == []
    return (
        result,
        parity_record(
            interface="mlx_injected_codec_backend",
            scenario=scenario,
            asynchronous=asynchronous,
            normalized_calls=tuple((call.name, call.arguments) for call in observed),
            exposed_schemas=parity_exposed_schemas(recorder.requests[0].tools),
            invocations=invocations,
            results=results,
            result=result,
            error=error,
            sink=sink,
        ),
        error,
        codec,
        backend,
    )


def _assert_mlx_parity_scenario(
    *,
    scenario: str,
    invoked: tuple[str, ...],
    fails: bool,
    result: object | None,
    record: object,
    error: Exception | None,
    codec: FakeMLXToolCodec,
    backend: SequencedToolCapableMLXBackend,
) -> None:
    assert tuple(name for name, _ in record.invocations) == invoked
    assert (error is not None) is fails
    assert (result is None) is fails
    if fails:
        assert isinstance(error, WorkflowExecutionError | ModelExecutionError)
        assert record.error_class in {"WorkflowExecutionError", "ModelExecutionError"}
    if scenario in {
        "S2-invalid",
        "S2-wrong-type",
        "S2-invalid-enum",
        "S2-unknown",
    }:
        assert isinstance(error, WorkflowExecutionError)
        assert record.error_class == "WorkflowExecutionError"
        assert record.trace_event_types.count("model_tool_loop_tool_call") == 1
    if scenario == "S2-malformed":
        assert isinstance(error, ModelExecutionError)
        assert record.error_class == "ModelExecutionError"
        assert "model_tool_loop_tool_call" not in record.trace_event_types
    if scenario == "S1":
        assert result is not None
        assert result.final_result == "created"
        assert record.normalized_calls == (
            ("create_record", '{"body":"controlled","title":"DAR"}'),
        )
    if scenario == "S3":
        assert len(codec.rendered_requests) == len(backend.rendered_prompts) == 3
        assert "record-seed" in str(codec.rendered_requests[1])
    if scenario == "S4":
        assert len(codec.rendered_requests) == len(backend.rendered_prompts) == 1
        assert record.stop_reasons == ("tool_failure",)
        assert isinstance(error, WorkflowExecutionError)
        assert "planned controlled failure" in str(error)
        assert record.trace_event_types.count("model_tool_loop_tool_call") == 1
    if scenario == "S6":
        assert len(codec.rendered_requests) == len(backend.rendered_prompts) == 1
        assert "tool_started" not in record.trace_event_types
        assert "model_tool_loop_tool_call" not in record.trace_event_types


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    ("scenario", "invoked", "fails"),
    [
        ("S1", ("create_record",), False),
        ("S2", ("transform_record",), False),
        ("S2-invalid", (), True),
        ("S2-wrong-type", (), True),
        ("S2-invalid-enum", (), True),
        ("S2-unknown", (), True),
        ("S2-malformed", (), True),
        ("S3", ("lookup_record", "transform_record"), False),
        ("S4", ("fail_controlled",), True),
        ("S5", (), False),
        ("S6", (), True),
    ],
)
def test_model_interface_parity_mlx_injected_pair_native_scenarios(
    scenario: str,
    invoked: tuple[str, ...],
    fails: bool,
    asynchronous: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_parity_io_blocker(monkeypatch)
    result, record, error, codec, backend = _run_mlx_parity(
        scenario,
        asynchronous=asynchronous,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    _assert_mlx_parity_scenario(
        scenario=scenario,
        invoked=invoked,
        fails=fails,
        result=result,
        record=record,
        error=error,
        codec=codec,
        backend=backend,
    )
    if not asynchronous:
        _, async_record, _, _, _ = _run_mlx_parity(
            scenario,
            asynchronous=True,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
        )
        assert parity_contract_projection(record) == parity_contract_projection(
            async_record
        )


@pytest.mark.parametrize("asynchronous", [False, True])
def test_model_interface_parity_stock_mlx_rejects_tools_before_dispatch(
    asynchronous: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner import (
        MLXLocalModelConfig,
        create_mlx_local_adapter,
        create_mlx_local_async_adapter,
    )
    import dynamic_agent_runner.mlx_models as mlx_models

    install_parity_io_blocker(monkeypatch)
    forbidden_calls: list[object] = []
    generation_calls: list[object] = []

    def forbidden(*args: object, **kwargs: object) -> object:
        forbidden_calls.append((args, kwargs))
        raise AssertionError("stock MLX parity must not load or download")

    def forbidden_generate(*args: object, **kwargs: object) -> object:
        generation_calls.append((args, kwargs))
        raise AssertionError("stock MLX parity must not generate")

    real_import = builtins.__import__

    def forbid_mlx_import(
        name: str,
        globals_: object | None = None,
        locals_: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "mlx_lm":
            raise AssertionError("stock MLX tool rejection must not import mlx_lm")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", forbid_mlx_import)
    monkeypatch.setattr(mlx_models, "_load_default_mlx_lm_backend", forbidden)
    monkeypatch.setattr(mlx_models._MLXLMBackend, "generate", forbidden_generate)
    stock_backend = mlx_models._MLXLMBackend(model=object(), tokenizer=object())
    codec = FakeMLXToolCodec(MLXToolCodecResponse(content="must not decode"))
    factory = (
        create_mlx_local_async_adapter if asynchronous else create_mlx_local_adapter
    )
    adapter = factory(
        MLXLocalModelConfig(
            model_aliases=("gpt-test",),
            model_path=tmp_path / "missing-stock-layout",
        ),
        backend=stock_backend,
        dependency_loader=forbidden,
        download_file=forbidden,
        download_snapshot=forbidden,
        tool_codec=codec,
        platform_system=lambda: "Darwin",
    )
    registry, invocations, _ = parity_registry()
    sink = InMemoryTraceSink()

    assert adapter.capabilities["tool_calling"] is False
    with pytest.raises(ModelExecutionError, match="does not support tool"):
        if asynchronous:
            asyncio.run(
                execute_workflow_async(
                    parity_loop_workflow(),
                    prompt="controlled parity",
                    tool_registry=registry,
                    model_adapter=adapter,
                    trace_sink=sink,
                )
            )
        else:
            execute_workflow(
                parity_loop_workflow(),
                prompt="controlled parity",
                tool_registry=registry,
                model_adapter=adapter,
                trace_sink=sink,
            )

    assert codec.rendered_requests == []
    assert codec.generated == []
    assert generation_calls == []
    assert forbidden_calls == []
    assert invocations == []
    assert not [
        event
        for event in sink.events
        if event.event_type in {"tool_started", "model_tool_loop_tool_call"}
    ]


def make_request(
    *,
    tools: tuple[dict[str, object], ...] = (),
    response_format: dict[str, object] | None = None,
) -> OpenAIModelRequest:
    return OpenAIModelRequest(
        model="mlx-local-chat",
        messages=({"role": "user", "content": "Hello"},),
        tools=tools,
        response_format=response_format,
    )


def tool_request() -> OpenAIModelRequest:
    return make_request(
        tools=(
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Look up a value.",
                    "parameters": {"type": "object"},
                },
            },
        )
    )


def test_mlx_adapter_uses_compatible_codec_for_tool_text_response(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    backend = FakeToolCapableMLXBackend("native text")
    codec = FakeMLXToolCodec(MLXToolCodecResponse(content="decoded text"))
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=backend,
        tool_codec=codec,
        platform_system=lambda: "Darwin",
    )

    request = tool_request()
    response = adapter.create_response(request)

    assert adapter.capabilities["tool_calling"] is True
    assert codec.rendered_requests == [request]
    assert backend.rendered_prompts == ["<tool-aware-prompt>"]
    assert codec.generated == ["native text"]
    assert response.content == "decoded text"
    assert response.tool_calls == ()
    assert response.response_id is not None
    assert response.response_id.startswith("mlx-")


def test_mlx_adapter_normalizes_one_codec_tool_call_with_response_scoped_id(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=FakeToolCapableMLXBackend("native call"),
        tool_codec=FakeMLXToolCodec(
            MLXToolCodecResponse(
                tool_call=MLXToolCallCandidate(
                    name="lookup",
                    arguments='{"query":"DAR"}',
                )
            )
        ),
        platform_system=lambda: "Darwin",
    )

    response = adapter.create_response(tool_request())

    assert response.content is None
    assert response.response_id is not None
    assert response.tool_calls[0].name == "lookup"
    assert response.tool_calls[0].arguments == '{"query":"DAR"}'
    assert response.tool_calls[0].id == f"{response.response_id}:1"


def test_mlx_adapter_rejects_incompatible_tool_codec_before_generation(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    backend = FakeToolCapableMLXBackend("must not generate")
    codec = FakeMLXToolCodec(MLXToolCodecResponse(content="not used"))
    codec.version = "unsupported-v1"
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=backend,
        tool_codec=codec,
        platform_system=lambda: "Darwin",
    )

    assert adapter.capabilities["tool_calling"] is False
    with pytest.raises(ModelExecutionError, match="does not support tool"):
        adapter.create_response(tool_request())
    assert backend.rendered_prompts == []


def test_mlx_adapter_rejects_unpaired_codec_before_model_resolution(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    dependency_loader_called = False

    def dependency_loader() -> object:
        nonlocal dependency_loader_called
        dependency_loader_called = True
        raise AssertionError("tool codec must be paired before model loading")

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "missing-model",
        ),
        dependency_loader=dependency_loader,
        tool_codec=FakeMLXToolCodec(MLXToolCodecResponse(content="not used")),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(ModelExecutionError, match="does not support tool"):
        adapter.create_response(tool_request())
    assert dependency_loader_called is False


def test_async_mlx_adapter_uses_compatible_tool_codec(tmp_path: Path) -> None:
    from dynamic_agent_runner import (
        MLXLocalModelConfig,
        create_mlx_local_async_adapter,
    )

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    adapter = create_mlx_local_async_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=FakeToolCapableMLXBackend("native text"),
        tool_codec=FakeMLXToolCodec(MLXToolCodecResponse(content="decoded text")),
        platform_system=lambda: "Darwin",
    )

    response = asyncio.run(adapter.create_response(tool_request()))

    assert adapter.capabilities["tool_calling"] is True
    assert response.content == "decoded text"
    assert response.response_id is not None


@pytest.mark.parametrize("is_async", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("supplied_id", [None, "codec-call-id"])
def test_mlx_adapter_renders_canonical_tool_result_continuation(
    tmp_path: Path,
    *,
    is_async: bool,
    supplied_id: str | None,
) -> None:
    from dynamic_agent_runner import (
        MLXLocalModelConfig,
        create_mlx_local_adapter,
        create_mlx_local_async_adapter,
    )

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    backend = FakeToolCapableMLXBackend("native response")
    codec = FakeMLXToolCodec(
        MLXToolCodecResponse(
            tool_call=MLXToolCallCandidate(
                name="lookup",
                arguments='{"z":1,"a":2}',
                id=supplied_id,
            )
        ),
        MLXToolCodecResponse(content="final answer"),
    )
    factory = create_mlx_local_async_adapter if is_async else create_mlx_local_adapter
    adapter = factory(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=backend,
        tool_codec=codec,
        platform_system=lambda: "Darwin",
    )
    request = replace(
        tool_request(),
        messages=(
            {"role": "system", "content": "Use tools when needed."},
            {"role": "user", "content": "Look up DAR."},
        ),
        tool_choice="required",
    )

    if is_async:
        first = asyncio.run(adapter.create_response(request))
    else:
        first = adapter.create_response(request)

    tool_call = first.tool_calls[0]
    expected_id = supplied_id or f"{first.response_id}:1"
    assert tool_call.id == expected_id
    assert tool_call.arguments == '{"a":2,"z":1}'
    assistant_call, tool_result = _model_tool_result_messages(
        tool_call,
        expected_id,
        ToolResult(
            tool_id="lookup",
            success=True,
            output={"record": "DAR"},
        ),
    )
    continuation = replace(
        request,
        messages=(*request.messages, assistant_call, tool_result),
    )

    if is_async:
        second = asyncio.run(adapter.create_response(continuation))
    else:
        second = adapter.create_response(continuation)

    assert codec.rendered_requests == [request, continuation]
    assert backend.rendered_prompts == ["<tool-aware-prompt>"] * 2
    assert continuation.tools == request.tools
    assert continuation.tool_choice == "required"
    assert continuation.messages[-2] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": expected_id,
                "type": "function",
                "function": {
                    "name": "lookup",
                    "arguments": '{"a":2,"z":1}',
                },
            }
        ],
        "_dar_transcript_type": "model_tool_call",
        "call_id": expected_id,
        "name": "lookup",
        "arguments": '{"a":2,"z":1}',
    }
    assert continuation.messages[-1] == {
        "role": "tool",
        "tool_call_id": expected_id,
        "name": "lookup",
        "content": '{"record": "DAR"}',
        "_dar_transcript_type": "model_tool_result",
        "call_id": expected_id,
        "output": '{"record": "DAR"}',
    }
    assert second.content == "final answer"
    assert second.tool_calls == ()


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (
            MLXToolCallCandidate(name="lookup", arguments="{not json}"),
            "valid JSON",
        ),
        (
            MLXToolCallCandidate(name="lookup", arguments='{"query":NaN}'),
            "non-finite",
        ),
        (
            MLXToolCallCandidate(name="lookup", arguments='{"a":1,"a":2}'),
            "duplicate",
        ),
        (MLXToolCallCandidate(name="lookup", arguments="[]"), "JSON object"),
        (MLXToolCallCandidate(name="unknown", arguments="{}"), "unavailable"),
    ],
)
def test_mlx_adapter_rejects_invalid_codec_tool_candidates(
    tmp_path: Path,
    candidate: MLXToolCallCandidate,
    message: str,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=FakeToolCapableMLXBackend("native call"),
        tool_codec=FakeMLXToolCodec(MLXToolCodecResponse(tool_call=candidate)),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(ModelExecutionError, match=message):
        adapter.create_response(tool_request())


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            '{"nested":' + "[" * 33 + "0" + "]" * 33 + "}",
            "nesting limit",
        ),
        (
            "{" + ",".join(f'"key{index}":{index}' for index in range(257)) + "}",
            "member limit",
        ),
        ('{"query":"' + "x" * (64 * 1024) + '"}', "byte limit"),
    ],
)
def test_mlx_adapter_rejects_tool_argument_bounds(
    tmp_path: Path,
    arguments: str,
    message: str,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=FakeToolCapableMLXBackend("native call"),
        tool_codec=FakeMLXToolCodec(
            MLXToolCodecResponse(
                tool_call=MLXToolCallCandidate(name="lookup", arguments=arguments)
            )
        ),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(ModelExecutionError, match=message):
        adapter.create_response(tool_request())


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (MLXToolCallCandidate(name=1, arguments="{}"), "must have a name"),  # type: ignore[arg-type]
        (MLXToolCallCandidate(name="lookup", arguments="{}", id=1), "ID"),  # type: ignore[arg-type]
        (MLXToolCallCandidate(name="lookup", arguments=1), "JSON object"),  # type: ignore[arg-type]
    ],
)
def test_mlx_adapter_rejects_runtime_invalid_codec_candidate_types(
    tmp_path: Path,
    candidate: MLXToolCallCandidate,
    message: str,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=FakeToolCapableMLXBackend("native call"),
        tool_codec=FakeMLXToolCodec(MLXToolCodecResponse(tool_call=candidate)),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(ModelExecutionError, match=message):
        adapter.create_response(tool_request())


def test_mlx_adapter_rejects_codec_text_combined_with_tool_call(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=FakeToolCapableMLXBackend("native call"),
        tool_codec=FakeMLXToolCodec(
            MLXToolCodecResponse(
                content="trailing prose",
                tool_call=MLXToolCallCandidate(name="lookup", arguments="{}"),
            )
        ),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(ModelExecutionError, match="text or exactly one tool call"):
        adapter.create_response(tool_request())


def test_mlx_adapter_rejects_runtime_invalid_codec_text(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=FakeToolCapableMLXBackend("native text"),
        tool_codec=FakeMLXToolCodec(MLXToolCodecResponse(content=1)),  # type: ignore[arg-type]
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(ModelExecutionError, match="text response must be a string"):
        adapter.create_response(tool_request())


def test_mlx_adapter_rejects_oversized_generated_tool_response(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    codec = FakeMLXToolCodec(MLXToolCodecResponse(content="not decoded"))
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=FakeToolCapableMLXBackend("x" * (128 * 1024 + 1)),
        tool_codec=codec,
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(ModelExecutionError, match="response exceeds the byte limit"):
        adapter.create_response(tool_request())
    assert codec.generated == []


def test_mlx_adapter_rejects_oversized_tool_call_candidate(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=FakeToolCapableMLXBackend("native call"),
        tool_codec=FakeMLXToolCodec(
            MLXToolCodecResponse(
                tool_call=MLXToolCallCandidate(
                    name="lookup",
                    arguments="{}",
                    id="x" * (66 * 1024),
                )
            )
        ),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(ModelExecutionError, match="call exceeds the byte limit"):
        adapter.create_response(tool_request())


def test_mlx_config_and_sync_factory_create_local_adapter(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    config = MLXLocalModelConfig(
        model_aliases=("mlx-local-chat",),
        model_path=model_path,
        expected_model_id="mlx-community/local-chat",
    )
    backend = FakeMLXBackend("sync local answer")

    adapter = create_mlx_local_adapter(
        config,
        backend=backend,
        platform_system=lambda: "Darwin",
    )

    assert adapter.models == ("mlx-local-chat",)
    assert adapter.is_local is True
    response = adapter.create_response(make_request())
    assert response.content == "sync local answer"
    assert backend.requests[0].model == "mlx-local-chat"


def test_mlx_config_and_async_factory_create_local_adapter(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_async_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    config = MLXLocalModelConfig(
        model_aliases=("mlx-local-chat",),
        model_path=model_path,
    )

    adapter = create_mlx_local_async_adapter(
        config,
        backend=FakeMLXBackend("async local answer"),
        platform_system=lambda: "Darwin",
    )

    assert adapter.models == ("mlx-local-chat",)
    assert adapter.is_local is True
    response = asyncio.run(adapter.create_response(make_request()))
    assert response.content == "async local answer"


def write_converted_mlx_model(model_path: Path) -> None:
    model_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (model_path / "tokenizer.model").write_text("tokenizer", encoding="utf-8")
    (model_path / "weights.npz").write_text("weights", encoding="utf-8")


def write_gguf_model(model_path: Path) -> None:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text("gguf", encoding="utf-8")


def test_mlx_adapter_validates_converted_model_directory(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    backend = FakeMLXBackend("converted model answer")

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=backend,
        platform_system=lambda: "Darwin",
    )

    response = adapter.create_response(make_request())

    assert response.content == "converted model answer"
    assert backend.requests


def test_mlx_adapter_supports_explicit_gguf_model_file(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "model.gguf"
    write_gguf_model(model_path)
    backend = FakeMLXBackend("gguf answer")

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
            model_format="gguf",
            expected_model_id="mlx-community/gguf-test",
        ),
        backend=backend,
        platform_system=lambda: "Darwin",
    )

    response = adapter.create_response(make_request())

    assert response.content == "gguf answer"
    assert backend.requests


def test_local_model_availability_supports_mlx_gguf_model_file(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import (
        LocalModelAssetReference,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    model_path = tmp_path / "model.gguf"
    write_gguf_model(model_path)

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="local_path",
            explicit_path=model_path,
            model_format="gguf",
            backend="mlx",
        )
    )

    assert availability.status is LocalModelAvailabilityStatus.AVAILABLE
    assert availability.resolved_path == model_path


def test_local_model_availability_supports_converted_mlx_directory(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import (
        LocalModelAssetReference,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="local_path",
            explicit_path=model_path,
            model_format="mlx",
            backend="mlx",
        )
    )

    assert availability.status is LocalModelAvailabilityStatus.AVAILABLE
    assert availability.resolved_path == model_path


def test_local_model_availability_rejects_incomplete_mlx_directory(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import (
        LocalModelAssetReference,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    model_path = tmp_path / "mlx-model"
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="local_path",
            explicit_path=model_path,
            model_format="mlx",
            backend="mlx",
        )
    )

    assert availability.status is LocalModelAvailabilityStatus.INVALID
    assert "tokenizer.model" in availability.message
    assert "weights.npz" in availability.message


def test_mlx_adapter_rejects_missing_gguf_file(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter
    from dynamic_agent_runner.errors import LocalModelResolutionError

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "missing.gguf",
            model_format="gguf",
        ),
        backend=FakeMLXBackend(),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(LocalModelResolutionError, match="GGUF"):
        adapter.create_response(make_request())


def test_mlx_adapter_rejects_non_gguf_file_when_format_is_gguf(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter
    from dynamic_agent_runner.errors import LocalModelResolutionError

    model_path = tmp_path / "model.bin"
    model_path.write_text("not gguf", encoding="utf-8")
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
            model_format="gguf",
        ),
        backend=FakeMLXBackend(),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(LocalModelResolutionError, match="\\.gguf"):
        adapter.create_response(make_request())


def test_mlx_adapter_passes_generation_kwargs_to_backend(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    backend = FakeMLXBackendWithKwargs("configured answer")

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
            generation_kwargs={"max_tokens": 128, "temperature": 0.2},
        ),
        backend=backend,
        platform_system=lambda: "Darwin",
    )

    response = adapter.create_response(make_request())

    assert response.content == "configured answer"
    assert backend.calls[0][1] == {"max_tokens": 128, "temperature": 0.2}


def test_mlx_adapter_uses_request_extra_generation_overrides(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    backend = FakeMLXBackendWithKwargs("request override")
    request = OpenAIModelRequest(
        model="mlx-local-chat",
        messages=({"role": "user", "content": "Hello"},),
        extra={"max_tokens": 64, "temperature": 0.7, "store": True},
    )

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
            generation_kwargs={"max_tokens": 128, "top_p": 0.9},
        ),
        backend=backend,
        platform_system=lambda: "Darwin",
    )

    adapter.create_response(request)

    assert backend.calls[0][1] == {
        "max_tokens": 64,
        "temperature": 0.7,
        "top_p": 0.9,
    }


def test_mlx_adapter_reports_conservative_capabilities(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        backend=FakeMLXBackend(),
        platform_system=lambda: "Darwin",
    )

    assert adapter.capabilities == {
        "provider": "mlx",
        "execution": "in_process",
        "local": True,
        "model_format": "mlx",
        "streaming": False,
        "tool_calling": False,
        "structured_output": False,
        "embeddings": False,
        "multimodal": False,
    }


def test_mlx_adapter_fails_before_generation_when_model_directory_is_missing(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter
    from dynamic_agent_runner.errors import LocalModelResolutionError

    backend = FakeMLXBackend()
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "missing-model",
        ),
        backend=backend,
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(LocalModelResolutionError, match="MLX local model"):
        adapter.create_response(make_request())

    assert backend.requests == []


def test_mlx_adapter_reports_model_identity_mismatch(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter
    from dynamic_agent_runner.errors import LocalModelIdentityMismatchError

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
            expected_model_id="mlx-community/expected-model",
        ),
        backend=FakeMLXBackend(model_id="mlx-community/other-model"),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(
        LocalModelIdentityMismatchError,
        match="mlx-community/expected-model",
    ):
        adapter.create_response(make_request())


def test_mlx_adapter_resolves_hub_file_reference_without_network(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter
    from dynamic_agent_runner.local_models import HuggingFaceModelFileReference

    downloaded_config = tmp_path / "hub-file" / "config.json"

    def fake_download(_: object, __: Path) -> Path:
        write_converted_mlx_model(downloaded_config.parent)
        return downloaded_config

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "missing-model",
            model_filename="config.json",
            huggingface_file=HuggingFaceModelFileReference(
                repo_id="mlx-community/test-model",
                filename="config.json",
            ),
        ),
        backend=FakeMLXBackend("hub file answer"),
        platform_system=lambda: "Darwin",
        download_file=fake_download,
    )

    response = adapter.create_response(make_request())

    assert response.content == "hub file answer"


def test_mlx_adapter_resolves_hub_snapshot_reference_without_network(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter
    from dynamic_agent_runner.local_models import HuggingFaceSnapshotReference

    snapshot_root = tmp_path / "hub-snapshot"

    def fake_download(_: object, __: Path) -> Path:
        write_converted_mlx_model(snapshot_root)
        return snapshot_root

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "missing-model",
            model_filename="config.json",
            huggingface_snapshot=HuggingFaceSnapshotReference(
                repo_id="mlx-community/test-model",
            ),
        ),
        backend=FakeMLXBackend("hub snapshot answer"),
        platform_system=lambda: "Darwin",
        download_snapshot=fake_download,
    )

    response = adapter.create_response(make_request())

    assert response.content == "hub snapshot answer"


def test_mlx_adapter_fails_clearly_on_unsupported_platform(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "mlx-model",
        ),
        backend=FakeMLXBackend(),
        platform_system=lambda: "Linux",
    )

    with pytest.raises(ModelExecutionError, match="MLX.*macOS"):
        adapter.create_response(make_request())


def test_mlx_adapter_does_not_load_model_on_unsupported_platform(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    dependency_loader_called = False

    def dependency_loader() -> object:
        nonlocal dependency_loader_called
        dependency_loader_called = True
        raise AssertionError("dependency loader should not run on non-macOS")

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "missing-model",
        ),
        dependency_loader=dependency_loader,
        platform_system=lambda: "Linux",
    )

    assert adapter.models == ("mlx-local-chat",)
    assert adapter.is_local is True
    with pytest.raises(ModelExecutionError, match="MLX.*macOS"):
        adapter.create_response(make_request())
    assert dependency_loader_called is False


def test_mlx_adapter_fails_clearly_when_dependency_is_missing(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    model_path = tmp_path / "mlx-model"
    write_converted_mlx_model(model_path)
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=model_path,
        ),
        dependency_loader=lambda: (_ for _ in ()).throw(ImportError("no mlx")),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(ModelExecutionError, match="MLX.*unavailable"):
        adapter.create_response(make_request())


def test_mlx_adapter_rejects_tool_calls(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "mlx-model",
        ),
        backend=FakeMLXBackend(),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(ModelExecutionError, match="MLX.*tool"):
        adapter.create_response(
            make_request(
                tools=(
                    {
                        "type": "function",
                        "function": {"name": "lookup", "parameters": {}},
                    },
                )
            )
        )


def test_mlx_adapter_rejects_structured_response_format(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "mlx-model",
        ),
        backend=FakeMLXBackend(),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(ModelExecutionError, match="MLX.*structured"):
        adapter.create_response(
            make_request(response_format={"type": "json_schema", "name": "Answer"})
        )
