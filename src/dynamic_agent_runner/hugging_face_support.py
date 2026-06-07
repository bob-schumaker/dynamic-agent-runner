"""Internal Hugging Face Hub support helpers."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path


ImportModuleCallable = Callable[[str], object]
HubLoaderCallable = Callable[[], object]


class HuggingFaceSupportError(Exception):
    """Raised when internal Hugging Face Hub mechanics fail."""


def load_hugging_face_hub(
    *,
    import_module: ImportModuleCallable = importlib.import_module,
) -> object:
    """Load the Hugging Face Hub SDK lazily."""

    try:
        return import_module("huggingface_hub")
    except Exception as exc:  # noqa: BLE001 - import failures vary.
        raise HuggingFaceSupportError(f"huggingface_hub is unavailable: {exc}") from exc


def list_hub_models(
    *,
    query: str | None,
    limit: int,
    task: str | None,
    tags: Sequence[str],
    sort: str | None,
    hub_loader: HubLoaderCallable = load_hugging_face_hub,
) -> Iterable[object]:
    """List Hugging Face models through the SDK."""

    try:
        hub = hub_loader()
        return hub.HfApi().list_models(
            search=query,
            limit=limit,
            pipeline_tag=task,
            filter=tuple(tags) or None,
            sort=sort,
        )
    except HuggingFaceSupportError:
        raise
    except Exception as exc:  # noqa: BLE001 - SDK failures vary.
        raise HuggingFaceSupportError(
            f"Hugging Face Hub model listing failed: {exc}"
        ) from exc


def download_hub_file(
    *,
    repo_id: str,
    filename: str,
    revision: str | None,
    cache_dir: Path,
    hub_loader: HubLoaderCallable = load_hugging_face_hub,
) -> Path:
    """Download or locate one Hugging Face Hub file."""

    try:
        hub = hub_loader()
        return Path(
            hub.hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                revision=revision,
                cache_dir=cache_dir,
            )
        )
    except HuggingFaceSupportError:
        raise
    except Exception as exc:  # noqa: BLE001 - SDK failures vary.
        raise HuggingFaceSupportError(
            f"Hugging Face Hub file download failed for {repo_id!r}/{filename!r}: {exc}"
        ) from exc


def download_hub_snapshot(
    *,
    repo_id: str,
    revision: str | None,
    cache_dir: Path,
    hub_loader: HubLoaderCallable = load_hugging_face_hub,
) -> Path:
    """Download or locate one Hugging Face Hub snapshot."""

    try:
        hub = hub_loader()
        return Path(
            hub.snapshot_download(
                repo_id=repo_id,
                revision=revision,
                cache_dir=cache_dir,
            )
        )
    except HuggingFaceSupportError:
        raise
    except Exception as exc:  # noqa: BLE001 - SDK failures vary.
        raise HuggingFaceSupportError(
            f"Hugging Face Hub snapshot download failed for {repo_id!r}: {exc}"
        ) from exc
