from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dynamic_agent_runner import (
    ModelResponse,
    OpenAIModelRequest,
    create_apple_foundation_external_adapter,
    create_llama_cpp_external_adapter,
    create_mlx_async_external_adapter,
    create_mlx_external_adapter,
)
from dynamic_agent_runner.external_adapter import (
    ExternalAdapterCancelledError,
    ExternalAdapterError,
    ExternalAdapterValidationError,
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


class FakeLlamaBackend:
    def create_chat_completion(self, **kwargs: object) -> object:
        return {"choices": [{"message": {"content": "llama"}}]}


class FakeMLXBackend:
    def generate(self, request: OpenAIModelRequest, **kwargs: object) -> str:
        return "mlx"


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
