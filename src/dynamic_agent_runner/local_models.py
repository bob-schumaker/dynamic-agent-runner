"""Helpers for caller-provided local OpenAI-compatible model endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import html
import inspect
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from dynamic_agent_runner.errors import (
    LocalModelEndpointConnectivityError,
    LocalModelEndpointProtocolError,
    LocalModelIdentityMismatchError,
    EmbeddingExecutionError,
    EmbeddingInputError,
    EmbeddingResultError,
    LlamaCppMemoryFitProfileError,
    LocalModelOfflinePolicyError,
    LocalModelResolutionError,
    ModelExecutionError,
)
from dynamic_agent_runner.hugging_face_support import (
    download_hub_file,
    download_hub_snapshot,
)
from dynamic_agent_runner.openai_client import (
    OpenAIProviderConfig,
    AsyncOpenAIClientAdapter,
    ModelResponse,
    ModelToolCall,
    OpenAIModelRequest,
    OpenAIClientAdapter,
    create_async_openai_adapter_from_provider_config,
    create_openai_adapter_from_provider_config,
)
from dynamic_agent_runner.models import ToolDefinition
from dynamic_agent_runner.registry import RegisteredTool, ToolResult


DownloadFileCallable = Callable[["HuggingFaceModelFileReference", Path], Path]
DownloadSnapshotCallable = Callable[["HuggingFaceSnapshotReference", Path], Path]
LlamaCppDependencyLoaderCallable = Callable[[Path, "LlamaCppLocalModelConfig"], object]
LlamaCppEmbeddingDependencyLoaderCallable = Callable[
    [Path, "LlamaCppLocalEmbeddingConfig"], object
]
RemoteMetadataLookupCallable = Callable[
    ["LocalModelAssetReference"],
    "LocalModelRemoteMetadata",
]


class LlamaCppMemoryFitStatus(str, Enum):
    """Advisory fit status for a resolved llama.cpp local model asset."""

    FITS = "fits"
    TOO_LARGE = "too_large"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    FAILED_OPEN = "failed_open"


class LocalModelAvailabilityStatus(str, Enum):
    """Read-only local-model availability status."""

    AVAILABLE = "available"
    MISSING = "missing"
    WOULD_DOWNLOAD = "would_download"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class LocalModelAvailabilitySource(str, Enum):
    """Source checked for a local-model availability result."""

    EXPLICIT_PATH = "explicit_path"
    EXPLICIT_CACHE_ROOT = "explicit_cache_root"
    DEFAULT_CACHE_ROOT = "default_cache_root"
    CALLER_PROVIDED_ROOT = "caller_provided_root"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class LlamaCppMemoryFitMeasurement:
    """Raw evaluator measurement normalized into package-owned fields."""

    resident_bytes: int | None = None
    context_bytes_per_1k_tokens: int | None = None
    memory_budget_bytes: int | None = None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class LlamaCppMemoryFitProfileResult:
    """Advisory memory-fit profile for one resolved local GGUF asset."""

    model_path: Path
    status: LlamaCppMemoryFitStatus
    resident_bytes: int | None = None
    context_bytes_per_1k_tokens: int | None = None
    memory_budget_bytes: int | None = None
    requested_context_tokens: int | None = None
    requested_context_fits: bool | None = None
    maximum_usable_context_tokens: int | None = None
    supported_context_tiers: tuple[int, ...] = ()
    estimated_memory_by_context_tier: Mapping[int, int] | None = None
    suggested_model_kwargs: Mapping[str, object] | None = None
    diagnostics: tuple[str, ...] = ()
    partial: bool = False


@runtime_checkable
class LlamaCppLocalBackend(Protocol):
    """Minimal backend interface for in-process llama.cpp chat generation."""

    def create_chat_completion(self, **kwargs: object) -> object:
        """Create a llama.cpp chat completion response."""


@runtime_checkable
class LlamaCppLocalEmbeddingBackend(Protocol):
    """Minimal backend interface for in-process llama.cpp embeddings."""

    def create_embedding(self, **kwargs: object) -> object:
        """Create a batch embedding response."""


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
class LocalModelAssetReference:
    """Public reference used for read-only local-model availability checks."""

    provider: str
    repo_id: str | None = None
    filename: str | None = None
    revision: str | None = None
    explicit_path: Path | None = None
    model_filename: str | None = None
    model_cache_root: Path | None = None
    model_format: str = "auto"
    backend: str = "auto"

    def __init__(
        self,
        *,
        provider: str,
        repo_id: str | None = None,
        filename: str | None = None,
        revision: str | None = None,
        explicit_path: str | Path | None = None,
        model_filename: str | None = None,
        model_cache_root: str | Path | None = None,
        model_format: str = "auto",
        backend: str = "auto",
    ) -> None:
        normalized_provider = str(provider)
        if normalized_provider not in {"hugging_face", "local_path"}:
            raise ValueError("provider must be 'hugging_face' or 'local_path'")
        normalized_model_format = str(model_format)
        if normalized_model_format not in {"gguf", "mlx", "auto"}:
            raise ValueError("model_format must be 'gguf', 'mlx', or 'auto'")
        normalized_backend = str(backend)
        if normalized_backend not in {"llama_cpp", "mlx", "auto"}:
            raise ValueError("backend must be 'llama_cpp', 'mlx', or 'auto'")
        object.__setattr__(self, "provider", normalized_provider)
        object.__setattr__(self, "repo_id", repo_id)
        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "revision", revision)
        object.__setattr__(
            self,
            "explicit_path",
            Path(explicit_path) if explicit_path is not None else None,
        )
        object.__setattr__(self, "model_filename", model_filename)
        object.__setattr__(
            self,
            "model_cache_root",
            Path(model_cache_root) if model_cache_root is not None else None,
        )
        object.__setattr__(self, "model_format", normalized_model_format)
        object.__setattr__(self, "backend", normalized_backend)


@dataclass(frozen=True)
class LocalModelAvailability:
    """Structured read-only availability result for a local model asset."""

    status: LocalModelAvailabilityStatus
    reference: LocalModelAssetReference
    resolved_path: Path | None = None
    cache_root: Path | None = None
    source: LocalModelAvailabilitySource | None = None
    size_bytes: int | None = None
    message: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalModelInventoryItem:
    """One read-only local model asset discovered in a scoped cache inventory."""

    path: Path
    cache_root: Path
    source: LocalModelAvailabilitySource
    model_format: str
    backend: str
    status: LocalModelAvailabilityStatus = LocalModelAvailabilityStatus.AVAILABLE
    message: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalModelInventory:
    """Read-only local model inventory for the roots in one caller request."""

    assets: tuple[LocalModelInventoryItem, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalModelRemoteMetadata:
    """Injected read-only remote metadata for a known local-model asset."""

    exists: bool | None
    size_bytes: int | None = None
    message: str = ""
    warnings: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class LlamaCppLocalModelConfig:
    """Configuration for a caller-owned direct llama.cpp local model."""

    model_aliases: tuple[str, ...]
    model_path: Path
    model_filename: str
    model_cache_root: Path | None = None
    huggingface_file: HuggingFaceModelFileReference | None = None
    huggingface_snapshot: HuggingFaceSnapshotReference | None = None
    expected_model_id: str | None = None
    expected_model_sha256: str | None = None
    model_kwargs: Mapping[str, object] | None = None
    allow_network: bool = True

    def __init__(
        self,
        *,
        model_aliases: Sequence[str],
        model_path: str | Path,
        model_filename: str | None = None,
        model_cache_root: str | Path | None = None,
        huggingface_file: HuggingFaceModelFileReference | None = None,
        huggingface_snapshot: HuggingFaceSnapshotReference | None = None,
        expected_model_id: str | None = None,
        expected_model_sha256: str | None = None,
        model_kwargs: Mapping[str, object] | None = None,
        allow_network: bool = True,
    ) -> None:
        resolved_model_path = Path(model_path)
        resolved_model_filename = model_filename or (
            huggingface_file.filename
            if huggingface_file is not None
            else resolved_model_path.name
        )
        object.__setattr__(
            self,
            "model_aliases",
            tuple(str(model_alias) for model_alias in model_aliases),
        )
        object.__setattr__(self, "model_path", resolved_model_path)
        object.__setattr__(self, "model_filename", resolved_model_filename)
        object.__setattr__(
            self,
            "model_cache_root",
            Path(model_cache_root) if model_cache_root is not None else None,
        )
        object.__setattr__(self, "huggingface_file", huggingface_file)
        object.__setattr__(self, "huggingface_snapshot", huggingface_snapshot)
        object.__setattr__(self, "expected_model_id", expected_model_id)
        object.__setattr__(
            self,
            "expected_model_sha256",
            _optional_sha256(expected_model_sha256, "expected_model_sha256"),
        )
        object.__setattr__(
            self,
            "model_kwargs",
            dict(model_kwargs) if model_kwargs is not None else None,
        )
        object.__setattr__(self, "allow_network", allow_network)


def llama_cpp_configuration_fingerprint(config: LlamaCppLocalModelConfig) -> str:
    """Return a stable fingerprint for an immutable direct llama.cpp binding."""

    value = {
        "model_aliases": config.model_aliases,
        "model_filename": config.model_filename,
        "huggingface_file": _huggingface_file_fingerprint(config.huggingface_file),
        "huggingface_snapshot": _huggingface_snapshot_fingerprint(
            config.huggingface_snapshot
        ),
        "expected_model_id": config.expected_model_id,
        "expected_model_sha256": config.expected_model_sha256,
        "allow_network": config.allow_network,
        "model_kwargs": config.model_kwargs,
    }
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("llama.cpp configuration is not fingerprintable") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EmbeddingInputItem:
    """One caller-supplied text entry for a standalone embedding batch."""

    id: str
    text: str


@dataclass(frozen=True)
class EmbeddingVectorItem:
    """One normalized vector in a standalone embedding batch result."""

    id: str
    vector: tuple[float, ...]


@dataclass(frozen=True)
class EmbeddingBatchResult:
    """Normalized ordered result from one standalone embedding batch."""

    model: str
    items: tuple[EmbeddingVectorItem, ...]


def create_local_embedding_tool(producer: object) -> RegisteredTool:
    """Create the fixed host-bound model tool for one embedding producer."""

    async def embed(arguments: Mapping[str, object]) -> ToolResult:
        items = _validate_tool_embedding_input(arguments)
        operation = getattr(producer, "embed", None)
        if not callable(operation):
            raise EmbeddingExecutionError("embedding tool has an invalid producer")
        result = operation(items)
        if inspect.isawaitable(result):
            result = await result
        normalized = _validate_tool_embedding_result(result, items)
        output = {
            "model": normalized.model,
            "items": [
                {"id": item.id, "vector": list(item.vector)}
                for item in normalized.items
            ],
        }
        return ToolResult(
            tool_id="local_embedding_batch",
            success=True,
            output=output,
            model_output=output,
            trace_output={"status": "embedding_result_redacted"},
        )

    return RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "local_embedding_batch",
                "description_for_llm": "Embed a bounded batch of text locally.",
                "side_effect": "read",
                "approval_required": "no",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 8,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                                "required": ["id", "text"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["items"],
                    "additionalProperties": False,
                },
            }
        ),
        embed,
    )


@dataclass(frozen=True)
class LlamaCppLocalEmbeddingConfig:
    """Configuration for a caller-owned direct llama.cpp embedding model."""

    model_path: Path
    model_filename: str
    expected_model_id: str
    model_cache_root: Path | None = None
    huggingface_file: HuggingFaceModelFileReference | None = None
    huggingface_snapshot: HuggingFaceSnapshotReference | None = None
    allow_network: bool = True
    model_kwargs: Mapping[str, object] | None = None

    def __init__(
        self,
        *,
        model_path: str | Path,
        expected_model_id: str | None = None,
        model_filename: str | None = None,
        model_cache_root: str | Path | None = None,
        huggingface_file: HuggingFaceModelFileReference | None = None,
        huggingface_snapshot: HuggingFaceSnapshotReference | None = None,
        allow_network: bool = True,
        model_kwargs: Mapping[str, object] | None = None,
    ) -> None:
        if not isinstance(expected_model_id, str) or not expected_model_id.strip():
            raise ValueError("expected_model_id must be a nonempty string")
        if huggingface_file is not None and huggingface_snapshot is not None:
            raise ValueError("only one Hugging Face embedding reference is allowed")
        if model_kwargs is not None and "embedding" in model_kwargs:
            raise ValueError("embedding model_kwargs is owned by the embedding adapter")
        resolved_model_path = Path(model_path)
        resolved_model_filename = model_filename or (
            huggingface_file.filename
            if huggingface_file is not None
            else resolved_model_path.name
        )
        object.__setattr__(self, "model_path", resolved_model_path)
        object.__setattr__(self, "model_filename", resolved_model_filename)
        object.__setattr__(self, "expected_model_id", expected_model_id)
        object.__setattr__(
            self,
            "model_cache_root",
            Path(model_cache_root) if model_cache_root is not None else None,
        )
        object.__setattr__(self, "huggingface_file", huggingface_file)
        object.__setattr__(self, "huggingface_snapshot", huggingface_snapshot)
        object.__setattr__(self, "allow_network", bool(allow_network))
        object.__setattr__(
            self,
            "model_kwargs",
            MappingProxyType(dict(model_kwargs)) if model_kwargs is not None else None,
        )


def profile_llama_cpp_model_memory_fit(
    config: LlamaCppLocalModelConfig,
    *,
    requested_context_tokens: int | None = None,
    context_tiers: Sequence[int] = (4096, 8192, 16384, 32768, 65536, 131072),
    memory_budget_bytes: int | None = None,
    mode: str = "fail_open",
    profiler: Callable[[Path], LlamaCppMemoryFitMeasurement] | None = None,
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
) -> LlamaCppMemoryFitProfileResult:
    """Profile llama.cpp memory fit through an injected advisory evaluator."""

    model_path = resolve_local_model_path(
        LocalModelPathConfig(
            model_filename=config.model_filename,
            explicit_model_path=config.model_path,
            model_cache_root=config.model_cache_root,
            huggingface_file=config.huggingface_file,
            huggingface_snapshot=config.huggingface_snapshot,
        ),
        download_file=download_file,
        download_snapshot=download_snapshot,
    )
    if mode == "strict" and profiler is None:
        raise LlamaCppMemoryFitProfileError(
            "llama.cpp memory-fit profiler is unavailable"
        )
    tiers = tuple(int(tier) for tier in context_tiers)
    if profiler is None:
        return LlamaCppMemoryFitProfileResult(
            model_path=model_path,
            status=LlamaCppMemoryFitStatus.UNAVAILABLE,
            requested_context_tokens=requested_context_tokens,
            memory_budget_bytes=memory_budget_bytes,
            supported_context_tiers=tiers,
            diagnostics=("llama.cpp memory-fit profiler is unavailable",),
        )
    try:
        measurement = profiler(model_path)
    except Exception as exc:  # noqa: BLE001 - profiler failures vary.
        if mode == "strict":
            raise LlamaCppMemoryFitProfileError(
                f"llama.cpp memory-fit profiling failed: {exc}"
            ) from exc
        return LlamaCppMemoryFitProfileResult(
            model_path=model_path,
            status=LlamaCppMemoryFitStatus.FAILED_OPEN,
            requested_context_tokens=requested_context_tokens,
            memory_budget_bytes=memory_budget_bytes,
            supported_context_tiers=tiers,
            diagnostics=(f"llama.cpp memory-fit profiling failed: {exc}",),
        )
    effective_budget = (
        memory_budget_bytes
        if memory_budget_bytes is not None
        else measurement.memory_budget_bytes
    )
    partial = _measurement_is_partial(measurement, effective_budget)
    fit = _llama_cpp_memory_fit_calculation(
        measurement=measurement,
        memory_budget_bytes=effective_budget,
        requested_context_tokens=requested_context_tokens,
        context_tiers=tiers,
    )
    return LlamaCppMemoryFitProfileResult(
        model_path=model_path,
        status=fit["status"],
        resident_bytes=measurement.resident_bytes,
        context_bytes_per_1k_tokens=measurement.context_bytes_per_1k_tokens,
        requested_context_tokens=requested_context_tokens,
        memory_budget_bytes=effective_budget,
        requested_context_fits=fit["requested_context_fits"],
        maximum_usable_context_tokens=fit["maximum_usable_context_tokens"],
        supported_context_tiers=fit["supported_context_tiers"],
        estimated_memory_by_context_tier=fit["estimated_memory_by_context_tier"],
        suggested_model_kwargs=fit["suggested_model_kwargs"],
        diagnostics=tuple(measurement.diagnostics),
        partial=partial,
    )


def check_local_model_availability(
    reference: LocalModelAssetReference,
    *,
    allow_network_metadata: bool = False,
    metadata_lookup: RemoteMetadataLookupCallable | None = None,
) -> LocalModelAvailability:
    """Check local-model asset availability without downloading or loading."""

    model_filename = _availability_model_filename(reference)
    if model_filename is None:
        return LocalModelAvailability(
            status=LocalModelAvailabilityStatus.UNKNOWN,
            reference=reference,
            source=LocalModelAvailabilitySource.NOT_FOUND,
            message="Local model availability requires a concrete model filename",
        )
    if reference.explicit_path is not None:
        return _availability_for_candidate(
            reference=reference,
            model_path=reference.explicit_path,
            source=LocalModelAvailabilitySource.EXPLICIT_PATH,
            cache_root=None,
            missing_message=(
                f"Explicit local model path {reference.explicit_path!s} does not exist"
            ),
        )
    explicit_cache_hit = _resolve_cache_hit(
        cache_root=reference.model_cache_root,
        model_filename=model_filename,
    )
    if explicit_cache_hit is not None:
        return _availability_for_candidate(
            reference=reference,
            model_path=explicit_cache_hit,
            source=LocalModelAvailabilitySource.EXPLICIT_CACHE_ROOT,
            cache_root=reference.model_cache_root,
        )
    default_cache_root = _default_local_model_cache_root()
    default_cache_hit = _resolve_default_cache_hit(
        cache_root=default_cache_root,
        model_filename=model_filename,
        repo_id=reference.repo_id,
        revision=reference.revision,
    )
    if default_cache_hit is not None:
        return _availability_for_candidate(
            reference=reference,
            model_path=default_cache_hit,
            source=LocalModelAvailabilitySource.DEFAULT_CACHE_ROOT,
            cache_root=default_cache_root,
        )
    if allow_network_metadata and metadata_lookup is not None:
        return _availability_from_remote_metadata(
            reference=reference,
            model_filename=model_filename,
            metadata_lookup=metadata_lookup,
        )
    return LocalModelAvailability(
        status=LocalModelAvailabilityStatus.MISSING,
        reference=reference,
        source=LocalModelAvailabilitySource.NOT_FOUND,
        message=f"Local model asset {model_filename!r} is not available locally",
    )


def list_local_model_assets(
    *,
    model_cache_roots: Sequence[str | Path] = (),
    include_default_cache_root: bool = True,
) -> LocalModelInventory:
    """List local model assets from package-used roots for this call only."""

    assets: list[LocalModelInventoryItem] = []
    warnings: list[str] = []
    seen_paths: set[Path] = set()
    seen_roots: set[Path] = set()
    if include_default_cache_root:
        default_cache_root = _default_local_model_cache_root()
        seen_roots.add(default_cache_root.resolve())
        _scan_local_model_inventory_root(
            cache_root=default_cache_root,
            source=LocalModelAvailabilitySource.DEFAULT_CACHE_ROOT,
            assets=assets,
            warnings=warnings,
            seen_paths=seen_paths,
            scan_hub_snapshots=True,
        )
    for cache_root_value in model_cache_roots:
        cache_root = Path(cache_root_value)
        resolved_root = cache_root.resolve()
        if resolved_root in seen_roots:
            continue
        seen_roots.add(resolved_root)
        _scan_local_model_inventory_root(
            cache_root=cache_root,
            source=LocalModelAvailabilitySource.CALLER_PROVIDED_ROOT,
            assets=assets,
            warnings=warnings,
            seen_paths=seen_paths,
            scan_hub_snapshots=False,
        )
    return LocalModelInventory(
        assets=tuple(assets),
        warnings=tuple(warnings),
    )


def _measurement_is_partial(
    measurement: LlamaCppMemoryFitMeasurement,
    memory_budget_bytes: int | None,
) -> bool:
    return (
        measurement.resident_bytes is None
        or measurement.context_bytes_per_1k_tokens is None
        or memory_budget_bytes is None
    )


def _llama_cpp_memory_fit_calculation(
    *,
    measurement: LlamaCppMemoryFitMeasurement,
    memory_budget_bytes: int | None,
    requested_context_tokens: int | None,
    context_tiers: Sequence[int],
) -> dict[str, object]:
    resident_bytes = measurement.resident_bytes
    context_bytes_per_1k = measurement.context_bytes_per_1k_tokens
    if (
        resident_bytes is None
        or context_bytes_per_1k is None
        or context_bytes_per_1k <= 0
        or memory_budget_bytes is None
    ):
        return {
            "status": LlamaCppMemoryFitStatus.UNKNOWN,
            "requested_context_fits": None,
            "maximum_usable_context_tokens": None,
            "supported_context_tiers": (),
            "estimated_memory_by_context_tier": None,
            "suggested_model_kwargs": None,
        }

    available_context_bytes = memory_budget_bytes - resident_bytes
    maximum_context = max(0, (available_context_bytes * 1000) // context_bytes_per_1k)
    tier_estimates = {
        int(tier): _estimated_llama_cpp_memory_bytes(
            resident_bytes=resident_bytes,
            context_bytes_per_1k=context_bytes_per_1k,
            context_tokens=int(tier),
        )
        for tier in context_tiers
    }
    supported_tiers = tuple(
        tier
        for tier, estimated_bytes in tier_estimates.items()
        if estimated_bytes <= memory_budget_bytes
    )
    requested_fits: bool | None = None
    suggested_kwargs: dict[str, int] | None = None
    status = LlamaCppMemoryFitStatus.UNKNOWN
    if requested_context_tokens is not None:
        requested_estimate = _estimated_llama_cpp_memory_bytes(
            resident_bytes=resident_bytes,
            context_bytes_per_1k=context_bytes_per_1k,
            context_tokens=requested_context_tokens,
        )
        requested_fits = requested_estimate <= memory_budget_bytes
        status = (
            LlamaCppMemoryFitStatus.FITS
            if requested_fits
            else LlamaCppMemoryFitStatus.TOO_LARGE
        )
        effective_context = (
            requested_context_tokens if requested_fits else maximum_context
        )
        if effective_context > 0:
            suggested_kwargs = {"n_ctx": effective_context}

    return {
        "status": status,
        "requested_context_fits": requested_fits,
        "maximum_usable_context_tokens": maximum_context,
        "supported_context_tiers": supported_tiers,
        "estimated_memory_by_context_tier": tier_estimates,
        "suggested_model_kwargs": suggested_kwargs,
    }


def _estimated_llama_cpp_memory_bytes(
    *,
    resident_bytes: int,
    context_bytes_per_1k: int,
    context_tokens: int,
) -> int:
    return resident_bytes + ((context_bytes_per_1k * context_tokens + 999) // 1000)


class LlamaCppLocalModelAdapter:
    """Sync adapter for direct in-process llama.cpp chat generation."""

    def __init__(
        self,
        config: LlamaCppLocalModelConfig,
        *,
        backend: LlamaCppLocalBackend | None = None,
        dependency_loader: LlamaCppDependencyLoaderCallable | None = None,
        download_file: DownloadFileCallable | None = None,
        download_snapshot: DownloadSnapshotCallable | None = None,
    ) -> None:
        self._config = config
        self._backend = backend
        self._dependency_loader = dependency_loader
        self._download_file = download_file
        self._download_snapshot = download_snapshot
        self._resolved_model_path: Path | None = None

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Generate and normalize a direct llama.cpp chat response."""

        model_path = self._resolve_model_path()
        backend = self._get_backend(model_path)
        validate_local_model_identity(
            requested_model=request.model,
            expected_model_id=self._config.expected_model_id,
            observed_model_id=_read_backend_model_id(backend),
            explicit_model_path=model_path,
            huggingface_file=self._config.huggingface_file,
            huggingface_snapshot=self._config.huggingface_snapshot,
        )
        try:
            uses_chatml_function_calling = (self._config.model_kwargs or {}).get(
                "chat_format"
            ) == "chatml-function-calling"
            raw_response = backend.create_chat_completion(
                messages=(
                    _llama_cpp_chatml_messages(request.messages)
                    if uses_chatml_function_calling
                    else [dict(message) for message in request.messages]
                ),
                tools=(
                    _llama_cpp_chatml_tools(request.tools)
                    if uses_chatml_function_calling
                    else [dict(tool) for tool in request.tools]
                )
                or None,
                tool_choice=(
                    "auto"
                    if (
                        request.tool_choice == "required"
                        and request.tools
                        and uses_chatml_function_calling
                    )
                    else request.tool_choice
                ),
                response_format=(
                    dict(request.response_format)
                    if request.response_format is not None
                    else None
                ),
            )
        except ModelExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - backend errors vary.
            raise ModelExecutionError(
                f"llama.cpp local model generation failed for {request.model!r}: {exc}"
            ) from exc
        return _normalize_llama_cpp_chat_response(raw_response)

    @property
    def models(self) -> tuple[str, ...]:
        """Return advertised model names for adapter selection."""

        return self._config.model_aliases

    @property
    def is_local(self) -> bool:
        """Return whether this adapter is local execution."""

        return True

    def _resolve_model_path(self) -> Path:
        if self._resolved_model_path is None:
            model_path = resolve_local_model_path(
                LocalModelPathConfig(
                    model_filename=self._config.model_filename,
                    explicit_model_path=self._config.model_path,
                    model_cache_root=self._config.model_cache_root,
                    huggingface_file=self._config.huggingface_file,
                    huggingface_snapshot=self._config.huggingface_snapshot,
                ),
                allow_network=self._config.allow_network,
                download_file=self._download_file,
                download_snapshot=self._download_snapshot,
            )
            _verify_model_sha256(model_path, self._config.expected_model_sha256)
            self._resolved_model_path = model_path
        return self._resolved_model_path

    def _get_backend(self, model_path: Path) -> LlamaCppLocalBackend:
        if self._backend is None:
            try:
                loaded = (
                    self._dependency_loader(model_path, self._config)
                    if self._dependency_loader is not None
                    else _load_default_llama_cpp_backend(model_path, self._config)
                )
            except ModelExecutionError:
                raise
            except ImportError as exc:
                raise ModelExecutionError(
                    "llama.cpp dependency unavailable for local model execution; "
                    "install llama-cpp-python before creating a default backend"
                ) from exc
            if not isinstance(loaded, LlamaCppLocalBackend):
                raise ModelExecutionError(
                    "llama.cpp dependency loader did not return a local chat backend"
                )
            self._backend = loaded
        return self._backend


class AsyncLlamaCppLocalModelAdapter:
    """Async adapter for direct in-process llama.cpp chat generation."""

    def __init__(
        self,
        config: LlamaCppLocalModelConfig,
        *,
        backend: LlamaCppLocalBackend | None = None,
        dependency_loader: LlamaCppDependencyLoaderCallable | None = None,
        download_file: DownloadFileCallable | None = None,
        download_snapshot: DownloadSnapshotCallable | None = None,
    ) -> None:
        self._sync_adapter = LlamaCppLocalModelAdapter(
            config,
            backend=backend,
            dependency_loader=dependency_loader,
            download_file=download_file,
            download_snapshot=download_snapshot,
        )

    async def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Generate a llama.cpp response without blocking the event loop directly."""

        return await asyncio.to_thread(self._sync_adapter.create_response, request)

    @property
    def models(self) -> tuple[str, ...]:
        """Return advertised model names for adapter selection."""

        return self._sync_adapter.models

    @property
    def is_local(self) -> bool:
        """Return whether this adapter is local execution."""

        return True


class LlamaCppLocalEmbeddingAdapter:
    """Sync adapter for direct in-process llama.cpp embeddings."""

    def __init__(
        self,
        config: LlamaCppLocalEmbeddingConfig,
        *,
        backend: LlamaCppLocalEmbeddingBackend | None = None,
        dependency_loader: LlamaCppEmbeddingDependencyLoaderCallable | None = None,
        download_file: DownloadFileCallable | None = None,
        download_snapshot: DownloadSnapshotCallable | None = None,
    ) -> None:
        self._config = config
        self._backend = backend
        self._dependency_loader = dependency_loader
        self._download_file = download_file
        self._download_snapshot = download_snapshot
        self._resolved_model_path: Path | None = None

    def embed(self, items: Sequence[EmbeddingInputItem]) -> EmbeddingBatchResult:
        """Embed one validated batch and return ordered caller IDs with vectors."""

        normalized_items = _validate_embedding_input(items)
        model_path = self._resolve_model_path()
        backend = self._get_backend(model_path)
        try:
            raw_response = backend.create_embedding(
                input=[item.text for item in normalized_items],
                model=self._config.expected_model_id,
            )
        except Exception as exc:  # noqa: BLE001 - backend errors vary.
            raise EmbeddingExecutionError(
                "llama.cpp embedding execution failed"
            ) from exc
        return _normalize_llama_cpp_embedding_response(
            raw_response,
            items=normalized_items,
            expected_model_id=self._config.expected_model_id,
        )

    def _resolve_model_path(self) -> Path:
        if self._resolved_model_path is None:
            self._resolved_model_path = resolve_local_model_path(
                LocalModelPathConfig(
                    model_filename=self._config.model_filename,
                    explicit_model_path=self._config.model_path,
                    model_cache_root=self._config.model_cache_root,
                    huggingface_file=self._config.huggingface_file,
                    huggingface_snapshot=self._config.huggingface_snapshot,
                ),
                allow_network=self._config.allow_network,
                download_file=self._download_file,
                download_snapshot=self._download_snapshot,
            )
        return self._resolved_model_path

    def _get_backend(self, model_path: Path) -> LlamaCppLocalEmbeddingBackend:
        if self._backend is None:
            try:
                loaded = (
                    self._dependency_loader(model_path, self._config)
                    if self._dependency_loader is not None
                    else _load_default_llama_cpp_embedding_backend(
                        model_path, self._config
                    )
                )
            except Exception as exc:  # noqa: BLE001 - loaders vary.
                raise EmbeddingExecutionError(
                    "llama.cpp embedding backend could not be loaded"
                ) from exc
            if not isinstance(loaded, LlamaCppLocalEmbeddingBackend):
                raise EmbeddingExecutionError(
                    "llama.cpp embedding dependency loader returned an invalid backend"
                )
            self._backend = loaded
        return self._backend


class AsyncLlamaCppLocalEmbeddingAdapter:
    """Async wrapper for direct in-process llama.cpp embeddings."""

    def __init__(
        self,
        config: LlamaCppLocalEmbeddingConfig,
        *,
        backend: LlamaCppLocalEmbeddingBackend | None = None,
        dependency_loader: LlamaCppEmbeddingDependencyLoaderCallable | None = None,
        download_file: DownloadFileCallable | None = None,
        download_snapshot: DownloadSnapshotCallable | None = None,
    ) -> None:
        self._sync_adapter = LlamaCppLocalEmbeddingAdapter(
            config,
            backend=backend,
            dependency_loader=dependency_loader,
            download_file=download_file,
            download_snapshot=download_snapshot,
        )

    async def embed(self, items: Sequence[EmbeddingInputItem]) -> EmbeddingBatchResult:
        """Embed a batch without blocking the event loop directly."""

        return await asyncio.to_thread(self._sync_adapter.embed, items)


def create_local_openai_adapter(
    config: LocalOpenAIEndpointConfig,
) -> OpenAIClientAdapter:
    """Build a sync local adapter through the existing provider seam."""

    return create_openai_adapter_from_provider_config(
        _provider_config_from_local_endpoint(config),
        models=config.model_aliases,
        is_local=True,
        execution_profile_adapter_id="strict-local-adapter-v1",
        model_id_mapping=(
            dict.fromkeys(config.model_aliases, config.expected_model_id)
            if config.expected_model_id is not None
            else None
        ),
        error_translator=_local_endpoint_error_translator(config),
        response_validator=_local_endpoint_response_validator(config),
    )


def create_local_async_openai_adapter(
    config: LocalOpenAIEndpointConfig,
) -> AsyncOpenAIClientAdapter:
    """Build an async local adapter through the existing provider seam."""

    return create_async_openai_adapter_from_provider_config(
        _provider_config_from_local_endpoint(config),
        models=config.model_aliases,
        is_local=True,
        execution_profile_adapter_id="strict-local-adapter-v1",
        model_id_mapping=(
            dict.fromkeys(config.model_aliases, config.expected_model_id)
            if config.expected_model_id is not None
            else None
        ),
        error_translator=_local_endpoint_error_translator(config),
        response_validator=_local_endpoint_response_validator(config),
    )


def create_llama_cpp_local_adapter(
    config: LlamaCppLocalModelConfig,
    *,
    backend: LlamaCppLocalBackend | None = None,
    dependency_loader: LlamaCppDependencyLoaderCallable | None = None,
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
) -> LlamaCppLocalModelAdapter:
    """Build a sync direct llama.cpp local adapter."""

    return LlamaCppLocalModelAdapter(
        config,
        backend=backend,
        dependency_loader=dependency_loader,
        download_file=download_file,
        download_snapshot=download_snapshot,
    )


def create_llama_cpp_local_async_adapter(
    config: LlamaCppLocalModelConfig,
    *,
    backend: LlamaCppLocalBackend | None = None,
    dependency_loader: LlamaCppDependencyLoaderCallable | None = None,
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
) -> AsyncLlamaCppLocalModelAdapter:
    """Build an async direct llama.cpp local adapter."""

    return AsyncLlamaCppLocalModelAdapter(
        config,
        backend=backend,
        dependency_loader=dependency_loader,
        download_file=download_file,
        download_snapshot=download_snapshot,
    )


def create_llama_cpp_local_embedding_adapter(
    config: LlamaCppLocalEmbeddingConfig,
    *,
    backend: LlamaCppLocalEmbeddingBackend | None = None,
    dependency_loader: LlamaCppEmbeddingDependencyLoaderCallable | None = None,
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
) -> LlamaCppLocalEmbeddingAdapter:
    """Build a sync direct llama.cpp embedding adapter."""

    return LlamaCppLocalEmbeddingAdapter(
        config,
        backend=backend,
        dependency_loader=dependency_loader,
        download_file=download_file,
        download_snapshot=download_snapshot,
    )


def create_llama_cpp_local_async_embedding_adapter(
    config: LlamaCppLocalEmbeddingConfig,
    *,
    backend: LlamaCppLocalEmbeddingBackend | None = None,
    dependency_loader: LlamaCppEmbeddingDependencyLoaderCallable | None = None,
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
) -> AsyncLlamaCppLocalEmbeddingAdapter:
    """Build an async direct llama.cpp embedding adapter."""

    return AsyncLlamaCppLocalEmbeddingAdapter(
        config,
        backend=backend,
        dependency_loader=dependency_loader,
        download_file=download_file,
        download_snapshot=download_snapshot,
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
    default_cache_hit = _resolve_default_cache_hit(
        cache_root=default_cache_root,
        model_filename=config.model_filename,
        repo_id=_huggingface_reference_repo_id(config),
        revision=_huggingface_reference_revision(config),
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
    explicit_model_path: Path | None = None,
    huggingface_file: HuggingFaceModelFileReference | None = None,
    huggingface_snapshot: HuggingFaceSnapshotReference | None = None,
) -> None:
    """Validate that the observed local-model identity matches the intended one."""

    if expected_model_id is None or observed_model_id is None:
        return
    if expected_model_id == observed_model_id:
        return
    if (
        explicit_model_path is not None
        and huggingface_file is not None
        and observed_model_id == str(explicit_model_path)
    ):
        return
    authoritative_identity = _describe_authoritative_model_identity(
        expected_model_id=expected_model_id,
        explicit_model_path=explicit_model_path,
        huggingface_file=huggingface_file,
        huggingface_snapshot=huggingface_snapshot,
    )
    raise LocalModelIdentityMismatchError(
        "Local model identity mismatch for requested model "
        f"{requested_model!r}: expected {authoritative_identity} but observed "
        f"{observed_model_id!r}"
    )


def _provider_config_from_local_endpoint(
    config: LocalOpenAIEndpointConfig,
) -> OpenAIProviderConfig:
    return OpenAIProviderConfig(
        base_url=config.base_url,
        api_key=config.api_key or "local-endpoint",
        provider_name=config.provider_name or "openai",
        discover_default_auth=False,
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


def _local_endpoint_response_validator(
    config: LocalOpenAIEndpointConfig,
):
    def validate(request: OpenAIModelRequest, response: ModelResponse) -> None:
        validate_local_model_identity(
            requested_model=request.model,
            expected_model_id=config.expected_model_id,
            observed_model_id=_read_observed_model_id(response.raw),
        )

    return validate


def _describe_local_endpoint(config: LocalOpenAIEndpointConfig) -> str:
    provider_name = config.provider_name or "local endpoint"
    aliases = ", ".join(repr(alias) for alias in config.model_aliases)
    return (
        f"provider {provider_name!r} at {config.base_url!r} serving aliases ({aliases})"
    )


def _describe_authoritative_model_identity(
    *,
    expected_model_id: str,
    explicit_model_path: Path | None,
    huggingface_file: HuggingFaceModelFileReference | None,
    huggingface_snapshot: HuggingFaceSnapshotReference | None,
) -> str:
    details = [f"runtime-owned expected model id {expected_model_id!r}"]
    if explicit_model_path is not None:
        details.append(f"explicit local path {str(explicit_model_path)!r}")
    if huggingface_file is not None:
        details.append(
            "Hugging Face file reference "
            f"repo_id={huggingface_file.repo_id!r}, "
            f"filename={huggingface_file.filename!r}, "
            f"revision={huggingface_file.revision!r}"
        )
    if huggingface_snapshot is not None:
        details.append(
            "Hugging Face snapshot reference "
            f"repo_id={huggingface_snapshot.repo_id!r}, "
            f"revision={huggingface_snapshot.revision!r}"
        )
    return ", ".join(details)


def _read_observed_model_id(raw_response: object) -> str | None:
    if isinstance(raw_response, dict):
        observed_model_id = raw_response.get("model")
    else:
        observed_model_id = getattr(raw_response, "model", None)
    return str(observed_model_id) if observed_model_id is not None else None


def _read_backend_model_id(backend: LlamaCppLocalBackend) -> str | None:
    for attribute_name in ("model_id", "model_name", "model_path"):
        model_id = getattr(backend, attribute_name, None)
        if model_id is not None:
            return str(model_id)
    return None


def _llama_cpp_chatml_tools(
    tools: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Adapt DAR's flat tool shape to llama.cpp's chatml handler contract."""

    adapted: list[dict[str, object]] = []
    for tool in tools:
        function = tool.get("function")
        if isinstance(function, Mapping):
            adapted.append(dict(tool))
            continue
        adapted.append(
            {
                "type": tool.get("type", "function"),
                "function": {
                    key: tool[key]
                    for key in ("name", "description", "parameters")
                    if key in tool
                },
            }
        )
    return adapted


def _llama_cpp_chatml_messages(
    messages: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Render tool results in the user role understood by llama.cpp's handler."""

    adapted: list[dict[str, object]] = []
    for message in messages:
        if message.get("role") != "tool":
            adapted.append(dict(message))
            continue
        tool_name = str(message.get("name") or "tool")
        adapted.append(
            {
                "role": "user",
                "content": f"Tool result from {tool_name}:\n{message.get('content', '')}",
            }
        )
    return adapted


def _normalize_llama_cpp_chat_response(raw_response: object) -> ModelResponse:
    if isinstance(raw_response, str):
        return ModelResponse(content=raw_response, raw=raw_response)
    if isinstance(raw_response, Mapping):
        content = _read_llama_cpp_response_content(raw_response)
        tool_calls = _read_llama_cpp_tool_calls(raw_response)
        response_id = raw_response.get("id")
        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            response_id=str(response_id) if response_id is not None else None,
            raw=raw_response,
        )
    content = getattr(raw_response, "content", None)
    if content is None:
        content = getattr(raw_response, "output_text", None)
    return ModelResponse(
        content=str(content) if content is not None else str(raw_response),
        raw=raw_response,
    )


def _read_llama_cpp_response_content(raw_response: Mapping[str, object]) -> str | None:
    output_text = raw_response.get("output_text")
    if output_text is not None:
        return str(output_text)
    choices = raw_response.get("choices")
    if not isinstance(choices, Sequence) or isinstance(choices, str):
        return None
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        text = choice.get("text")
        if text is not None:
            return str(text)
        message = choice.get("message")
        if isinstance(message, Mapping):
            content = message.get("content")
            if content is not None:
                return str(content)
    return None


def _read_llama_cpp_tool_calls(
    raw_response: Mapping[str, object],
) -> tuple[ModelToolCall, ...]:
    calls = _read_llama_cpp_explicit_tool_calls(raw_response)
    return calls or _read_llama_cpp_chatml_function_text(raw_response)


def _read_llama_cpp_explicit_tool_calls(
    raw_response: Mapping[str, object],
) -> tuple[ModelToolCall, ...]:
    choices = raw_response.get("choices")
    if not isinstance(choices, Sequence) or isinstance(choices, str):
        return ()
    calls: list[ModelToolCall] = []
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        message = choice.get("message")
        if not isinstance(message, Mapping):
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, Sequence) or isinstance(tool_calls, str):
            continue
        for tool_call in tool_calls:
            if not isinstance(tool_call, Mapping):
                continue
            function = tool_call.get("function")
            if not isinstance(function, Mapping):
                continue
            name = function.get("name")
            if name is None:
                continue
            calls.append(
                ModelToolCall(
                    id=(
                        str(tool_call["id"])
                        if tool_call.get("id") is not None
                        else None
                    ),
                    name=str(name),
                    arguments=function.get("arguments", ""),
                )
            )
    return tuple(calls)


def _read_llama_cpp_chatml_function_text(
    raw_response: Mapping[str, object],
) -> tuple[ModelToolCall, ...]:
    """Decode one escaped ChatML handler function call emitted as message text."""

    content = _read_llama_cpp_response_content(raw_response)
    if content is None:
        return ()
    matched = re.fullmatch(
        r"\s*functions\.([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(\{.*\})\s*",
        html.unescape(content),
        flags=re.DOTALL,
    )
    if matched is None:
        return ()
    try:
        arguments = json.loads(matched.group(2))
    except json.JSONDecodeError:
        return ()
    if not isinstance(arguments, Mapping):
        return ()
    return (
        ModelToolCall(
            id=None,
            name=matched.group(1),
            arguments=dict(arguments),
        ),
    )


def _load_default_llama_cpp_backend(
    model_path: Path,
    config: LlamaCppLocalModelConfig,
) -> object:
    try:
        from llama_cpp import Llama
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise ModelExecutionError(
            "llama.cpp dependency unavailable for local model execution; install "
            "llama-cpp-python before using the default llama.cpp backend"
        ) from exc
    try:
        return Llama(model_path=str(model_path), **dict(config.model_kwargs or {}))
    except Exception as exc:  # noqa: BLE001 - llama.cpp load errors vary.
        raise ModelExecutionError(
            f"llama.cpp local model load failed for {model_path!s}: {exc}"
        ) from exc


def _load_default_llama_cpp_embedding_backend(
    model_path: Path,
    config: LlamaCppLocalEmbeddingConfig,
) -> object:
    try:
        from llama_cpp import Llama
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise EmbeddingExecutionError(
            "llama.cpp dependency unavailable for local embedding execution"
        ) from exc
    try:
        return Llama(
            model_path=str(model_path),
            embedding=True,
            **dict(config.model_kwargs or {}),
        )
    except Exception as exc:  # noqa: BLE001 - llama.cpp load errors vary.
        raise EmbeddingExecutionError("llama.cpp embedding model load failed") from exc


def _validate_embedding_input(
    items: Sequence[EmbeddingInputItem],
) -> tuple[EmbeddingInputItem, ...]:
    normalized_items = tuple(items)
    if not normalized_items or len(normalized_items) > 128:
        raise EmbeddingInputError("embedding batch has an invalid entry count")
    seen_ids: set[str] = set()
    total_text_bytes = 0
    for item in normalized_items:
        if not isinstance(item, EmbeddingInputItem):
            raise EmbeddingInputError("embedding batch contains an invalid entry")
        if not item.id or not isinstance(item.id, str) or item.id in seen_ids:
            raise EmbeddingInputError("embedding batch contains an invalid entry ID")
        if not isinstance(item.text, str):
            raise EmbeddingInputError("embedding batch contains invalid text")
        try:
            id_bytes = len(item.id.encode("utf-8"))
            text_bytes = len(item.text.encode("utf-8"))
        except UnicodeError as exc:
            raise EmbeddingInputError("embedding batch contains invalid text") from exc
        if id_bytes > 128:
            raise EmbeddingInputError("embedding batch contains an oversized entry ID")
        if text_bytes > 64 * 1024:
            raise EmbeddingInputError("embedding batch contains oversized text")
        total_text_bytes += text_bytes
        if total_text_bytes > 1024 * 1024:
            raise EmbeddingInputError("embedding batch text exceeds the batch limit")
        seen_ids.add(item.id)
    return normalized_items


def _validate_tool_embedding_input(
    arguments: Mapping[str, object],
) -> tuple[EmbeddingInputItem, ...]:
    if set(arguments) != {"items"}:
        raise EmbeddingInputError("embedding tool has invalid input")
    raw_items = arguments.get("items")
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 8:
        raise EmbeddingInputError("embedding tool has invalid input")
    items: list[EmbeddingInputItem] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping) or set(raw_item) != {"id", "text"}:
            raise EmbeddingInputError("embedding tool has invalid input")
        item_id = raw_item.get("id")
        text = raw_item.get("text")
        if not isinstance(item_id, str) or not isinstance(text, str):
            raise EmbeddingInputError("embedding tool has invalid input")
        items.append(EmbeddingInputItem(id=item_id, text=text))
    normalized = _validate_embedding_input(items)
    if any(len(item.text.encode("utf-8")) > 8 * 1024 for item in normalized):
        raise EmbeddingInputError("embedding tool has oversized text")
    if sum(len(item.text.encode("utf-8")) for item in normalized) > 64 * 1024:
        raise EmbeddingInputError("embedding tool input exceeds the batch limit")
    return normalized


def _validate_tool_embedding_result(
    result: object, items: tuple[EmbeddingInputItem, ...]
) -> EmbeddingBatchResult:
    if not isinstance(result, EmbeddingBatchResult) or not result.model:
        raise EmbeddingResultError("embedding tool returned an invalid result")
    if not isinstance(result.model, str) or not isinstance(result.items, tuple):
        raise EmbeddingResultError("embedding tool returned an invalid result")
    if tuple(item.id for item in result.items) != tuple(item.id for item in items):
        raise EmbeddingResultError("embedding tool returned an invalid result")
    dimension: int | None = None
    scalar_count = 0
    for item in result.items:
        item_dimension = _validate_tool_embedding_vector(item)
        if dimension is None:
            dimension = item_dimension
        elif item_dimension != dimension:
            raise EmbeddingResultError("embedding tool returned an invalid result")
        scalar_count += item_dimension
    if scalar_count > 16_384:
        raise EmbeddingResultError("embedding tool returned an invalid result")
    encoded = json.dumps(
        {
            "model": result.model,
            "items": [{"id": item.id, "vector": item.vector} for item in result.items],
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > 256 * 1024:
        raise EmbeddingResultError("embedding tool returned an invalid result")
    return result


def _validate_tool_embedding_vector(item: object) -> int:
    if not isinstance(item, EmbeddingVectorItem) or not isinstance(item.vector, tuple):
        raise EmbeddingResultError("embedding tool returned an invalid result")
    if not 1 <= len(item.vector) <= 2048:
        raise EmbeddingResultError("embedding tool returned an invalid result")
    if any(
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(float(value))
        for value in item.vector
    ):
        raise EmbeddingResultError("embedding tool returned an invalid result")
    return len(item.vector)


def _normalize_llama_cpp_embedding_response(
    raw_response: object,
    *,
    items: tuple[EmbeddingInputItem, ...],
    expected_model_id: str,
) -> EmbeddingBatchResult:
    if not isinstance(raw_response, Mapping):
        raise EmbeddingResultError("llama.cpp returned an invalid embedding result")
    observed_model_id = raw_response.get("model")
    if not isinstance(observed_model_id, str) or not observed_model_id:
        raise EmbeddingResultError("llama.cpp embedding result has no model identity")
    validate_local_model_identity(
        requested_model=expected_model_id,
        expected_model_id=expected_model_id,
        observed_model_id=observed_model_id,
    )
    raw_data = raw_response.get("data")
    if not isinstance(raw_data, Sequence) or isinstance(raw_data, str):
        raise EmbeddingResultError("llama.cpp returned an invalid embedding result")
    if len(raw_data) != len(items):
        raise EmbeddingResultError("llama.cpp returned an invalid embedding result")

    vectors_by_index = _normalize_embedding_rows(raw_data, entry_count=len(items))

    if len(vectors_by_index) != len(items):
        raise EmbeddingResultError("llama.cpp returned an invalid embedding result")
    result_items = tuple(
        EmbeddingVectorItem(id=item.id, vector=vectors_by_index[index])
        for index, item in enumerate(items)
    )
    result = EmbeddingBatchResult(model=observed_model_id, items=result_items)
    encoded_result = json.dumps(
        {
            "model": result.model,
            "items": [{"id": item.id, "vector": item.vector} for item in result.items],
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded_result) > 16 * 1024 * 1024:
        raise EmbeddingResultError("llama.cpp returned an oversized embedding result")
    return result


def _normalize_embedding_rows(
    raw_data: Sequence[object], *, entry_count: int
) -> dict[int, tuple[float, ...]]:
    vectors_by_index: dict[int, tuple[float, ...]] = {}
    expected_dimension: int | None = None
    scalar_count = 0
    for raw_entry in raw_data:
        index, vector = _normalize_embedding_row(
            raw_entry,
            entry_count=entry_count,
            seen_indexes=vectors_by_index,
        )
        if expected_dimension is None:
            expected_dimension = len(vector)
        elif len(vector) != expected_dimension:
            raise EmbeddingResultError("llama.cpp returned ragged embeddings")
        scalar_count += len(vector)
        if scalar_count > 1_048_576:
            raise EmbeddingResultError("llama.cpp returned oversized embeddings")
        vectors_by_index[index] = vector
    return vectors_by_index


def _normalize_embedding_row(
    raw_entry: object,
    *,
    entry_count: int,
    seen_indexes: Mapping[int, tuple[float, ...]],
) -> tuple[int, tuple[float, ...]]:
    if not isinstance(raw_entry, Mapping):
        raise EmbeddingResultError("llama.cpp returned an invalid embedding result")
    index = raw_entry.get("index")
    raw_vector = raw_entry.get("embedding")
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or index < 0
        or index >= entry_count
        or index in seen_indexes
        or not isinstance(raw_vector, list | tuple)
        or not raw_vector
    ):
        raise EmbeddingResultError("llama.cpp returned an invalid embedding result")
    vector = _normalize_embedding_vector(raw_vector)
    if len(vector) > 8192:
        raise EmbeddingResultError("llama.cpp returned an oversized embedding")
    return index, vector


def _normalize_embedding_vector(raw_vector: Sequence[object]) -> tuple[float, ...]:
    vector: list[float] = []
    for raw_scalar in raw_vector:
        if isinstance(raw_scalar, bool) or not isinstance(raw_scalar, int | float):
            raise EmbeddingResultError("llama.cpp returned an invalid embedding result")
        try:
            scalar = float(raw_scalar)
        except OverflowError as exc:
            raise EmbeddingResultError(
                "llama.cpp returned an invalid embedding result"
            ) from exc
        if not math.isfinite(scalar):
            raise EmbeddingResultError("llama.cpp returned an invalid embedding result")
        vector.append(scalar)
    return tuple(vector)


def _default_local_model_cache_root() -> Path:
    return Path.home() / ".cache" / "huggingface" / "hub"


def _availability_model_filename(reference: LocalModelAssetReference) -> str | None:
    if reference.model_filename:
        return reference.model_filename
    if reference.filename:
        return reference.filename
    if reference.explicit_path is not None:
        return reference.explicit_path.name
    return None


def _availability_for_candidate(
    *,
    reference: LocalModelAssetReference,
    model_path: Path,
    source: LocalModelAvailabilitySource,
    cache_root: Path | None,
    missing_message: str | None = None,
) -> LocalModelAvailability:
    if not model_path.exists():
        return LocalModelAvailability(
            status=LocalModelAvailabilityStatus.MISSING,
            reference=reference,
            cache_root=cache_root,
            source=LocalModelAvailabilitySource.NOT_FOUND,
            message=missing_message or f"Local model asset {model_path!s} is missing",
        )
    validation_message = _validate_available_model_path(model_path, reference)
    if validation_message is not None:
        return LocalModelAvailability(
            status=LocalModelAvailabilityStatus.INVALID,
            reference=reference,
            resolved_path=model_path,
            cache_root=cache_root,
            source=source,
            message=validation_message,
        )
    return LocalModelAvailability(
        status=LocalModelAvailabilityStatus.AVAILABLE,
        reference=reference,
        resolved_path=model_path,
        cache_root=cache_root,
        source=source,
        message=f"Local model asset {model_path!s} is available",
    )


def _validate_available_model_path(
    model_path: Path,
    reference: LocalModelAssetReference,
) -> str | None:
    effective_format = _availability_effective_model_format(model_path, reference)
    if effective_format == "gguf":
        if not model_path.is_file():
            return f"GGUF local model path {model_path!s} is not a file"
        if model_path.suffix.lower() != ".gguf":
            return f"GGUF local model path {model_path!s} must use a .gguf suffix"
    if effective_format == "mlx":
        model_directory = model_path if model_path.is_dir() else model_path.parent
        return _validate_available_mlx_directory(model_directory)
    return None


def _availability_effective_model_format(
    model_path: Path,
    reference: LocalModelAssetReference,
) -> str:
    if reference.model_format != "auto":
        return reference.model_format
    if model_path.suffix.lower() == ".gguf":
        return "gguf"
    return "mlx" if reference.backend == "mlx" else "auto"


def _validate_available_mlx_directory(model_directory: Path) -> str | None:
    return _validate_mlx_model_directory(model_directory)


_NATIVE_MLX_SHARD_PATTERN = re.compile(r"model(?:-\d{5}-of-\d{5})?\.safetensors")
_NATIVE_MLX_INDEX_MAX_BYTES = 1024 * 1024
_NATIVE_MLX_INDEX_MAX_ENTRIES = 10_000


def _validate_mlx_model_directory(model_directory: Path) -> str | None:
    if not model_directory.is_dir():
        return f"MLX local model path {model_directory!s} is not a directory"
    allowed_root = _mlx_allowed_root(model_directory)
    converted_error = _converted_mlx_directory_error(
        model_directory,
        allowed_root=allowed_root if allowed_root != model_directory else None,
    )
    if converted_error is None:
        return None
    if any(
        (model_directory / filename).exists()
        for filename in (
            "tokenizer.json",
            "model.safetensors",
            "model.safetensors.index.json",
        )
    ):
        return _native_mlx_directory_error(model_directory)
    return converted_error


def _converted_mlx_directory_error(
    model_directory: Path,
    *,
    allowed_root: Path | None,
) -> str | None:
    def exists(filename: str) -> bool:
        path = model_directory / filename
        return (
            _is_contained_regular_file(path, allowed_root)
            if allowed_root is not None
            else path.exists()
        )

    missing_files = [
        filename
        for filename in ("config.json", "tokenizer.model")
        if not exists(filename)
    ]
    weights = [model_directory / "weights.npz", *model_directory.glob("weights.*.npz")]
    if not any(
        _is_contained_regular_file(path, allowed_root)
        if allowed_root is not None
        else path.exists()
        for path in weights
    ):
        missing_files.append("weights.npz")
    if missing_files:
        return (
            f"MLX local model directory {model_directory!s} is missing "
            f"required file(s): {', '.join(missing_files)}"
        )
    return None


def _native_mlx_directory_error(model_directory: Path) -> str | None:
    allowed_root = _mlx_allowed_root(model_directory)
    for filename in ("config.json", "tokenizer.json"):
        if not _is_contained_regular_file(model_directory / filename, allowed_root):
            return (
                f"MLX native model directory {model_directory!s} is missing "
                f"required file(s): {filename}"
            )
    index_path = model_directory / "model.safetensors.index.json"
    shard_paths = {
        path.name: path
        for path in model_directory.iterdir()
        if _NATIVE_MLX_SHARD_PATTERN.fullmatch(path.name)
    }
    if not index_path.exists():
        if set(shard_paths) != {"model.safetensors"}:
            return (
                f"MLX native model directory {model_directory!s} requires exactly "
                "model.safetensors or a valid index"
            )
        if not _is_contained_regular_file(
            shard_paths["model.safetensors"], allowed_root
        ):
            return f"MLX native model directory {model_directory!s} has an invalid model.safetensors"
        return None
    return _native_mlx_index_error(model_directory, allowed_root, shard_paths)


def _native_mlx_index_error(
    model_directory: Path,
    allowed_root: Path,
    shard_paths: Mapping[str, Path],
) -> str | None:
    index_path = model_directory / "model.safetensors.index.json"
    if not _is_contained_regular_file(index_path, allowed_root):
        return f"MLX native model directory {model_directory!s} has an invalid safetensors index"
    try:
        if index_path.stat().st_size > _NATIVE_MLX_INDEX_MAX_BYTES:
            raise ValueError("index exceeds byte limit")
        payload = index_path.read_bytes()
        index = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_object_keys,
        )
        weight_map = index["weight_map"]
        if (
            not isinstance(index, dict)
            or not isinstance(weight_map, dict)
            or not weight_map
            or len(weight_map) > _NATIVE_MLX_INDEX_MAX_ENTRIES
        ):
            raise ValueError("invalid weight map")
    except (
        KeyError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        TypeError,
    ):
        return f"MLX native model directory {model_directory!s} has an invalid safetensors index"
    referenced = set()
    for shard_name in weight_map.values():
        if not isinstance(shard_name, str) or not _NATIVE_MLX_SHARD_PATTERN.fullmatch(
            shard_name
        ):
            return f"MLX native model directory {model_directory!s} has an invalid safetensors shard reference"
        shard_path = model_directory / shard_name
        if not _is_contained_regular_file(shard_path, allowed_root):
            return f"MLX native model directory {model_directory!s} has an invalid safetensors shard reference"
        referenced.add(shard_name)
    if set(shard_paths) != referenced:
        return f"MLX native model directory {model_directory!s} has unreferenced safetensors shard files"
    return None


def _reject_duplicate_json_object_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _mlx_allowed_root(model_directory: Path) -> Path:
    snapshots_root = model_directory.parent
    repository_root = snapshots_root.parent
    if snapshots_root.name == "snapshots" and repository_root.name.startswith(
        "models--"
    ):
        return repository_root
    return model_directory


def _is_contained_regular_file(path: Path, allowed_root: Path) -> bool:
    return path.is_file() and _is_path_within(path, allowed_root)


def _scan_local_model_inventory_root(
    *,
    cache_root: Path,
    source: LocalModelAvailabilitySource,
    assets: list[LocalModelInventoryItem],
    warnings: list[str],
    seen_paths: set[Path],
    scan_hub_snapshots: bool,
) -> None:
    if not cache_root.exists():
        warnings.append(f"Local model inventory root {cache_root!s} does not exist")
        return
    if not cache_root.is_dir():
        warnings.append(f"Local model inventory root {cache_root!s} is not a directory")
        return
    if scan_hub_snapshots:
        _scan_hub_snapshot_inventory_root(
            cache_root=cache_root,
            source=source,
            assets=assets,
            seen_paths=seen_paths,
        )
        return
    for child in sorted(cache_root.iterdir(), key=lambda path: path.name):
        if child.name.startswith("."):
            continue
        resolved_child = child.resolve()
        if resolved_child in seen_paths:
            continue
        item = _local_model_inventory_item_for_child(
            child=child,
            cache_root=cache_root,
            source=source,
        )
        if item is None:
            continue
        seen_paths.add(resolved_child)
        assets.append(item)


def _scan_hub_snapshot_inventory_root(
    *,
    cache_root: Path,
    source: LocalModelAvailabilitySource,
    assets: list[LocalModelInventoryItem],
    seen_paths: set[Path],
) -> None:
    resolved_cache_root = cache_root.resolve()
    for repository_root in sorted(
        cache_root.glob("models--*"), key=lambda path: path.name
    ):
        if repository_root.is_symlink() or not repository_root.is_dir():
            continue
        if not _is_path_within(repository_root, resolved_cache_root):
            continue
        snapshots_root = repository_root / "snapshots"
        if snapshots_root.is_symlink() or not snapshots_root.is_dir():
            continue
        for snapshot_root in sorted(
            snapshots_root.iterdir(), key=lambda path: path.name
        ):
            if (
                snapshot_root.is_symlink()
                or not snapshot_root.is_dir()
                or not _is_safe_hub_component(snapshot_root.name)
                or not _is_path_within(snapshot_root, snapshots_root)
            ):
                continue
            _append_hub_snapshot_inventory_items(
                snapshot_root=snapshot_root,
                repository_root=repository_root,
                cache_root=cache_root,
                source=source,
                assets=assets,
                seen_paths=seen_paths,
            )


def _append_hub_snapshot_inventory_items(
    *,
    snapshot_root: Path,
    repository_root: Path,
    cache_root: Path,
    source: LocalModelAvailabilitySource,
    assets: list[LocalModelInventoryItem],
    seen_paths: set[Path],
) -> None:
    if _is_contained_hub_mlx_snapshot(snapshot_root, repository_root):
        resolved_snapshot = snapshot_root.resolve()
        if resolved_snapshot not in seen_paths:
            seen_paths.add(resolved_snapshot)
            assets.append(
                LocalModelInventoryItem(
                    path=snapshot_root,
                    cache_root=cache_root,
                    source=source,
                    model_format="mlx",
                    backend="mlx",
                )
            )
        return
    for child in sorted(snapshot_root.iterdir(), key=lambda path: path.name):
        if (
            child.suffix.lower() != ".gguf"
            or not child.is_file()
            or not _is_path_within(child, repository_root)
        ):
            continue
        resolved_child = child.resolve()
        if resolved_child in seen_paths:
            continue
        seen_paths.add(resolved_child)
        assets.append(
            LocalModelInventoryItem(
                path=child,
                cache_root=cache_root,
                source=source,
                model_format="gguf",
                backend="llama_cpp",
            )
        )


def _is_contained_hub_mlx_snapshot(
    snapshot_root: Path,
    repository_root: Path,
) -> bool:
    return (
        _mlx_allowed_root(snapshot_root) == repository_root
        and _validate_mlx_model_directory(snapshot_root) is None
    )


def _local_model_inventory_item_for_child(
    *,
    child: Path,
    cache_root: Path,
    source: LocalModelAvailabilitySource,
) -> LocalModelInventoryItem | None:
    if child.is_file() and child.suffix.lower() == ".gguf":
        return LocalModelInventoryItem(
            path=child,
            cache_root=cache_root,
            source=source,
            model_format="gguf",
            backend="llama_cpp",
        )
    if child.is_dir() and _validate_available_mlx_directory(child) is None:
        return LocalModelInventoryItem(
            path=child,
            cache_root=cache_root,
            source=source,
            model_format="mlx",
            backend="mlx",
        )
    return None


def _availability_from_remote_metadata(
    *,
    reference: LocalModelAssetReference,
    model_filename: str,
    metadata_lookup: RemoteMetadataLookupCallable,
) -> LocalModelAvailability:
    try:
        metadata = metadata_lookup(reference)
    except Exception as exc:  # noqa: BLE001 - metadata backends vary.
        return LocalModelAvailability(
            status=LocalModelAvailabilityStatus.UNKNOWN,
            reference=reference,
            source=LocalModelAvailabilitySource.NOT_FOUND,
            message=f"Local model remote metadata lookup failed: {exc}",
        )
    if metadata.exists is True:
        return LocalModelAvailability(
            status=LocalModelAvailabilityStatus.WOULD_DOWNLOAD,
            reference=reference,
            source=LocalModelAvailabilitySource.NOT_FOUND,
            size_bytes=metadata.size_bytes,
            message=metadata.message
            or f"Local model asset {model_filename!r} would require download",
            warnings=metadata.warnings,
        )
    if metadata.exists is False:
        return LocalModelAvailability(
            status=LocalModelAvailabilityStatus.INVALID,
            reference=reference,
            source=LocalModelAvailabilitySource.NOT_FOUND,
            message=metadata.message
            or f"Remote local model asset {model_filename!r} is unavailable",
            warnings=metadata.warnings,
        )
    return LocalModelAvailability(
        status=LocalModelAvailabilityStatus.UNKNOWN,
        reference=reference,
        source=LocalModelAvailabilitySource.NOT_FOUND,
        size_bytes=metadata.size_bytes,
        message=metadata.message
        or f"Local model asset {model_filename!r} availability is unknown",
        warnings=metadata.warnings,
    )


def _resolve_cache_hit(*, cache_root: Path | None, model_filename: str) -> Path | None:
    if cache_root is None:
        return None
    candidate = Path(cache_root) / model_filename
    if candidate.exists():
        return candidate
    return None


def _resolve_default_cache_hit(
    *,
    cache_root: Path,
    model_filename: str,
    repo_id: str | None,
    revision: str | None,
) -> Path | None:
    if repo_id is None:
        return _resolve_cache_hit(cache_root=cache_root, model_filename=model_filename)
    repository_root = _hub_repository_cache_root(cache_root, repo_id)
    if repository_root is None:
        return None
    snapshot_id = _hub_snapshot_id(
        repository_root=repository_root,
        revision=revision,
    )
    if snapshot_id is None:
        return None
    filename_parts = _safe_hub_relative_parts(model_filename)
    if filename_parts is None:
        return None
    snapshots_root = repository_root / "snapshots"
    snapshot_root = snapshots_root / snapshot_id
    candidate = snapshot_root.joinpath(*filename_parts)
    if (
        not candidate.exists()
        or not _is_path_within(snapshot_root, snapshots_root)
        or not _is_path_within(candidate, repository_root)
    ):
        return None
    return candidate


def _huggingface_reference_repo_id(config: LocalModelPathConfig) -> str | None:
    if config.huggingface_file is not None:
        return config.huggingface_file.repo_id
    if config.huggingface_snapshot is not None:
        return config.huggingface_snapshot.repo_id
    return None


def _huggingface_reference_revision(config: LocalModelPathConfig) -> str | None:
    if config.huggingface_file is not None:
        return config.huggingface_file.revision
    if config.huggingface_snapshot is not None:
        return config.huggingface_snapshot.revision
    return None


def _hub_repository_cache_root(cache_root: Path, repo_id: str) -> Path | None:
    repo_parts = _safe_hub_relative_parts(repo_id)
    if repo_parts is None:
        return None
    repository_root = Path(cache_root) / f"models--{'--'.join(repo_parts)}"
    if (
        repository_root.is_symlink()
        or not repository_root.is_dir()
        or not _is_path_within(repository_root, cache_root)
    ):
        return None
    return repository_root


def _hub_snapshot_id(*, repository_root: Path, revision: str | None) -> str | None:
    requested_revision = revision or "main"
    if not _is_safe_hub_component(requested_revision):
        return None
    snapshots_root = repository_root / "snapshots"
    if (
        snapshots_root.is_symlink()
        or not snapshots_root.is_dir()
        or not _is_path_within(snapshots_root, repository_root)
    ):
        return None
    direct_snapshot = snapshots_root / requested_revision
    if direct_snapshot.is_dir() and not direct_snapshot.is_symlink():
        return requested_revision
    refs_root = repository_root / "refs"
    if (
        refs_root.is_symlink()
        or not refs_root.is_dir()
        or not _is_path_within(refs_root, repository_root)
    ):
        return None
    ref_path = refs_root / requested_revision
    if (
        ref_path.is_symlink()
        or not ref_path.is_file()
        or not _is_path_within(ref_path, refs_root)
    ):
        return None
    try:
        snapshot_id = ref_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return snapshot_id if _is_safe_hub_component(snapshot_id) else None


def _safe_hub_relative_parts(value: str) -> tuple[str, ...] | None:
    if not value or value.startswith("/") or "\\" in value:
        return None
    parts = tuple(value.split("/"))
    if not parts or any(not _is_safe_hub_component(part) for part in parts):
        return None
    return parts


def _is_safe_hub_component(value: str) -> bool:
    return (
        bool(value)
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
        and not any(character.isspace() and character != " " for character in value)
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _is_path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


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
    def download_file(
        reference: HuggingFaceModelFileReference,
        cache_root: Path,
    ) -> Path:
        return download_hub_file(
            repo_id=reference.repo_id,
            filename=reference.filename,
            revision=reference.revision,
            cache_dir=cache_root,
        )

    def download_snapshot(
        reference: HuggingFaceSnapshotReference,
        cache_root: Path,
    ) -> Path:
        return download_hub_snapshot(
            repo_id=reference.repo_id,
            revision=reference.revision,
            cache_dir=cache_root,
        )

    return download_file, download_snapshot


def _optional_sha256(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in value)
    ):
        raise ValueError(f"{name} must be a SHA-256 hex digest")
    return value.lower()


def _huggingface_file_fingerprint(
    reference: HuggingFaceModelFileReference | None,
) -> Mapping[str, str | None] | None:
    if reference is None:
        return None
    return {
        "repo_id": reference.repo_id,
        "filename": reference.filename,
        "revision": reference.revision,
    }


def _huggingface_snapshot_fingerprint(
    reference: HuggingFaceSnapshotReference | None,
) -> Mapping[str, str | None] | None:
    if reference is None:
        return None
    return {"repo_id": reference.repo_id, "revision": reference.revision}


def _verify_model_sha256(model_path: Path, expected_sha256: str | None) -> None:
    if expected_sha256 is None:
        return
    digest = hashlib.sha256()
    try:
        with model_path.open("rb") as model_file:
            for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise LocalModelResolutionError("local model asset is unavailable") from exc
    if digest.hexdigest() != expected_sha256:
        raise LocalModelIdentityMismatchError(
            "local model SHA-256 does not match the configured artifact"
        )
