from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dynamic_agent_runner import (
    ModelResponse,
    ModelToolCall,
    ModelExecutionError,
    OpenAIModelRequest,
    create_apple_foundation_external_adapter,
    create_llama_cpp_external_adapter,
    create_mlx_async_external_adapter,
    create_mlx_external_adapter,
)
from dynamic_agent_runner.external_adapter import (
    ExternalAdapterCancelledError,
    ExternalAdapterError,
    ExternalAdapterUnavailableError,
    ExternalAdapterValidationError,
    ExternalModelAdapterHealth,
    ExternalModelAdapterFacade,
)
from dynamic_agent_runner.local_models import (
    LlamaCppLocalModelAdapter,
    LlamaCppLocalModelConfig,
)
from dynamic_agent_runner.mlx_models import (
    AsyncMLXLocalModelAdapter,
    MLXLocalModelAdapter,
    MLXLocalModelConfig,
    MLXToolCallCandidate,
    MLXToolCodecResponse,
)


def _request(model: str) -> OpenAIModelRequest:
    return OpenAIModelRequest(
        model=model,
        messages=({"role": "user", "content": "hello"},),
    )


class FakeApple:
    models = ("apple-test",)
    capabilities = {"structured_output": True}

    async def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        return ModelResponse(content="apple")

    def health(self):
        from dynamic_agent_runner.external_adapter import ExternalModelAdapterHealth

        return ExternalModelAdapterHealth("ready")


class SlowApple(FakeApple):
    async def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        await asyncio.sleep(0.05)
        return ModelResponse(content="late")


class SlowHealthApple(FakeApple):
    def health(self):
        import time

        time.sleep(0.05)
        return ExternalModelAdapterHealth("ready")


class LazyClientApple(FakeApple):
    @property
    def client(self):
        raise AssertionError("factory must not trigger lazy native client creation")


class FailingApple(FakeApple):
    async def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        raise ModelExecutionError("secret model path and prompt")


class FakeLlamaBackend:
    def create_chat_completion(self, **kwargs: object) -> object:
        return {"choices": [{"message": {"content": "llama"}}]}


class FakeMLXBackend:
    def generate(self, request: OpenAIModelRequest, **kwargs: object) -> str:
        return "mlx"


class FakeMLXToolBackend(FakeMLXBackend):
    tool_codec_versions = frozenset({"codec-v1"})

    def generate_rendered(self, prompt: str, **kwargs: object) -> str:
        return "tool-output"


class FakeMLXToolCodec:
    version = "codec-v1"

    def render(self, request: OpenAIModelRequest) -> str:
        return "rendered"

    def decode(self, generated: str) -> MLXToolCodecResponse:
        return MLXToolCodecResponse(
            tool_call=MLXToolCallCandidate(
                name="lookup", arguments='{"key":"value"}', id="call-1"
            )
        )


def test_apple_external_adapter_is_async_only_and_omits_callback_tools() -> None:
    adapter = create_apple_foundation_external_adapter(
        FakeApple(), adapter_id="apple.test"
    )
    assert adapter.describe().execution_modes == frozenset({"async"})
    assert "tool_calling" not in adapter.describe().capabilities
    result = asyncio.run(
        ExternalModelAdapterFacade(adapter).create_response_async(
            _request("apple-test")
        )
    )
    assert result.content == "apple"


def test_external_factories_reject_alias_ambiguity_and_invalid_timeout() -> None:
    class MultiAliasApple(FakeApple):
        models = ("one", "two")

    with pytest.raises(ExternalAdapterValidationError):
        create_apple_foundation_external_adapter(
            MultiAliasApple(), adapter_id="apple.test"
        )
    with pytest.raises(ExternalAdapterValidationError):
        create_apple_foundation_external_adapter(
            FakeApple(), adapter_id="apple.test", health_timeout_seconds=121
        )
    create_apple_foundation_external_adapter(
        LazyClientApple(), adapter_id="apple.no-lazy-client"
    )


def test_facade_health_timeout_and_worker_saturation_fail_closed(monkeypatch) -> None:
    timed = create_apple_foundation_external_adapter(
        SlowHealthApple(), adapter_id="apple.slow-health", health_timeout_seconds=0.001
    )
    with pytest.raises(ExternalAdapterUnavailableError, match="health timed out"):
        asyncio.run(
            ExternalModelAdapterFacade(timed).create_response_async(
                _request("apple-test")
            )
        )

    class SaturatedDispatcher:
        def submit(self, *_args, **_kwargs):
            raise ExternalAdapterUnavailableError(
                "external adapter worker capacity is full"
            )

    import dynamic_agent_runner.external_adapter as external_adapter_module

    facade = ExternalModelAdapterFacade(
        create_apple_foundation_external_adapter(FakeApple(), adapter_id="apple.full")
    )
    monkeypatch.setattr(
        external_adapter_module, "_EXTERNAL_DISPATCHER", SaturatedDispatcher()
    )
    with pytest.raises(ExternalAdapterUnavailableError, match="capacity is full"):
        asyncio.run(facade.create_response_async(_request("apple-test")))


def test_parity_projection_excludes_unstable_response_metadata() -> None:
    def project(response: ModelResponse) -> tuple[object, ...]:
        return (
            response.content,
            tuple((call.name, call.arguments) for call in response.tool_calls),
            response.metadata.get("finish_reason"),
        )

    first = ModelResponse(
        content="same", response_id="apple-unstable", raw={"provider": "a"}
    )
    second = ModelResponse(
        content="same", response_id="mlx-unstable", raw={"provider": "b"}
    )
    assert project(first) == project(second)


def test_native_errors_are_redacted_at_the_external_boundary() -> None:
    adapter = create_apple_foundation_external_adapter(
        FailingApple(), adapter_id="apple.failure"
    )
    with pytest.raises(ExternalAdapterError) as error:
        asyncio.run(
            ExternalModelAdapterFacade(adapter).create_response_async(
                _request("apple-test")
            )
        )
    assert "secret model path" not in str(error.value)


def test_llama_external_adapter_projects_identity_and_sync_response(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"fake")
    native = LlamaCppLocalModelAdapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-test",), model_path=model_path, allow_network=False
        ),
        backend=FakeLlamaBackend(),
    )
    adapter = create_llama_cpp_external_adapter(native, adapter_id="llama.test")
    assert adapter.describe().canonical_model_id.startswith("llama.cpp/")
    assert (
        ExternalModelAdapterFacade(adapter)
        .create_response(_request("llama-test"))
        .content
        == "llama"
    )
    assert (
        asyncio.run(
            ExternalModelAdapterFacade(adapter).create_response_async(
                _request("llama-test")
            )
        ).content
        == "llama"
    )


def test_sync_async_offload_does_not_schedule_health_recursively(
    tmp_path: Path, monkeypatch
) -> None:
    from concurrent.futures import Future

    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"fake")
    native = LlamaCppLocalModelAdapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-test",), model_path=model_path, allow_network=False
        ),
        backend=FakeLlamaBackend(),
    )
    facade = ExternalModelAdapterFacade(
        create_llama_cpp_external_adapter(native, adapter_id="llama.offload")
    )

    class RecordingDispatcher:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def submit(self, function, *args):
            self.calls.append(function.__name__)
            future = Future()
            try:
                future.set_result(function(*args))
            except BaseException as error:
                future.set_exception(error)
            return future

    dispatcher = RecordingDispatcher()
    import dynamic_agent_runner.external_adapter as external_adapter_module

    monkeypatch.setattr(external_adapter_module, "_EXTERNAL_DISPATCHER", dispatcher)
    result = asyncio.run(facade.create_response_async(_request("llama-test")))
    assert result.content == "llama"
    assert dispatcher.calls == ["_run_health", "_dispatch_sync_prepared"]


def test_llama_and_mlx_factories_reject_multi_alias_bindings(tmp_path: Path) -> None:
    llama_path = tmp_path / "model.gguf"
    llama_path.write_bytes(b"fake")
    llama = LlamaCppLocalModelAdapter(
        LlamaCppLocalModelConfig(
            model_aliases=("one", "two"), model_path=llama_path, allow_network=False
        ),
        backend=FakeLlamaBackend(),
    )
    with pytest.raises(ExternalAdapterValidationError):
        create_llama_cpp_external_adapter(llama, adapter_id="llama.multi")

    mlx_path = tmp_path / "mlx"
    mlx_path.mkdir()
    for filename in ("config.json", "tokenizer.model", "weights.npz"):
        (mlx_path / filename).write_bytes(b"fake")
    mlx = MLXLocalModelAdapter(
        MLXLocalModelConfig(model_aliases=("one", "two"), model_path=mlx_path),
        backend=FakeMLXBackend(),
        platform_system=lambda: "Darwin",
    )
    with pytest.raises(ExternalAdapterValidationError):
        create_mlx_external_adapter(mlx, adapter_id="mlx.multi")


def test_mlx_external_adapters_match_sync_and_async_modes(tmp_path: Path) -> None:
    model_path = tmp_path / "mlx"
    model_path.mkdir()
    for filename in ("config.json", "tokenizer.model", "weights.npz"):
        (model_path / filename).write_bytes(b"fake")
    config = MLXLocalModelConfig(model_aliases=("mlx-test",), model_path=model_path)
    native = MLXLocalModelAdapter(
        config, backend=FakeMLXBackend(), platform_system=lambda: "Darwin"
    )
    async_native = AsyncMLXLocalModelAdapter(
        config, backend=FakeMLXBackend(), platform_system=lambda: "Darwin"
    )
    sync_adapter = create_mlx_external_adapter(native, adapter_id="mlx.sync")
    async_adapter = create_mlx_async_external_adapter(
        async_native, adapter_id="mlx.async"
    )
    assert sync_adapter.describe().execution_modes == frozenset({"sync"})
    assert async_adapter.describe().execution_modes == frozenset({"async"})
    assert (
        ExternalModelAdapterFacade(sync_adapter)
        .create_response(_request("mlx-test"))
        .content
        == "mlx"
    )
    assert (
        asyncio.run(
            ExternalModelAdapterFacade(async_adapter).create_response_async(
                _request("mlx-test")
            )
        ).content
        == "mlx"
    )


def test_mlx_text_only_binding_denies_tools_and_structured_output(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "mlx"
    model_path.mkdir()
    for filename in ("config.json", "tokenizer.model", "weights.npz"):
        (model_path / filename).write_bytes(b"fake")
    native = MLXLocalModelAdapter(
        MLXLocalModelConfig(model_aliases=("mlx-test",), model_path=model_path),
        backend=FakeMLXBackend(),
        platform_system=lambda: "Darwin",
    )
    facade = ExternalModelAdapterFacade(
        create_mlx_external_adapter(native, adapter_id="mlx.test")
    )
    with pytest.raises(ExternalAdapterError):
        facade.create_response(
            OpenAIModelRequest(
                model="mlx-test",
                messages=({"role": "user", "content": "hello"},),
                tools=({"type": "function", "name": "tool"},),
            )
        )
    with pytest.raises(ExternalAdapterError):
        facade.create_response(
            OpenAIModelRequest(
                model="mlx-test",
                messages=({"role": "user", "content": "hello"},),
                response_format={"type": "json_schema"},
            )
        )


def test_mlx_exact_codec_advertises_and_normalizes_tool_calls(tmp_path: Path) -> None:
    model_path = tmp_path / "mlx"
    model_path.mkdir()
    for filename in ("config.json", "tokenizer.model", "weights.npz"):
        (model_path / filename).write_bytes(b"fake")
    native = MLXLocalModelAdapter(
        MLXLocalModelConfig(model_aliases=("mlx-tools",), model_path=model_path),
        backend=FakeMLXToolBackend(),
        platform_system=lambda: "Darwin",
        tool_codec=FakeMLXToolCodec(),
    )
    adapter = create_mlx_external_adapter(native, adapter_id="mlx.tools")
    assert "tool_calling" in adapter.describe().capabilities
    result = ExternalModelAdapterFacade(adapter).create_response(
        OpenAIModelRequest(
            model="mlx-tools",
            messages=({"role": "user", "content": "hello"},),
            tools=({"type": "function", "name": "lookup"},),
        )
    )
    assert result.tool_calls == (
        ModelToolCall(id="call-1", name="lookup", arguments='{"key":"value"}'),
    )


def test_apple_binding_without_structured_capability_denies_json_schema() -> None:
    class TextOnlyApple(FakeApple):
        capabilities = {"structured_output": False}

    facade = ExternalModelAdapterFacade(
        create_apple_foundation_external_adapter(
            TextOnlyApple(), adapter_id="apple.text-only"
        )
    )
    with pytest.raises(ExternalAdapterError):
        asyncio.run(
            facade.create_response_async(
                OpenAIModelRequest(
                    model="apple-test",
                    messages=({"role": "user", "content": "hello"},),
                    response_format={"type": "json_schema"},
                )
            )
        )


def test_apple_capability_profile_changes_canonical_identity() -> None:
    structured = create_apple_foundation_external_adapter(
        FakeApple(), adapter_id="apple.structured"
    )

    class TextOnlyApple(FakeApple):
        capabilities = {"structured_output": False}

    text_only = create_apple_foundation_external_adapter(
        TextOnlyApple(), adapter_id="apple.text-only"
    )
    assert (
        structured.describe().canonical_model_id
        != text_only.describe().canonical_model_id
    )
    assert structured.describe().contract_digest != text_only.describe().contract_digest


def test_async_deadline_cancels_without_late_response() -> None:
    adapter = create_apple_foundation_external_adapter(
        SlowApple(), adapter_id="apple.slow"
    )
    with pytest.raises(ExternalAdapterCancelledError):
        asyncio.run(
            ExternalModelAdapterFacade(adapter).create_response_async(
                OpenAIModelRequest(
                    model="apple-test",
                    messages=({"role": "user", "content": "hello"},),
                    extra={"timeout_seconds": 0.001},
                )
            )
        )
