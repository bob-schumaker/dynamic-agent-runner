"""Focused tests for public Hugging Face model discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class _FakeHubModel:
    modelId: str
    pipeline_tag: str | None = None
    tags: tuple[str, ...] = ()
    likes: int | None = None
    downloads: int | None = None
    lastModified: str | None = None


def test_search_hugging_face_models_returns_repository_owned_results() -> None:
    from dynamic_agent_runner.hugging_face_models import (
        HuggingFaceModelSearchResult,
        search_hugging_face_models,
    )

    def fake_adapter(**_: object) -> list[_FakeHubModel]:
        return [
            _FakeHubModel(
                modelId="Qwen/Qwen3-4B-GGUF",
                pipeline_tag="text-generation",
                tags=("gguf", "qwen3"),
                likes=42,
                downloads=9001,
                lastModified="2026-01-02T03:04:05.000Z",
            )
        ]

    results = search_hugging_face_models(
        "qwen gguf",
        limit=1,
        _search_adapter=fake_adapter,
    )

    assert results == (
        HuggingFaceModelSearchResult(
            repo_id="Qwen/Qwen3-4B-GGUF",
            display_name="Qwen3-4B-GGUF",
            task="text-generation",
            tags=("gguf", "qwen3"),
            likes=42,
            downloads=9001,
            last_modified="2026-01-02T03:04:05.000Z",
        ),
    )


def test_search_hugging_face_models_shapes_limited_filter_set() -> None:
    from dynamic_agent_runner.hugging_face_models import search_hugging_face_models

    adapter_calls: list[dict[str, object]] = []

    def fake_adapter(**kwargs: object) -> list[dict[str, object]]:
        adapter_calls.append(kwargs)
        return [
            {
                "modelId": "sentence-transformers/all-MiniLM-L6-v2",
                "pipeline_tag": "feature-extraction",
                "tags": ["sentence-transformers", "embeddings"],
            }
        ]

    search_hugging_face_models(
        "mini lm",
        limit=5,
        task="feature-extraction",
        tags=("sentence-transformers", "embeddings"),
        sort="downloads",
        direction="desc",
        _search_adapter=fake_adapter,
    )

    assert adapter_calls == [
        {
            "query": "mini lm",
            "limit": 5,
            "task": "feature-extraction",
            "tags": ("sentence-transformers", "embeddings"),
            "sort": "downloads",
            "direction": "desc",
        }
    ]


def test_search_hugging_face_models_translates_discovery_failures() -> None:
    from dynamic_agent_runner import HuggingFaceModelSearchError
    from dynamic_agent_runner.hugging_face_models import search_hugging_face_models

    def fake_adapter(**_: object) -> list[object]:
        raise RuntimeError("hub unavailable")

    with pytest.raises(HuggingFaceModelSearchError) as exc_info:
        search_hugging_face_models("qwen", _search_adapter=fake_adapter)

    assert "Hugging Face model discovery failed" in str(exc_info.value)
    assert "hub unavailable" in str(exc_info.value)


def test_package_root_exports_hugging_face_model_search_api() -> None:
    import dynamic_agent_runner

    assert dynamic_agent_runner.search_hugging_face_models is not None
    assert dynamic_agent_runner.HuggingFaceModelSearchResult is not None
    assert dynamic_agent_runner.HuggingFaceModelSearchError is not None
