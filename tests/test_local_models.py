"""Focused tests for local-model reference resolution helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def _default_cache_root(home_dir: Path) -> Path:
    return home_dir / ".ollama" / "models"


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

    default_cache_hit = _default_cache_root(home_dir) / "chat-model.gguf"
    default_cache_hit.parent.mkdir(parents=True)
    default_cache_hit.write_text("default-cache-model", encoding="utf-8")

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

    default_cache_hit = _default_cache_root(home_dir) / "chat-model.gguf"
    default_cache_hit.parent.mkdir(parents=True)
    default_cache_hit.write_text("default-cache-model", encoding="utf-8")

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
