"""Transport-neutral external model adapter protocol and DAR façade."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Mapping
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
)
from dataclasses import dataclass, replace
import hashlib
import inspect
import json
import math
import re
from threading import BoundedSemaphore
from time import monotonic
from typing import Any, Literal, Protocol, runtime_checkable
from types import MappingProxyType
from uuid import uuid4

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import (
    ModelResponse,
    OpenAIModelRequest,
)


ExternalAdapterCapability = Literal[
    "text_generation", "structured_output", "tool_calling"
]
ExternalAdapterMode = Literal["sync", "async"]


class ExternalAdapterError(ModelExecutionError):
    """Base error for external adapter contract and dispatch failures."""


class ExternalAdapterValidationError(ExternalAdapterError):
    """Raised when an external adapter contract value is invalid."""


class ExternalAdapterUnavailableError(ExternalAdapterError):
    """Raised when an external adapter is not ready for dispatch."""


class ExternalAdapterCancelledError(ExternalAdapterError):
    """Raised when an external adapter request is cancelled or expired."""


class CancellationHandle(Protocol):
    @property
    def cancelled(self) -> bool: ...

    def raise_if_cancelled(self) -> None: ...


class _Cancellation:
    def __init__(self) -> None:
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise ExternalAdapterCancelledError("external adapter request cancelled")


@dataclass
class _DispatchToken:
    token_id: str
    adapter_id: str
    descriptor_digest: str
    model_alias: str
    mode: ExternalAdapterMode
    expires_at: float | None
    consumed: bool = False
    revoked: bool = False


class _BoundedExternalDispatcher:
    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="dar-external-adapter",
        )
        self._slots = BoundedSemaphore(max_workers)

    def submit(self, function: Any, *args: Any) -> Future[Any]:
        if not self._slots.acquire(blocking=False):
            raise ExternalAdapterUnavailableError(
                "external adapter worker capacity is full"
            )
        try:
            future = self._executor.submit(function, *args)
        except Exception:
            self._slots.release()
            raise
        future.add_done_callback(lambda _: self._slots.release())
        return future


_EXTERNAL_DISPATCHER = _BoundedExternalDispatcher()


@dataclass(frozen=True)
class ExternalModelAdapterDescriptor:
    """Immutable v1 identity, capability, and limit declaration."""

    adapter_id: str
    provider_id: str
    protocol_id: Literal["dar.external-model.v1"]
    protocol_version: Literal["1.0"]
    model_alias: str
    canonical_model_id: str
    execution_location: Literal["local", "remote"]
    execution_modes: frozenset[ExternalAdapterMode]
    input_modalities: frozenset[Literal["text"]]
    output_modalities: frozenset[Literal["text"]]
    response_formats: frozenset[Literal["text", "json_schema"]]
    capabilities: frozenset[ExternalAdapterCapability]
    limits: Mapping[str, int]
    contract_digest: str

    def __post_init__(self) -> None:  # noqa: C901 - contract validation is one boundary.
        object.__setattr__(self, "execution_modes", frozenset(self.execution_modes))
        object.__setattr__(self, "input_modalities", frozenset(self.input_modalities))
        object.__setattr__(self, "output_modalities", frozenset(self.output_modalities))
        object.__setattr__(self, "response_formats", frozenset(self.response_formats))
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        object.__setattr__(self, "limits", MappingProxyType(dict(self.limits)))
        if not isinstance(self.adapter_id, str) or not self.adapter_id.strip():
            raise ExternalAdapterValidationError("adapter_id is required")
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            raise ExternalAdapterValidationError("provider_id is required")
        if self.protocol_id != "dar.external-model.v1":
            raise ExternalAdapterValidationError(
                "unsupported external adapter protocol"
            )
        if self.protocol_version != "1.0":
            raise ExternalAdapterValidationError("unsupported external adapter version")
        if not isinstance(self.model_alias, str) or not self.model_alias.strip():
            raise ExternalAdapterValidationError("model_alias is required")
        if not isinstance(self.canonical_model_id, str) or not self.canonical_model_id:
            raise ExternalAdapterValidationError("canonical_model_id is required")
        if self.execution_location not in {"local", "remote"}:
            raise ExternalAdapterValidationError("invalid execution location")
        _require_nonempty_subset(
            self.execution_modes, {"sync", "async"}, "execution_modes"
        )
        if self.input_modalities != frozenset({"text"}):
            raise ExternalAdapterValidationError("v1 input modality must be text")
        if self.output_modalities != frozenset({"text"}):
            raise ExternalAdapterValidationError("v1 output modality must be text")
        if not self.response_formats or not self.response_formats.issubset(
            {"text", "json_schema"}
        ):
            raise ExternalAdapterValidationError("invalid response formats")
        if not self.capabilities or not self.capabilities.issubset(
            {"text_generation", "structured_output", "tool_calling"}
        ):
            raise ExternalAdapterValidationError("invalid adapter capabilities")
        if "text_generation" not in self.capabilities:
            raise ExternalAdapterValidationError(
                "text_generation capability is required"
            )
        if (
            "structured_output" in self.capabilities
            and "json_schema" not in self.response_formats
        ):
            raise ExternalAdapterValidationError(
                "structured_output requires json_schema response format"
            )
        for key, value in self.limits.items():
            if key not in {"max_context_tokens", "max_output_tokens"}:
                raise ExternalAdapterValidationError("unknown adapter limit")
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ExternalAdapterValidationError(
                    "adapter limits must be non-negative integers"
                )
        if not isinstance(self.contract_digest, str) or len(self.contract_digest) != 64:
            raise ExternalAdapterValidationError("invalid contract digest")
        if any(
            character not in "0123456789abcdef" for character in self.contract_digest
        ):
            raise ExternalAdapterValidationError("invalid contract digest")
        if self.contract_digest != canonical_descriptor_digest(self):
            raise ExternalAdapterValidationError(
                "external adapter descriptor digest mismatch"
            )


def _require_nonempty_subset(
    value: frozenset[str], allowed: set[str], field_name: str
) -> None:
    if not value or not value.issubset(allowed):
        raise ExternalAdapterValidationError(f"invalid {field_name}")


def _descriptor_payload(descriptor: ExternalModelAdapterDescriptor) -> dict[str, Any]:
    return {
        "adapter_id": descriptor.adapter_id,
        "provider_id": descriptor.provider_id,
        "protocol_id": descriptor.protocol_id,
        "protocol_version": descriptor.protocol_version,
        "model_alias": descriptor.model_alias,
        "canonical_model_id": descriptor.canonical_model_id,
        "execution_location": descriptor.execution_location,
        "execution_modes": sorted(descriptor.execution_modes),
        "input_modalities": sorted(descriptor.input_modalities),
        "output_modalities": sorted(descriptor.output_modalities),
        "response_formats": sorted(descriptor.response_formats),
        "capabilities": sorted(descriptor.capabilities),
        "limits": dict(sorted(descriptor.limits.items())),
    }


def canonical_descriptor_digest(descriptor: ExternalModelAdapterDescriptor) -> str:
    """Return the canonical SHA-256 digest excluding ``contract_digest``."""

    encoded = json.dumps(
        _descriptor_payload(descriptor),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ExternalModelAdapterHealth:
    """Redacted readiness state reported by an external adapter."""

    status: Literal["ready", "unavailable", "failed"]
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ready", "unavailable", "failed"}:
            raise ExternalAdapterValidationError("invalid external adapter health")
        if self.error_code is not None and (
            not isinstance(self.error_code, str)
            or len(self.error_code) > 128
            or re.fullmatch(r"[a-z0-9_.-]+", self.error_code) is None
        ):
            raise ExternalAdapterValidationError("invalid external adapter error code")


@dataclass(frozen=True)
class DARExternalRequestContext:
    """Minimal DAR-owned context visible to an external adapter call."""

    correlation_id: str
    deadline_monotonic: float | None
    cancellation: CancellationHandle


@runtime_checkable
class DARExternalAdapterProtocol(Protocol):
    """Public BYOM contract for receiver-approved external model adapters."""

    adapter_id: str
    protocol_id: Literal["dar.external-model.v1"]
    protocol_version: Literal["1.0"]

    def describe(self) -> ExternalModelAdapterDescriptor: ...

    def health(self) -> ExternalModelAdapterHealth: ...

    def create_response(
        self, request: OpenAIModelRequest
    ) -> ModelResponse | Awaitable[ModelResponse]: ...


def is_external_adapter(value: object) -> bool:
    return all(
        callable(getattr(value, name, None))
        for name in ("describe", "health", "create_response")
    ) and all(
        isinstance(getattr(value, name, None), str)
        for name in ("adapter_id", "protocol_id", "protocol_version")
    )


class ExternalModelAdapterFacade:
    """DAR-owned model-adapter projection for one external descriptor."""

    def __init__(self, adapter: DARExternalAdapterProtocol) -> None:
        if not is_external_adapter(adapter):
            raise ExternalAdapterValidationError(
                "object does not implement external adapter protocol"
            )
        descriptor = adapter.describe()
        if not isinstance(descriptor, ExternalModelAdapterDescriptor):
            raise ExternalAdapterValidationError(
                "adapter returned an invalid descriptor"
            )
        if descriptor.adapter_id != adapter.adapter_id:
            raise ExternalAdapterValidationError(
                "adapter identity does not match descriptor"
            )
        if (
            descriptor.protocol_id != adapter.protocol_id
            or descriptor.protocol_version != adapter.protocol_version
        ):
            raise ExternalAdapterValidationError(
                "adapter protocol identity does not match descriptor"
            )
        self._adapter = adapter
        self._descriptor = descriptor
        self._revoked = False
        self._dispatch_tokens: dict[str, _DispatchToken] = {}

    @property
    def descriptor(self) -> ExternalModelAdapterDescriptor:
        return self._descriptor

    @property
    def models(self) -> tuple[str, ...]:
        return (self._descriptor.model_alias,)

    @property
    def capabilities(self) -> Mapping[str, object]:
        return dict.fromkeys(self._descriptor.capabilities, True)

    @property
    def execution_profile_adapter_id(self) -> str:
        return self._descriptor.adapter_id

    def revoke(self) -> None:
        """Reject future calls while allowing a currently dispatched call to finish."""

        self._revoked = True
        for token in self._dispatch_tokens.values():
            token.revoked = True

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        if "sync" not in self._descriptor.execution_modes:
            raise ExternalAdapterError(
                "external adapter does not support sync execution"
            )
        return self._dispatch_sync(request)

    async def create_response_async(self, request: OpenAIModelRequest) -> ModelResponse:
        if inspect.iscoroutinefunction(self._adapter.create_response):
            return await self._dispatch_async(request)
        loop = asyncio.get_running_loop()
        future = _EXTERNAL_DISPATCHER.submit(self._dispatch_sync, request)
        return await asyncio.wrap_future(future, loop=loop)

    def _prepare_request(  # noqa: C901 - admission validates one public request boundary.
        self, request: OpenAIModelRequest
    ) -> OpenAIModelRequest:
        if self._revoked:
            raise ExternalAdapterUnavailableError("external adapter has been removed")
        if not isinstance(request, OpenAIModelRequest):
            raise ExternalAdapterValidationError("external adapter request is invalid")
        if request.model != self._descriptor.model_alias:
            raise ExternalAdapterValidationError(
                "external adapter model alias mismatch"
            )
        if not request.messages or any(
            not isinstance(message, Mapping)
            or not isinstance(message.get("content"), str)
            for message in request.messages
        ):
            raise ExternalAdapterValidationError(
                "external adapter accepts text messages only"
            )
        if any(
            request.extra.get(key)
            for key in ("stream", "streaming", "persistent_session", "native_callback")
        ):
            raise ExternalAdapterValidationError(
                "external adapter request mode is unsupported"
            )
        if request.response_format is not None:
            format_type = request.response_format.get("type")
            if format_type == "json_schema":
                if "structured_output" not in self._descriptor.capabilities:
                    raise ExternalAdapterValidationError(
                        "structured output is not supported"
                    )
            elif format_type not in {"text", None}:
                raise ExternalAdapterValidationError("response format is not supported")
        if request.tools and "tool_calling" not in self._descriptor.capabilities:
            raise ExternalAdapterValidationError("model tool calling is not supported")
        requested_output = request.extra.get("max_output_tokens")
        output_limit = self._descriptor.limits.get("max_output_tokens")
        if requested_output is not None and (
            not isinstance(requested_output, int)
            or isinstance(requested_output, bool)
            or output_limit is not None
            and requested_output > output_limit
        ):
            raise ExternalAdapterValidationError(
                "requested output exceeds adapter limit"
            )
        context_limit = self._descriptor.limits.get("max_context_tokens")
        requested_context = request.extra.get("estimated_context_tokens")
        if (
            context_limit is not None
            and requested_context is not None
            and (
                not isinstance(requested_context, int)
                or isinstance(requested_context, bool)
                or requested_context > context_limit
            )
        ):
            raise ExternalAdapterValidationError(
                "request exceeds adapter context limit"
            )
        timeout_seconds = request.extra.get("timeout_seconds")
        if timeout_seconds is not None and (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not math.isfinite(float(timeout_seconds))
            or timeout_seconds < 0
        ):
            raise ExternalAdapterValidationError("invalid external adapter timeout")
        cancellation = _Cancellation()
        context = DARExternalRequestContext(
            correlation_id=uuid4().hex,
            deadline_monotonic=(
                monotonic() + float(timeout_seconds)
                if timeout_seconds is not None
                else None
            ),
            cancellation=cancellation,
        )
        return replace(request, adapter_context=context)

    def _dispatch_sync(self, request: OpenAIModelRequest) -> ModelResponse:
        prepared = self._prepare_request(request)
        health = self._health()
        if health.status != "ready":
            raise ExternalAdapterUnavailableError("external adapter is unavailable")
        _check_context(prepared.adapter_context)
        token = self._issue_dispatch_token(prepared, "sync")
        self._consume_dispatch_token(token.token_id, prepared, "sync")
        try:
            result = self._adapter.create_response(prepared)
            if inspect.isawaitable(result):
                raise ExternalAdapterError(
                    "sync external adapter returned an awaitable"
                )
            _check_context(prepared.adapter_context)
            return _normalize_external_response(prepared, result, self._descriptor)
        except ExternalAdapterError:
            raise
        except Exception as error:  # noqa: BLE001 - provider boundary is redacted.
            raise ExternalAdapterError("external adapter request failed") from error

    async def _dispatch_async(self, request: OpenAIModelRequest) -> ModelResponse:  # noqa: C901 - dispatch owns one bounded async boundary.
        prepared = self._prepare_request(request)
        loop = asyncio.get_running_loop()
        health_future = _EXTERNAL_DISPATCHER.submit(self._run_health)
        try:
            health_timeout = self._health_timeout_seconds()
            if health_timeout is None:
                health = await asyncio.wrap_future(health_future, loop=loop)
            else:
                health = await asyncio.wait_for(
                    asyncio.wrap_future(health_future, loop=loop),
                    timeout=health_timeout,
                )
        except asyncio.TimeoutError as error:
            raise ExternalAdapterUnavailableError(
                "external adapter health timed out"
            ) from error
        if health.status != "ready":
            raise ExternalAdapterUnavailableError("external adapter is unavailable")
        _check_context(prepared.adapter_context)
        token = self._issue_dispatch_token(prepared, "async")
        self._consume_dispatch_token(token.token_id, prepared, "async")
        try:
            result = self._adapter.create_response(prepared)
            if inspect.isawaitable(result):
                deadline = prepared.adapter_context.deadline_monotonic  # type: ignore[union-attr]
                if deadline is None:
                    result = await result
                else:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise ExternalAdapterCancelledError(
                            "external adapter deadline expired"
                        )
                    try:
                        result = await asyncio.wait_for(result, timeout=remaining)
                    except asyncio.TimeoutError as error:
                        raise ExternalAdapterCancelledError(
                            "external adapter deadline expired"
                        ) from error
            _check_context(prepared.adapter_context)
            return _normalize_external_response(prepared, result, self._descriptor)
        except ExternalAdapterError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - provider boundary is redacted.
            raise ExternalAdapterError("external adapter request failed") from error

    def _health(self) -> ExternalModelAdapterHealth:
        future = _EXTERNAL_DISPATCHER.submit(self._run_health)
        try:
            timeout = self._health_timeout_seconds()
            health = future.result(timeout=timeout)
        except FutureTimeoutError as error:
            raise ExternalAdapterUnavailableError(
                "external adapter health timed out"
            ) from error
        except ExternalAdapterError:
            raise
        if not isinstance(health, ExternalModelAdapterHealth):
            raise ExternalAdapterValidationError("adapter returned invalid health")
        return health

    def _run_health(self) -> ExternalModelAdapterHealth:
        try:
            health = self._adapter.health()
        except ExternalAdapterError:
            raise
        except Exception as error:  # noqa: BLE001 - provider health is redacted.
            raise ExternalAdapterUnavailableError(
                "external adapter health failed"
            ) from error
        if not isinstance(health, ExternalModelAdapterHealth):
            raise ExternalAdapterValidationError("adapter returned invalid health")
        return health

    def _health_timeout_seconds(self) -> float | None:
        timeout = getattr(self._adapter, "health_timeout_seconds", None)
        if timeout is None:
            return None
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ExternalAdapterValidationError(
                "invalid external adapter health timeout"
            )
        return float(timeout)

    def _issue_dispatch_token(
        self, request: OpenAIModelRequest, mode: ExternalAdapterMode
    ) -> _DispatchToken:
        context = request.adapter_context
        if not isinstance(context, DARExternalRequestContext):
            raise ExternalAdapterValidationError("external adapter context is invalid")
        token = _DispatchToken(
            token_id=uuid4().hex,
            adapter_id=self._descriptor.adapter_id,
            descriptor_digest=self._descriptor.contract_digest,
            model_alias=request.model,
            mode=mode,
            expires_at=context.deadline_monotonic,
        )
        self._dispatch_tokens[token.token_id] = token
        return token

    def _consume_dispatch_token(
        self,
        token_id: str,
        request: OpenAIModelRequest,
        mode: ExternalAdapterMode,
    ) -> None:
        token = self._dispatch_tokens.get(token_id)
        if token is None:
            raise ExternalAdapterError("external adapter dispatch token is invalid")
        if token.consumed:
            raise ExternalAdapterError("external adapter dispatch token was replayed")
        if token.revoked or self._revoked:
            raise ExternalAdapterUnavailableError(
                "external adapter dispatch token was revoked"
            )
        if token.adapter_id != self._descriptor.adapter_id:
            raise ExternalAdapterError(
                "external adapter dispatch token identity mismatch"
            )
        if token.descriptor_digest != self._descriptor.contract_digest:
            raise ExternalAdapterError(
                "external adapter dispatch token digest mismatch"
            )
        if token.model_alias != request.model or token.mode != mode:
            raise ExternalAdapterError(
                "external adapter dispatch token request mismatch"
            )
        if token.expires_at is not None and monotonic() >= token.expires_at:
            raise ExternalAdapterCancelledError(
                "external adapter dispatch token expired"
            )
        token.consumed = True


def _normalize_external_response(
    request: OpenAIModelRequest,
    response: object,
    descriptor: ExternalModelAdapterDescriptor,
) -> ModelResponse:
    if not isinstance(response, ModelResponse):
        raise ExternalAdapterValidationError(
            "external adapter returned invalid response"
        )
    if response.content is not None and not isinstance(response.content, str):
        raise ExternalAdapterValidationError("external adapter returned invalid text")
    if response.tool_calls and "tool_calling" not in descriptor.capabilities:
        raise ExternalAdapterValidationError(
            "external adapter returned unsupported tool calls"
        )
    content = response.content
    if (
        request.response_format is not None
        and request.response_format.get("type") == "json_schema"
    ):
        content = _validate_json_schema_content(content, request.response_format)
    return ModelResponse(
        content=content,
        tool_calls=tuple(response.tool_calls),
        response_id=response.response_id,
        raw=None,
        metadata=_redacted_metadata(response.metadata),
    )


def _check_context(context: object) -> None:
    if not isinstance(context, DARExternalRequestContext):
        raise ExternalAdapterValidationError("external adapter context is invalid")
    context.cancellation.raise_if_cancelled()
    if (
        context.deadline_monotonic is not None
        and monotonic() >= context.deadline_monotonic
    ):
        raise ExternalAdapterCancelledError("external adapter deadline expired")


def _validate_json_schema_content(
    content: str | None, response_format: Mapping[str, Any]
) -> str:
    if content is None:
        raise ExternalAdapterValidationError("structured response is empty")
    try:
        value = json.loads(content)
    except (TypeError, ValueError) as error:
        raise ExternalAdapterValidationError(
            "structured response is not valid JSON"
        ) from error
    schema_wrapper = response_format.get("json_schema")
    schema = (
        schema_wrapper.get("schema") if isinstance(schema_wrapper, Mapping) else None
    )
    if isinstance(schema, Mapping):
        try:
            from jsonschema import Draft202012Validator

            errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
        except Exception as error:  # noqa: BLE001 - schema boundary is redacted.
            raise ExternalAdapterValidationError(
                "structured response schema is invalid"
            ) from error
        if errors:
            raise ExternalAdapterValidationError(
                "structured response does not match schema"
            )
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _redacted_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"safe", "usage", "finish_reason", "provider", "model"}
    return {key: value for key, value in metadata.items() if key in allowed}


__all__ = [
    "CancellationHandle",
    "DARExternalAdapterProtocol",
    "DARExternalRequestContext",
    "ExternalAdapterCancelledError",
    "ExternalAdapterError",
    "ExternalAdapterUnavailableError",
    "ExternalAdapterValidationError",
    "ExternalModelAdapterDescriptor",
    "ExternalModelAdapterFacade",
    "ExternalModelAdapterHealth",
    "canonical_descriptor_digest",
    "is_external_adapter",
]
