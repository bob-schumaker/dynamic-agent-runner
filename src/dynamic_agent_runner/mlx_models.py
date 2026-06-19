"""Helpers for caller-provided local MLX model execution."""

from __future__ import annotations

import asyncio
import platform
from collections.abc import Callable, Mapping, Sequence
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

    def generate(self, request: OpenAIModelRequest, **kwargs: object) -> str:
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
    model_format: str = "mlx"
    generation_kwargs: Mapping[str, object] | None = None

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
        model_format: str = "mlx",
        generation_kwargs: Mapping[str, object] | None = None,
    ) -> None:
        normalized_model_format = str(model_format)
        if normalized_model_format not in {"mlx", "gguf", "auto"}:
            raise ValueError("MLX model_format must be 'mlx', 'gguf', or 'auto'")
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
        object.__setattr__(self, "model_format", normalized_model_format)
        object.__setattr__(
            self,
            "generation_kwargs",
            dict(generation_kwargs) if generation_kwargs is not None else None,
        )


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
            generation_kwargs = _generation_kwargs(self._config, request)
            content = _generate_with_backend(backend, request, generation_kwargs)
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

    @property
    def capabilities(self) -> Mapping[str, object]:
        """Return conservative MLX adapter capability metadata."""

        return {
            "provider": "mlx",
            "execution": "in_process",
            "local": True,
            "model_format": (
                "mlx"
                if self._config.model_format == "auto"
                else self._config.model_format
            ),
            "streaming": False,
            "tool_calling": False,
            "structured_output": False,
            "embeddings": False,
            "multimodal": False,
        }

    def _get_backend(self, model_path: Path) -> MLXLocalBackend:
        if self._backend is None:
            try:
                loaded = (
                    self._dependency_loader()
                    if self._dependency_loader is not None
                    else _load_default_mlx_lm_backend(self._config, model_path)
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

    def _resolve_model_path(self) -> Path:
        configured_path = self._config.model_path
        if configured_path.exists():
            return _validate_resolved_mlx_model_path(
                configured_path,
                model_format=self._config.model_format,
            )

        if (
            self._config.huggingface_file is None
            and self._config.huggingface_snapshot is None
        ):
            if self._config.model_format == "gguf":
                _validate_gguf_model_file(configured_path)
            raise LocalModelResolutionError(
                f"MLX local model directory {configured_path!s} does not exist"
            )

        resolved_path = resolve_local_model_path(
            LocalModelPathConfig(
                model_filename=self._config.model_filename,
                model_cache_root=self._config.model_cache_root,
                huggingface_file=self._config.huggingface_file,
                huggingface_snapshot=self._config.huggingface_snapshot,
            ),
            download_file=self._download_file,
            download_snapshot=self._download_snapshot,
        )
        return _validate_resolved_mlx_model_path(
            resolved_path,
            model_format=self._config.model_format,
        )


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

    @property
    def capabilities(self) -> Mapping[str, object]:
        """Return conservative MLX adapter capability metadata."""

        return self._sync_adapter.capabilities


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


def _validate_resolved_mlx_model_path(
    model_path: Path,
    *,
    model_format: str,
) -> Path:
    effective_format = _effective_model_format(model_path, model_format)
    if effective_format == "gguf":
        _validate_gguf_model_file(model_path)
        return model_path
    model_directory = model_path if model_path.is_dir() else model_path.parent
    _validate_converted_mlx_model_directory(model_directory)
    return model_directory


def _effective_model_format(model_path: Path, model_format: str) -> str:
    if model_format != "auto":
        return model_format
    return "gguf" if model_path.suffix.lower() == ".gguf" else "mlx"


def _validate_gguf_model_file(model_path: Path) -> None:
    if not model_path.exists():
        raise LocalModelResolutionError(
            f"MLX GGUF local model file {model_path!s} does not exist"
        )
    if not model_path.is_file():
        raise LocalModelResolutionError(
            f"MLX GGUF local model path {model_path!s} is not a file"
        )
    if model_path.suffix.lower() != ".gguf":
        raise LocalModelResolutionError(
            f"MLX GGUF local model path {model_path!s} must use a .gguf suffix"
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

    def generate(self, request: OpenAIModelRequest, **kwargs: object) -> str:
        try:
            from mlx_lm import generate
        except Exception as exc:  # noqa: BLE001 - import errors vary.
            raise ModelExecutionError(
                "MLX dependency unavailable for local model execution; install "
                "mlx-lm before using the default MLX backend"
            ) from exc
        prompt = _prompt_from_request(request)
        kwargs.setdefault("verbose", False)
        return str(generate(self._model, self._tokenizer, prompt=prompt, **kwargs))


def _load_default_mlx_lm_backend(
    config: MLXLocalModelConfig,
    model_path: Path,
) -> object:
    try:
        from mlx_lm import load
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise ModelExecutionError(
            "MLX dependency unavailable for local model execution; install mlx-lm "
            "before using the default MLX backend"
        ) from exc
    try:
        model, tokenizer = load(str(model_path))
    except Exception as exc:  # noqa: BLE001 - MLX load errors vary.
        raise ModelExecutionError(
            f"MLX local model load failed for {model_path!s}: {exc}"
        ) from exc
    return _MLXLMBackend(model=model, tokenizer=tokenizer)


_SUPPORTED_GENERATION_KWARGS = frozenset(
    {
        "max_tokens",
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "repetition_penalty",
        "repetition_context_size",
        "seed",
    }
)


def _generation_kwargs(
    config: MLXLocalModelConfig,
    request: OpenAIModelRequest,
) -> dict[str, object]:
    kwargs = {
        key: value
        for key, value in dict(config.generation_kwargs or {}).items()
        if key in _SUPPORTED_GENERATION_KWARGS
    }
    kwargs.update(
        {
            key: value
            for key, value in dict(request.extra).items()
            if key in _SUPPORTED_GENERATION_KWARGS
        }
    )
    return kwargs


def _generate_with_backend(
    backend: MLXLocalBackend,
    request: OpenAIModelRequest,
    generation_kwargs: Mapping[str, object],
) -> str:
    if generation_kwargs:
        return backend.generate(request, **dict(generation_kwargs))
    return backend.generate(request)


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
