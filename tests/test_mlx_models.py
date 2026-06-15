"""Focused tests for macOS MLX local-model adapter helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import OpenAIModelRequest


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
