"""Helpers for caller-provided local OpenAI-compatible model endpoints."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from dynamic_agent_runner.errors import (
    LocalModelEndpointConnectivityError,
    LocalModelEndpointProtocolError,
    LocalModelIdentityMismatchError,
    LocalModelOfflinePolicyError,
    LocalModelResolutionError,
    ModelExecutionError,
)
from dynamic_agent_runner.openai_client import (
    OpenAIProviderConfig,
    AsyncOpenAIClientAdapter,
    OpenAIClientAdapter,
    create_async_openai_adapter_from_provider_config,
    create_openai_adapter_from_provider_config,
)


DownloadFileCallable = Callable[["HuggingFaceModelFileReference", Path], Path]
DownloadSnapshotCallable = Callable[["HuggingFaceSnapshotReference", Path], Path]


@dataclass(frozen=True)
class HuggingFaceModelFileReference:
    """Runtime-owned reference to a single model file on the Hugging Face Hub."""

    repo_id: str
    filename: str
    revision: str | None = None


@dataclass(frozen=True)
class HuggingFaceSnapshotReference:
    """Runtime-owned reference to a repository snapshot on the Hugging Face Hub."""

    repo_id: str
    revision: str | None = None


@dataclass(frozen=True)
class LocalModelPathConfig:
    """Runtime-owned local-model asset resolution inputs."""

    model_filename: str
    explicit_model_path: Path | None = None
    model_cache_root: Path | None = None
    huggingface_file: HuggingFaceModelFileReference | None = None
    huggingface_snapshot: HuggingFaceSnapshotReference | None = None


@dataclass(frozen=True)
class LocalOpenAIEndpointConfig:
    """Configuration for a caller-owned local OpenAI-compatible endpoint."""

    base_url: str
    model_aliases: tuple[str, ...]
    api_key: str | None = None
    provider_name: str | None = None
    expected_model_id: str | None = None

    def __init__(
        self,
        *,
        base_url: str,
        model_aliases: Sequence[str],
        api_key: str | None = None,
        provider_name: str | None = None,
        expected_model_id: str | None = None,
    ) -> None:
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(
            self,
            "model_aliases",
            tuple(str(model_alias) for model_alias in model_aliases),
        )
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "provider_name", provider_name)
        object.__setattr__(self, "expected_model_id", expected_model_id)


def create_local_openai_adapter(
    config: LocalOpenAIEndpointConfig,
) -> OpenAIClientAdapter:
    """Build a sync local adapter through the existing provider seam."""

    return create_openai_adapter_from_provider_config(
        _provider_config_from_local_endpoint(config),
        models=config.model_aliases,
        is_local=True,
        error_translator=_local_endpoint_error_translator(config),
    )


def create_local_async_openai_adapter(
    config: LocalOpenAIEndpointConfig,
) -> AsyncOpenAIClientAdapter:
    """Build an async local adapter through the existing provider seam."""

    return create_async_openai_adapter_from_provider_config(
        _provider_config_from_local_endpoint(config),
        models=config.model_aliases,
        is_local=True,
        error_translator=_local_endpoint_error_translator(config),
    )


def resolve_local_model_path(
    config: LocalModelPathConfig,
    *,
    allow_network: bool = True,
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
) -> Path:
    """Resolve the local model path using the approved precedence order."""

    explicit_model_path = config.explicit_model_path
    if explicit_model_path is not None:
        explicit_model_path = Path(explicit_model_path)
        if explicit_model_path.exists():
            return explicit_model_path

    explicit_cache_hit = _resolve_cache_hit(
        cache_root=config.model_cache_root,
        model_filename=config.model_filename,
    )
    if explicit_cache_hit is not None:
        return explicit_cache_hit

    default_cache_root = _default_local_model_cache_root()
    default_cache_hit = _resolve_cache_hit(
        cache_root=default_cache_root,
        model_filename=config.model_filename,
    )
    if default_cache_hit is not None:
        return default_cache_hit

    if config.huggingface_file is not None:
        return _download_model_file(
            config=config,
            cache_root=default_cache_root,
            allow_network=allow_network,
            download_file=download_file,
        )

    if config.huggingface_snapshot is not None:
        return _download_model_snapshot(
            config=config,
            cache_root=default_cache_root,
            allow_network=allow_network,
            download_snapshot=download_snapshot,
        )

    raise LocalModelResolutionError(
        "Could not resolve local model asset "
        f"{config.model_filename!r} from explicit path, explicit cache root, "
        "default cache root, or a configured Hugging Face reference"
    )


def validate_local_model_identity(
    *,
    requested_model: str,
    expected_model_id: str | None,
    observed_model_id: str | None,
) -> None:
    """Validate that the observed local-model identity matches the intended one."""

    if expected_model_id is None or observed_model_id is None:
        return
    if expected_model_id == observed_model_id:
        return
    raise LocalModelIdentityMismatchError(
        "Local model identity mismatch for requested model "
        f"{requested_model!r}: expected {expected_model_id!r} but observed "
        f"{observed_model_id!r}"
    )


def _provider_config_from_local_endpoint(
    config: LocalOpenAIEndpointConfig,
) -> OpenAIProviderConfig:
    return OpenAIProviderConfig(
        base_url=config.base_url,
        api_key=config.api_key,
        provider_name=config.provider_name,
    )


def _local_endpoint_error_translator(
    config: LocalOpenAIEndpointConfig,
):
    def translate(error: ModelExecutionError) -> ModelExecutionError:
        if isinstance(
            error, LocalModelResolutionError | LocalModelIdentityMismatchError
        ):
            return error

        cause = error.__cause__ if isinstance(error.__cause__, Exception) else error
        message = str(cause).lower()
        endpoint_label = _describe_local_endpoint(config)

        if isinstance(cause, (ConnectionError, TimeoutError)) or any(
            token in message
            for token in (
                "connect",
                "connection refused",
                "network",
                "timed out",
                "timeout",
                "unreachable",
                "service unavailable",
                "not ready",
            )
        ):
            return LocalModelEndpointConnectivityError(
                f"Local endpoint connectivity failure for {endpoint_label}: {cause}"
            )

        return LocalModelEndpointProtocolError(
            f"Local endpoint protocol failure for {endpoint_label}: {cause}"
        )

    return translate


def _describe_local_endpoint(config: LocalOpenAIEndpointConfig) -> str:
    provider_name = config.provider_name or "local endpoint"
    aliases = ", ".join(repr(alias) for alias in config.model_aliases)
    return (
        f"provider {provider_name!r} at {config.base_url!r} serving aliases ({aliases})"
    )


def _default_local_model_cache_root() -> Path:
    return Path.home() / ".ollama" / "models"


def _resolve_cache_hit(*, cache_root: Path | None, model_filename: str) -> Path | None:
    if cache_root is None:
        return None
    candidate = Path(cache_root) / model_filename
    if candidate.exists():
        return candidate
    return None


def _download_model_file(
    *,
    config: LocalModelPathConfig,
    cache_root: Path,
    allow_network: bool,
    download_file: DownloadFileCallable | None,
) -> Path:
    reference = config.huggingface_file
    assert reference is not None
    if not allow_network:
        raise LocalModelOfflinePolicyError(
            "offline policy blocks network download for local model asset "
            f"{config.model_filename!r}"
        )
    if download_file is None:
        download_file, _ = _load_huggingface_download_helpers()
    try:
        resolved_path = Path(download_file(reference, cache_root))
    except Exception as exc:  # noqa: BLE001 - normalize download failures.
        raise LocalModelResolutionError(
            "Could not resolve local model asset "
            f"{config.model_filename!r} from Hugging Face file reference "
            f"{reference.repo_id!r}: {exc}"
        ) from exc
    if not resolved_path.exists():
        raise LocalModelResolutionError(
            "Hugging Face file download did not produce a local asset for "
            f"{config.model_filename!r}"
        )
    return resolved_path


def _download_model_snapshot(
    *,
    config: LocalModelPathConfig,
    cache_root: Path,
    allow_network: bool,
    download_snapshot: DownloadSnapshotCallable | None,
) -> Path:
    reference = config.huggingface_snapshot
    assert reference is not None
    if not allow_network:
        raise LocalModelOfflinePolicyError(
            "offline policy blocks network snapshot download for local model "
            f"asset {config.model_filename!r}"
        )
    if download_snapshot is None:
        _, download_snapshot = _load_huggingface_download_helpers()
    try:
        snapshot_root = Path(download_snapshot(reference, cache_root))
    except Exception as exc:  # noqa: BLE001 - normalize download failures.
        raise LocalModelResolutionError(
            "Could not resolve local model asset "
            f"{config.model_filename!r} from Hugging Face snapshot reference "
            f"{reference.repo_id!r}: {exc}"
        ) from exc
    candidate = snapshot_root / config.model_filename
    if not candidate.exists():
        raise LocalModelResolutionError(
            "Hugging Face snapshot did not contain local model asset "
            f"{config.model_filename!r}"
        )
    return candidate


def _load_huggingface_download_helpers() -> tuple[
    DownloadFileCallable, DownloadSnapshotCallable
]:
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except Exception as exc:  # noqa: BLE001 - dependency/import errors vary.
        raise LocalModelResolutionError(
            "huggingface_hub is required for default local-model download wiring"
        ) from exc

    def download_file(
        reference: HuggingFaceModelFileReference,
        cache_root: Path,
    ) -> Path:
        return Path(
            hf_hub_download(
                repo_id=reference.repo_id,
                filename=reference.filename,
                revision=reference.revision,
                cache_dir=cache_root,
            )
        )

    def download_snapshot(
        reference: HuggingFaceSnapshotReference,
        cache_root: Path,
    ) -> Path:
        return Path(
            snapshot_download(
                repo_id=reference.repo_id,
                revision=reference.revision,
                cache_dir=cache_root,
            )
        )

    return download_file, download_snapshot
