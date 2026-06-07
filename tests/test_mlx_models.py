"""Focused tests for macOS MLX local-model adapter helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import OpenAIModelRequest


class FakeMLXBackend:
    def __init__(self, content: str = "local answer") -> None:
        self.content = content
        self.requests: list[OpenAIModelRequest] = []

    def generate(self, request: OpenAIModelRequest) -> str:
        self.requests.append(request)
        return self.content


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


def test_mlx_config_and_sync_factory_create_local_adapter(tmp_path: Path) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    config = MLXLocalModelConfig(
        model_aliases=("mlx-local-chat",),
        model_path=tmp_path / "mlx-model",
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

    config = MLXLocalModelConfig(
        model_aliases=("mlx-local-chat",),
        model_path=tmp_path / "mlx-model",
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


def test_mlx_adapter_fails_clearly_when_dependency_is_missing(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner import MLXLocalModelConfig, create_mlx_local_adapter

    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "mlx-model",
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
