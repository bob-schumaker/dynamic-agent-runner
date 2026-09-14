"""Sealed, macOS-only admission boundary for generic MLX embeddings."""

from __future__ import annotations

import asyncio
import platform
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol

from dynamic_agent_runner.errors import EmbeddingExecutionError
from dynamic_agent_runner.local_models import EmbeddingBatchResult, EmbeddingInputItem
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptor,
    ExecutionDescriptorError,
    ExecutionDescriptorValidatorRegistry,
)


_MLX_VERSION = "0.32.2"


@dataclass(frozen=True)
class MLXPreparedEmbeddingArtifacts:
    """Receiver-private, admitted material and execution-descriptor identity."""

    execution_abi_id: str
    execution_abi_version: str
    execution_abi_contract_digest: str
    execution_descriptor_digest: str
    material_lock_digest: str
    execution_descriptor: ExecutionDescriptor


class MLXLocalEmbeddingBackend(Protocol):
    """Narrow backend seam used only after closed admission succeeds."""

    def embed(
        self,
        items: tuple[EmbeddingInputItem, ...],
        materials: MLXPreparedEmbeddingArtifacts,
    ) -> EmbeddingBatchResult:
        """Embed one ordered batch using the admitted materials."""


MaterialResolver = Callable[[], MLXPreparedEmbeddingArtifacts]
DependencyLoader = Callable[[], str | None]
PlatformSystem = Callable[[], str]
MacOSVersion = Callable[[], tuple[int, int]]
Machine = Callable[[], str]


@dataclass(frozen=True)
class MLXLocalEmbeddingConfig:
    """Configuration that deliberately excludes model paths and repositories."""

    material_resolver: MaterialResolver
    descriptor_validators: ExecutionDescriptorValidatorRegistry


class MLXLocalEmbeddingAdapter:
    """Synchronously admit and invoke the sealed generic MLX backend."""

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

    def _resolve_materials(self) -> MLXPreparedEmbeddingArtifacts:
        try:
            materials = self._config.material_resolver()
        except Exception as error:  # noqa: BLE001 - receiver material boundary.
            raise EmbeddingExecutionError(
                "MLX embedding material is unavailable"
            ) from error
        if not _has_valid_material_identity(materials):
            raise EmbeddingExecutionError("MLX embedding material is unavailable")
        try:
            self._config.descriptor_validators.validate(materials.execution_descriptor)
        except ExecutionDescriptorError as error:
            raise EmbeddingExecutionError(
                "MLX embedding material is unavailable"
            ) from error
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
    """Build the synchronous sealed generic MLX embedding adapter."""

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
    """Build the asynchronous sealed generic MLX embedding adapter."""

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


def _has_valid_material_identity(materials: object) -> bool:
    if not isinstance(materials, MLXPreparedEmbeddingArtifacts):
        return False
    return bool(
        materials.execution_abi_id
        and materials.execution_abi_version
        and _is_sha256(materials.execution_abi_contract_digest)
        and _is_sha256(materials.execution_descriptor_digest)
        and _is_sha256(materials.material_lock_digest)
        and isinstance(materials.execution_descriptor, ExecutionDescriptor)
        and materials.execution_descriptor.digest
        == materials.execution_descriptor_digest
        and materials.execution_descriptor.architecture_abi.abi_id
        == materials.execution_abi_id
        and materials.execution_descriptor.architecture_abi.version
        == materials.execution_abi_version
        and materials.execution_descriptor.architecture_abi.contract_digest
        == materials.execution_abi_contract_digest
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _load_mlx_version() -> str | None:
    mlx = import_module("mlx")
    version = getattr(mlx, "__version__", None)
    if isinstance(version, str):
        return version

    return getattr(import_module("mlx.core"), "__version__", None)


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
