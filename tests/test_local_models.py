"""Focused tests for local-model reference resolution helpers."""

from __future__ import annotations

import asyncio
import builtins
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from dynamic_agent_runner.errors import WorkflowExecutionError
from dynamic_agent_runner.executor import execute_workflow, execute_workflow_async
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


class _RecordingToolEmbeddingProducer:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[object, ...]] = []

    def embed(self, items: tuple[object, ...]) -> object:
        self.calls.append(items)
        return self.result


class _AsyncRecordingToolEmbeddingProducer(_RecordingToolEmbeddingProducer):
    async def embed(self, items: tuple[object, ...]) -> object:
        self.calls.append(items)
        return self.result


def _tool_embedding_result() -> object:
    from dynamic_agent_runner.local_models import (
        EmbeddingBatchResult,
        EmbeddingVectorItem,
    )

    return EmbeddingBatchResult(
        model="embedding-test",
        items=(EmbeddingVectorItem(id="entry-1", vector=(0.25, 0.75)),),
    )


def test_local_embedding_tool_has_fixed_schema_and_redacted_trace_output() -> None:
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_local_embedding_tool,
    )

    producer = _RecordingToolEmbeddingProducer(_tool_embedding_result())
    tool = create_local_embedding_tool(producer)

    assert tool.id == "local_embedding_batch"
    assert tool.definition.side_effect == "read"
    assert tool.definition.approval_required == "no"
    assert tool.definition.raw["input_schema"] == {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["id", "text"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }

    result = asyncio.run(
        tool.handler({"items": [{"id": "entry-1", "text": "private text"}]})
    )

    assert producer.calls == [(EmbeddingInputItem(id="entry-1", text="private text"),)]
    assert result.model_facing_output == {
        "model": "embedding-test",
        "items": [{"id": "entry-1", "vector": [0.25, 0.75]}],
    }
    assert result.trace_payload()["output"] == {"status": "embedding_result_redacted"}


@pytest.mark.parametrize(
    "arguments",
    [
        {"items": {"id": "entry-1", "text": "private text"}},
        {"items": [{"id": "entry-1"}]},
        {"items": [{"id": "entry-1", "text": "private text", "profile": "x"}]},
        {"items": [{"id": "entry-1", "text": "€" * 3_000}]},
    ],
)
def test_local_embedding_tool_rejects_nested_invalid_input_before_producer(
    arguments: dict[str, object],
) -> None:
    from dynamic_agent_runner.errors import EmbeddingInputError
    from dynamic_agent_runner.local_models import create_local_embedding_tool

    producer = _RecordingToolEmbeddingProducer(_tool_embedding_result())
    tool = create_local_embedding_tool(producer)

    with pytest.raises(EmbeddingInputError):
        asyncio.run(tool.handler(arguments))

    assert producer.calls == []


def test_local_embedding_tool_rejects_result_with_unmatched_ids() -> None:
    from dynamic_agent_runner.errors import EmbeddingResultError
    from dynamic_agent_runner.local_models import (
        EmbeddingBatchResult,
        EmbeddingVectorItem,
        create_local_embedding_tool,
    )

    producer = _RecordingToolEmbeddingProducer(
        EmbeddingBatchResult(
            model="embedding-test",
            items=(EmbeddingVectorItem(id="foreign", vector=(0.25, 0.75)),),
        )
    )
    tool = create_local_embedding_tool(producer)

    with pytest.raises(EmbeddingResultError):
        asyncio.run(
            tool.handler({"items": [{"id": "entry-1", "text": "private text"}]})
        )

    assert len(producer.calls) == 1


def test_local_embedding_tool_accepts_async_producer() -> None:
    from dynamic_agent_runner.local_models import create_local_embedding_tool

    producer = _AsyncRecordingToolEmbeddingProducer(_tool_embedding_result())
    tool = create_local_embedding_tool(producer)

    result = asyncio.run(
        tool.handler({"items": [{"id": "entry-1", "text": "private text"}]})
    )

    assert result.success is True
    assert len(producer.calls) == 1


def _default_cache_root(home_dir: Path) -> Path:
    return home_dir / ".cache" / "huggingface" / "hub"


def _hub_snapshot_root(home_dir: Path, repo_id: str, revision: str) -> Path:
    return (
        _default_cache_root(home_dir)
        / f"models--{repo_id.replace('/', '--')}"
        / "snapshots"
        / revision
    )


def _guard_ollama_access(
    monkeypatch: pytest.MonkeyPatch,
    home_dir: Path,
) -> list[Path]:
    ollama_root = home_dir / ".ollama"
    observed: list[Path] = []
    for method_name in (
        "exists",
        "is_dir",
        "is_file",
        "is_symlink",
        "iterdir",
        "read_text",
        "resolve",
    ):
        original = getattr(Path, method_name)

        def guarded(
            path: Path,
            *args: object,
            _original: Callable[..., object] = original,
            **kwargs: object,
        ) -> object:
            if path == ollama_root or ollama_root in path.parents:
                observed.append(path)
                raise AssertionError(f"A5.1 must not access {path!s}")
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(Path, method_name, guarded)
    return observed


class _FailingResponses:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def create(self, **_: object) -> object:
        raise self.error


class _FailingClient:
    def __init__(self, error: Exception) -> None:
        self.responses = _FailingResponses(error)


class _FailingAsyncResponses:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def create(self, **_: object) -> object:
        raise self.error


class _FailingAsyncClient:
    def __init__(self, error: Exception) -> None:
        self.responses = _FailingAsyncResponses(error)


class _StaticResponses:
    def __init__(self, response: object) -> None:
        self.response = response

    def create(self, **_: object) -> object:
        return self.response


class _StaticClient:
    def __init__(self, response: object) -> None:
        self.responses = _StaticResponses(response)


class _RecordingResponses:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class _RecordingClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = _RecordingResponses(responses)


class _RecordingAsyncResponses(_RecordingResponses):
    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class _RecordingAsyncClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = _RecordingAsyncResponses(responses)


class _RecordingAdapter:
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


class _AsyncRecordingAdapter:
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


def _endpoint_tool_response(name: str, arguments: str) -> dict[str, object]:
    return {
        "id": "response-tool",
        "model": "gpt-test",
        "output": [
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": name,
                "arguments": arguments,
            }
        ],
    }


def _llama_tool_response(name: str, arguments: str) -> dict[str, object]:
    return {
        "id": "response-tool",
        "model": "gpt-test",
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                }
            }
        ],
    }


def _parity_scenarios(
    tool_response: Callable[[str, str], dict[str, object]],
) -> list[tuple[str, list[object], tuple[str, ...], bool]]:
    return [
        ("S5", [{"model": "gpt-test", "output_text": "no tool"}], (), False),
        (
            "S1",
            [
                tool_response("create_record", '{"title":"DAR","body":"controlled"}'),
                {"model": "gpt-test", "output_text": "created"},
            ],
            ("create_record",),
            False,
        ),
        (
            "S2",
            [
                tool_response(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase"}',
                ),
                {"model": "gpt-test", "output_text": "transformed"},
            ],
            ("transform_record",),
            False,
        ),
        (
            "S2-invalid",
            [tool_response("transform_record", '{"record_id":"record-seed"}')],
            (),
            True,
        ),
        (
            "S2-wrong-type",
            [
                tool_response(
                    "transform_record", '{"record_id":1,"operation":"uppercase"}'
                )
            ],
            (),
            True,
        ),
        (
            "S2-invalid-enum",
            [
                tool_response(
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
                tool_response(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase","unknown":true}',
                )
            ],
            (),
            True,
        ),
        ("S2-malformed", [tool_response("transform_record", "not-json")], (), True),
        (
            "S3",
            [
                tool_response("lookup_record", '{"key":"seed"}'),
                tool_response(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase"}',
                ),
                {"model": "gpt-test", "output_text": "SEED"},
            ],
            ("lookup_record", "transform_record"),
            False,
        ),
        (
            "S4",
            [tool_response("fail_controlled", '{"code":"planned"}')],
            ("fail_controlled",),
            True,
        ),
        ("S6", [tool_response("lookup_record", "not-json")], (), True),
    ]


def _run_local_endpoint_parity(
    scenario: str,
    native_responses: list[object],
    *,
    asynchronous: bool,
    monkeypatch: pytest.MonkeyPatch,
):
    from dynamic_agent_runner.local_models import (
        LocalOpenAIEndpointConfig,
        create_local_async_openai_adapter,
        create_local_openai_adapter,
    )

    config = LocalOpenAIEndpointConfig(
        base_url="http://127.0.0.1:8000/v1",
        model_aliases=("gpt-test",),
        expected_model_id="gpt-test",
    )
    adapter = (
        create_local_async_openai_adapter(config)
        if asynchronous
        else create_local_openai_adapter(config)
    )
    assert adapter._client is None
    client = (
        _RecordingAsyncClient(native_responses)
        if asynchronous
        else _RecordingClient(native_responses)
    )
    provider = adapter._provider
    provider_calls: list[object] = []

    def forbidden_provider_client(*args: object, **kwargs: object) -> object:
        provider_calls.append((args, kwargs))
        raise AssertionError("parity tests must not use the default endpoint client")

    monkeypatch.setattr(type(provider), "get_client", forbidden_provider_client)
    adapter._client = client
    observed: list[object] = []
    recorder = (
        _AsyncRecordingAdapter(adapter, observed)
        if asynchronous
        else _RecordingAdapter(adapter, observed)
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
    assert adapter._provider is provider
    assert provider_calls == []
    return (
        result,
        parity_record(
            interface="local_endpoint_recording_client",
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
        client.responses.calls,
    )


class _FakeLlamaCppBackend:
    model_id = "Qwen/Qwen3-4B-Instruct-2507"

    def __init__(self, response: object | None = None) -> None:
        self.response = response or {
            "model": self.model_id,
            "choices": [{"message": {"content": "hello from llama.cpp"}}],
        }
        self.calls: list[dict[str, object]] = []

    def create_chat_completion(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class _SequencedLlamaCppBackend:
    model_id = "gpt-test"

    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def create_chat_completion(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class _FakeLlamaCppEmbeddingBackend:
    """Test-local embedding seam; it deliberately has no chat operation."""

    model_id = "embedding-test"

    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create_embedding(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


def _embedding_config(
    model_path: Path,
    *,
    allow_network: bool = True,
    **kwargs: object,
):
    from dynamic_agent_runner.local_models import LlamaCppLocalEmbeddingConfig

    return LlamaCppLocalEmbeddingConfig(
        model_path=model_path,
        model_filename="embedding.gguf",
        expected_model_id="embedding-test",
        allow_network=allow_network,
        **kwargs,
    )


def test_llama_cpp_embedding_public_values_are_frozen_and_tuple_backed(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        EmbeddingBatchResult,
        EmbeddingInputItem,
        EmbeddingVectorItem,
    )

    item = EmbeddingInputItem(id="entry-1", text="controlled input")
    vector = EmbeddingVectorItem(id="entry-1", vector=(0.25, -0.5))
    result = EmbeddingBatchResult(model="embedding-test", items=(vector,))
    config = _embedding_config(tmp_path / "embedding.gguf")

    assert result.items == (vector,)
    with pytest.raises(FrozenInstanceError):
        item.text = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        vector.vector = (1.0,)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.model = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        config.allow_network = False  # type: ignore[misc]


def test_llama_cpp_embedding_config_requires_bound_identity_and_rejects_empty_vectors(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.errors import EmbeddingResultError
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        LlamaCppLocalEmbeddingConfig,
        create_llama_cpp_local_embedding_adapter,
    )

    with pytest.raises(ValueError):
        LlamaCppLocalEmbeddingConfig(model_path=tmp_path / "embedding.gguf")

    model_path = tmp_path / "embedding.gguf"
    model_path.touch()
    backend = _FakeLlamaCppEmbeddingBackend(
        {"model": "embedding-test", "data": [{"index": 0, "embedding": []}]}
    )
    adapter = create_llama_cpp_local_embedding_adapter(
        _embedding_config(model_path), backend=backend
    )

    with pytest.raises(EmbeddingResultError):
        adapter.embed((EmbeddingInputItem(id="entry", text="controlled"),))


def test_llama_cpp_embedding_sync_resolves_before_one_indexed_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dynamic_agent_runner.local_models as local_models
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_embedding_adapter,
    )

    model_path = tmp_path / "embedding.gguf"
    model_path.touch()
    backend = _FakeLlamaCppEmbeddingBackend(
        {
            "model": "embedding-test",
            "data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ],
        }
    )
    forbidden_calls: list[object] = []

    def forbidden(*args: object, **kwargs: object) -> object:
        forbidden_calls.append((args, kwargs))
        raise AssertionError(
            "embedding adapter must not load or download on a local hit"
        )

    monkeypatch.setattr(local_models, "_load_default_llama_cpp_backend", forbidden)
    adapter = create_llama_cpp_local_embedding_adapter(
        _embedding_config(model_path),
        backend=backend,
        dependency_loader=forbidden,
        download_file=forbidden,
        download_snapshot=forbidden,
    )

    result = adapter.embed(
        (
            EmbeddingInputItem(id="first", text="controlled first"),
            EmbeddingInputItem(id="second", text="controlled second"),
        )
    )

    assert result.model == "embedding-test"
    assert tuple(item.id for item in result.items) == ("first", "second")
    assert tuple(item.vector for item in result.items) == ((1.0, 0.0), (0.0, 1.0))
    assert backend.calls == [
        {
            "input": ["controlled first", "controlled second"],
            "model": "embedding-test",
        }
    ]
    assert forbidden_calls == []


def test_llama_cpp_embedding_async_matches_sync_contract(tmp_path: Path) -> None:
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_async_embedding_adapter,
    )

    model_path = tmp_path / "embedding.gguf"
    model_path.touch()
    backend = _FakeLlamaCppEmbeddingBackend(
        {
            "model": "embedding-test",
            "data": [{"index": 0, "embedding": [0.125, 0.875]}],
        }
    )
    adapter = create_llama_cpp_local_async_embedding_adapter(
        _embedding_config(model_path), backend=backend
    )

    result = asyncio.run(
        adapter.embed((EmbeddingInputItem(id="entry-1", text="controlled"),))
    )

    assert result.model == "embedding-test"
    assert result.items[0].id == "entry-1"
    assert result.items[0].vector == (0.125, 0.875)
    assert len(backend.calls) == 1


def test_llama_cpp_embedding_accepts_exact_utf8_input_limits(tmp_path: Path) -> None:
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_embedding_adapter,
    )

    model_path = tmp_path / "embedding.gguf"
    model_path.touch()
    item = EmbeddingInputItem(
        id=("€" * 42) + "ab",
        text=("€" * 21_845) + "a",
    )
    backend = _FakeLlamaCppEmbeddingBackend(
        {"model": "embedding-test", "data": [{"index": 0, "embedding": [1.0]}]}
    )
    adapter = create_llama_cpp_local_embedding_adapter(
        _embedding_config(model_path), backend=backend
    )

    result = adapter.embed((item,))

    assert result.items[0].id == item.id
    assert len(backend.calls) == 1


@pytest.mark.parametrize(
    "raw_response",
    [
        {"model": "embedding-test", "data": []},
        (
            {
                "model": "embedding-test",
                "data": [{"index": 1, "embedding": [0.0]}],
            }
        ),
        (
            {
                "model": "embedding-test",
                "data": [{"index": 0, "embedding": [float("nan")]}],
            }
        ),
    ],
)
def test_llama_cpp_embedding_rejects_malformed_results_without_partial_output(
    tmp_path: Path,
    raw_response: object,
) -> None:
    from dynamic_agent_runner.errors import EmbeddingResultError
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_embedding_adapter,
    )

    model_path = tmp_path / "embedding.gguf"
    model_path.touch()
    backend = _FakeLlamaCppEmbeddingBackend(raw_response)
    adapter = create_llama_cpp_local_embedding_adapter(
        _embedding_config(model_path), backend=backend
    )

    with pytest.raises(EmbeddingResultError):
        adapter.embed((EmbeddingInputItem(id="entry-1", text="secret input"),))

    assert len(backend.calls) == 1


def test_llama_cpp_embedding_rejects_invalid_input_before_backend(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.errors import EmbeddingInputError
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_embedding_adapter,
    )

    backend = _FakeLlamaCppEmbeddingBackend({"model": "embedding-test", "data": []})
    adapter = create_llama_cpp_local_embedding_adapter(
        _embedding_config(tmp_path / "missing.gguf"), backend=backend
    )

    with pytest.raises(EmbeddingInputError) as raised:
        adapter.embed((EmbeddingInputItem(id="", text="secret input"),))

    assert "secret input" not in str(raised.value)
    assert backend.calls == []


def test_llama_cpp_embedding_rejects_invalid_unicode_before_backend(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.errors import EmbeddingInputError
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_embedding_adapter,
    )

    backend = _FakeLlamaCppEmbeddingBackend({"model": "embedding-test", "data": []})
    forbidden_calls: list[object] = []

    def forbidden(*args: object, **kwargs: object) -> object:
        forbidden_calls.append((args, kwargs))
        raise AssertionError("invalid input must not resolve, load, or download")

    adapter = create_llama_cpp_local_embedding_adapter(
        _embedding_config(tmp_path / "missing.gguf"),
        backend=backend,
        dependency_loader=forbidden,
        download_file=forbidden,
        download_snapshot=forbidden,
    )
    sentinel = chr(0xD800) + "secret-input"

    with pytest.raises(EmbeddingInputError) as raised:
        adapter.embed((EmbeddingInputItem(id="entry", text=sentinel),))

    assert "secret-input" not in str(raised.value)
    assert backend.calls == []
    assert forbidden_calls == []


def test_llama_cpp_embedding_factory_and_preflight_perform_no_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket
    import subprocess

    import dynamic_agent_runner.local_models as local_models
    import dynamic_agent_runner.openai_client as openai_client
    from dynamic_agent_runner.local_models import (
        create_llama_cpp_local_embedding_adapter,
        create_llama_cpp_local_async_embedding_adapter,
    )

    calls: list[object] = []

    def forbidden(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("factory/preflight must not perform I/O")

    monkeypatch.setattr(local_models, "_load_default_llama_cpp_backend", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(local_models, "download_hub_file", forbidden)
    monkeypatch.setattr(local_models, "download_hub_snapshot", forbidden)
    monkeypatch.setattr(
        local_models, "create_openai_adapter_from_provider_config", forbidden
    )
    monkeypatch.setattr(openai_client, "_read_codex_auth_defaults", forbidden)
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        if name.partition(".")[0] in {"llama_cpp", "huggingface_hub"}:
            return forbidden(name, *args, **kwargs)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    config = _embedding_config(tmp_path / "unresolved.gguf")

    create_llama_cpp_local_embedding_adapter(
        config,
        dependency_loader=forbidden,
        download_file=forbidden,
        download_snapshot=forbidden,
    )
    create_llama_cpp_local_async_embedding_adapter(
        config,
        dependency_loader=forbidden,
        download_file=forbidden,
        download_snapshot=forbidden,
    )

    assert calls == []


def test_llama_cpp_embedding_rejects_ambiguous_config(tmp_path: Path) -> None:
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        HuggingFaceSnapshotReference,
    )

    with pytest.raises(ValueError):
        _embedding_config(
            tmp_path / "embedding.gguf",
            huggingface_file=HuggingFaceModelFileReference(
                repo_id="org/embedding", filename="embedding.gguf"
            ),
            huggingface_snapshot=HuggingFaceSnapshotReference(repo_id="org/embedding"),
        )


def test_llama_cpp_embedding_resolver_precedence_and_offline_download_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.errors import LocalModelOfflinePolicyError
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        HuggingFaceModelFileReference,
        create_llama_cpp_local_embedding_adapter,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    hub_reference = HuggingFaceModelFileReference(
        repo_id="org/embedding", filename="embedding.gguf", revision="commit-123"
    )
    explicit_path = tmp_path / "explicit.gguf"
    explicit_path.touch()
    caller_cache = tmp_path / "caller-cache"
    caller_cache.mkdir()
    caller_hit = caller_cache / "embedding.gguf"
    caller_hit.touch()
    hub_hit = (
        _hub_snapshot_root(home_dir, "org/embedding", "commit-123") / "embedding.gguf"
    )
    hub_hit.parent.mkdir(parents=True)
    hub_hit.touch()
    backend = _FakeLlamaCppEmbeddingBackend(
        {"model": "embedding-test", "data": [{"index": 0, "embedding": [1.0]}]}
    )
    download_calls: list[object] = []

    def download(*args: object, **kwargs: object) -> Path:
        download_calls.append((args, kwargs))
        return tmp_path / "downloaded.gguf"

    loaded_paths: list[Path] = []

    def load_embedding(model_path: Path, _: object) -> _FakeLlamaCppEmbeddingBackend:
        loaded_paths.append(model_path)
        return backend

    explicit = create_llama_cpp_local_embedding_adapter(
        _embedding_config(
            explicit_path,
            model_cache_root=caller_cache,
            huggingface_file=hub_reference,
        ),
        dependency_loader=load_embedding,
        download_file=download,
    )
    explicit.embed((EmbeddingInputItem(id="entry", text="controlled"),))
    assert download_calls == []
    assert loaded_paths == [explicit_path]

    caller = create_llama_cpp_local_embedding_adapter(
        _embedding_config(
            tmp_path / "missing.gguf",
            model_cache_root=caller_cache,
            huggingface_file=hub_reference,
        ),
        dependency_loader=load_embedding,
        download_file=download,
    )
    caller.embed((EmbeddingInputItem(id="entry", text="controlled"),))
    assert download_calls == []
    assert loaded_paths == [explicit_path, caller_hit]

    caller_hit.unlink()
    hub = create_llama_cpp_local_embedding_adapter(
        _embedding_config(tmp_path / "missing.gguf", huggingface_file=hub_reference),
        dependency_loader=load_embedding,
        download_file=download,
    )
    hub.embed((EmbeddingInputItem(id="entry", text="controlled"),))
    assert download_calls == []
    assert loaded_paths == [explicit_path, caller_hit, hub_hit]

    hub_hit.unlink()
    offline = create_llama_cpp_local_embedding_adapter(
        _embedding_config(
            tmp_path / "missing.gguf",
            huggingface_file=hub_reference,
            allow_network=False,
        ),
        dependency_loader=load_embedding,
        download_file=download,
    )
    with pytest.raises(LocalModelOfflinePolicyError):
        offline.embed((EmbeddingInputItem(id="entry", text="controlled"),))
    assert download_calls == []
    assert loaded_paths == [explicit_path, caller_hit, hub_hit]

    downloaded = tmp_path / "downloaded.gguf"
    downloaded.touch()
    online = create_llama_cpp_local_embedding_adapter(
        _embedding_config(tmp_path / "missing.gguf", huggingface_file=hub_reference),
        dependency_loader=load_embedding,
        download_file=download,
    )
    online.embed((EmbeddingInputItem(id="entry", text="controlled"),))
    assert len(download_calls) == 1
    assert loaded_paths == [explicit_path, caller_hit, hub_hit, downloaded]


@pytest.mark.parametrize(
    "items",
    [
        (),
        (("", "controlled"),),
        (("duplicate", "controlled"), ("duplicate", "controlled")),
        (("x" * 129, "controlled"),),
        (("€" * 43, "controlled"),),
        (("entry", "x" * 65_537),),
        (("entry", "€" * 21_846),),
        tuple((str(index), "controlled") for index in range(129)),
        tuple((str(index), "x" * 65_536) for index in range(17)),
    ],
)
def test_llama_cpp_embedding_rejects_declared_input_bounds_before_resolution(
    tmp_path: Path,
    items: tuple[tuple[str, str], ...],
) -> None:
    from dynamic_agent_runner.errors import EmbeddingInputError
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_embedding_adapter,
    )

    normalized_items = tuple(
        EmbeddingInputItem(id=item_id, text=text) for item_id, text in items
    )
    backend = _FakeLlamaCppEmbeddingBackend({"model": "embedding-test", "data": []})
    forbidden_calls: list[object] = []

    def forbidden(*args: object, **kwargs: object) -> object:
        forbidden_calls.append((args, kwargs))
        raise AssertionError("invalid input must not resolve, load, or download")

    adapter = create_llama_cpp_local_embedding_adapter(
        _embedding_config(tmp_path / "missing.gguf"),
        backend=backend,
        dependency_loader=forbidden,
        download_file=forbidden,
        download_snapshot=forbidden,
    )

    with pytest.raises(EmbeddingInputError) as raised:
        adapter.embed(normalized_items)

    assert backend.calls == []
    assert forbidden_calls == []
    assert all(text not in str(raised.value) for _, text in items)


@pytest.mark.parametrize(
    "raw_response",
    [
        {"data": [{"index": 0, "embedding": [1.0]}]},
        {"model": "embedding-test", "data": [{"index": 0, "embedding": [[1.0]]}]},
        {"model": "embedding-test", "data": [{"index": 0, "embedding": b"\x01"}]},
        {"model": "embedding-test", "data": [{"index": 0, "embedding": [10**100_000]}]},
        {"model": "embedding-test", "data": [{"index": 0, "embedding": [1.0] * 8193}]},
        {
            "model": "embedding-test",
            "data": [
                {"index": 0, "embedding": [1.0]},
                {"index": 0, "embedding": [2.0]},
            ],
        },
        {"model": "wrong-model", "data": [{"index": 0, "embedding": [1.0]}]},
    ],
)
def test_llama_cpp_embedding_rejects_remaining_malformed_or_mismatched_results(
    tmp_path: Path,
    raw_response: object,
) -> None:
    from dynamic_agent_runner.errors import (
        EmbeddingResultError,
        LocalModelIdentityMismatchError,
    )
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_embedding_adapter,
    )

    model_path = tmp_path / "embedding.gguf"
    model_path.touch()
    backend = _FakeLlamaCppEmbeddingBackend(raw_response)
    adapter = create_llama_cpp_local_embedding_adapter(
        _embedding_config(model_path), backend=backend
    )

    with pytest.raises(
        (EmbeddingResultError, LocalModelIdentityMismatchError)
    ) as raised:
        adapter.embed((EmbeddingInputItem(id="entry", text="secret input"),))

    assert "secret input" not in str(raised.value)
    assert backend.calls


def test_llama_cpp_embedding_wraps_provider_failure_without_raw_input(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.errors import EmbeddingExecutionError
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_embedding_adapter,
    )

    class FailingBackend(_FakeLlamaCppEmbeddingBackend):
        def create_embedding(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            raise RuntimeError("provider received secret input")

    model_path = tmp_path / "embedding.gguf"
    model_path.touch()
    backend = FailingBackend({})
    adapter = create_llama_cpp_local_embedding_adapter(
        _embedding_config(model_path), backend=backend
    )

    with pytest.raises(EmbeddingExecutionError) as raised:
        adapter.embed((EmbeddingInputItem(id="entry", text="secret input"),))

    assert "secret input" not in str(raised.value)
    assert len(backend.calls) == 1


def test_default_llama_cpp_embedding_loader_forces_embedding_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    from types import SimpleNamespace

    import dynamic_agent_runner.local_models as local_models

    calls: list[dict[str, object]] = []

    class FakeLlama:
        def __init__(self, **kwargs: object) -> None:
            calls.append(kwargs)

    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=FakeLlama))
    config = _embedding_config(tmp_path / "embedding.gguf", model_kwargs={"n_ctx": 512})

    backend = local_models._load_default_llama_cpp_embedding_backend(
        tmp_path / "embedding.gguf", config
    )

    assert isinstance(backend, FakeLlama)
    assert calls == [
        {
            "model_path": str(tmp_path / "embedding.gguf"),
            "embedding": True,
            "n_ctx": 512,
        }
    ]
    with pytest.raises(ValueError):
        _embedding_config(
            tmp_path / "embedding.gguf", model_kwargs={"embedding": False}
        )


def test_llama_cpp_embedding_rejects_ragged_and_scalar_vectors_without_raw_data(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.errors import EmbeddingResultError
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_embedding_adapter,
    )

    model_path = tmp_path / "embedding.gguf"
    model_path.touch()
    for raw_response, items in (
        (
            {
                "model": "embedding-test",
                "data": [
                    {"index": 0, "embedding": [1.0]},
                    {"index": 1, "embedding": [1.0, 2.0]},
                ],
            },
            (
                EmbeddingInputItem(id="first", text="controlled"),
                EmbeddingInputItem(id="second", text="controlled"),
            ),
        ),
        (
            {
                "model": "embedding-test",
                "data": [
                    {"index": 0, "embedding": [1.0]},
                    {"index": 1, "embedding": ["secret-vector"]},
                ],
            },
            (
                EmbeddingInputItem(id="first", text="controlled"),
                EmbeddingInputItem(id="second", text="controlled"),
            ),
        ),
        (
            {
                "model": "embedding-test",
                "data": [
                    {"index": 0, "embedding": 1.0},
                    {"index": 1, "embedding": [1.0]},
                ],
            },
            (
                EmbeddingInputItem(id="first", text="controlled"),
                EmbeddingInputItem(id="second", text="controlled"),
            ),
        ),
    ):
        backend = _FakeLlamaCppEmbeddingBackend(raw_response)
        adapter = create_llama_cpp_local_embedding_adapter(
            _embedding_config(model_path), backend=backend
        )

        with pytest.raises(EmbeddingResultError) as raised:
            adapter.embed(items)

        assert "secret-vector" not in str(raised.value)
        assert len(backend.calls) == 1


def test_llama_cpp_embedding_rejects_encoded_output_limit(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.errors import EmbeddingResultError
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_embedding_adapter,
    )

    model_path = tmp_path / "embedding.gguf"
    model_path.touch()
    items = tuple(
        EmbeddingInputItem(id=str(index), text="controlled") for index in range(128)
    )
    raw_response = {
        "model": "embedding-test",
        "data": [
            {"index": index, "embedding": [1.7976931348623157e308] * 8192}
            for index in range(128)
        ],
    }
    backend = _FakeLlamaCppEmbeddingBackend(raw_response)
    adapter = create_llama_cpp_local_embedding_adapter(
        _embedding_config(model_path), backend=backend
    )

    with pytest.raises(EmbeddingResultError) as raised:
        adapter.embed(items)

    assert "1.7976931348623157e308" not in str(raised.value)
    assert len(backend.calls) == 1


def test_llama_cpp_embedding_async_rejects_invalid_input_before_backend(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.errors import EmbeddingInputError
    from dynamic_agent_runner.local_models import (
        EmbeddingInputItem,
        create_llama_cpp_local_async_embedding_adapter,
    )

    backend = _FakeLlamaCppEmbeddingBackend({"model": "embedding-test", "data": []})
    forbidden_calls: list[object] = []

    def forbidden(*args: object, **kwargs: object) -> object:
        forbidden_calls.append((args, kwargs))
        raise AssertionError("invalid input must not resolve, load, or download")

    adapter = create_llama_cpp_local_async_embedding_adapter(
        _embedding_config(tmp_path / "missing.gguf"),
        backend=backend,
        dependency_loader=forbidden,
        download_file=forbidden,
        download_snapshot=forbidden,
    )

    with pytest.raises(EmbeddingInputError):
        asyncio.run(adapter.embed((EmbeddingInputItem(id="", text="secret input"),)))

    assert backend.calls == []
    assert forbidden_calls == []


def _run_llama_cpp_parity(
    scenario: str,
    native_responses: list[object],
    *,
    asynchronous: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import dynamic_agent_runner.local_models as local_models
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        create_llama_cpp_local_adapter,
        create_llama_cpp_local_async_adapter,
    )

    sentinel = tmp_path / "inert-model-path"
    sentinel.touch()
    forbidden_calls: list[object] = []

    def forbidden(*args: object, **kwargs: object) -> object:
        forbidden_calls.append((args, kwargs))
        raise AssertionError("parity tests must not load or download a llama model")

    monkeypatch.setattr(local_models, "_load_default_llama_cpp_backend", forbidden)
    backend = _SequencedLlamaCppBackend(native_responses)
    config = LlamaCppLocalModelConfig(
        model_aliases=("gpt-test",),
        model_path=sentinel,
        expected_model_id="gpt-test",
    )
    adapter = (
        create_llama_cpp_local_async_adapter(
            config,
            backend=backend,
            dependency_loader=forbidden,
            download_file=forbidden,
            download_snapshot=forbidden,
        )
        if asynchronous
        else create_llama_cpp_local_adapter(
            config,
            backend=backend,
            dependency_loader=forbidden,
            download_file=forbidden,
            download_snapshot=forbidden,
        )
    )
    observed: list[object] = []
    recorder = (
        _AsyncRecordingAdapter(adapter, observed)
        if asynchronous
        else _RecordingAdapter(adapter, observed)
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
    return (
        result,
        parity_record(
            interface="llama_cpp_injected_backend",
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
        backend.calls,
    )


def _assert_local_parity_scenario(
    *,
    scenario: str,
    invoked: tuple[str, ...],
    fails: bool,
    result: object | None,
    record: object,
    error: Exception | None,
    calls: list[dict[str, object]],
) -> None:
    assert tuple(name for name, _ in record.invocations) == invoked
    assert (error is not None) is fails
    assert (result is None) is fails
    if fails:
        assert isinstance(error, WorkflowExecutionError)
        assert record.error_class == "WorkflowExecutionError"
    if scenario == "S1":
        assert result is not None
        assert result.final_result == "created"
        assert record.normalized_calls == (
            ("create_record", '{"title":"DAR","body":"controlled"}'),
        )
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


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    ("scenario", "responses", "invoked", "fails"),
    _parity_scenarios(_endpoint_tool_response),
)
def test_model_interface_parity_local_endpoint_native_scenarios(
    scenario: str,
    responses: list[object],
    invoked: tuple[str, ...],
    fails: bool,
    asynchronous: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_parity_io_blocker(monkeypatch)
    result, record, error, calls = _run_local_endpoint_parity(
        scenario, responses, asynchronous=asynchronous, monkeypatch=monkeypatch
    )
    _assert_local_parity_scenario(
        scenario=scenario,
        invoked=invoked,
        fails=fails,
        result=result,
        record=record,
        error=error,
        calls=calls,
    )
    if not asynchronous:
        _, async_record, _, _ = _run_local_endpoint_parity(
            scenario, responses, asynchronous=True, monkeypatch=monkeypatch
        )
        assert parity_contract_projection(record) == parity_contract_projection(
            async_record
        )


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    ("scenario", "responses", "invoked", "fails"),
    _parity_scenarios(_llama_tool_response),
)
def test_model_interface_parity_llama_cpp_native_scenarios(
    scenario: str,
    responses: list[object],
    invoked: tuple[str, ...],
    fails: bool,
    asynchronous: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_parity_io_blocker(monkeypatch)
    result, record, error, calls = _run_llama_cpp_parity(
        scenario,
        responses,
        asynchronous=asynchronous,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    _assert_local_parity_scenario(
        scenario=scenario,
        invoked=invoked,
        fails=fails,
        result=result,
        record=record,
        error=error,
        calls=calls,
    )
    if not asynchronous:
        _, async_record, _, _ = _run_llama_cpp_parity(
            scenario,
            responses,
            asynchronous=True,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
        )
        assert parity_contract_projection(record) == parity_contract_projection(
            async_record
        )


class _FailingLlamaCppBackend:
    def create_chat_completion(self, **_: object) -> object:
        raise RuntimeError("llama.cpp generation failed")


def test_local_model_availability_public_contract_shape() -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailability,
        LocalModelAvailabilitySource,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    reference = LocalModelAssetReference(
        provider="hugging_face",
        repo_id="Qwen/Qwen3-4B-GGUF",
        filename="chat-model.gguf",
        model_format="gguf",
        backend="llama_cpp",
    )

    availability = check_local_model_availability(reference)

    assert availability == LocalModelAvailability(
        status=LocalModelAvailabilityStatus.MISSING,
        reference=reference,
        source=LocalModelAvailabilitySource.NOT_FOUND,
        message="Local model asset 'chat-model.gguf' is not available locally",
    )
    assert availability.resolved_path is None
    assert availability.cache_root is None
    assert availability.size_bytes is None
    assert availability.warnings == ()


def test_local_model_inventory_public_contract_shape() -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelInventory,
        list_local_model_assets,
    )

    inventory = list_local_model_assets(include_default_cache_root=False)

    assert inventory == LocalModelInventory(assets=(), warnings=())


def test_list_local_model_assets_scans_default_cache_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAvailabilitySource,
        LocalModelAvailabilityStatus,
        list_local_model_assets,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    cache_root = _default_cache_root(home_dir)
    gguf_model = (
        _hub_snapshot_root(
            home_dir,
            "Qwen/Qwen3-4B-GGUF",
            "commit-gguf",
        )
        / "chat-model.gguf"
    )
    gguf_model.parent.mkdir(parents=True)
    gguf_model.write_text("gguf", encoding="utf-8")
    mlx_model = _hub_snapshot_root(
        home_dir,
        "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
        "commit-mlx",
    )
    mlx_model.mkdir(parents=True)
    (mlx_model / "config.json").write_text("{}", encoding="utf-8")
    (mlx_model / "tokenizer.model").write_text("tokenizer", encoding="utf-8")
    (mlx_model / "weights.npz").write_text("weights", encoding="utf-8")

    inventory = list_local_model_assets()

    assert [asset.path for asset in inventory.assets] == [gguf_model, mlx_model]
    assert [asset.cache_root for asset in inventory.assets] == [cache_root, cache_root]
    assert [asset.source for asset in inventory.assets] == [
        LocalModelAvailabilitySource.DEFAULT_CACHE_ROOT,
        LocalModelAvailabilitySource.DEFAULT_CACHE_ROOT,
    ]
    assert [asset.model_format for asset in inventory.assets] == ["gguf", "mlx"]
    assert [asset.backend for asset in inventory.assets] == ["llama_cpp", "mlx"]
    assert all(
        asset.status is LocalModelAvailabilityStatus.AVAILABLE
        for asset in inventory.assets
    )
    assert inventory.warnings == ()


def test_list_local_model_assets_scans_native_mlx_hub_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.local_models import list_local_model_assets

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    snapshot_root = _hub_snapshot_root(
        home_dir,
        "mlx-community/Qwen3-4B-MLX-4bit",
        "commit-native",
    )
    snapshot_root.mkdir(parents=True)
    (snapshot_root / "config.json").write_text("{}", encoding="utf-8")
    (snapshot_root / "tokenizer.json").write_text("{}", encoding="utf-8")
    (snapshot_root / "model.safetensors").write_text("weights", encoding="utf-8")

    inventory = list_local_model_assets()

    assert [asset.path for asset in inventory.assets] == [snapshot_root]
    assert inventory.assets[0].model_format == "mlx"
    assert inventory.assets[0].backend == "mlx"


def test_list_local_model_assets_accepts_contained_native_mlx_blob_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.local_models import list_local_model_assets

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    snapshot_root = _hub_snapshot_root(
        home_dir,
        "mlx-community/Qwen3-4B-MLX-4bit",
        "commit-native",
    )
    repository_root = snapshot_root.parent.parent
    blobs = repository_root / "blobs"
    blobs.mkdir(parents=True)
    snapshot_root.mkdir(parents=True)
    for filename in ("config.json", "tokenizer.json", "model.safetensors"):
        blob = blobs / filename
        blob.write_text("{}", encoding="utf-8")
        (snapshot_root / filename).symlink_to(blob)

    inventory = list_local_model_assets()

    assert [asset.path for asset in inventory.assets] == [snapshot_root]


def test_list_local_model_assets_omits_native_mlx_snapshot_with_missing_shard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.local_models import list_local_model_assets

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    snapshot_root = _hub_snapshot_root(
        home_dir,
        "mlx-community/Qwen3-4B-MLX-4bit",
        "commit-native",
    )
    snapshot_root.mkdir(parents=True)
    (snapshot_root / "config.json").write_text("{}", encoding="utf-8")
    (snapshot_root / "tokenizer.json").write_text("{}", encoding="utf-8")
    (snapshot_root / "model.safetensors.index.json").write_text(
        '{"weight_map":{"missing":"model-00001-of-00001.safetensors"}}',
        encoding="utf-8",
    )

    assert list_local_model_assets().assets == ()


def test_list_local_model_assets_scans_current_caller_roots_without_persisting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAvailabilitySource,
        list_local_model_assets,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    caller_root = tmp_path / "caller-root"
    caller_root.mkdir()
    caller_model = caller_root / "caller-model.gguf"
    caller_model.write_text("gguf", encoding="utf-8")

    with_caller_root = list_local_model_assets(
        model_cache_roots=(caller_root,),
        include_default_cache_root=False,
    )
    without_caller_root = list_local_model_assets(include_default_cache_root=False)

    assert [asset.path for asset in with_caller_root.assets] == [caller_model]
    assert with_caller_root.assets[0].cache_root == caller_root
    assert (
        with_caller_root.assets[0].source
        is LocalModelAvailabilitySource.CALLER_PROVIDED_ROOT
    )
    assert without_caller_root.assets == ()


def test_list_local_model_assets_deduplicates_roots_and_warns_for_bad_roots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAvailabilitySource,
        list_local_model_assets,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    cache_root = _default_cache_root(home_dir)
    model_path = (
        _hub_snapshot_root(
            home_dir,
            "Qwen/Qwen3-4B-GGUF",
            "commit-gguf",
        )
        / "chat-model.gguf"
    )
    model_path.parent.mkdir(parents=True)
    model_path.write_text("gguf", encoding="utf-8")
    missing_root = tmp_path / "missing-root"
    not_directory = tmp_path / "not-directory"
    not_directory.write_text("not a directory", encoding="utf-8")

    inventory = list_local_model_assets(
        model_cache_roots=(cache_root, missing_root, not_directory),
    )

    assert [asset.path for asset in inventory.assets] == [model_path]
    assert inventory.assets[0].source is LocalModelAvailabilitySource.DEFAULT_CACHE_ROOT
    assert any(str(missing_root) in warning for warning in inventory.warnings)
    assert any(str(not_directory) in warning for warning in inventory.warnings)


def test_list_local_model_assets_does_not_scan_sibling_or_nested_directories(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import list_local_model_assets

    caller_root = tmp_path / "caller-root"
    caller_root.mkdir()
    (caller_root / "direct-model.gguf").write_text("gguf", encoding="utf-8")
    nested = caller_root / "nested"
    nested.mkdir()
    (nested / "nested-model.gguf").write_text("gguf", encoding="utf-8")
    sibling = tmp_path / "sibling-root"
    sibling.mkdir()
    (sibling / "sibling-model.gguf").write_text("gguf", encoding="utf-8")

    inventory = list_local_model_assets(
        model_cache_roots=(caller_root,),
        include_default_cache_root=False,
    )

    assert [asset.path for asset in inventory.assets] == [
        caller_root / "direct-model.gguf"
    ]


def test_list_local_model_assets_is_read_only_and_offline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_agent_runner.local_models as local_models

    caller_root = tmp_path / "caller-root"
    caller_root.mkdir()
    model_path = caller_root / "chat-model.gguf"
    model_path.write_text("gguf", encoding="utf-8")
    forbidden_calls: list[str] = []

    def forbidden_call(*_: object, **__: object) -> Path:
        forbidden_calls.append("called")
        raise AssertionError("inventory must not call mutating/runtime helpers")

    monkeypatch.setattr(local_models, "download_hub_file", forbidden_call)
    monkeypatch.setattr(local_models, "download_hub_snapshot", forbidden_call)
    monkeypatch.setattr(
        local_models,
        "_load_default_llama_cpp_backend",
        forbidden_call,
    )

    inventory = local_models.list_local_model_assets(
        model_cache_roots=(caller_root,),
        include_default_cache_root=False,
    )

    assert [asset.path for asset in inventory.assets] == [model_path]
    assert forbidden_calls == []


def test_check_local_model_availability_reports_available_explicit_gguf_path(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailabilitySource,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    model_path = tmp_path / "chat-model.gguf"
    model_path.write_text("gguf", encoding="utf-8")
    reference = LocalModelAssetReference(
        provider="local_path",
        explicit_path=model_path,
        model_format="gguf",
        backend="llama_cpp",
    )

    availability = check_local_model_availability(reference)

    assert availability.status is LocalModelAvailabilityStatus.AVAILABLE
    assert availability.resolved_path == model_path
    assert availability.cache_root is None
    assert availability.source is LocalModelAvailabilitySource.EXPLICIT_PATH


def test_check_local_model_availability_reports_missing_explicit_path(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailabilitySource,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    model_path = tmp_path / "missing.gguf"

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="local_path",
            explicit_path=model_path,
            model_format="gguf",
            backend="llama_cpp",
        )
    )

    assert availability.status is LocalModelAvailabilityStatus.MISSING
    assert availability.resolved_path is None
    assert availability.source is LocalModelAvailabilitySource.NOT_FOUND
    assert str(model_path) in availability.message


def test_check_local_model_availability_reports_invalid_gguf_path(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    model_path = tmp_path / "chat-model.bin"
    model_path.write_text("not gguf", encoding="utf-8")

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="local_path",
            explicit_path=model_path,
            model_format="gguf",
            backend="llama_cpp",
        )
    )

    assert availability.status is LocalModelAvailabilityStatus.INVALID
    assert availability.resolved_path == model_path
    assert ".gguf" in availability.message


def test_check_local_model_availability_does_not_fallback_from_explicit_path(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    cache_root = tmp_path / "cache-root"
    cache_root.mkdir()
    cache_hit = cache_root / "chat-model.gguf"
    cache_hit.write_text("cached", encoding="utf-8")

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="local_path",
            explicit_path=tmp_path / "missing.gguf",
            model_filename="chat-model.gguf",
            model_cache_root=cache_root,
            model_format="gguf",
            backend="llama_cpp",
        )
    )

    assert availability.status is LocalModelAvailabilityStatus.MISSING
    assert availability.resolved_path is None


def test_check_local_model_availability_prefers_explicit_cache_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailabilitySource,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    default_cache_hit = (
        _hub_snapshot_root(
            home_dir,
            "Qwen/Qwen3-4B-GGUF",
            "commit-123",
        )
        / "chat-model.gguf"
    )
    default_cache_hit.parent.mkdir(parents=True)
    default_cache_hit.write_text("default", encoding="utf-8")
    refs_main = default_cache_hit.parents[2] / "refs" / "main"
    refs_main.parent.mkdir(parents=True)
    refs_main.write_text("commit-123", encoding="utf-8")
    explicit_cache_root = tmp_path / "explicit-cache-root"
    explicit_cache_root.mkdir()
    explicit_cache_hit = explicit_cache_root / "chat-model.gguf"
    explicit_cache_hit.write_text("explicit", encoding="utf-8")

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="hugging_face",
            repo_id="Qwen/Qwen3-4B-GGUF",
            filename="chat-model.gguf",
            model_cache_root=explicit_cache_root,
            model_format="gguf",
            backend="llama_cpp",
        )
    )

    assert availability.status is LocalModelAvailabilityStatus.AVAILABLE
    assert availability.resolved_path == explicit_cache_hit
    assert availability.cache_root == explicit_cache_root
    assert availability.source is LocalModelAvailabilitySource.EXPLICIT_CACHE_ROOT


def test_check_local_model_availability_uses_default_cache_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailabilitySource,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    default_cache_hit = (
        _hub_snapshot_root(
            home_dir,
            "Qwen/Qwen3-4B-GGUF",
            "commit-123",
        )
        / "chat-model.gguf"
    )
    default_cache_hit.parent.mkdir(parents=True)
    default_cache_hit.write_text("default", encoding="utf-8")
    refs_main = default_cache_hit.parents[2] / "refs" / "main"
    refs_main.parent.mkdir(parents=True)
    refs_main.write_text("commit-123", encoding="utf-8")

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="hugging_face",
            repo_id="Qwen/Qwen3-4B-GGUF",
            filename="chat-model.gguf",
            model_format="gguf",
            backend="llama_cpp",
        )
    )

    assert availability.status is LocalModelAvailabilityStatus.AVAILABLE
    assert availability.resolved_path == default_cache_hit
    assert availability.cache_root == _default_cache_root(home_dir)
    assert availability.source is LocalModelAvailabilitySource.DEFAULT_CACHE_ROOT


def test_check_local_model_availability_skips_metadata_when_disabled() -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    metadata_calls: list[LocalModelAssetReference] = []
    reference = LocalModelAssetReference(
        provider="hugging_face",
        repo_id="Qwen/Qwen3-4B-GGUF",
        filename="chat-model.gguf",
        model_format="gguf",
        backend="llama_cpp",
    )

    availability = check_local_model_availability(
        reference,
        metadata_lookup=metadata_calls.append,
    )

    assert availability.status is LocalModelAvailabilityStatus.MISSING
    assert metadata_calls == []


def test_check_local_model_availability_reports_would_download_from_metadata() -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailabilityStatus,
        LocalModelRemoteMetadata,
        check_local_model_availability,
    )

    reference = LocalModelAssetReference(
        provider="hugging_face",
        repo_id="Qwen/Qwen3-4B-GGUF",
        filename="chat-model.gguf",
        model_format="gguf",
        backend="llama_cpp",
    )

    availability = check_local_model_availability(
        reference,
        allow_network_metadata=True,
        metadata_lookup=lambda _: LocalModelRemoteMetadata(
            exists=True,
            size_bytes=8_300_000_000,
            message="remote file exists",
            warnings=("large download",),
        ),
    )

    assert availability.status is LocalModelAvailabilityStatus.WOULD_DOWNLOAD
    assert availability.size_bytes == 8_300_000_000
    assert availability.message == "remote file exists"
    assert availability.warnings == ("large download",)


def test_check_local_model_availability_reports_invalid_remote_metadata() -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailabilityStatus,
        LocalModelRemoteMetadata,
        check_local_model_availability,
    )

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="hugging_face",
            repo_id="Qwen/Qwen3-4B-GGUF",
            filename="missing.gguf",
        ),
        allow_network_metadata=True,
        metadata_lookup=lambda _: LocalModelRemoteMetadata(
            exists=False,
            message="remote file is missing",
        ),
    )

    assert availability.status is LocalModelAvailabilityStatus.INVALID
    assert availability.message == "remote file is missing"


def test_check_local_model_availability_reports_unknown_metadata_failure() -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    def failing_metadata(_: LocalModelAssetReference) -> object:
        raise RuntimeError("metadata unavailable")

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="hugging_face",
            repo_id="Qwen/Qwen3-4B-GGUF",
            filename="chat-model.gguf",
        ),
        allow_network_metadata=True,
        metadata_lookup=failing_metadata,
    )

    assert availability.status is LocalModelAvailabilityStatus.UNKNOWN
    assert "metadata unavailable" in availability.message


def test_resolve_local_model_path_prefers_explicit_local_path_over_cache_and_hub(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    explicit_model_path = tmp_path / "explicit" / "chat-model.gguf"
    explicit_model_path.parent.mkdir(parents=True)
    explicit_model_path.write_text("explicit-model", encoding="utf-8")

    cache_root = tmp_path / "cache-root"
    cache_root.mkdir()
    (cache_root / "chat-model.gguf").write_text("cached-model", encoding="utf-8")

    config = LocalModelPathConfig(
        model_filename="chat-model.gguf",
        explicit_model_path=explicit_model_path,
        model_cache_root=cache_root,
        huggingface_file=HuggingFaceModelFileReference(
            repo_id="Qwen/Qwen3-4B-GGUF",
            filename="chat-model.gguf",
        ),
    )

    download_calls: list[tuple[object, Path]] = []

    def fake_download(reference: object, target_cache_root: Path) -> Path:
        download_calls.append((reference, target_cache_root))
        return target_cache_root / "downloaded.gguf"

    resolved_path = resolve_local_model_path(config, download_file=fake_download)

    assert resolved_path == explicit_model_path
    assert download_calls == []


def test_resolve_local_model_path_uses_declared_default_hub_file_snapshot_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    repo_id = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
    snapshot_root = _hub_snapshot_root(home_dir, repo_id, "commit-123")
    cached_model = snapshot_root / "model.safetensors"
    cached_model.parent.mkdir(parents=True)
    cached_model.write_text("cached", encoding="utf-8")
    sentinel = home_dir / ".ollama" / "models" / "sentinel"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("untouched", encoding="utf-8")
    download_calls: list[object] = []
    ollama_accesses = _guard_ollama_access(monkeypatch, home_dir)

    resolved = resolve_local_model_path(
        LocalModelPathConfig(
            model_filename="model.safetensors",
            huggingface_file=HuggingFaceModelFileReference(
                repo_id=repo_id,
                filename="model.safetensors",
                revision="commit-123",
            ),
        ),
        allow_network=False,
        download_file=lambda *_: download_calls.append("download"),  # type: ignore[arg-type]
    )

    assert resolved == cached_model
    assert download_calls == []
    assert ollama_accesses == []


def test_check_local_model_availability_uses_declared_default_hub_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        LocalModelAssetReference,
        LocalModelAvailabilitySource,
        LocalModelAvailabilityStatus,
        check_local_model_availability,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    repo_id = "Qwen/Qwen2.5-3B-Instruct-GGUF"
    cached_model = _hub_snapshot_root(home_dir, repo_id, "commit-123") / "chat.gguf"
    cached_model.parent.mkdir(parents=True)
    cached_model.write_text("cached", encoding="utf-8")

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="hugging_face",
            repo_id=repo_id,
            filename="chat.gguf",
            revision="commit-123",
            backend="llama_cpp",
        )
    )

    assert availability.status is LocalModelAvailabilityStatus.AVAILABLE
    assert availability.source is LocalModelAvailabilitySource.DEFAULT_CACHE_ROOT
    assert availability.resolved_path == cached_model


def test_resolve_local_model_path_uses_declared_symbolic_hub_snapshot_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        HuggingFaceSnapshotReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    repo_id = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
    cached_model = (
        _hub_snapshot_root(home_dir, repo_id, "commit-123") / "model.safetensors"
    )
    cached_model.parent.mkdir(parents=True)
    cached_model.write_text("cached", encoding="utf-8")
    ref_path = cached_model.parents[2] / "refs" / "main"
    ref_path.parent.mkdir(parents=True)
    ref_path.write_text("commit-123", encoding="utf-8")

    resolved = resolve_local_model_path(
        LocalModelPathConfig(
            model_filename="model.safetensors",
            huggingface_snapshot=HuggingFaceSnapshotReference(
                repo_id=repo_id,
                revision="main",
            ),
        ),
        allow_network=False,
    )

    assert resolved == cached_model


def test_resolve_local_model_path_rejects_default_hub_cross_repo_alias_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.errors import LocalModelOfflinePolicyError
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    foreign_model = (
        _hub_snapshot_root(
            home_dir,
            "other-org/other-model",
            "commit-123",
        )
        / "chat.gguf"
    )
    foreign_model.parent.mkdir(parents=True)
    foreign_model.write_text("foreign", encoding="utf-8")
    flat_alias = _default_cache_root(home_dir) / "chat.gguf"
    flat_alias.write_text("flat", encoding="utf-8")
    download_calls: list[object] = []

    with pytest.raises(LocalModelOfflinePolicyError):
        resolve_local_model_path(
            LocalModelPathConfig(
                model_filename="chat.gguf",
                huggingface_file=HuggingFaceModelFileReference(
                    repo_id="wanted-org/wanted-model",
                    filename="chat.gguf",
                    revision="commit-123",
                ),
            ),
            allow_network=False,
            download_file=lambda *_: download_calls.append("download"),  # type: ignore[arg-type]
        )

    assert download_calls == []


def test_default_hub_symlinked_repository_never_aliases_a_foreign_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.errors import LocalModelOfflinePolicyError
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelAssetReference,
        LocalModelAvailabilityStatus,
        LocalModelPathConfig,
        check_local_model_availability,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    foreign_model = (
        _hub_snapshot_root(
            home_dir,
            "foreign-org/foreign-model",
            "commit-123",
        )
        / "chat.gguf"
    )
    foreign_model.parent.mkdir(parents=True)
    foreign_model.write_text("foreign", encoding="utf-8")
    declared_repository_root = (
        _default_cache_root(home_dir) / "models--declared-org--declared-model"
    )
    declared_repository_root.symlink_to(
        foreign_model.parents[2],
        target_is_directory=True,
    )
    reference = HuggingFaceModelFileReference(
        repo_id="declared-org/declared-model",
        filename="chat.gguf",
        revision="commit-123",
    )
    download_calls: list[object] = []

    with pytest.raises(LocalModelOfflinePolicyError):
        resolve_local_model_path(
            LocalModelPathConfig(
                model_filename="chat.gguf",
                huggingface_file=reference,
            ),
            allow_network=False,
            download_file=lambda *_: download_calls.append("download"),  # type: ignore[arg-type]
        )

    availability = check_local_model_availability(
        LocalModelAssetReference(
            provider="hugging_face",
            repo_id=reference.repo_id,
            filename=reference.filename,
            revision=reference.revision,
            backend="llama_cpp",
        )
    )

    assert availability.status is LocalModelAvailabilityStatus.MISSING
    assert download_calls == []


def test_resolve_local_model_path_rejects_escaping_hub_snapshot_file_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.errors import LocalModelOfflinePolicyError
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    repo_id = "Qwen/Qwen2.5-3B-Instruct-GGUF"
    outside = tmp_path / "outside.gguf"
    outside.write_text("outside", encoding="utf-8")
    cached_model = _hub_snapshot_root(home_dir, repo_id, "commit-123") / "chat.gguf"
    cached_model.parent.mkdir(parents=True)
    cached_model.symlink_to(outside)

    with pytest.raises(LocalModelOfflinePolicyError):
        resolve_local_model_path(
            LocalModelPathConfig(
                model_filename="chat.gguf",
                huggingface_file=HuggingFaceModelFileReference(
                    repo_id=repo_id,
                    filename="chat.gguf",
                    revision="commit-123",
                ),
            ),
            allow_network=False,
        )


@pytest.mark.parametrize(
    ("repo_id", "filename"),
    [
        ("wanted-org/./wanted-model", "chat.gguf"),
        ("wanted-org/wanted-model", "./chat.gguf"),
        ("wanted-org/wanted-model", "chat\x00.gguf"),
    ],
)
def test_resolve_local_model_path_rejects_malformed_hub_cache_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repo_id: str,
    filename: str,
) -> None:
    from dynamic_agent_runner.errors import LocalModelOfflinePolicyError
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    download_calls: list[object] = []

    with pytest.raises(LocalModelOfflinePolicyError):
        resolve_local_model_path(
            LocalModelPathConfig(
                model_filename=filename,
                huggingface_file=HuggingFaceModelFileReference(
                    repo_id=repo_id,
                    filename=filename,
                    revision="commit-123",
                ),
            ),
            allow_network=False,
            download_file=lambda *_: download_calls.append("download"),  # type: ignore[arg-type]
        )

    assert download_calls == []


def test_list_local_model_assets_scans_only_default_hub_snapshots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.local_models import list_local_model_assets

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    repo_id = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
    snapshot_root = _hub_snapshot_root(home_dir, repo_id, "commit-123")
    for filename in ("config.json", "tokenizer.model", "weights.npz"):
        path = snapshot_root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(filename, encoding="utf-8")
    ignored_blob = (
        _default_cache_root(home_dir)
        / f"models--{repo_id.replace('/', '--')}"
        / "blobs"
        / "weights.npz"
    )
    ignored_blob.parent.mkdir(parents=True)
    ignored_blob.write_text("not an inventory root", encoding="utf-8")
    sentinel = home_dir / ".ollama" / "models" / "sentinel"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("untouched", encoding="utf-8")
    ollama_accesses = _guard_ollama_access(monkeypatch, home_dir)

    inventory = list_local_model_assets()

    assert [asset.path for asset in inventory.assets] == [snapshot_root]
    assert ollama_accesses == []


def test_default_hub_inventory_ignores_escaping_mlx_required_file_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.local_models import list_local_model_assets

    home_dir = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    snapshot_root = _hub_snapshot_root(
        home_dir,
        "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
        "commit-123",
    )
    snapshot_root.mkdir(parents=True)
    (snapshot_root / "config.json").write_text("{}", encoding="utf-8")
    (snapshot_root / "weights.npz").write_text("weights", encoding="utf-8")
    outside_tokenizer = tmp_path / "outside-tokenizer.model"
    outside_tokenizer.write_text("outside", encoding="utf-8")
    (snapshot_root / "tokenizer.model").symlink_to(outside_tokenizer)

    inventory = list_local_model_assets()

    assert inventory.assets == ()


def test_resolve_local_model_path_prefers_explicit_cache_root_over_default_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))

    default_cache_hit = (
        _hub_snapshot_root(
            home_dir,
            "Qwen/Qwen3-4B-GGUF",
            "commit-123",
        )
        / "chat-model.gguf"
    )
    default_cache_hit.parent.mkdir(parents=True)
    default_cache_hit.write_text("default-cache-model", encoding="utf-8")
    refs_main = default_cache_hit.parents[2] / "refs" / "main"
    refs_main.parent.mkdir(parents=True)
    refs_main.write_text("commit-123", encoding="utf-8")

    explicit_cache_root = tmp_path / "explicit-cache-root"
    explicit_cache_root.mkdir()
    explicit_cache_hit = explicit_cache_root / "chat-model.gguf"
    explicit_cache_hit.write_text("explicit-cache-model", encoding="utf-8")

    config = LocalModelPathConfig(
        model_filename="chat-model.gguf",
        model_cache_root=explicit_cache_root,
        huggingface_file=HuggingFaceModelFileReference(
            repo_id="Qwen/Qwen3-4B-GGUF",
            filename="chat-model.gguf",
        ),
    )

    download_calls: list[tuple[object, Path]] = []

    def fake_download(reference: object, target_cache_root: Path) -> Path:
        download_calls.append((reference, target_cache_root))
        return target_cache_root / "downloaded.gguf"

    resolved_path = resolve_local_model_path(config, download_file=fake_download)

    assert resolved_path == explicit_cache_hit
    assert download_calls == []


def test_resolve_local_model_path_prefers_default_cache_root_over_hub_download(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))

    default_cache_hit = (
        _hub_snapshot_root(
            home_dir,
            "Qwen/Qwen3-4B-GGUF",
            "commit-123",
        )
        / "chat-model.gguf"
    )
    default_cache_hit.parent.mkdir(parents=True)
    default_cache_hit.write_text("default-cache-model", encoding="utf-8")
    refs_main = default_cache_hit.parents[2] / "refs" / "main"
    refs_main.parent.mkdir(parents=True)
    refs_main.write_text("commit-123", encoding="utf-8")

    explicit_cache_root = tmp_path / "empty-explicit-cache-root"
    explicit_cache_root.mkdir()

    config = LocalModelPathConfig(
        model_filename="chat-model.gguf",
        model_cache_root=explicit_cache_root,
        huggingface_file=HuggingFaceModelFileReference(
            repo_id="Qwen/Qwen3-4B-GGUF",
            filename="chat-model.gguf",
        ),
    )

    download_calls: list[tuple[object, Path]] = []

    def fake_download(reference: object, target_cache_root: Path) -> Path:
        download_calls.append((reference, target_cache_root))
        return target_cache_root / "downloaded.gguf"

    resolved_path = resolve_local_model_path(config, download_file=fake_download)

    assert resolved_path == default_cache_hit
    assert download_calls == []


def test_resolve_local_model_path_falls_back_to_hub_reference_after_local_misses(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))

    explicit_cache_root = tmp_path / "empty-explicit-cache-root"
    explicit_cache_root.mkdir()
    hub_reference = HuggingFaceModelFileReference(
        repo_id="Qwen/Qwen3-4B-GGUF",
        filename="chat-model.gguf",
        revision="main",
    )

    config = LocalModelPathConfig(
        model_filename="chat-model.gguf",
        model_cache_root=explicit_cache_root,
        huggingface_file=hub_reference,
    )

    download_calls: list[tuple[object, Path]] = []
    downloaded_path = _default_cache_root(home_dir) / "downloads" / "chat-model.gguf"
    downloaded_path.parent.mkdir(parents=True)

    def fake_download(reference: object, target_cache_root: Path) -> Path:
        download_calls.append((reference, target_cache_root))
        downloaded_path.write_text("downloaded-model", encoding="utf-8")
        return downloaded_path

    resolved_path = resolve_local_model_path(config, download_file=fake_download)

    assert resolved_path == downloaded_path
    assert download_calls == [(hub_reference, _default_cache_root(home_dir))]


def test_resolve_local_model_path_blocks_hub_download_when_offline_policy_disallows_network(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dynamic_agent_runner.errors import LocalModelOfflinePolicyError
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))

    explicit_cache_root = tmp_path / "empty-explicit-cache-root"
    explicit_cache_root.mkdir()
    hub_reference = HuggingFaceModelFileReference(
        repo_id="Qwen/Qwen3-4B-GGUF",
        filename="chat-model.gguf",
        revision="main",
    )
    config = LocalModelPathConfig(
        model_filename="chat-model.gguf",
        model_cache_root=explicit_cache_root,
        huggingface_file=hub_reference,
    )

    download_calls: list[tuple[object, Path]] = []

    def fake_download(reference: object, target_cache_root: Path) -> Path:
        download_calls.append((reference, target_cache_root))
        return target_cache_root / "downloaded.gguf"

    with pytest.raises(
        LocalModelOfflinePolicyError, match="offline.*chat-model\\.gguf"
    ):
        resolve_local_model_path(
            config,
            allow_network=False,
            download_file=fake_download,
        )

    assert download_calls == []


def test_resolve_local_model_path_classifies_invalid_hub_reference_as_resolution_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dynamic_agent_runner.errors import LocalModelResolutionError
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))

    explicit_cache_root = tmp_path / "empty-explicit-cache-root"
    explicit_cache_root.mkdir()
    hub_reference = HuggingFaceModelFileReference(
        repo_id="Qwen/Qwen3-4B-GGUF",
        filename="missing-chat-model.gguf",
        revision="main",
    )
    config = LocalModelPathConfig(
        model_filename="missing-chat-model.gguf",
        model_cache_root=explicit_cache_root,
        huggingface_file=hub_reference,
    )

    def fake_download(reference: object, target_cache_root: Path) -> Path:
        raise FileNotFoundError(
            f"missing remote asset for {reference!r} in {target_cache_root}"
        )

    with pytest.raises(
        LocalModelResolutionError,
        match="missing-chat-model\\.gguf",
    ):
        resolve_local_model_path(config, download_file=fake_download)


def test_resolve_local_model_path_classifies_cache_miss_without_remote_reference_as_resolution_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from dynamic_agent_runner.errors import LocalModelResolutionError
    from dynamic_agent_runner.local_models import (
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))

    explicit_cache_root = tmp_path / "empty-explicit-cache-root"
    explicit_cache_root.mkdir()
    config = LocalModelPathConfig(
        model_filename="chat-model.gguf",
        model_cache_root=explicit_cache_root,
    )

    with pytest.raises(LocalModelResolutionError, match="chat-model\\.gguf"):
        resolve_local_model_path(config)


def test_validate_local_model_identity_classifies_model_mismatch_with_runtime_owned_identity() -> (
    None
):
    from dynamic_agent_runner.errors import LocalModelIdentityMismatchError
    from dynamic_agent_runner.local_models import validate_local_model_identity

    with pytest.raises(
        LocalModelIdentityMismatchError,
        match="local-qwen-chat.*Qwen/Qwen3-4B-Instruct-2507.*llama-2-7b-chat",
    ):
        validate_local_model_identity(
            requested_model="local-qwen-chat",
            expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
            observed_model_id="llama-2-7b-chat",
        )


def test_validate_local_model_identity_reports_explicit_local_path_metadata() -> None:
    from dynamic_agent_runner.errors import LocalModelIdentityMismatchError
    from dynamic_agent_runner.local_models import validate_local_model_identity

    with pytest.raises(
        LocalModelIdentityMismatchError,
        match="local-qwen-chat.*Qwen/Qwen3-4B-Instruct-2507.*models/chat-model\\.gguf.*llama-2-7b-chat",
    ):
        validate_local_model_identity(
            requested_model="local-qwen-chat",
            expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
            observed_model_id="llama-2-7b-chat",
            explicit_model_path=Path("/models/chat-model.gguf"),
        )


def test_validate_local_model_identity_reports_hub_file_reference_metadata() -> None:
    from dynamic_agent_runner.errors import LocalModelIdentityMismatchError
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        validate_local_model_identity,
    )

    with pytest.raises(
        LocalModelIdentityMismatchError,
        match="local-qwen-chat.*Qwen/Qwen3-4B-Instruct-2507.*Qwen/Qwen3-4B-GGUF.*chat-model\\.gguf.*main.*llama-2-7b-chat",
    ):
        validate_local_model_identity(
            requested_model="local-qwen-chat",
            expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
            observed_model_id="llama-2-7b-chat",
            huggingface_file=HuggingFaceModelFileReference(
                repo_id="Qwen/Qwen3-4B-GGUF",
                filename="chat-model.gguf",
                revision="main",
            ),
        )


def test_local_openai_adapter_validates_observed_model_against_expected_identity() -> (
    None
):
    from dynamic_agent_runner.errors import LocalModelIdentityMismatchError
    from dynamic_agent_runner.local_models import (
        LocalOpenAIEndpointConfig,
        create_local_openai_adapter,
    )
    from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request

    adapter = create_local_openai_adapter(
        LocalOpenAIEndpointConfig(
            base_url="http://localhost:11434/v1",
            model_aliases=["local-qwen-chat"],
            provider_name="llama.cpp",
            expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
        )
    )
    adapter._client = _StaticClient(
        {
            "id": "resp_1",
            "model": "llama-2-7b-chat",
            "output_text": "hello from the wrong model",
        }
    )

    request = build_openai_request(
        model="local-qwen-chat",
        messages=[OpenAIMessage("user", "Hello")],
    )

    with pytest.raises(
        LocalModelIdentityMismatchError,
        match="local-qwen-chat.*Qwen/Qwen3-4B-Instruct-2507.*llama-2-7b-chat",
    ):
        adapter.create_response(request)


def test_local_openai_adapter_translates_endpoint_connectivity_failures() -> None:
    from dynamic_agent_runner.errors import LocalModelEndpointConnectivityError
    from dynamic_agent_runner.local_models import (
        LocalOpenAIEndpointConfig,
        create_local_openai_adapter,
    )
    from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request

    adapter = create_local_openai_adapter(
        LocalOpenAIEndpointConfig(
            base_url="http://localhost:11434/v1",
            model_aliases=["local-qwen-chat"],
            provider_name="llama.cpp",
        )
    )
    adapter._client = _FailingClient(ConnectionError("connection refused"))

    request = build_openai_request(
        model="local-qwen-chat",
        messages=[OpenAIMessage("user", "Hello")],
    )

    with pytest.raises(
        LocalModelEndpointConnectivityError,
        match="localhost:11434/v1.*connection refused",
    ):
        adapter.create_response(request)


def test_local_openai_endpoint_disables_default_auth_discovery() -> None:
    """A loopback model endpoint must not inherit Codex or API-key auth."""

    from dynamic_agent_runner.local_models import (
        LocalOpenAIEndpointConfig,
        _provider_config_from_local_endpoint,
    )

    provider = _provider_config_from_local_endpoint(
        LocalOpenAIEndpointConfig(
            base_url="http://localhost:11434/v1",
            model_aliases=["local-qwen-chat"],
        )
    )

    assert provider.base_url == "http://localhost:11434/v1"
    assert provider.api_key == "local-endpoint"
    assert provider.provider_name == "openai"
    assert provider.discover_default_auth is False


def test_local_async_openai_adapter_translates_endpoint_protocol_failures() -> None:
    from dynamic_agent_runner.errors import LocalModelEndpointProtocolError
    from dynamic_agent_runner.local_models import (
        LocalOpenAIEndpointConfig,
        create_local_async_openai_adapter,
    )
    from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request

    adapter = create_local_async_openai_adapter(
        LocalOpenAIEndpointConfig(
            base_url="http://localhost:11434/v1",
            model_aliases=["local-qwen-chat"],
            provider_name="llama.cpp",
        )
    )
    adapter._client = _FailingAsyncClient(RuntimeError("unexpected response schema"))

    request = build_openai_request(
        model="local-qwen-chat",
        messages=[OpenAIMessage("user", "Hello")],
    )

    with pytest.raises(
        LocalModelEndpointProtocolError,
        match="localhost:11434/v1.*unexpected response schema",
    ):
        asyncio.run(adapter.create_response(request))


def test_resolve_local_model_path_uses_default_hub_file_download_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        HuggingFaceModelFileReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))

    explicit_cache_root = tmp_path / "empty-explicit-cache-root"
    explicit_cache_root.mkdir()
    hub_reference = HuggingFaceModelFileReference(
        repo_id="Qwen/Qwen3-4B-GGUF",
        filename="chat-model.gguf",
        revision="main",
    )
    config = LocalModelPathConfig(
        model_filename="chat-model.gguf",
        model_cache_root=explicit_cache_root,
        huggingface_file=hub_reference,
    )

    download_calls: list[tuple[object, Path]] = []
    downloaded_path = _default_cache_root(home_dir) / "downloads" / "chat-model.gguf"
    downloaded_path.parent.mkdir(parents=True)

    def fake_default_file_download(reference: object, target_cache_root: Path) -> Path:
        download_calls.append((reference, target_cache_root))
        downloaded_path.write_text("downloaded-model", encoding="utf-8")
        return downloaded_path

    def fake_default_snapshot_download(_: object, __: Path) -> Path:
        raise AssertionError("snapshot helper should not be used for file references")

    monkeypatch.setattr(
        "dynamic_agent_runner.local_models._load_huggingface_download_helpers",
        lambda: (fake_default_file_download, fake_default_snapshot_download),
    )

    resolved_path = resolve_local_model_path(config)

    assert resolved_path == downloaded_path
    assert download_calls == [(hub_reference, _default_cache_root(home_dir))]


def test_resolve_local_model_path_uses_default_hub_snapshot_download_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.local_models import (
        HuggingFaceSnapshotReference,
        LocalModelPathConfig,
        resolve_local_model_path,
    )

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))

    explicit_cache_root = tmp_path / "empty-explicit-cache-root"
    explicit_cache_root.mkdir()
    hub_reference = HuggingFaceSnapshotReference(
        repo_id="Qwen/Qwen3-4B-GGUF",
        revision="main",
    )
    config = LocalModelPathConfig(
        model_filename="chat-model.gguf",
        model_cache_root=explicit_cache_root,
        huggingface_snapshot=hub_reference,
    )

    download_calls: list[tuple[object, Path]] = []
    snapshot_root = _default_cache_root(home_dir) / "snapshots" / "qwen"
    snapshot_root.mkdir(parents=True)
    expected_path = snapshot_root / "chat-model.gguf"
    expected_path.write_text("downloaded-model", encoding="utf-8")

    def fake_default_file_download(_: object, __: Path) -> Path:
        raise AssertionError("file helper should not be used for snapshot references")

    def fake_default_snapshot_download(
        reference: object,
        target_cache_root: Path,
    ) -> Path:
        download_calls.append((reference, target_cache_root))
        return snapshot_root

    monkeypatch.setattr(
        "dynamic_agent_runner.local_models._load_huggingface_download_helpers",
        lambda: (fake_default_file_download, fake_default_snapshot_download),
    )

    resolved_path = resolve_local_model_path(config)

    assert resolved_path == expected_path
    assert download_calls == [(hub_reference, _default_cache_root(home_dir))]


def test_llama_cpp_local_config_and_factories_are_package_exports() -> None:
    import dynamic_agent_runner

    assert dynamic_agent_runner.LlamaCppLocalModelConfig is not None
    assert dynamic_agent_runner.create_llama_cpp_local_adapter is not None
    assert dynamic_agent_runner.create_llama_cpp_local_async_adapter is not None


def test_llama_cpp_memory_fit_contract_and_exports_are_available() -> None:
    import dynamic_agent_runner
    from dynamic_agent_runner.errors import LlamaCppMemoryFitProfileError
    from dynamic_agent_runner.local_models import (
        LlamaCppMemoryFitMeasurement,
        LlamaCppMemoryFitProfileResult,
        LlamaCppMemoryFitStatus,
        profile_llama_cpp_model_memory_fit,
    )

    measurement = LlamaCppMemoryFitMeasurement(
        resident_bytes=4_000_000_000,
        context_bytes_per_1k_tokens=250_000_000,
        memory_budget_bytes=6_000_000_000,
        diagnostics=("fake evaluator",),
    )
    result = LlamaCppMemoryFitProfileResult(
        model_path=Path("model.gguf"),
        status=LlamaCppMemoryFitStatus.FITS,
        resident_bytes=measurement.resident_bytes,
        context_bytes_per_1k_tokens=measurement.context_bytes_per_1k_tokens,
        memory_budget_bytes=measurement.memory_budget_bytes,
        requested_context_tokens=4096,
        requested_context_fits=True,
        maximum_usable_context_tokens=8000,
        supported_context_tiers=(4096, 8192),
        estimated_memory_by_context_tier={4096: 5_024_000_000},
        suggested_model_kwargs={"n_ctx": 4096},
        diagnostics=measurement.diagnostics,
        partial=False,
    )

    assert LlamaCppMemoryFitStatus.FITS.value == "fits"
    assert LlamaCppMemoryFitStatus.TOO_LARGE.value == "too_large"
    assert LlamaCppMemoryFitStatus.UNKNOWN.value == "unknown"
    assert LlamaCppMemoryFitStatus.UNAVAILABLE.value == "unavailable"
    assert LlamaCppMemoryFitStatus.FAILED_OPEN.value == "failed_open"
    assert result.status is LlamaCppMemoryFitStatus.FITS
    assert profile_llama_cpp_model_memory_fit is not None
    assert issubclass(
        LlamaCppMemoryFitProfileError, dynamic_agent_runner.LocalModelError
    )
    assert dynamic_agent_runner.LlamaCppMemoryFitMeasurement is (
        LlamaCppMemoryFitMeasurement
    )
    assert dynamic_agent_runner.LlamaCppMemoryFitProfileResult is (
        LlamaCppMemoryFitProfileResult
    )
    assert dynamic_agent_runner.LlamaCppMemoryFitStatus is LlamaCppMemoryFitStatus
    assert dynamic_agent_runner.profile_llama_cpp_model_memory_fit is (
        profile_llama_cpp_model_memory_fit
    )


def test_llama_cpp_memory_fit_profiles_resolved_local_path(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        LlamaCppMemoryFitMeasurement,
        LlamaCppMemoryFitStatus,
        profile_llama_cpp_model_memory_fit,
    )

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")
    calls: list[Path] = []

    def fake_profiler(path: Path) -> LlamaCppMemoryFitMeasurement:
        calls.append(path)
        return LlamaCppMemoryFitMeasurement(
            resident_bytes=4_000_000_000,
            context_bytes_per_1k_tokens=250_000_000,
            memory_budget_bytes=6_000_000_000,
            diagnostics=("profiled",),
        )

    result = profile_llama_cpp_model_memory_fit(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
        profiler=fake_profiler,
    )

    assert calls == [model_path]
    assert result.model_path == model_path
    assert result.status is LlamaCppMemoryFitStatus.UNKNOWN
    assert result.resident_bytes == 4_000_000_000
    assert result.context_bytes_per_1k_tokens == 250_000_000
    assert result.memory_budget_bytes == 6_000_000_000
    assert result.diagnostics == ("profiled",)


def test_llama_cpp_memory_fit_missing_profiler_is_fail_open(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        LlamaCppMemoryFitStatus,
        profile_llama_cpp_model_memory_fit,
    )

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")

    result = profile_llama_cpp_model_memory_fit(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        )
    )

    assert result.model_path == model_path
    assert result.status is LlamaCppMemoryFitStatus.UNAVAILABLE
    assert result.suggested_model_kwargs is None
    assert "unavailable" in " ".join(result.diagnostics)


def test_llama_cpp_memory_fit_missing_profiler_raises_in_strict_mode(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.errors import LlamaCppMemoryFitProfileError
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        profile_llama_cpp_model_memory_fit,
    )

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")

    with pytest.raises(LlamaCppMemoryFitProfileError, match="unavailable"):
        profile_llama_cpp_model_memory_fit(
            LlamaCppLocalModelConfig(
                model_aliases=("llama-local-chat",),
                model_path=model_path,
            ),
            mode="strict",
        )


def test_llama_cpp_memory_fit_estimates_supported_context_and_kwargs(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        LlamaCppMemoryFitMeasurement,
        LlamaCppMemoryFitStatus,
        profile_llama_cpp_model_memory_fit,
    )

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")

    result = profile_llama_cpp_model_memory_fit(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
        requested_context_tokens=4096,
        context_tiers=(4096, 8192, 16384),
        profiler=lambda _: LlamaCppMemoryFitMeasurement(
            resident_bytes=4_000_000_000,
            context_bytes_per_1k_tokens=250_000_000,
            memory_budget_bytes=6_000_000_000,
            diagnostics=("profiled",),
        ),
    )

    assert result.status is LlamaCppMemoryFitStatus.FITS
    assert result.requested_context_fits is True
    assert result.maximum_usable_context_tokens == 8000
    assert result.supported_context_tiers == (4096,)
    assert result.estimated_memory_by_context_tier == {
        4096: 5_024_000_000,
        8192: 6_048_000_000,
        16384: 8_096_000_000,
    }
    assert result.suggested_model_kwargs == {"n_ctx": 4096}
    assert result.partial is False


def test_llama_cpp_memory_fit_suggests_lower_context_when_requested_is_too_large(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        LlamaCppMemoryFitMeasurement,
        LlamaCppMemoryFitStatus,
        profile_llama_cpp_model_memory_fit,
    )

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")

    result = profile_llama_cpp_model_memory_fit(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
        requested_context_tokens=16_384,
        memory_budget_bytes=6_000_000_000,
        profiler=lambda _: LlamaCppMemoryFitMeasurement(
            resident_bytes=4_000_000_000,
            context_bytes_per_1k_tokens=250_000_000,
            memory_budget_bytes=8_000_000_000,
        ),
    )

    assert result.status is LlamaCppMemoryFitStatus.TOO_LARGE
    assert result.requested_context_fits is False
    assert result.maximum_usable_context_tokens == 8000
    assert result.suggested_model_kwargs == {"n_ctx": 8000}


def test_llama_cpp_memory_fit_without_budget_remains_unknown_and_partial(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        LlamaCppMemoryFitMeasurement,
        LlamaCppMemoryFitStatus,
        profile_llama_cpp_model_memory_fit,
    )

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")

    result = profile_llama_cpp_model_memory_fit(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
        profiler=lambda _: LlamaCppMemoryFitMeasurement(
            resident_bytes=4_000_000_000,
            context_bytes_per_1k_tokens=250_000_000,
        ),
    )

    assert result.status is LlamaCppMemoryFitStatus.UNKNOWN
    assert result.partial is True
    assert result.requested_context_fits is None
    assert result.maximum_usable_context_tokens is None
    assert result.suggested_model_kwargs is None


def test_create_llama_cpp_local_adapter_advertises_aliases_without_loading_dependency(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        create_llama_cpp_local_adapter,
    )

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")
    backend = _FakeLlamaCppBackend()

    adapter = create_llama_cpp_local_adapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
            expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
        ),
        backend=backend,
    )

    assert adapter.models == ("llama-local-chat",)
    assert adapter.is_local is True


def test_llama_cpp_local_adapter_resolves_model_and_normalizes_chat_response(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        create_llama_cpp_local_adapter,
    )
    from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")
    backend = _FakeLlamaCppBackend()
    adapter = create_llama_cpp_local_adapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
            expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
        ),
        backend=backend,
    )

    response = adapter.create_response(
        build_openai_request(
            model="llama-local-chat",
            messages=[OpenAIMessage("user", "Hello")],
        )
    )

    assert response.content == "hello from llama.cpp"
    assert response.raw == backend.response
    assert backend.calls == [
        {
            "messages": [{"role": "user", "content": "Hello"}],
            "tools": None,
            "response_format": None,
        }
    ]


def test_llama_cpp_local_adapter_translates_missing_dependency(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.errors import ModelExecutionError
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        create_llama_cpp_local_adapter,
    )
    from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")

    def failing_loader(_: Path, __: object) -> object:
        raise ImportError("missing llama_cpp")

    adapter = create_llama_cpp_local_adapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
        dependency_loader=failing_loader,
    )

    with pytest.raises(ModelExecutionError, match="llama.cpp dependency unavailable"):
        adapter.create_response(
            build_openai_request(
                model="llama-local-chat",
                messages=[OpenAIMessage("user", "Hello")],
            )
        )


def test_llama_cpp_local_adapter_handles_missing_default_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.errors import ModelExecutionError
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        create_llama_cpp_local_adapter,
    )
    from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")
    real_import = builtins.__import__

    def missing_llama_cpp_import(
        name: str,
        globals_: object | None = None,
        locals_: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "llama_cpp":
            raise ModuleNotFoundError("No module named 'llama_cpp'")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", missing_llama_cpp_import)
    adapter = create_llama_cpp_local_adapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
    )

    with pytest.raises(ModelExecutionError, match="llama.cpp dependency unavailable"):
        adapter.create_response(
            build_openai_request(
                model="llama-local-chat",
                messages=[OpenAIMessage("user", "Hello")],
            )
        )


def test_llama_cpp_local_adapter_translates_backend_generation_failures(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.errors import ModelExecutionError
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        create_llama_cpp_local_adapter,
    )
    from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")
    adapter = create_llama_cpp_local_adapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
        backend=_FailingLlamaCppBackend(),
    )

    with pytest.raises(ModelExecutionError, match="llama.cpp generation failed"):
        adapter.create_response(
            build_openai_request(
                model="llama-local-chat",
                messages=[OpenAIMessage("user", "Hello")],
            )
        )


def test_llama_cpp_local_adapter_validates_backend_identity(tmp_path: Path) -> None:
    from dynamic_agent_runner.errors import LocalModelIdentityMismatchError
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        create_llama_cpp_local_adapter,
    )
    from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")
    backend = _FakeLlamaCppBackend()
    backend.model_id = "wrong-model"
    adapter = create_llama_cpp_local_adapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
            expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
        ),
        backend=backend,
    )

    with pytest.raises(
        LocalModelIdentityMismatchError,
        match="llama-local-chat.*Qwen/Qwen3-4B-Instruct-2507.*wrong-model",
    ):
        adapter.create_response(
            build_openai_request(
                model="llama-local-chat",
                messages=[OpenAIMessage("user", "Hello")],
            )
        )


def test_llama_cpp_local_async_adapter_wraps_sync_generation(tmp_path: Path) -> None:
    from dynamic_agent_runner.local_models import (
        LlamaCppLocalModelConfig,
        create_llama_cpp_local_async_adapter,
    )
    from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request

    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")
    backend = _FakeLlamaCppBackend()
    adapter = create_llama_cpp_local_async_adapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
        backend=backend,
    )

    response = asyncio.run(
        adapter.create_response(
            build_openai_request(
                model="llama-local-chat",
                messages=[OpenAIMessage("user", "Hello")],
            )
        )
    )

    assert response.content == "hello from llama.cpp"
    assert adapter.models == ("llama-local-chat",)
    assert adapter.is_local is True
