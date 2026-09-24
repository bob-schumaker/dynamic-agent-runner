"""Helpers for caller-provided local MLX model execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import uuid4

from dynamic_agent_runner.local_models import (
    DownloadFileCallable,
    DownloadSnapshotCallable,
    HuggingFaceModelFileReference,
    HuggingFaceSnapshotReference,
    LocalModelPathConfig,
    _validate_mlx_model_directory,
    resolve_local_model_path,
    validate_local_model_identity,
)
from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.errors import LocalModelResolutionError
from dynamic_agent_runner.external_adapter import (
    AsyncNativeExternalAdapter,
    ExternalAdapterValidationError,
    ExternalModelAdapterHealth,
    NativeExternalAdapter,
    build_external_adapter_descriptor,
    validate_external_adapter_timeout,
)
from dynamic_agent_runner.openai_client import (
    ModelResponse,
    ModelToolCall,
    OpenAIModelRequest,
)


PlatformSystemCallable = Callable[[], str]
DependencyLoaderCallable = Callable[[], object]


@runtime_checkable
class MLXLocalBackend(Protocol):
    """Minimal backend interface for MLX text generation."""

    def generate(self, request: OpenAIModelRequest, **kwargs: object) -> str:
        """Generate final text for a normalized model request."""


@dataclass(frozen=True)
class MLXToolCallCandidate:
    """One model-family tool call before DAR normalization."""

    name: str
    arguments: str | Mapping[str, object]
    id: str | None = None


@dataclass(frozen=True)
class MLXToolCodecResponse:
    """Decoded MLX output containing text or one tool-call candidate."""

    content: str | None = None
    tool_call: MLXToolCallCandidate | None = None


@runtime_checkable
class MLXToolCodec(Protocol):
    """Versioned caller-injected MLX tool prompt and response codec."""

    version: str

    def render(self, request: OpenAIModelRequest) -> str:
        """Render a complete normalized DAR request for this model family."""

    def decode(self, generated: str) -> MLXToolCodecResponse:
        """Decode text or one candidate from a model-family response."""


@runtime_checkable
class MLXToolCapableBackend(MLXLocalBackend, Protocol):
    """MLX backend that explicitly supports selected tool codec versions."""

    tool_codec_versions: frozenset[str]

    def generate_rendered(self, prompt: str, **kwargs: object) -> str:
        """Generate from a codec-rendered prompt."""


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
        tool_codec: MLXToolCodec | None = None,
    ) -> None:
        self._config = config
        self._backend = backend
        self._dependency_loader = dependency_loader
        self._platform_system = platform_system or platform.system
        self._download_file = download_file
        self._download_snapshot = download_snapshot
        self._tool_codec = tool_codec
        self._generation_lock = threading.Lock()

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Generate and normalize a local MLX model response."""

        _ensure_supported_platform(self._platform_system())
        if request.tools and not _backend_supports_tool_codec(
            self._backend,
            self._tool_codec,
        ):
            raise ModelExecutionError(
                f"MLX local model adapter does not support tool calls for {request.model!r}"
            )
        _validate_supported_request(request, tool_codec=self._tool_codec)
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
        with self._generation_lock:
            try:
                generation_kwargs = _generation_kwargs(self._config, request)
                _validate_supported_request(
                    request,
                    backend=backend,
                    tool_codec=self._tool_codec,
                )
                if request.tools:
                    return _generate_tool_response(
                        backend,
                        self._tool_codec,
                        request,
                        generation_kwargs,
                    )
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
            "tool_calling": _backend_supports_tool_codec(
                self._backend,
                self._tool_codec,
            ),
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
        tool_codec: MLXToolCodec | None = None,
    ) -> None:
        self._sync_adapter = MLXLocalModelAdapter(
            config,
            backend=backend,
            dependency_loader=dependency_loader,
            platform_system=platform_system,
            download_file=download_file,
            download_snapshot=download_snapshot,
            tool_codec=tool_codec,
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
    tool_codec: MLXToolCodec | None = None,
) -> MLXLocalModelAdapter:
    """Build a sync local MLX adapter."""

    return MLXLocalModelAdapter(
        config,
        backend=backend,
        dependency_loader=dependency_loader,
        platform_system=platform_system,
        download_file=download_file,
        download_snapshot=download_snapshot,
        tool_codec=tool_codec,
    )


def create_mlx_local_async_adapter(
    config: MLXLocalModelConfig,
    *,
    backend: MLXLocalBackend | None = None,
    dependency_loader: DependencyLoaderCallable | None = None,
    platform_system: PlatformSystemCallable | None = None,
    download_file: DownloadFileCallable | None = None,
    download_snapshot: DownloadSnapshotCallable | None = None,
    tool_codec: MLXToolCodec | None = None,
) -> AsyncMLXLocalModelAdapter:
    """Build an async local MLX adapter."""

    return AsyncMLXLocalModelAdapter(
        config,
        backend=backend,
        dependency_loader=dependency_loader,
        platform_system=platform_system,
        download_file=download_file,
        download_snapshot=download_snapshot,
        tool_codec=tool_codec,
    )


def _create_mlx_external_descriptor(
    native_adapter: MLXLocalModelAdapter | AsyncMLXLocalModelAdapter,
    *,
    adapter_id: str,
    execution_modes: frozenset[str],
) -> tuple[object, object]:
    aliases = tuple(getattr(native_adapter, "models", ()))
    if len(aliases) != 1:
        raise ExternalAdapterValidationError(
            "MLX external adapter requires exactly one model alias"
        )
    sync_native = getattr(native_adapter, "_sync_adapter", native_adapter)
    config = getattr(sync_native, "_config", None)
    if not isinstance(config, MLXLocalModelConfig):
        raise ExternalAdapterValidationError("MLX adapter configuration is unavailable")
    codec = getattr(sync_native, "_tool_codec", None)
    backend = getattr(sync_native, "_backend", None)
    codec_version = getattr(codec, "version", None)
    codec_enabled = _backend_supports_tool_codec(backend, codec)
    identity = {
        "model_path": str(config.model_path),
        "model_id": config.expected_model_id,
        "model_format": config.model_format,
        "generation": dict(config.generation_kwargs or {}),
        "codec": codec_version if codec_enabled else None,
    }
    canonical_model_id = (
        "mlx/"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    capabilities = {"text_generation"}
    if codec_enabled:
        capabilities.add("tool_calling")
    descriptor = build_external_adapter_descriptor(
        adapter_id=adapter_id,
        provider_id="mlx",
        model_alias=aliases[0],
        canonical_model_id=canonical_model_id,
        execution_modes=execution_modes,  # type: ignore[arg-type]
        capabilities=frozenset(capabilities),
        response_formats=frozenset({"text"}),
    )
    return sync_native, descriptor


def _mlx_health(native_adapter: object) -> ExternalModelAdapterHealth:
    if callable(getattr(native_adapter, "health", None)):
        return native_adapter.health()
    sync_native = getattr(native_adapter, "_sync_adapter", native_adapter)
    try:
        _ensure_supported_platform(sync_native._platform_system())
        path = (
            getattr(sync_native, "_resolved_model_path", None)
            or sync_native._config.model_path
        )
        if not isinstance(path, Path) or not path.exists():
            return ExternalModelAdapterHealth("unavailable", "material_unavailable")
        if getattr(sync_native, "_backend", None) is None:
            return ExternalModelAdapterHealth("unavailable", "runtime_unavailable")
        return ExternalModelAdapterHealth("ready")
    except ModelExecutionError:
        return ExternalModelAdapterHealth("unavailable", "native_unavailable")
    except Exception:
        return ExternalModelAdapterHealth("failed", "native_health_failed")


def create_mlx_external_adapter(
    native_adapter: MLXLocalModelAdapter,
    *,
    adapter_id: str,
    health_timeout_seconds: float = 30.0,
) -> NativeExternalAdapter:
    """Project one caller-owned synchronous MLX adapter onto v1."""

    _, descriptor = _create_mlx_external_descriptor(
        native_adapter,
        adapter_id=adapter_id,
        execution_modes=frozenset({"sync"}),
    )
    return NativeExternalAdapter(
        native_adapter,
        descriptor,
        health_probe=lambda: _mlx_health(native_adapter),
        health_timeout_seconds=validate_external_adapter_timeout(
            health_timeout_seconds
        ),
    )


def create_mlx_async_external_adapter(
    native_adapter: AsyncMLXLocalModelAdapter,
    *,
    adapter_id: str,
    health_timeout_seconds: float = 30.0,
) -> AsyncNativeExternalAdapter:
    """Project one caller-owned asynchronous MLX adapter onto v1."""

    _, descriptor = _create_mlx_external_descriptor(
        native_adapter,
        adapter_id=adapter_id,
        execution_modes=frozenset({"async"}),
    )
    return AsyncNativeExternalAdapter(
        native_adapter,
        descriptor,
        health_probe=lambda: _mlx_health(native_adapter),
        health_timeout_seconds=validate_external_adapter_timeout(
            health_timeout_seconds
        ),
    )


def _ensure_supported_platform(platform_system: str) -> None:
    if platform_system != "Darwin":
        raise ModelExecutionError(
            "MLX local model execution is macOS-only; "
            f"current platform is {platform_system!r}"
        )


def _validate_supported_request(
    request: OpenAIModelRequest,
    *,
    backend: MLXLocalBackend | None = None,
    tool_codec: MLXToolCodec | None = None,
) -> None:
    if request.tools and (
        tool_codec is None
        or (
            backend is not None
            and not _backend_supports_tool_codec(backend, tool_codec)
        )
    ):
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
    validation_error = _validate_mlx_model_directory(model_directory)
    if validation_error is not None:
        raise LocalModelResolutionError(validation_error)
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
_MAX_TOOL_RESPONSE_BYTES = 128 * 1024
_MAX_TOOL_CANDIDATE_BYTES = 66 * 1024
_MAX_TOOL_ARGUMENT_BYTES = 64 * 1024
_MAX_TOOL_ARGUMENT_DEPTH = 32
_MAX_TOOL_ARGUMENT_MEMBERS = 256


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


def _backend_supports_tool_codec(
    backend: MLXLocalBackend | None,
    tool_codec: MLXToolCodec | None,
) -> bool:
    return (
        tool_codec is not None
        and isinstance(backend, MLXToolCapableBackend)
        and tool_codec.version in backend.tool_codec_versions
    )


def _generate_tool_response(
    backend: MLXLocalBackend,
    tool_codec: MLXToolCodec | None,
    request: OpenAIModelRequest,
    generation_kwargs: Mapping[str, object],
) -> ModelResponse:
    if tool_codec is None or not isinstance(backend, MLXToolCapableBackend):
        raise ModelExecutionError(
            f"MLX local model adapter does not support tool calls for {request.model!r}"
        )
    prompt = tool_codec.render(request)
    generated = (
        backend.generate_rendered(prompt, **dict(generation_kwargs))
        if generation_kwargs
        else backend.generate_rendered(prompt)
    )
    generated_text = str(generated)
    if len(generated_text.encode("utf-8")) > _MAX_TOOL_RESPONSE_BYTES:
        raise ModelExecutionError("MLX tool codec response exceeds the byte limit")
    response_id = f"mlx-{uuid4().hex}"
    decoded = tool_codec.decode(generated_text)
    return _normalize_tool_codec_response(decoded, response_id, generated, request)


def _normalize_tool_codec_response(
    decoded: MLXToolCodecResponse,
    response_id: str,
    raw: object,
    request: OpenAIModelRequest,
) -> ModelResponse:
    if not isinstance(decoded, MLXToolCodecResponse):
        raise ModelExecutionError("MLX tool codec returned an invalid response")
    if (decoded.content is None) == (decoded.tool_call is None):
        raise ModelExecutionError(
            "MLX tool codec response must contain text or exactly one tool call"
        )
    if decoded.content is not None:
        if not isinstance(decoded.content, str):
            raise ModelExecutionError("MLX tool codec text response must be a string")
        return ModelResponse(content=decoded.content, response_id=response_id, raw=raw)

    candidate = decoded.tool_call
    assert candidate is not None
    if not isinstance(candidate, MLXToolCallCandidate):
        raise ModelExecutionError("MLX tool codec returned an invalid tool call")
    if not isinstance(candidate.name, str) or not candidate.name:
        raise ModelExecutionError("MLX tool codec call must have a name")
    if candidate.name not in _tool_names(request):
        raise ModelExecutionError(
            f"MLX tool codec call requests unavailable tool {candidate.name!r}"
        )
    if candidate.id is not None and (
        not isinstance(candidate.id, str) or not candidate.id
    ):
        raise ModelExecutionError("MLX tool codec call ID must be non-empty")
    if _tool_candidate_byte_size(candidate) > _MAX_TOOL_CANDIDATE_BYTES:
        raise ModelExecutionError("MLX tool codec call exceeds the byte limit")
    call_id = candidate.id or f"{response_id}:1"
    arguments = _normalize_tool_arguments(candidate.arguments)
    return ModelResponse(
        content=None,
        tool_calls=(
            ModelToolCall(
                id=call_id,
                name=candidate.name,
                arguments=arguments,
            ),
        ),
        response_id=response_id,
        raw=raw,
    )


def _tool_names(request: OpenAIModelRequest) -> frozenset[str]:
    names: set[str] = set()
    for tool in request.tools:
        function = tool.get("function")
        name = (
            function.get("name") if isinstance(function, Mapping) else tool.get("name")
        )
        if isinstance(name, str) and (
            isinstance(function, Mapping) or tool.get("type") == "function"
        ):
            names.add(name)
    return frozenset(names)


def _tool_candidate_byte_size(candidate: MLXToolCallCandidate) -> int:
    return sum(
        len(value.encode("utf-8"))
        for value in (
            candidate.name,
            candidate.id or "",
            _tool_argument_source(candidate.arguments),
        )
    )


def _normalize_tool_arguments(arguments: str | Mapping[str, object]) -> str:
    source = _tool_argument_source(arguments)
    if len(source.encode("utf-8")) > _MAX_TOOL_ARGUMENT_BYTES:
        raise ModelExecutionError("MLX tool codec arguments exceed the byte limit")
    try:
        value = json.loads(
            source,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_non_finite_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ModelExecutionError(
            "MLX tool codec arguments must be valid JSON"
        ) from exc
    except ValueError as exc:
        raise ModelExecutionError(str(exc)) from exc
    if not isinstance(value, dict):
        raise ModelExecutionError("MLX tool codec arguments must be a JSON object")
    _validate_tool_argument_structure(value)
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _tool_argument_source(arguments: str | Mapping[str, object]) -> str:
    try:
        source = (
            arguments
            if isinstance(arguments, str)
            else json.dumps(
                arguments,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    except (TypeError, ValueError) as exc:
        raise ModelExecutionError(
            "MLX tool codec arguments must be JSON-compatible"
        ) from exc
    if not isinstance(source, str):
        raise ModelExecutionError(
            "MLX tool codec arguments must be a JSON string or object"
        )
    return source


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("MLX tool codec arguments contain duplicate JSON keys")
        result[key] = value
    return result


def _reject_non_finite_json_constant(value: str) -> object:
    raise ValueError(
        f"MLX tool codec arguments contain non-finite JSON value {value!r}"
    )


def _validate_tool_argument_structure(value: object, depth: int = 0) -> int:
    if depth > _MAX_TOOL_ARGUMENT_DEPTH:
        raise ModelExecutionError("MLX tool codec arguments exceed the nesting limit")
    if isinstance(value, dict):
        members = len(value)
        for item in value.values():
            members += _validate_tool_argument_structure(item, depth + 1)
    elif isinstance(value, list):
        members = sum(
            _validate_tool_argument_structure(item, depth + 1) for item in value
        )
    else:
        members = 0
    if members > _MAX_TOOL_ARGUMENT_MEMBERS:
        raise ModelExecutionError("MLX tool codec arguments exceed the member limit")
    return members


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
