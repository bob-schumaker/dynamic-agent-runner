"""Direct, explicitly configured OpenAI-compatible external model adapters."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
import ipaddress
import math
from time import monotonic
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.external_adapter import (
    DARExternalAdapterProtocol,
    DARExternalRequestContext,
    ExternalAdapterCancelledError,
    ExternalAdapterError,
    ExternalAdapterValidationError,
    ExternalModelAdapterDescriptor,
    ExternalModelAdapterHealth,
    canonical_descriptor_digest,
)
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientProtocol,
    ModelResponse,
    OpenAIClientProtocol,
    OpenAIModelRequest,
    OpenAIProviderConfig,
    create_async_openai_response,
    create_official_async_openai_client,
    create_official_openai_client,
    create_openai_response,
    list_openai_model_ids,
)


@dataclass(frozen=True)
class OpenAICompatibleExternalConfig:
    """Non-secret configuration for one endpoint and one service model."""

    adapter_id: str
    base_url: str
    model_alias: str
    service_model_id: str
    canonical_model_id: str
    tool_calling: bool = False
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        for field_name in (
            "adapter_id",
            "base_url",
            "model_alias",
            "service_model_id",
            "canonical_model_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ExternalAdapterValidationError(f"{field_name} is required")
        if not isinstance(self.tool_calling, bool):
            raise ExternalAdapterValidationError("tool_calling must be boolean")
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or isinstance(self.timeout_seconds, bool)
            or not math.isfinite(float(self.timeout_seconds))
            or not 0 < float(self.timeout_seconds) <= 120
        ):
            raise ExternalAdapterValidationError("timeout_seconds must be in (0, 120]")
        object.__setattr__(self, "base_url", validate_external_base_url(self.base_url))


@runtime_checkable
class OpenAICompatibleSyncTransport(Protocol):
    def list_models(self, *, timeout_seconds: float) -> Sequence[str]: ...

    def create_response(
        self,
        request: OpenAIModelRequest,
        *,
        deadline_monotonic: float | None,
        cancellation: object,
    ) -> ModelResponse: ...


@runtime_checkable
class OpenAICompatibleAsyncTransport(Protocol):
    async def create_response(
        self,
        request: OpenAIModelRequest,
        *,
        deadline_monotonic: float | None,
        cancellation: object,
    ) -> ModelResponse: ...


def validate_external_base_url(value: str) -> str:
    """Validate and return one canonical endpoint URL."""

    if not isinstance(value, str):
        raise ExternalAdapterValidationError("base_url must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ExternalAdapterValidationError("base_url must use HTTPS or loopback HTTP")
    if parsed.username is not None or parsed.password is not None:
        raise ExternalAdapterValidationError("base_url must not contain userinfo")
    if parsed.query or parsed.fragment:
        raise ExternalAdapterValidationError(
            "base_url must not contain query or fragment"
        )
    if parsed.scheme == "http":
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError as error:
            raise ExternalAdapterValidationError(
                "plain HTTP requires a loopback IP literal"
            ) from error
        if not address.is_loopback:
            raise ExternalAdapterValidationError(
                "plain HTTP requires a loopback IP literal"
            )
    try:
        _port = parsed.port
    except ValueError as error:
        raise ExternalAdapterValidationError("base_url has an invalid port") from error
    return value.rstrip("/")


def _request_for_service(
    request: OpenAIModelRequest, service_model_id: str
) -> OpenAIModelRequest:
    extra = {
        key: value
        for key, value in request.extra.items()
        if key not in {"timeout_seconds", "estimated_context_tokens"}
    }
    return replace(request, model=service_model_id, extra=extra)


class _SyncSDKTransport:
    def __init__(self, client: OpenAIClientProtocol, service_model_id: str) -> None:
        self._client = client
        self._service_model_id = service_model_id

    def list_models(self, *, timeout_seconds: float) -> Sequence[str]:
        del timeout_seconds  # The explicit SDK client owns its network timeout.
        return list_openai_model_ids(self._client)

    def create_response(
        self,
        request: OpenAIModelRequest,
        *,
        deadline_monotonic: float | None,
        cancellation: object,
    ) -> ModelResponse:
        _check_transport_context(deadline_monotonic, cancellation)
        response = create_openai_response(self._client, request)
        _check_transport_context(deadline_monotonic, cancellation)
        return response


class _AsyncSDKTransport:
    def __init__(
        self, client: AsyncOpenAIClientProtocol, service_model_id: str
    ) -> None:
        self._client = client
        self._service_model_id = service_model_id

    async def create_response(
        self,
        request: OpenAIModelRequest,
        *,
        deadline_monotonic: float | None,
        cancellation: object,
    ) -> ModelResponse:
        _check_transport_context(deadline_monotonic, cancellation)
        response = await create_async_openai_response(self._client, request)
        _check_transport_context(deadline_monotonic, cancellation)
        return response


def _check_transport_context(
    deadline_monotonic: float | None, cancellation: object
) -> None:
    if getattr(cancellation, "cancelled", False):
        raise ExternalAdapterCancelledError("external adapter request cancelled")
    if deadline_monotonic is not None and monotonic() >= deadline_monotonic:
        raise ExternalAdapterCancelledError("external adapter deadline expired")


class _BaseAdapter:
    protocol_id = "dar.external-model.v1"
    protocol_version = "1.0"

    def __init__(
        self,
        config: OpenAICompatibleExternalConfig,
        api_key: str | None,
        health_transport: OpenAICompatibleSyncTransport,
    ) -> None:
        self._config = config
        self._api_key = api_key
        self._health_transport = health_transport
        self.health_timeout_seconds = config.timeout_seconds
        self._descriptor = self._make_descriptor()

    @property
    def adapter_id(self) -> str:
        return self._config.adapter_id

    def _make_descriptor(self) -> ExternalModelAdapterDescriptor:
        values: dict[str, Any] = {
            "adapter_id": self._config.adapter_id,
            "provider_id": "openai-compatible-external",
            "protocol_id": "dar.external-model.v1",
            "protocol_version": "1.0",
            "model_alias": self._config.model_alias,
            "canonical_model_id": self._config.canonical_model_id,
            "execution_location": (
                "local" if _is_loopback_url(self._config.base_url) else "remote"
            ),
            "execution_modes": frozenset(self._execution_modes),
            "input_modalities": frozenset({"text"}),
            "output_modalities": frozenset({"text"}),
            "response_formats": frozenset({"text", "json_schema"}),
            "capabilities": frozenset(
                {"text_generation", "structured_output"}
                | ({"tool_calling"} if self._config.tool_calling else set())
            ),
            "limits": {},
            "contract_digest": "",
        }
        provisional = object.__new__(ExternalModelAdapterDescriptor)
        for key, value in values.items():
            object.__setattr__(provisional, key, value)
        values["contract_digest"] = canonical_descriptor_digest(provisional)
        return ExternalModelAdapterDescriptor(**values)

    def describe(self) -> ExternalModelAdapterDescriptor:
        return self._descriptor

    def health(self) -> ExternalModelAdapterHealth:
        try:
            inventory = tuple(
                self._health_transport.list_models(
                    timeout_seconds=self._config.timeout_seconds
                )
            )
            if not inventory or any(
                not isinstance(item, str) or not item for item in inventory
            ):
                return ExternalModelAdapterHealth("unavailable", "malformed_inventory")
            if len(set(inventory)) != len(inventory):
                return ExternalModelAdapterHealth("unavailable", "duplicate_inventory")
            if self._config.service_model_id not in inventory:
                return ExternalModelAdapterHealth("unavailable", "model_not_advertised")
            return ExternalModelAdapterHealth("ready")
        except (ExternalAdapterError, ModelExecutionError):
            return ExternalModelAdapterHealth("unavailable", "transport_failed")
        except Exception:
            return ExternalModelAdapterHealth("failed", "health_failed")

    def _prepare_transport_request(
        self, request: OpenAIModelRequest
    ) -> OpenAIModelRequest:
        context = request.adapter_context
        if not isinstance(context, DARExternalRequestContext):
            raise ExternalAdapterValidationError("external adapter context is invalid")
        return _request_for_service(request, self._config.service_model_id)


class OpenAICompatibleExternalAdapter(_BaseAdapter):
    _execution_modes = frozenset({"sync"})

    def __init__(
        self,
        config: OpenAICompatibleExternalConfig,
        api_key: str | None,
        transport: OpenAICompatibleSyncTransport,
        health_transport: OpenAICompatibleSyncTransport | None = None,
    ) -> None:
        super().__init__(config, api_key, health_transport or transport)
        self._transport = transport

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        prepared = self._prepare_transport_request(request)
        context = prepared.adapter_context
        return self._transport.create_response(
            prepared,
            deadline_monotonic=context.deadline_monotonic,
            cancellation=context.cancellation,
        )


class AsyncOpenAICompatibleExternalAdapter(_BaseAdapter):
    _execution_modes = frozenset({"async"})

    def __init__(
        self,
        config: OpenAICompatibleExternalConfig,
        api_key: str | None,
        transport: OpenAICompatibleAsyncTransport,
        health_transport: OpenAICompatibleSyncTransport,
    ) -> None:
        super().__init__(config, api_key, health_transport)
        self._transport = transport

    async def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        prepared = self._prepare_transport_request(request)
        context = prepared.adapter_context
        return await self._transport.create_response(
            prepared,
            deadline_monotonic=context.deadline_monotonic,
            cancellation=context.cancellation,
        )


def create_openai_compatible_external_adapter(
    config: OpenAICompatibleExternalConfig,
    *,
    api_key: str | None = None,
    transport: OpenAICompatibleSyncTransport | None = None,
    health_transport: OpenAICompatibleSyncTransport | None = None,
    client: OpenAIClientProtocol | None = None,
) -> DARExternalAdapterProtocol:
    """Create the explicitly configured synchronous adapter."""

    if transport is None:
        client = client or create_official_openai_client(
            OpenAIProviderConfig(
                base_url=config.base_url,
                api_key=api_key,
                discover_default_auth=False,
                timeout_seconds=config.timeout_seconds,
                trust_env=False,
                follow_redirects=False,
                suppress_auth_header=api_key is None,
            )
        )
        transport = _SyncSDKTransport(client, config.service_model_id)
    return OpenAICompatibleExternalAdapter(config, api_key, transport, health_transport)


def create_async_openai_compatible_external_adapter(
    config: OpenAICompatibleExternalConfig,
    *,
    api_key: str | None = None,
    transport: OpenAICompatibleAsyncTransport | None = None,
    health_transport: OpenAICompatibleSyncTransport | None = None,
    client: AsyncOpenAIClientProtocol | None = None,
    health_client: OpenAIClientProtocol | None = None,
) -> DARExternalAdapterProtocol:
    """Create the explicitly configured asynchronous adapter."""

    if transport is None:
        client = client or create_official_async_openai_client(
            OpenAIProviderConfig(
                base_url=config.base_url,
                api_key=api_key,
                discover_default_auth=False,
                timeout_seconds=config.timeout_seconds,
                trust_env=False,
                follow_redirects=False,
                suppress_auth_header=api_key is None,
            )
        )
        transport = _AsyncSDKTransport(client, config.service_model_id)
    if health_transport is None:
        health_client = health_client or create_official_openai_client(
            OpenAIProviderConfig(
                base_url=config.base_url,
                api_key=api_key,
                discover_default_auth=False,
                timeout_seconds=config.timeout_seconds,
                trust_env=False,
                follow_redirects=False,
                suppress_auth_header=api_key is None,
            )
        )
        health_transport = _SyncSDKTransport(health_client, config.service_model_id)
    return AsyncOpenAICompatibleExternalAdapter(
        config, api_key, transport, health_transport
    )


def _is_loopback_url(value: str) -> bool:
    parsed = urlsplit(value)
    try:
        return ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        return False


__all__ = [
    "AsyncOpenAICompatibleExternalAdapter",
    "OpenAICompatibleAsyncTransport",
    "OpenAICompatibleExternalAdapter",
    "OpenAICompatibleExternalConfig",
    "OpenAICompatibleSyncTransport",
    "create_async_openai_compatible_external_adapter",
    "create_openai_compatible_external_adapter",
    "validate_external_base_url",
]
