"""Focused tests for local-model reference resolution helpers."""

from __future__ import annotations

from pathlib import Path


def _default_cache_root(home_dir: Path) -> Path:
    return home_dir / ".ollama" / "models"


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
