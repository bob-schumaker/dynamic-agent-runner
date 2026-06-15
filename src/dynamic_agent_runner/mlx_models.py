"""Helpers for caller-provided local MLX model execution."""

from __future__ import annotations

import asyncio
import platform
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from dynamic_agent_runner.local_models import (
    DownloadFileCallable,
    DownloadSnapshotCallable,
    HuggingFaceModelFileReference,
    HuggingFaceSnapshotReference,
    LocalModelPathConfig,
    resolve_local_model_path,
    validate_local_model_identity,
)
from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.errors import LocalModelResolutionError
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
    model_filename: str
    model_cache_root: Path | None = None
    huggingface_file: HuggingFaceModelFileReference | None = None
    huggingface_snapshot: HuggingFaceSnapshotReference | None = None
    expected_model_id: str | None = None

    def __init__(
        self,
        *,
        model_aliases: Sequence[str],
        model_path: str | Path,
        model_filename: str = "config.json",
        model_cache_root: str | Path | None = None,
        huggingface_file: HuggingFaceModelFileReference | None = None,
        huggingface_snapshot: HuggingFaceSnapshotReference | None = None,
        expected_model_id: str | None = None,
    ) -> None:
        object.__setattr__(
            self,
            "model_aliases",
            tuple(str(model_alias) for model_alias in model_aliases),
        )
        object.__setattr__(self, "model_path", Path(model_path))
        object.__setattr__(self, "model_filename", model_filename)
        object.__setattr__(
            self,
            "model_cache_root",
            Path(model_cache_root) if model_cache_root is not None else None,
        )
        object.__setattr__(self, "huggingface_file", huggingface_file)
        object.__setattr__(self, "huggingface_snapshot", huggingface_snapshot)
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
        download_file: DownloadFileCallable | None = None,
        download_snapshot: DownloadSnapshotCallable | None = None,
    ) -> None:
        self._config = config
        self._backend = backend
        self._dependency_loader = dependency_loader
        self._platform_system = platform_system or platform.system
        self._download_file = download_file
        self._download_snapshot = download_snapshot

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Generate and normalize a local MLX model response."""

        _ensure_supported_platform(self._platform_system())
        _validate_supported_request(request)
        model_path = self._resolve_model_directory()
        backend = self._get_backend()
        validate_local_model_identity(
            requested_model=request.model,
            expected_model_id=self._config.expected_model_id,
            observed_model_id=_read_backend_model_id(backend),
            explicit_model_path=model_path,
            huggingface_file=self._config.huggingface_file,
            huggingface_snapshot=self._config.huggingface_snapshot,
        )
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
                loaded = (
                    self._dependency_loader()
                    if self._dependency_loader is not None
                    else _load_default_mlx_lm_backend(self._config)
                )
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

    def _resolve_model_directory(self) -> Path:
        configured_path = self._config.model_path
        if configured_path.exists():
            model_directory = (
                configured_path if configured_path.is_dir() else configured_path.parent
            )
            _validate_converted_mlx_model_directory(model_directory)
            return model_directory

        if (
            self._config.huggingface_file is None
            and self._config.huggingface_snapshot is None
        ):
            raise LocalModelResolutionError(
                f"MLX local model directory {configured_path!s} does not exist"
            )

        resolved_file = resolve_local_model_path(
            LocalModelPathConfig(
                model_filename=self._config.model_filename,
                model_cache_root=self._config.model_cache_root,
                huggingface_file=self._config.huggingface_file,
                huggingface_snapshot=self._config.huggingface_snapshot,
            ),
            download_file=self._download_file,
            download_snapshot=self._download_snapshot,
        )
        model_directory = resolved_file.parent
        _validate_converted_mlx_model_directory(model_directory)
        return model_directory


class AsyncMLXLocalModelAdapter:
    """Async adapter for in-process local MLX text generation."""

    def __init__(
        self,
        config: MLXLocalModelConfig,
        *,
        backend: MLXLocalBackend | None = None,
        dependency_loader: DependencyLoaderCallable | None = None,
        platform_system: PlatformSystemCallable | None = None,
        download_file: DownloadFileCallable | None = None,
        download_snapshot: DownloadSnapshotCallable | None = None,
    ) -> None:
        self._sync_adapter = MLXLocalModelAdapter(
            config,
            backend=backend,
            dependency_loader=dependency_loader,
            platform_system=platform_system,
            download_file=download_file,
            download_snapshot=download_snapshot,
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
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
) -> MLXLocalModelAdapter:
    """Build a sync local MLX adapter."""

    return MLXLocalModelAdapter(
        config,
        backend=backend,
        dependency_loader=dependency_loader,
        platform_system=platform_system,
        download_file=download_file,
        download_snapshot=download_snapshot,
    )


def create_mlx_local_async_adapter(
    config: MLXLocalModelConfig,
    *,
    backend: MLXLocalBackend | None = None,
    dependency_loader: DependencyLoaderCallable | None = None,
    platform_system: PlatformSystemCallable | None = None,
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
) -> AsyncMLXLocalModelAdapter:
    """Build an async local MLX adapter."""

    return AsyncMLXLocalModelAdapter(
        config,
        backend=backend,
        dependency_loader=dependency_loader,
        platform_system=platform_system,
        download_file=download_file,
        download_snapshot=download_snapshot,
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


def _validate_converted_mlx_model_directory(model_directory: Path) -> None:
    if not model_directory.is_dir():
        raise LocalModelResolutionError(
            f"MLX local model path {model_directory!s} is not a directory"
        )
    missing_files = [
        filename
        for filename in ("config.json", "tokenizer.model")
        if not (model_directory / filename).exists()
    ]
    if not (model_directory / "weights.npz").exists() and not list(
        model_directory.glob("weights.*.npz")
    ):
        missing_files.append("weights.npz")
    if missing_files:
        raise LocalModelResolutionError(
            "MLX local model directory "
            f"{model_directory!s} is missing required file(s): "
            f"{', '.join(missing_files)}"
        )


def _read_backend_model_id(backend: MLXLocalBackend) -> str | None:
    model_id = getattr(backend, "model_id", None)
    if model_id is None:
        model_id = getattr(backend, "model_name", None)
    if model_id is None:
        return None
    return str(model_id)


class _MLXLMBackend:
    def __init__(self, *, model: object, tokenizer: object) -> None:
        self._model = model
        self._tokenizer = tokenizer

    def generate(self, request: OpenAIModelRequest) -> str:
        try:
            from mlx_lm import generate
        except Exception as exc:  # noqa: BLE001 - import errors vary.
            raise ModelExecutionError(
                "MLX dependency unavailable for local model execution; install "
                "mlx-lm before using the default MLX backend"
            ) from exc
        prompt = _prompt_from_request(request)
        return str(generate(self._model, self._tokenizer, prompt=prompt, verbose=False))


def _load_default_mlx_lm_backend(config: MLXLocalModelConfig) -> object:
    try:
        from mlx_lm import load
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise ModelExecutionError(
            "MLX dependency unavailable for local model execution; install mlx-lm "
            "before using the default MLX backend"
        ) from exc
    try:
        model, tokenizer = load(str(config.model_path))
    except Exception as exc:  # noqa: BLE001 - MLX load errors vary.
        raise ModelExecutionError(
            f"MLX local model load failed for {config.model_path!s}: {exc}"
        ) from exc
    return _MLXLMBackend(model=model, tokenizer=tokenizer)


def _prompt_from_request(request: OpenAIModelRequest) -> str:
    parts: list[str] = []
    for message in request.messages:
        role = str(message.get("role", "user"))
        content = message.get("content", "")
        if isinstance(content, str):
            rendered_content = content
        else:
            rendered_content = str(content)
        parts.append(f"{role}: {rendered_content}")
    return "\n".join(parts)
