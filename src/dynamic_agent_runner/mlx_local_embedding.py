"""Closed, macOS-only admission boundary for the MLX GTE Tiny adapter."""

from __future__ import annotations

import asyncio
import platform
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from dynamic_agent_runner.errors import EmbeddingExecutionError
from dynamic_agent_runner.local_models import EmbeddingBatchResult, EmbeddingInputItem


_MLX_VERSION = "0.32.2"
_MATERIAL_LOCK_DIGEST = (
    "c2fc8b91d1b4514f2411f30c4d81fa3a702e902b70ae8a7eb83567696a158c87"
)
_ROLES = (
    "bert_config",
    "bert_weights",
    "modules_manifest",
    "pooling_config",
    "sentence_transformer_config",
    "tokenizer_added_tokens",
    "tokenizer_config",
    "tokenizer_json",
    "tokenizer_special_tokens",
    "tokenizer_vocab",
)


@dataclass(frozen=True)
class MLXGteTinyPreparedArtifacts:
    """Receiver-private, already-resolved materials for the one MLX profile."""

    runner_contract_id: str
    runner_contract_version: str
    loader_profile_contract_id: str
    loader_profile_contract_version: str
    material_lock_digest: str
    roles: tuple[str, ...]


class MLXLocalEmbeddingBackend(Protocol):
    """Narrow backend seam used only after closed admission succeeds."""

    def embed(
        self,
        items: tuple[EmbeddingInputItem, ...],
        materials: MLXGteTinyPreparedArtifacts,
    ) -> EmbeddingBatchResult:
        """Embed one ordered batch using the admitted materials."""


MaterialResolver = Callable[[], MLXGteTinyPreparedArtifacts]
DependencyLoader = Callable[[], str | None]
PlatformSystem = Callable[[], str]
MacOSVersion = Callable[[], tuple[int, int]]
Machine = Callable[[], str]


@dataclass(frozen=True)
class MLXLocalEmbeddingConfig:
    """Configuration that deliberately excludes model paths and repositories."""

    material_resolver: MaterialResolver


class MLXLocalEmbeddingAdapter:
    """Synchronously admit and invoke the closed GTE Tiny backend."""

    def __init__(
        self,
        config: MLXLocalEmbeddingConfig,
        *,
        backend: MLXLocalEmbeddingBackend | None = None,
        dependency_loader: DependencyLoader | None = None,
        platform_system: PlatformSystem | None = None,
        macos_version: MacOSVersion | None = None,
        machine: Machine | None = None,
    ) -> None:
        self._config = config
        self._backend = backend
        self._dependency_loader = dependency_loader or _load_mlx_version
        self._platform_system = platform_system or platform.system
        self._macos_version = macos_version or _macos_version
        self._machine = machine or platform.machine

    def embed(self, items: Sequence[EmbeddingInputItem]) -> EmbeddingBatchResult:
        """Embed an ordered input batch after platform and material admission."""

        self._ensure_supported_platform()
        self._ensure_dependency()
        materials = self._resolve_materials()
        backend = self._backend
        if backend is None:
            raise EmbeddingExecutionError("MLX embedding backend is unavailable")
        try:
            return backend.embed(tuple(items), materials)
        except EmbeddingExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - receiver backend boundary.
            raise EmbeddingExecutionError("MLX embedding execution failed") from error

    @property
    def capabilities(self) -> dict[str, object]:
        """Return inert metadata without probing a host or its materials."""

        return _capabilities(embeddings=False)

    def resolved_capabilities(self) -> dict[str, object]:
        """Report available embeddings only after repeating private admission."""

        self._ensure_supported_platform()
        self._ensure_dependency()
        self._resolve_materials()
        return _capabilities(embeddings=True)

    def _ensure_supported_platform(self) -> None:
        if (
            self._platform_system() != "Darwin"
            or self._macos_version() < (14, 0)
            or self._machine() != "arm64"
        ):
            raise EmbeddingExecutionError("MLX embedding is unavailable")

    def _ensure_dependency(self) -> None:
        try:
            version = self._dependency_loader()
        except Exception as error:  # noqa: BLE001 - import and ABI errors vary.
            raise EmbeddingExecutionError(
                "MLX embedding dependency is unavailable"
            ) from error
        if version != _MLX_VERSION:
            raise EmbeddingExecutionError("MLX embedding dependency is unavailable")

    def _resolve_materials(self) -> MLXGteTinyPreparedArtifacts:
        try:
            materials = self._config.material_resolver()
        except Exception as error:  # noqa: BLE001 - receiver material boundary.
            raise EmbeddingExecutionError(
                "MLX embedding material is unavailable"
            ) from error
        if not _has_expected_material_identity(materials):
            raise EmbeddingExecutionError("MLX embedding material is unavailable")
        return materials


class AsyncMLXLocalEmbeddingAdapter:
    """Async wrapper over the identical synchronous admission path."""

    def __init__(self, adapter: MLXLocalEmbeddingAdapter) -> None:
        self._adapter = adapter

    async def embed(self, items: Sequence[EmbeddingInputItem]) -> EmbeddingBatchResult:
        """Embed without blocking the caller's event loop."""

        return await asyncio.to_thread(self._adapter.embed, items)

    @property
    def capabilities(self) -> dict[str, object]:
        """Return the synchronous adapter's inert capability metadata."""

        return self._adapter.capabilities

    async def resolved_capabilities(self) -> dict[str, object]:
        """Resolve capability admission without blocking the event loop."""

        return await asyncio.to_thread(self._adapter.resolved_capabilities)


def create_mlx_local_embedding_adapter(
    config: MLXLocalEmbeddingConfig,
    *,
    backend: MLXLocalEmbeddingBackend | None = None,
    dependency_loader: DependencyLoader | None = None,
    platform_system: PlatformSystem | None = None,
    macos_version: MacOSVersion | None = None,
    machine: Machine | None = None,
) -> MLXLocalEmbeddingAdapter:
    """Build the synchronous closed MLX GTE Tiny adapter."""

    return MLXLocalEmbeddingAdapter(
        config,
        backend=backend,
        dependency_loader=dependency_loader,
        platform_system=platform_system,
        macos_version=macos_version,
        machine=machine,
    )


def create_mlx_local_embedding_async_adapter(
    config: MLXLocalEmbeddingConfig,
    *,
    backend: MLXLocalEmbeddingBackend | None = None,
    dependency_loader: DependencyLoader | None = None,
    platform_system: PlatformSystem | None = None,
    macos_version: MacOSVersion | None = None,
    machine: Machine | None = None,
) -> AsyncMLXLocalEmbeddingAdapter:
    """Build the asynchronous closed MLX GTE Tiny adapter."""

    return AsyncMLXLocalEmbeddingAdapter(
        create_mlx_local_embedding_adapter(
            config,
            backend=backend,
            dependency_loader=dependency_loader,
            platform_system=platform_system,
            macos_version=macos_version,
            machine=machine,
        )
    )


def _has_expected_material_identity(materials: object) -> bool:
    return isinstance(materials, MLXGteTinyPreparedArtifacts) and (
        materials.runner_contract_id,
        materials.runner_contract_version,
        materials.loader_profile_contract_id,
        materials.loader_profile_contract_version,
        materials.material_lock_digest,
        materials.roles,
    ) == (
        "mlx-gte-tiny-v1",
        "1",
        "mlx-gte-tiny-v1",
        "1",
        _MATERIAL_LOCK_DIGEST,
        _ROLES,
    )


def _load_mlx_version() -> str | None:
    import mlx

    return getattr(mlx, "__version__", None)


def _macos_version() -> tuple[int, int]:
    parts = platform.mac_ver()[0].split(".")
    try:
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return 0, 0


def _capabilities(*, embeddings: bool) -> dict[str, object]:
    return {
        "provider": "mlx",
        "execution": "in_process",
        "local": True,
        "embeddings": embeddings,
        "text_generation": False,
        "tool_calling": False,
        "structured_output": False,
        "streaming": False,
        "multimodal": False,
        "reranking": False,
    }
