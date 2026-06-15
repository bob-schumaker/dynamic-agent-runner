"""Public Hugging Face model discovery helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from dynamic_agent_runner.errors import HuggingFaceModelSearchError
from dynamic_agent_runner.hugging_face_support import (
    HuggingFaceSupportError,
    list_hub_models,
)


SearchAdapter = Callable[..., Iterable[object]]


@dataclass(frozen=True)
class HuggingFaceModelSearchResult:
    """Repository-owned summary of a Hugging Face model search result."""

    repo_id: str
    display_name: str | None = None
    task: str | None = None
    tags: tuple[str, ...] = ()
    likes: int | None = None
    downloads: int | None = None
    last_modified: str | None = None


def search_hugging_face_models(
    query: str | None = None,
    *,
    limit: int = 10,
    task: str | None = None,
    tags: Sequence[str] = (),
    sort: str | None = None,
    direction: str | None = None,
    _search_adapter: SearchAdapter | None = None,
) -> tuple[HuggingFaceModelSearchResult, ...]:
    """Search Hugging Face models through a repository-owned public contract."""

    search_adapter = _search_adapter or _default_hub_search
    normalized_tags = tuple(tags)
    try:
        raw_results = search_adapter(
            query=query,
            limit=limit,
            task=task,
            tags=normalized_tags,
            sort=sort,
            direction=direction,
        )
        return tuple(_normalize_model_search_result(result) for result in raw_results)
    except HuggingFaceModelSearchError:
        raise
    except Exception as exc:
        raise HuggingFaceModelSearchError(
            f"Hugging Face model discovery failed: {exc}"
        ) from exc


def _default_hub_search(
    *,
    query: str | None,
    limit: int,
    task: str | None,
    tags: Sequence[str],
    sort: str | None,
    direction: str | None,
) -> Iterable[object]:
    try:
        return list_hub_models(
            query=query,
            limit=limit,
            task=task,
            tags=tags,
            sort=_hub_sort_value(sort=sort, direction=direction),
        )
    except HuggingFaceSupportError as exc:
        raise HuggingFaceModelSearchError(
            f"Hugging Face model discovery failed: {exc}"
        ) from exc


def _hub_sort_value(*, sort: str | None, direction: str | None) -> str | None:
    if sort is None:
        return None
    if direction == "desc":
        return f"-{sort}"
    return sort


def _normalize_model_search_result(
    raw_result: object,
) -> HuggingFaceModelSearchResult:
    repo_id = _read_string(raw_result, "modelId", "model_id", "id", "repo_id")
    if repo_id is None:
        raise HuggingFaceModelSearchError(
            "Hugging Face model discovery failed: search result did not include "
            "a model repository id"
        )

    return HuggingFaceModelSearchResult(
        repo_id=repo_id,
        display_name=_display_name_from_repo_id(repo_id),
        task=_read_string(raw_result, "pipeline_tag", "task"),
        tags=_read_string_tuple(raw_result, "tags"),
        likes=_read_int(raw_result, "likes"),
        downloads=_read_int(raw_result, "downloads"),
        last_modified=_read_last_modified(raw_result),
    )


def _display_name_from_repo_id(repo_id: str) -> str | None:
    if not repo_id:
        return None
    return repo_id.rsplit("/", maxsplit=1)[-1]


def _read_string(raw_result: object, *names: str) -> str | None:
    value = _read_first_value(raw_result, names)
    if value is None:
        return None
    return str(value)


def _read_string_tuple(raw_result: object, *names: str) -> tuple[str, ...]:
    value = _read_first_value(raw_result, names)
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return ()


def _read_int(raw_result: object, *names: str) -> int | None:
    value = _read_first_value(raw_result, names)
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_last_modified(raw_result: object) -> str | None:
    value = _read_first_value(raw_result, ("lastModified", "last_modified"))
    if value is None:
        return None
    return str(value)


def _read_first_value(raw_result: object, names: Sequence[str]) -> Any:
    for name in names:
        value = _read_value(raw_result, name)
        if value is not None:
            return value
    return None


def _read_value(raw_result: object, name: str) -> Any:
    if isinstance(raw_result, dict):
        return raw_result.get(name)
    return getattr(raw_result, name, None)
