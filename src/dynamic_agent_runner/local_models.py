"""Helpers for caller-provided local OpenAI-compatible model endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from dynamic_agent_runner.errors import (
    LocalModelEndpointConnectivityError,
    LocalModelEndpointProtocolError,
    LocalModelIdentityMismatchError,
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


DownloadFileCallable = Callable[["HuggingFaceModelFileReference", Path], Path]
DownloadSnapshotCallable = Callable[["HuggingFaceSnapshotReference", Path], Path]
LlamaCppDependencyLoaderCallable = Callable[[Path, "LlamaCppLocalModelConfig"], object]


class LlamaCppMemoryFitStatus(str, Enum):
    """Advisory fit status for a resolved llama.cpp local model asset."""

    FITS = "fits"
    TOO_LARGE = "too_large"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    FAILED_OPEN = "failed_open"


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
    model_kwargs: Mapping[str, object] | None = None

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
        model_kwargs: Mapping[str, object] | None = None,
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
            "model_kwargs",
            dict(model_kwargs) if model_kwargs is not None else None,
        )


def profile_llama_cpp_model_memory_fit(
    config: LlamaCppLocalModelConfig,
    *,
    requested_context_tokens: int | None = None,
    context_tiers: Sequence[int] = (4096, 8192, 16384, 32768, 65536, 131072),
    memory_budget_bytes: int | None = None,
    mode: str = "fail_open",
    profiler: Callable[[Path], LlamaCppMemoryFitMeasurement] | None = None,
) -> LlamaCppMemoryFitProfileResult:
    """Return a fail-open advisory placeholder for llama.cpp memory fit."""

    if mode == "strict" and profiler is None:
        raise LlamaCppMemoryFitProfileError(
            "llama.cpp memory-fit profiler is unavailable"
        )
    return LlamaCppMemoryFitProfileResult(
        model_path=Path(config.model_path),
        status=LlamaCppMemoryFitStatus.UNAVAILABLE,
        requested_context_tokens=requested_context_tokens,
        memory_budget_bytes=memory_budget_bytes,
        supported_context_tiers=tuple(int(tier) for tier in context_tiers),
        diagnostics=("llama.cpp memory-fit profiler is unavailable",),
    )


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
            raw_response = backend.create_chat_completion(
                messages=[dict(message) for message in request.messages],
                tools=[dict(tool) for tool in request.tools] or None,
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
            self._resolved_model_path = resolve_local_model_path(
                LocalModelPathConfig(
                    model_filename=self._config.model_filename,
                    explicit_model_path=self._config.model_path,
                    model_cache_root=self._config.model_cache_root,
                    huggingface_file=self._config.huggingface_file,
                    huggingface_snapshot=self._config.huggingface_snapshot,
                ),
                download_file=self._download_file,
                download_snapshot=self._download_snapshot,
            )
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


def create_local_openai_adapter(
    config: LocalOpenAIEndpointConfig,
) -> OpenAIClientAdapter:
    """Build a sync local adapter through the existing provider seam."""

    return create_openai_adapter_from_provider_config(
        _provider_config_from_local_endpoint(config),
        models=config.model_aliases,
        is_local=True,
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
    explicit_model_path: Path | None = None,
    huggingface_file: HuggingFaceModelFileReference | None = None,
    huggingface_snapshot: HuggingFaceSnapshotReference | None = None,
) -> None:
    """Validate that the observed local-model identity matches the intended one."""

    if expected_model_id is None or observed_model_id is None:
        return
    if expected_model_id == observed_model_id:
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
