"""Focused tests for internal Hugging Face support helpers."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest


class FakeHubApi:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def list_models(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return [{"modelId": "mlx-community/test-model"}]


def test_load_hugging_face_hub_translates_import_failures() -> None:
    from dynamic_agent_runner.hugging_face_support import (
        HuggingFaceSupportError,
        load_hugging_face_hub,
    )

    def failing_import(_: str) -> object:
        raise ImportError("missing hub")

    with pytest.raises(HuggingFaceSupportError, match="huggingface_hub"):
        load_hugging_face_hub(import_module=failing_import)


def test_list_hub_models_wraps_hub_api_calls() -> None:
    from dynamic_agent_runner.hugging_face_support import list_hub_models

    fake_api = FakeHubApi()
    fake_hub = SimpleNamespace(HfApi=lambda: fake_api)

    results = list_hub_models(
        query="mlx",
        limit=3,
        task="text-generation",
        tags=("mlx", "text-generation"),
        sort="-downloads",
        hub_loader=lambda: fake_hub,
    )

    assert results == [{"modelId": "mlx-community/test-model"}]
    assert fake_api.calls == [
        {
            "search": "mlx",
            "limit": 3,
            "pipeline_tag": "text-generation",
            "filter": ("mlx", "text-generation"),
            "sort": "-downloads",
        }
    ]


def test_list_hub_models_translates_sdk_failures() -> None:
    from dynamic_agent_runner.hugging_face_support import (
        HuggingFaceSupportError,
        list_hub_models,
    )

    fake_hub = SimpleNamespace(HfApi=lambda: FakeHubApi(error=RuntimeError("boom")))

    with pytest.raises(HuggingFaceSupportError, match="boom"):
        list_hub_models(
            query=None,
            limit=1,
            task=None,
            tags=(),
            sort=None,
            hub_loader=lambda: fake_hub,
        )


def test_model_search_translates_support_layer_failures() -> None:
    from dynamic_agent_runner.errors import HuggingFaceModelSearchError
    from dynamic_agent_runner.hugging_face_models import search_hugging_face_models
    from dynamic_agent_runner.hugging_face_support import HuggingFaceSupportError

    def failing_adapter(**_: object) -> object:
        raise HuggingFaceSupportError("low-level hub failure")

    with pytest.raises(HuggingFaceModelSearchError, match="low-level hub failure"):
        search_hugging_face_models("mlx", _search_adapter=failing_adapter)


def test_hugging_face_support_layer_is_not_package_root_exported() -> None:
    import dynamic_agent_runner

    assert not hasattr(dynamic_agent_runner, "HuggingFaceSupportError")
    assert not hasattr(dynamic_agent_runner, "list_hub_models")
    assert not hasattr(dynamic_agent_runner, "download_hub_file")
    assert not hasattr(dynamic_agent_runner, "download_hub_snapshot")


def test_download_hub_file_wraps_hub_download_callable(tmp_path: Path) -> None:
    from dynamic_agent_runner.hugging_face_support import download_hub_file

    calls: list[dict[str, object]] = []
    downloaded_path = tmp_path / "downloaded.gguf"

    def fake_download(**kwargs: object) -> str:
        calls.append(kwargs)
        return str(downloaded_path)

    fake_hub = SimpleNamespace(hf_hub_download=fake_download)

    result = download_hub_file(
        repo_id="mlx-community/test-model",
        filename="model.safetensors",
        revision="main",
        cache_dir=tmp_path / "cache",
        hub_loader=lambda: fake_hub,
    )

    assert result == downloaded_path
    assert calls == [
        {
            "repo_id": "mlx-community/test-model",
            "filename": "model.safetensors",
            "revision": "main",
            "cache_dir": tmp_path / "cache",
        }
    ]


def test_download_hub_snapshot_wraps_hub_download_callable(tmp_path: Path) -> None:
    from dynamic_agent_runner.hugging_face_support import download_hub_snapshot

    calls: list[dict[str, object]] = []
    snapshot_path = tmp_path / "snapshot"

    def fake_snapshot(**kwargs: object) -> str:
        calls.append(kwargs)
        return str(snapshot_path)

    fake_hub = SimpleNamespace(snapshot_download=fake_snapshot)

    result = download_hub_snapshot(
        repo_id="mlx-community/test-model",
        revision="main",
        cache_dir=tmp_path / "cache",
        hub_loader=lambda: fake_hub,
    )

    assert result == snapshot_path
    assert calls == [
        {
            "repo_id": "mlx-community/test-model",
            "revision": "main",
            "cache_dir": tmp_path / "cache",
        }
    ]


def test_download_hub_file_translates_sdk_failures(tmp_path: Path) -> None:
    from dynamic_agent_runner.hugging_face_support import (
        HuggingFaceSupportError,
        download_hub_file,
    )

    def fake_download(**_: object) -> str:
        raise RuntimeError("download failed")

    fake_hub = SimpleNamespace(hf_hub_download=fake_download)

    with pytest.raises(HuggingFaceSupportError, match="download failed"):
        download_hub_file(
            repo_id="mlx-community/test-model",
            filename="model.safetensors",
            revision=None,
            cache_dir=tmp_path / "cache",
            hub_loader=lambda: fake_hub,
        )
