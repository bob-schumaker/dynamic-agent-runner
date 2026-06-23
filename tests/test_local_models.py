"""Focused tests for local-model reference resolution helpers."""

from __future__ import annotations

import asyncio
import builtins
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


class _StaticResponses:
    def __init__(self, response: object) -> None:
        self.response = response

    def create(self, **_: object) -> object:
        return self.response


class _StaticClient:
    def __init__(self, response: object) -> None:
        self.responses = _StaticResponses(response)


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
    default_cache_hit = _default_cache_root(home_dir) / "chat-model.gguf"
    default_cache_hit.parent.mkdir(parents=True)
    default_cache_hit.write_text("default", encoding="utf-8")
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
    default_cache_hit = _default_cache_root(home_dir) / "chat-model.gguf"
    default_cache_hit.parent.mkdir(parents=True)
    default_cache_hit.write_text("default", encoding="utf-8")

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
