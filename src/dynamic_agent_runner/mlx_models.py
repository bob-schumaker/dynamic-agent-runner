"""Helpers for caller-provided local MLX model execution."""

from __future__ import annotations

import asyncio
import platform
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import ModelResponse, OpenAIModelRequest


PlatformSystemCallable = Callable[[], str]
DependencyLoaderCallable = Callable[[], object]


@runtime_checkable
class MLXLocalBackend(Protocol):
    """Minimal backend interface for MLX text generation."""

    def generate(self, request: OpenAIModelRequest) -> str:
        """Generate final text for a normalized model request."""


@dataclass(frozen=True)
class MLXLocalModelConfig:
    """Configuration for a caller-owned local MLX model."""

    model_aliases: tuple[str, ...]
    model_path: Path
    expected_model_id: str | None = None

    def __init__(
        self,
        *,
        model_aliases: Sequence[str],
        model_path: str | Path,
        expected_model_id: str | None = None,
    ) -> None:
        object.__setattr__(
            self,
            "model_aliases",
            tuple(str(model_alias) for model_alias in model_aliases),
        )
        object.__setattr__(self, "model_path", Path(model_path))
        object.__setattr__(self, "expected_model_id", expected_model_id)


class MLXLocalModelAdapter:
    """Sync adapter for in-process local MLX text generation."""

    def __init__(
        self,
        config: MLXLocalModelConfig,
        *,
        backend: MLXLocalBackend | None = None,
        dependency_loader: DependencyLoaderCallable | None = None,
        platform_system: PlatformSystemCallable | None = None,
    ) -> None:
        self._config = config
        self._backend = backend
        self._dependency_loader = dependency_loader or _default_dependency_loader
        self._platform_system = platform_system or platform.system

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Generate and normalize a local MLX model response."""

        _ensure_supported_platform(self._platform_system())
        _validate_supported_request(request)
        backend = self._get_backend()
        try:
            content = backend.generate(request)
        except ModelExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - backend errors vary.
            raise ModelExecutionError(
                f"MLX local model generation failed for {request.model!r}: {exc}"
            ) from exc
        return ModelResponse(content=str(content), raw=content)

    @property
    def models(self) -> tuple[str, ...]:
        """Return advertised model names for adapter selection."""

        return self._config.model_aliases

    @property
    def is_local(self) -> bool:
        """Return whether this adapter is local execution."""

        return True

    def _get_backend(self) -> MLXLocalBackend:
        if self._backend is None:
            try:
                loaded = self._dependency_loader()
            except ModelExecutionError:
                raise
            except ImportError as exc:
                raise ModelExecutionError(
                    "MLX dependency unavailable for local model execution; "
                    "install MLX support before creating a default MLX backend"
                ) from exc
            if not isinstance(loaded, MLXLocalBackend):
                raise ModelExecutionError(
                    "MLX dependency loader did not return a local generation backend"
                )
            self._backend = loaded
        return self._backend


class AsyncMLXLocalModelAdapter:
    """Async adapter for in-process local MLX text generation."""

    def __init__(
        self,
        config: MLXLocalModelConfig,
        *,
        backend: MLXLocalBackend | None = None,
        dependency_loader: DependencyLoaderCallable | None = None,
        platform_system: PlatformSystemCallable | None = None,
    ) -> None:
        self._sync_adapter = MLXLocalModelAdapter(
            config,
            backend=backend,
            dependency_loader=dependency_loader,
            platform_system=platform_system,
        )

    async def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Generate a local MLX model response without blocking the event loop."""

        return await asyncio.to_thread(self._sync_adapter.create_response, request)

    @property
    def models(self) -> tuple[str, ...]:
        """Return advertised model names for adapter selection."""

        return self._sync_adapter.models

    @property
    def is_local(self) -> bool:
        """Return whether this adapter is local execution."""

        return True


def create_mlx_local_adapter(
    config: MLXLocalModelConfig,
    *,
    backend: MLXLocalBackend | None = None,
    dependency_loader: DependencyLoaderCallable | None = None,
    platform_system: PlatformSystemCallable | None = None,
) -> MLXLocalModelAdapter:
    """Build a sync local MLX adapter."""

    return MLXLocalModelAdapter(
        config,
        backend=backend,
        dependency_loader=dependency_loader,
        platform_system=platform_system,
    )


def create_mlx_local_async_adapter(
    config: MLXLocalModelConfig,
    *,
    backend: MLXLocalBackend | None = None,
    dependency_loader: DependencyLoaderCallable | None = None,
    platform_system: PlatformSystemCallable | None = None,
) -> AsyncMLXLocalModelAdapter:
    """Build an async local MLX adapter."""

    return AsyncMLXLocalModelAdapter(
        config,
        backend=backend,
        dependency_loader=dependency_loader,
        platform_system=platform_system,
    )


def _ensure_supported_platform(platform_system: str) -> None:
    if platform_system != "Darwin":
        raise ModelExecutionError(
            "MLX local model execution is macOS-only; "
            f"current platform is {platform_system!r}"
        )


def _validate_supported_request(request: OpenAIModelRequest) -> None:
    if request.tools:
        raise ModelExecutionError(
            f"MLX local model adapter does not support tool calls for {request.model!r}"
        )
    if request.response_format is not None:
        raise ModelExecutionError(
            "MLX local model adapter does not support structured response "
            f"formats for {request.model!r}"
        )


def _default_dependency_loader() -> object:
    try:
        import mlx  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise ModelExecutionError(
            "MLX dependency unavailable for local model execution; install MLX "
            "support before creating a default MLX backend"
        ) from exc
    raise ModelExecutionError(
        "MLX local model backend is not configured; provide a backend or use a "
        "future packaged MLX backend implementation"
    )
