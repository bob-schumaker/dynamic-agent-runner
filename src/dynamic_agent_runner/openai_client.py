"""OpenAI client adapter boundary for dynamic-agent workflow execution."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import inspect
import json
import os
from pathlib import Path
import re
from threading import RLock
import tomllib
from typing import Any, Protocol

from dynamic_agent_runner.errors import ModelExecutionError


ErrorTranslator = Callable[[ModelExecutionError], ModelExecutionError]

_CONTEXT_OVERFLOW_MARKERS = (
    "context_length_exceeded",
    "context window",
    "context limit",
    "maximum context",
    "token limit",
    "too many tokens",
)
ResponseValidator = Callable[["OpenAIModelRequest", "ModelResponse"], None]
CHATGPT_CODEX_BACKEND_BASE_URL = "https://chatgpt.com/backend-api/codex"
CHATGPT_CODEX_PROVIDER_NAME = "chatgpt-codex"
CHATGPT_CODEX_FALLBACK_CLIENT_VERSION = "0.137.0"
CODEX_AUTH_API_KEY_FIRST = "api_key_first"
CODEX_AUTH_CHATGPT_FIRST = "chatgpt_first"
_DAR_TRANSCRIPT_TYPE_KEY = "_dar_transcript_type"
_DAR_MODEL_TOOL_CALL = "model_tool_call"
_DAR_MODEL_TOOL_RESULT = "model_tool_result"


class OpenAIResponsesResource(Protocol):
    """Minimal subset of the OpenAI Responses API used by the runtime."""

    def create(self, **kwargs: Any) -> Any:
        """Create a model response."""


class OpenAIClientProtocol(Protocol):
    """Operational OpenAI client boundary with injectable implementations."""

    responses: OpenAIResponsesResource


class AsyncOpenAIResponsesResource(Protocol):
    """Minimal async OpenAI Responses API subset used by the runtime."""

    async def create(self, **kwargs: Any) -> Any:
        """Create a model response asynchronously."""


class AsyncOpenAIClientProtocol(Protocol):
    """Operational async OpenAI client boundary with injectable implementations."""

    responses: AsyncOpenAIResponsesResource


@dataclass(frozen=True)
class OpenAIProviderConfig:
    """Repository-owned configuration for an OpenAI-compatible provider."""

    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)
    provider_name: str | None = None
    chatgpt_account_id: str | None = field(default=None, repr=False)
    discover_default_auth: bool = True
    codex_auth_preference: str = "api_key_first"


class OpenAIClientProvider(Protocol):
    """Repository-owned sync provider facade for constructing model clients."""

    config: OpenAIProviderConfig

    def get_client(self) -> OpenAIClientProtocol:
        """Return a sync client compatible with the runtime adapter boundary."""


class AsyncOpenAIClientProvider(Protocol):
    """Repository-owned async provider facade for constructing model clients."""

    config: OpenAIProviderConfig

    def get_client(self) -> AsyncOpenAIClientProtocol:
        """Return an async client compatible with the runtime adapter boundary."""


@dataclass(frozen=True)
class SDKBackedOpenAIClientProvider:
    """SDK-backed sync provider for hosted OpenAI and compatible endpoints."""

    config: OpenAIProviderConfig = field(default_factory=OpenAIProviderConfig)

    def get_client(self) -> OpenAIClientProtocol:
        try:
            from openai import OpenAI
        except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
            raise ModelExecutionError(
                "official openai package is not available"
            ) from exc
        return OpenAI(**_provider_config_to_client_kwargs(self.config))


@dataclass(frozen=True)
class SDKBackedAsyncOpenAIClientProvider:
    """SDK-backed async provider for hosted OpenAI and compatible endpoints."""

    config: OpenAIProviderConfig = field(default_factory=OpenAIProviderConfig)

    def get_client(self) -> AsyncOpenAIClientProtocol:
        try:
            from openai import AsyncOpenAI
        except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
            raise ModelExecutionError(
                "official openai package is not available"
            ) from exc
        return AsyncOpenAI(**_provider_config_to_client_kwargs(self.config))


@dataclass(frozen=True)
class ChatGPTCodexBackendOpenAIClientProvider:
    """SDK-backed sync provider for Codex backend auth."""

    config: OpenAIProviderConfig
    token: str = field(repr=False)

    def get_client(self) -> OpenAIClientProtocol:
        try:
            from openai import OpenAI
        except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
            raise ModelExecutionError(
                "official openai package is not available"
            ) from exc
        return OpenAI(
            **_chatgpt_provider_config_to_client_kwargs(self.config, self.token)
        )


@dataclass(frozen=True)
class ChatGPTCodexBackendAsyncOpenAIClientProvider:
    """SDK-backed async provider for Codex backend auth."""

    config: OpenAIProviderConfig
    token: str = field(repr=False)

    def get_client(self) -> AsyncOpenAIClientProtocol:
        try:
            from openai import AsyncOpenAI
        except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
            raise ModelExecutionError(
                "official openai package is not available"
            ) from exc
        return AsyncOpenAI(
            **_chatgpt_provider_config_to_client_kwargs(self.config, self.token)
        )


@dataclass(frozen=True)
class OpenAIMessage:
    """Rendered message sent to the model adapter."""

    role: str
    content: str

    def to_mapping(self) -> dict[str, str]:
        """Return the OpenAI-compatible message mapping."""

        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class OpenAIModelRequest:
    """Normalized model request before it is sent through the OpenAI SDK."""

    model: str
    messages: tuple[Mapping[str, Any], ...]
    tools: tuple[Mapping[str, Any], ...] = ()
    tool_choice: str | Mapping[str, Any] | None = None
    response_format: Mapping[str, Any] | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)
    adapter_context: object | None = field(default=None, repr=False, compare=False)

    def to_kwargs(self) -> dict[str, Any]:
        """Return keyword arguments for ``client.responses.create``."""

        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": [
                _request_message_to_provider_input(message) for message in self.messages
            ],
        }
        if self.tools:
            kwargs["tools"] = [dict(tool) for tool in self.tools]
        if self.tool_choice is not None:
            kwargs["tool_choice"] = self.tool_choice
        if self.response_format is not None:
            kwargs["response_format"] = dict(self.response_format)
        kwargs.update(dict(self.extra))
        return kwargs


@dataclass(frozen=True)
class ModelToolCall:
    """Normalized model-requested tool call."""

    id: str | None
    name: str
    arguments: str | Mapping[str, Any]


def is_context_overflow_error(error: BaseException) -> bool:
    """Return whether an error looks like a provider context-window overflow."""

    message = str(error).lower()
    if "400" in message or "invalid_request" in message or "context" in message:
        return any(marker in message for marker in _CONTEXT_OVERFLOW_MARKERS)
    return False


@dataclass(frozen=True)
class ModelResponse:
    """Normalized model response returned by the adapter."""

    content: str | None
    tool_calls: tuple[ModelToolCall, ...] = ()
    response_id: str | None = None
    raw: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _ResolvedDefaultOpenAIProvider:
    config: OpenAIProviderConfig
    chatgpt_token: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class _CodexAuthDefaults:
    api_key: str | None = field(default=None, repr=False)
    chatgpt_token: str | None = field(default=None, repr=False)
    chatgpt_account_id: str | None = field(default=None, repr=False)
    unsupported_mode: str | None = None


class OpenAIClientAdapter:
    """Small adapter around a repository-owned OpenAI-compatible client boundary."""

    def __init__(
        self,
        client: OpenAIClientProtocol | None = None,
        *,
        provider: OpenAIClientProvider | None = None,
        models: Sequence[str] | None = None,
        is_local: bool = False,
        execution_profile_adapter_id: str | None = None,
        model_id_mapping: Mapping[str, str] | None = None,
        error_translator: ErrorTranslator | None = None,
        response_validator: ResponseValidator | None = None,
    ) -> None:
        if client is not None and provider is not None:
            raise ValueError("OpenAIClientAdapter accepts either client or provider")
        self._client = client
        self._provider = provider
        self._client_lock = RLock()
        self._models = tuple(str(model) for model in models or ())
        self._is_local = is_local
        self._execution_profile_adapter_id = execution_profile_adapter_id
        self._model_id_mapping = dict(model_id_mapping or {})
        self._error_translator = error_translator
        self._response_validator = response_validator
        self._available_model_ids: tuple[str, ...] | None = None

    @property
    def client(self) -> OpenAIClientProtocol:
        """Return the injected or lazily constructed OpenAI-compatible client."""

        with self._client_lock:
            if self._client is None:
                if self._provider is None:
                    self._provider = create_default_openai_provider()
                self._client = self._provider.get_client()
            return self._client

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Send a request and normalize the returned model response."""

        client = self.client
        original_request = request
        try:
            request = replace(request, model=self.resolved_model_id(request.model))
            self._validate_request_model_available(client, request)
            response = create_openai_response(
                client,
                _prepare_chatgpt_codex_request(self._provider, request),
            )
        except ModelExecutionError as exc:
            if self._error_translator is None:
                raise
            translated = self._error_translator(exc)
            if translated is exc:
                raise
            raise translated from exc
        if self._response_validator is not None:
            self._response_validator(original_request, response)
        return response

    @property
    def models(self) -> tuple[str, ...]:
        """Return advertised model names for capability-aware selection."""

        return self._models

    @property
    def capabilities(self) -> Mapping[str, object]:
        """Return the baseline capabilities of this adapter boundary."""

        return {"text_generation": True}

    @property
    def execution_profile_adapter_id(self) -> str | None:
        """Return the host-factory identity used for profile admission."""

        return self._execution_profile_adapter_id

    def resolved_model_id(self, model_id: str) -> str:
        """Resolve a host-owned execution alias without widening model access."""

        return self._model_id_mapping.get(model_id, model_id)

    def list_supported_models(self, *, refresh: bool = False) -> tuple[str, ...]:
        """Return model ids supported by this adapter's configured provider."""

        if self._models and not refresh:
            return self._models
        if self._available_model_ids is not None and not refresh:
            return self._available_model_ids
        self._available_model_ids = self._list_client_model_ids(self.client)
        return self._available_model_ids

    def default_model(self, *, refresh: bool = False) -> str:
        """Return the first supported model to use when callers did not choose one."""

        models = self.list_supported_models(refresh=refresh)
        if not models:
            raise ModelExecutionError("OpenAI provider did not advertise any models")
        return models[0]

    @property
    def is_local(self) -> bool:
        """Return whether this adapter should be treated as local-only."""

        return self._is_local

    def _validate_request_model_available(
        self,
        client: OpenAIClientProtocol,
        request: OpenAIModelRequest,
    ) -> None:
        if not _provider_uses_chatgpt_codex(self._provider):
            return
        available_model_ids = self._available_model_ids
        if available_model_ids is None:
            available_model_ids = self._list_client_model_ids(client)
            self._available_model_ids = available_model_ids
        _raise_if_model_is_unavailable(
            request.model,
            available_model_ids,
            provider_label="ChatGPT/Codex",
        )

    def _list_client_model_ids(
        self,
        client: OpenAIClientProtocol,
    ) -> tuple[str, ...]:
        return list_openai_model_ids(
            client,
            chatgpt_codex=_provider_uses_chatgpt_codex(self._provider),
            extra_query=(
                _chatgpt_codex_models_extra_query()
                if _provider_uses_chatgpt_codex(self._provider)
                else None
            ),
        )


class AsyncOpenAIClientAdapter:
    """Async adapter around a repository-owned OpenAI-compatible client boundary."""

    def __init__(
        self,
        client: AsyncOpenAIClientProtocol | None = None,
        *,
        provider: AsyncOpenAIClientProvider | None = None,
        models: Sequence[str] | None = None,
        is_local: bool = False,
        execution_profile_adapter_id: str | None = None,
        model_id_mapping: Mapping[str, str] | None = None,
        error_translator: ErrorTranslator | None = None,
        response_validator: ResponseValidator | None = None,
    ) -> None:
        if client is not None and provider is not None:
            raise ValueError(
                "AsyncOpenAIClientAdapter accepts either client or provider"
            )
        self._client = client
        self._provider = provider
        self._client_lock = RLock()
        self._models = tuple(str(model) for model in models or ())
        self._is_local = is_local
        self._execution_profile_adapter_id = execution_profile_adapter_id
        self._model_id_mapping = dict(model_id_mapping or {})
        self._error_translator = error_translator
        self._response_validator = response_validator
        self._available_model_ids: tuple[str, ...] | None = None

    @property
    def client(self) -> AsyncOpenAIClientProtocol:
        """Return the injected or lazily constructed async OpenAI-compatible client."""

        with self._client_lock:
            if self._client is None:
                if self._provider is None:
                    self._provider = create_default_async_openai_provider()
                self._client = self._provider.get_client()
            return self._client

    async def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Send a request asynchronously and normalize the model response."""

        client = self.client
        original_request = request
        try:
            request = replace(request, model=self.resolved_model_id(request.model))
            await self._validate_request_model_available(client, request)
            response = await create_async_openai_response(
                client,
                _prepare_chatgpt_codex_request(self._provider, request),
            )
        except ModelExecutionError as exc:
            if self._error_translator is None:
                raise
            translated = self._error_translator(exc)
            if translated is exc:
                raise
            raise translated from exc
        if self._response_validator is not None:
            self._response_validator(original_request, response)
        return response

    @property
    def models(self) -> tuple[str, ...]:
        """Return advertised model names for capability-aware selection."""

        return self._models

    @property
    def capabilities(self) -> Mapping[str, object]:
        """Return the baseline capabilities of this adapter boundary."""

        return {"text_generation": True}

    @property
    def execution_profile_adapter_id(self) -> str | None:
        """Return the host-factory identity used for profile admission."""

        return self._execution_profile_adapter_id

    def resolved_model_id(self, model_id: str) -> str:
        """Resolve a host-owned execution alias without widening model access."""

        return self._model_id_mapping.get(model_id, model_id)

    async def list_supported_models(self, *, refresh: bool = False) -> tuple[str, ...]:
        """Return model ids supported by this adapter's configured provider."""

        if self._models and not refresh:
            return self._models
        if self._available_model_ids is not None and not refresh:
            return self._available_model_ids
        self._available_model_ids = await self._list_client_model_ids(self.client)
        return self._available_model_ids

    async def default_model(self, *, refresh: bool = False) -> str:
        """Return the first supported model to use when callers did not choose one."""

        models = await self.list_supported_models(refresh=refresh)
        if not models:
            raise ModelExecutionError("OpenAI provider did not advertise any models")
        return models[0]

    @property
    def is_local(self) -> bool:
        """Return whether this adapter should be treated as local-only."""

        return self._is_local

    async def _validate_request_model_available(
        self,
        client: AsyncOpenAIClientProtocol,
        request: OpenAIModelRequest,
    ) -> None:
        if not _provider_uses_chatgpt_codex(self._provider):
            return
        available_model_ids = self._available_model_ids
        if available_model_ids is None:
            available_model_ids = await self._list_client_model_ids(client)
            self._available_model_ids = available_model_ids
        _raise_if_model_is_unavailable(
            request.model,
            available_model_ids,
            provider_label="ChatGPT/Codex",
        )

    async def _list_client_model_ids(
        self,
        client: AsyncOpenAIClientProtocol,
    ) -> tuple[str, ...]:
        return await list_async_openai_model_ids(
            client,
            chatgpt_codex=_provider_uses_chatgpt_codex(self._provider),
            extra_query=(
                _chatgpt_codex_models_extra_query()
                if _provider_uses_chatgpt_codex(self._provider)
                else None
            ),
        )


def create_default_openai_provider(
    config: OpenAIProviderConfig | None = None,
) -> OpenAIClientProvider:
    """Construct the default sync LiteLLM-backed provider facade."""

    resolved = _resolve_default_openai_provider_defaults(
        config or OpenAIProviderConfig()
    )
    if resolved.chatgpt_token is not None:
        return ChatGPTCodexBackendOpenAIClientProvider(
            config=resolved.config,
            token=resolved.chatgpt_token,
        )
    from dynamic_agent_runner.litellm_client import LiteLLMClientProvider

    return LiteLLMClientProvider(config=resolved.config)


def create_default_openai_client(
    config: OpenAIProviderConfig | None = None,
) -> OpenAIClientProtocol:
    """Construct the default LiteLLM-backed client from environment/default config."""

    return create_default_openai_provider(config).get_client()


def create_official_openai_provider(
    config: OpenAIProviderConfig | None = None,
) -> OpenAIClientProvider:
    """Construct the explicit official-SDK compatibility provider."""

    resolved = _resolve_default_openai_provider_defaults(
        config or OpenAIProviderConfig()
    )
    if resolved.chatgpt_token is not None:
        return ChatGPTCodexBackendOpenAIClientProvider(
            config=resolved.config,
            token=resolved.chatgpt_token,
        )
    return SDKBackedOpenAIClientProvider(resolved.config)


def create_official_openai_client(
    config: OpenAIProviderConfig | None = None,
) -> OpenAIClientProtocol:
    """Construct the explicit official OpenAI SDK compatibility client."""

    return create_official_openai_provider(config).get_client()


def create_openai_adapter(
    *,
    client: OpenAIClientProtocol | None = None,
    provider: OpenAIClientProvider | None = None,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    execution_profile_adapter_id: str | None = None,
    model_id_mapping: Mapping[str, str] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> OpenAIClientAdapter:
    """Construct a sync adapter through the repository-owned adapter seam."""

    return OpenAIClientAdapter(
        client=client,
        provider=provider,
        models=models,
        is_local=is_local,
        execution_profile_adapter_id=execution_profile_adapter_id,
        model_id_mapping=model_id_mapping,
        error_translator=error_translator,
        response_validator=response_validator,
    )


def create_openai_adapter_from_provider_config(
    config: OpenAIProviderConfig,
    *,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    execution_profile_adapter_id: str | None = None,
    model_id_mapping: Mapping[str, str] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> OpenAIClientAdapter:
    """Construct a sync adapter from provider config through repo-owned helpers."""

    return create_openai_adapter(
        provider=create_default_openai_provider(config),
        models=models,
        is_local=is_local,
        execution_profile_adapter_id=execution_profile_adapter_id,
        model_id_mapping=model_id_mapping,
        error_translator=error_translator,
        response_validator=response_validator,
    )


def create_default_async_openai_provider(
    config: OpenAIProviderConfig | None = None,
) -> AsyncOpenAIClientProvider:
    """Construct the default async LiteLLM-backed provider facade."""

    resolved = _resolve_default_openai_provider_defaults(
        config or OpenAIProviderConfig()
    )
    if resolved.chatgpt_token is not None:
        return ChatGPTCodexBackendAsyncOpenAIClientProvider(
            config=resolved.config,
            token=resolved.chatgpt_token,
        )
    from dynamic_agent_runner.litellm_client import AsyncLiteLLMClientProvider

    return AsyncLiteLLMClientProvider(config=resolved.config)


def create_default_async_openai_client(
    config: OpenAIProviderConfig | None = None,
) -> AsyncOpenAIClientProtocol:
    """Construct the default async LiteLLM-backed client."""

    return create_default_async_openai_provider(config).get_client()


def create_official_async_openai_provider(
    config: OpenAIProviderConfig | None = None,
) -> AsyncOpenAIClientProvider:
    """Construct the explicit official async SDK compatibility provider."""

    resolved = _resolve_default_openai_provider_defaults(
        config or OpenAIProviderConfig()
    )
    if resolved.chatgpt_token is not None:
        return ChatGPTCodexBackendAsyncOpenAIClientProvider(
            config=resolved.config,
            token=resolved.chatgpt_token,
        )
    return SDKBackedAsyncOpenAIClientProvider(resolved.config)


def create_official_async_openai_client(
    config: OpenAIProviderConfig | None = None,
) -> AsyncOpenAIClientProtocol:
    """Construct the explicit official async OpenAI SDK compatibility client."""

    return create_official_async_openai_provider(config).get_client()


def create_async_openai_adapter(
    *,
    client: AsyncOpenAIClientProtocol | None = None,
    provider: AsyncOpenAIClientProvider | None = None,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    execution_profile_adapter_id: str | None = None,
    model_id_mapping: Mapping[str, str] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> AsyncOpenAIClientAdapter:
    """Construct an async adapter through the repository-owned adapter seam."""

    return AsyncOpenAIClientAdapter(
        client=client,
        provider=provider,
        models=models,
        is_local=is_local,
        execution_profile_adapter_id=execution_profile_adapter_id,
        model_id_mapping=model_id_mapping,
        error_translator=error_translator,
        response_validator=response_validator,
    )


def create_async_openai_adapter_from_provider_config(
    config: OpenAIProviderConfig,
    *,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    execution_profile_adapter_id: str | None = None,
    model_id_mapping: Mapping[str, str] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> AsyncOpenAIClientAdapter:
    """Construct an async adapter from provider config through repo-owned helpers."""

    return create_async_openai_adapter(
        provider=create_default_async_openai_provider(config),
        models=models,
        is_local=is_local,
        execution_profile_adapter_id=execution_profile_adapter_id,
        model_id_mapping=model_id_mapping,
        error_translator=error_translator,
        response_validator=response_validator,
    )


def build_openai_request(
    *,
    model: str,
    messages: Sequence[OpenAIMessage | Mapping[str, Any]],
    tools: Iterable[Mapping[str, Any]] | None = None,
    tool_choice: str | Mapping[str, Any] | None = None,
    response_format: Mapping[str, Any] | None = None,
    adapter_context: object | None = None,
    **extra: Any,
) -> OpenAIModelRequest:
    """Build a normalized OpenAI model request from rendered messages."""

    if not model:
        raise ModelExecutionError("OpenAI model request requires a model")
    normalized_messages = tuple(_message_to_mapping(message) for message in messages)
    if not normalized_messages:
        raise ModelExecutionError("OpenAI model request requires at least one message")
    return OpenAIModelRequest(
        model=model,
        messages=normalized_messages,
        tools=tuple(dict(tool) for tool in tools or ()),
        tool_choice=tool_choice,
        response_format=dict(response_format) if response_format is not None else None,
        extra={key: value for key, value in extra.items() if value is not None},
        adapter_context=adapter_context,
    )


def normalize_openai_response(raw_response: Any) -> ModelResponse:
    """Normalize an OpenAI Responses API object into runtime response data."""

    response_id = _optional_str(_read_value(raw_response, "id"))
    content = _extract_text(raw_response)
    tool_calls = tuple(_extract_tool_calls(raw_response))
    return ModelResponse(
        content=content,
        tool_calls=tool_calls,
        response_id=response_id,
        raw=raw_response,
    )


def create_openai_response(
    client: OpenAIClientProtocol,
    request: OpenAIModelRequest,
) -> ModelResponse:
    """Dispatch a sync OpenAI-compatible request through repo-owned helpers."""

    try:
        kwargs = request.to_kwargs()
        raw_response = client.responses.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 - normalize SDK/client failures.
        raise ModelExecutionError(f"OpenAI model request failed: {exc}") from exc
    if isinstance(raw_response, ModelResponse):
        return raw_response
    if kwargs.get("stream") and not isinstance(raw_response, Mapping):
        return _normalize_openai_stream(raw_response)
    return normalize_openai_response(raw_response)


async def create_async_openai_response(
    client: AsyncOpenAIClientProtocol,
    request: OpenAIModelRequest,
) -> ModelResponse:
    """Dispatch an async OpenAI-compatible request through repo-owned helpers."""

    try:
        kwargs = request.to_kwargs()
        raw_response = await client.responses.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 - normalize SDK/client failures.
        raise ModelExecutionError(f"OpenAI model request failed: {exc}") from exc
    if isinstance(raw_response, ModelResponse):
        return raw_response
    if kwargs.get("stream") and not isinstance(raw_response, Mapping):
        return await _normalize_async_openai_stream(raw_response)
    return normalize_openai_response(raw_response)


def list_openai_model_ids(
    client: OpenAIClientProtocol,
    *,
    extra_query: Mapping[str, object] | None = None,
    chatgpt_codex: bool = False,
) -> tuple[str, ...]:
    """List available model ids from an authenticated OpenAI-compatible client."""

    models_resource = getattr(client, "models", None)
    list_method = getattr(models_resource, "list", None)
    if not callable(list_method):
        raise ModelExecutionError(
            "OpenAI provider does not expose available model listing"
        )
    try:
        raw_models = (
            list_method(extra_query=dict(extra_query))
            if extra_query is not None
            else list_method()
        )
    except Exception as exc:  # noqa: BLE001 - normalize SDK/client failures.
        raise ModelExecutionError("OpenAI available model listing failed") from exc
    return (
        _extract_chatgpt_codex_model_ids(raw_models)
        if chatgpt_codex
        else _extract_model_ids(raw_models)
    )


async def list_async_openai_model_ids(
    client: AsyncOpenAIClientProtocol,
    *,
    extra_query: Mapping[str, object] | None = None,
    chatgpt_codex: bool = False,
) -> tuple[str, ...]:
    """List available model ids from an authenticated async OpenAI-compatible client."""

    models_resource = getattr(client, "models", None)
    list_method = getattr(models_resource, "list", None)
    if not callable(list_method):
        raise ModelExecutionError(
            "OpenAI provider does not expose available model listing"
        )
    try:
        raw_models = (
            list_method(extra_query=dict(extra_query))
            if extra_query is not None
            else list_method()
        )
        if inspect.isawaitable(raw_models):
            raw_models = await raw_models
    except Exception as exc:  # noqa: BLE001 - normalize SDK/client failures.
        raise ModelExecutionError("OpenAI available model listing failed") from exc
    return (
        _extract_chatgpt_codex_model_ids(raw_models)
        if chatgpt_codex
        else _extract_model_ids(raw_models)
    )


def _extract_model_ids(raw_models: Any) -> tuple[str, ...]:
    data = _read_value(raw_models, "data")
    models = _read_value(raw_models, "models")
    extra_models = _read_value(_read_value(raw_models, "model_extra"), "models")
    if data is not None:
        items = data
    elif models is not None:
        items = models
    elif extra_models is not None:
        items = extra_models
    else:
        items = raw_models
    model_ids: list[str] = []
    for item in _as_sequence(items):
        model_id = item if isinstance(item, str) else _read_model_id(item)
        if isinstance(model_id, str) and model_id.strip():
            model_ids.append(model_id.strip())
    return _sort_model_ids_by_version(tuple(dict.fromkeys(model_ids)))


def _extract_chatgpt_codex_model_ids(raw_models: Any) -> tuple[str, ...]:
    """Preserve ChatGPT/Codex catalog priority and hide picker-only entries."""

    data = _read_value(raw_models, "data")
    models = _read_value(raw_models, "models")
    extra_models = _read_value(_read_value(raw_models, "model_extra"), "models")
    items = data if data is not None else models
    if items is None:
        items = extra_models if extra_models is not None else raw_models
    ranked: list[tuple[int, int, str]] = []
    for index, item in enumerate(_as_sequence(items)):
        model_id = item if isinstance(item, str) else _read_model_id(item)
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        visibility = str(_read_value(item, "visibility") or "").lower()
        if visibility == "hide":
            continue
        priority = _read_value(item, "priority")
        rank = (
            priority
            if isinstance(priority, int) and not isinstance(priority, bool)
            else index
        )
        ranked.append((rank, index, model_id.strip()))
    return tuple(dict.fromkeys(model_id for _rank, _index, model_id in sorted(ranked)))


_MODEL_VERSION_PATTERN = re.compile(r"(?<!\d)(\d+(?:\.\d+)*)(?!\d)")


def _sort_model_ids_by_version(model_ids: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(model_ids, key=_model_id_version_sort_key))


def _model_id_version_sort_key(model_id: str) -> tuple[int, tuple[int, ...], str]:
    match = _MODEL_VERSION_PATTERN.search(model_id)
    if match is None:
        return (1, (), model_id)
    version = tuple(int(part) for part in match.group(1).split("."))
    return (0, version, model_id)


def _normalize_openai_stream(raw_stream: Any) -> ModelResponse:
    events: list[Any] = []
    for event in raw_stream:
        events.append(event)
    return _normalize_openai_stream_events(events)


async def _normalize_async_openai_stream(raw_stream: Any) -> ModelResponse:
    events: list[Any] = []
    if hasattr(raw_stream, "__aiter__"):
        async for event in raw_stream:
            events.append(event)
    else:
        for event in raw_stream:
            events.append(event)
    return _normalize_openai_stream_events(events)


def _normalize_openai_stream_events(events: Sequence[Any]) -> ModelResponse:
    deltas: list[str] = []
    output_items: list[Any] = []
    response_id: str | None = None
    completed_response: Any = None
    for event in events:
        event_type = _read_value(event, "type")
        if event_type == "response.output_text.delta":
            delta = _read_value(event, "delta")
            if delta is not None:
                deltas.append(str(delta))
            continue
        if event_type == "response.output_item.done":
            item = _read_value(event, "item")
            if item is not None:
                output_items.append(item)
            continue
        response = _read_value(event, "response")
        if response is not None:
            response_id = _optional_str(_read_value(response, "id")) or response_id
            if event_type == "response.completed":
                completed_response = response

    streamed_response = (
        normalize_openai_response({"id": response_id, "output": output_items})
        if output_items
        else None
    )
    if completed_response is not None:
        normalized = normalize_openai_response(completed_response)
        return ModelResponse(
            content=(
                normalized.content
                or (
                    streamed_response.content if streamed_response is not None else None
                )
                or ("".join(deltas) if deltas else None)
            ),
            tool_calls=normalized.tool_calls
            or (
                streamed_response.tool_calls
                if streamed_response is not None
                else normalized.tool_calls
            ),
            response_id=normalized.response_id or response_id,
            raw=completed_response,
        )
    return ModelResponse(
        content=(
            streamed_response.content
            if streamed_response is not None and streamed_response.content is not None
            else ("".join(deltas) if deltas else None)
        ),
        tool_calls=(
            streamed_response.tool_calls if streamed_response is not None else ()
        ),
        response_id=response_id,
        raw=tuple(events),
    )


def _read_model_id(item: Any) -> Any:
    return (
        _read_value(item, "id")
        or _read_value(item, "slug")
        or _read_value(_read_value(item, "model_extra"), "slug")
    )


def _provider_uses_chatgpt_codex(provider: Any) -> bool:
    config = getattr(provider, "config", None)
    return getattr(config, "provider_name", None) == CHATGPT_CODEX_PROVIDER_NAME


def _prepare_chatgpt_codex_request(
    provider: Any,
    request: OpenAIModelRequest,
) -> OpenAIModelRequest:
    if not _provider_uses_chatgpt_codex(provider):
        return request

    input_messages: list[Mapping[str, Any]] = []
    instruction_parts: list[str] = []
    for message in request.messages:
        transcript_item = _chatgpt_codex_transcript_input_item(message)
        if transcript_item is not None:
            input_messages.append(transcript_item)
            continue
        role = str(message.get("role") or "")
        content = message.get("content")
        if role in {"system", "developer"}:
            if content is not None and str(content).strip():
                instruction_parts.append(str(content).strip())
        else:
            input_messages.append(message)

    extra = dict(request.extra)
    existing_instructions = extra.get("instructions")
    if existing_instructions is not None and str(existing_instructions).strip():
        instruction_parts.insert(0, str(existing_instructions).strip())
    extra["instructions"] = (
        "\n\n".join(instruction_parts)
        if instruction_parts
        else "You are a helpful assistant."
    )
    extra["store"] = False
    extra["stream"] = True

    return OpenAIModelRequest(
        model=request.model,
        messages=tuple(input_messages or request.messages),
        tools=request.tools,
        tool_choice=request.tool_choice,
        response_format=request.response_format,
        extra=extra,
        adapter_context=request.adapter_context,
    )


def _chatgpt_codex_transcript_input_item(
    message: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    transcript_type = message.get(_DAR_TRANSCRIPT_TYPE_KEY)
    if transcript_type == _DAR_MODEL_TOOL_CALL:
        return {
            "type": "function_call",
            "call_id": str(message.get("call_id") or message.get("tool_call_id") or ""),
            "name": str(message.get("name") or ""),
            "arguments": str(message.get("arguments") or "{}"),
        }
    if transcript_type == _DAR_MODEL_TOOL_RESULT:
        return {
            "type": "function_call_output",
            "call_id": str(message.get("call_id") or message.get("tool_call_id") or ""),
            "output": str(message.get("output") or message.get("content") or ""),
        }
    return None


def _request_message_to_provider_input(message: Mapping[str, Any]) -> Mapping[str, Any]:
    if message.get(_DAR_TRANSCRIPT_TYPE_KEY) is None:
        return dict(message)
    if message.get(_DAR_TRANSCRIPT_TYPE_KEY) == _DAR_MODEL_TOOL_CALL:
        return {
            key: value
            for key, value in message.items()
            if key in {"role", "content", "tool_calls"}
        }
    return {
        key: value
        for key, value in message.items()
        if key in {"role", "tool_call_id", "name", "content"}
    }


def _chatgpt_codex_models_extra_query() -> dict[str, str]:
    client_version = (
        os.environ.get("DYNAMIC_AGENT_RUNNER_CODEX_CLIENT_VERSION")
        or os.environ.get("CODEX_CLIENT_VERSION")
        or _read_codex_client_version()
        or CHATGPT_CODEX_FALLBACK_CLIENT_VERSION
    )
    return {"client_version": client_version}


def _read_codex_client_version() -> str | None:
    try:
        codex_home = _resolve_codex_home()
    except ModelExecutionError:
        return None
    if codex_home is None:
        return None
    version_file = codex_home / "version.json"
    if not version_file.exists():
        return None
    try:
        with version_file.open(encoding="utf-8") as handle:
            version = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(version, Mapping):
        return None
    latest_version = version.get("latest_version")
    if not isinstance(latest_version, str):
        return None
    whole_version = latest_version.strip().partition("-")[0]
    return whole_version or None


def _raise_if_model_is_unavailable(
    model: str,
    available_model_ids: Sequence[str],
    *,
    provider_label: str,
) -> None:
    if model in available_model_ids:
        return
    available = ", ".join(available_model_ids) if available_model_ids else "none"
    raise ModelExecutionError(
        f"{provider_label} provider does not advertise model {model!r}; "
        f"available models: {available}"
    )


def _message_to_mapping(
    message: OpenAIMessage | Mapping[str, Any],
) -> Mapping[str, Any]:
    if isinstance(message, OpenAIMessage):
        return message.to_mapping()
    if not isinstance(message, Mapping):
        raise ModelExecutionError("OpenAI message must be a mapping or OpenAIMessage")
    if not message.get("role") or message.get("content") is None:
        raise ModelExecutionError("OpenAI message requires role and content")
    return dict(message)


def _extract_text(raw_response: Any) -> str | None:
    output_text = _read_value(raw_response, "output_text")
    if output_text is not None:
        return str(output_text)
    chunks: list[str] = []
    for item in _as_sequence(_read_value(raw_response, "output")):
        if _read_value(item, "type") != "message":
            continue
        for content_item in _as_sequence(_read_value(item, "content")):
            text = _read_value(content_item, "text")
            if text is not None:
                chunks.append(str(text))
    return "".join(chunks) if chunks else None


def _extract_tool_calls(raw_response: Any) -> list[ModelToolCall]:
    tool_calls: list[ModelToolCall] = []
    for item in _as_sequence(_read_value(raw_response, "output")):
        if _read_value(item, "type") != "function_call":
            continue
        name = _read_value(item, "name")
        if name is None:
            continue
        tool_calls.append(
            ModelToolCall(
                id=_optional_str(
                    _read_value(item, "call_id") or _read_value(item, "id")
                ),
                name=str(name),
                arguments=_read_value(item, "arguments") or {},
            )
        )
    return tool_calls


def _read_value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _as_sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return (value,)


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _resolve_default_openai_provider_config(
    config: OpenAIProviderConfig,
) -> OpenAIProviderConfig:
    """Resolve host-owned defaults for the SDK-backed OpenAI provider."""

    return _resolve_default_openai_provider_defaults(config).config


def _resolve_default_openai_provider_defaults(
    config: OpenAIProviderConfig,
) -> _ResolvedDefaultOpenAIProvider:
    _validate_codex_auth_preference(config.codex_auth_preference)

    if not config.discover_default_auth:
        return _ResolvedDefaultOpenAIProvider(
            OpenAIProviderConfig(
                base_url=config.base_url,
                api_key=config.api_key,
                provider_name=config.provider_name,
                chatgpt_account_id=config.chatgpt_account_id,
                discover_default_auth=config.discover_default_auth,
                codex_auth_preference=config.codex_auth_preference,
            )
        )

    base_url = config.base_url
    api_key = config.api_key
    provider_name = config.provider_name
    chatgpt_token: str | None = None
    chatgpt_account_id: str | None = config.chatgpt_account_id
    codex_home: Path | None = None

    if api_key is None:
        api_key = _read_non_empty_env("OPENAI_API_KEY")
        if api_key is None:
            codex_home = _resolve_codex_home()
            if codex_home is not None:
                selected_codex_auth = _resolve_selected_codex_auth(
                    codex_home, config.codex_auth_preference
                )
                api_key = selected_codex_auth.api_key
                chatgpt_token = selected_codex_auth.chatgpt_token
                chatgpt_account_id = (
                    selected_codex_auth.chatgpt_account_id or chatgpt_account_id
                )
                if chatgpt_token is not None:
                    provider_name = provider_name or CHATGPT_CODEX_PROVIDER_NAME

    if base_url is None:
        if chatgpt_token is not None:
            base_url = CHATGPT_CODEX_BACKEND_BASE_URL
        else:
            if codex_home is None:
                codex_home = _resolve_codex_home()
            if codex_home is not None:
                base_url = _read_codex_openai_base_url(codex_home)

    return _ResolvedDefaultOpenAIProvider(
        OpenAIProviderConfig(
            base_url=base_url,
            api_key=api_key,
            provider_name=provider_name,
            chatgpt_account_id=chatgpt_account_id,
            discover_default_auth=config.discover_default_auth,
            codex_auth_preference=config.codex_auth_preference,
        ),
        chatgpt_token=chatgpt_token,
    )


def _validate_codex_auth_preference(value: str) -> None:
    if value not in {CODEX_AUTH_API_KEY_FIRST, CODEX_AUTH_CHATGPT_FIRST}:
        raise ModelExecutionError(
            "OpenAIProviderConfig.codex_auth_preference must be "
            "'api_key_first' or 'chatgpt_first'"
        )


def _resolve_selected_codex_auth(
    codex_home: Path,
    preference: str,
) -> _CodexAuthDefaults:
    codex_auth = _read_codex_auth_defaults(codex_home)
    selected_auth = _select_codex_auth(codex_auth, preference)
    if selected_auth == "api_key":
        return _CodexAuthDefaults(api_key=codex_auth.api_key)
    if selected_auth == "chatgpt":
        return _CodexAuthDefaults(
            chatgpt_token=codex_auth.chatgpt_token,
            chatgpt_account_id=codex_auth.chatgpt_account_id,
        )
    return _CodexAuthDefaults()


def _read_non_empty_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _resolve_codex_home() -> Path | None:
    raw_codex_home = os.environ.get("CODEX_HOME")
    if raw_codex_home is not None and raw_codex_home.strip():
        codex_home = Path(raw_codex_home.strip()).expanduser()
        if not codex_home.is_dir():
            raise ModelExecutionError(
                f"CODEX_HOME must point to an existing directory: {codex_home}"
            )
        return codex_home

    codex_home = Path.home() / ".codex"
    if not codex_home.exists():
        return None
    if not codex_home.is_dir():
        raise ModelExecutionError(
            f"default Codex home must be a directory: {codex_home}"
        )
    return codex_home


def _read_codex_openai_base_url(codex_home: Path) -> str | None:
    config_file = codex_home / "config.toml"
    if not config_file.exists():
        return None
    text = config_file.read_text(encoding="utf-8")
    try:
        config = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return _read_codex_openai_base_url_from_top_level_text(config_file, text)
    value = config.get("openai_base_url")
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _read_codex_openai_base_url_from_top_level_text(
    config_file: Path,
    text: str,
) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("["):
            return None
        key, separator, _value = stripped.partition("=")
        if key.strip() != "openai_base_url" or not separator:
            continue
        try:
            value = tomllib.loads(line).get("openai_base_url")
        except tomllib.TOMLDecodeError as exc:
            raise ModelExecutionError(
                f"failed to parse Codex config file {config_file}"
            ) from exc
        if not isinstance(value, str):
            return None
        return value.strip() or None
    return None


def _read_codex_auth_defaults(codex_home: Path) -> _CodexAuthDefaults:
    auth_file = codex_home / "auth.json"
    if not auth_file.exists():
        return _CodexAuthDefaults()
    try:
        with auth_file.open(encoding="utf-8") as handle:
            auth = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ModelExecutionError(
            f"failed to parse Codex auth file {auth_file}"
        ) from exc
    if not isinstance(auth, Mapping):
        raise ModelExecutionError(f"Codex auth file {auth_file} must contain an object")

    declared_mode = _resolve_declared_codex_auth_mode(auth)
    unsupported_mode = _resolve_unsupported_codex_auth_mode(auth)
    if unsupported_mode is not None:
        return _CodexAuthDefaults(unsupported_mode=unsupported_mode)

    if declared_mode == "api_key":
        return _CodexAuthDefaults(api_key=_read_codex_api_key_value(auth, auth_file))
    if declared_mode == "chatgpt":
        chatgpt_token = _read_codex_chatgpt_token(auth)
        if chatgpt_token is None:
            raise ModelExecutionError(
                f"Codex auth file {auth_file} uses ChatGPT auth but has no token"
            )
        return _CodexAuthDefaults(
            chatgpt_token=chatgpt_token,
            chatgpt_account_id=_read_chatgpt_account_id(auth),
        )

    api_key = _read_codex_api_key_value(auth, auth_file)
    chatgpt_token = _read_codex_chatgpt_token(auth)
    return _CodexAuthDefaults(
        api_key=api_key,
        chatgpt_token=chatgpt_token,
        chatgpt_account_id=_read_chatgpt_account_id(auth),
    )


def _read_chatgpt_account_id(auth: Mapping[str, Any]) -> str | None:
    tokens = auth.get("tokens")
    if not isinstance(tokens, Mapping):
        return None
    account_id = tokens.get("account_id")
    if not isinstance(account_id, str):
        return None
    stripped = account_id.strip()
    return stripped or None


def _read_codex_api_key_value(
    auth: Mapping[str, Any],
    auth_file: Path,
) -> str | None:
    if _declared_auth_mode_is(auth, "api_key") and not isinstance(
        auth.get("OPENAI_API_KEY"), str
    ):
        raise ModelExecutionError(
            f"Codex auth file {auth_file} uses API-key auth but has no key"
        )

    value = auth.get("OPENAI_API_KEY")
    if not isinstance(value, str):
        return None
    if not value.strip():
        if _declared_auth_mode_is(auth, "api_key"):
            raise ModelExecutionError(
                f"Codex auth file {auth_file} uses API-key auth but has no key"
            )
        return None
    return value.strip()


def _read_codex_chatgpt_token(auth: Mapping[str, Any]) -> str | None:
    tokens = auth.get("tokens")
    if isinstance(tokens, Mapping):
        for key in ("access_token", "id_token"):
            value = tokens.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _select_codex_auth(
    auth: _CodexAuthDefaults,
    preference: str,
) -> str | None:
    if preference == CODEX_AUTH_CHATGPT_FIRST:
        if auth.chatgpt_token is not None:
            return "chatgpt"
        if auth.api_key is not None:
            return "api_key"
    else:
        if auth.api_key is not None:
            return "api_key"
        if auth.chatgpt_token is not None:
            return "chatgpt"

    if auth.unsupported_mode is not None:
        raise ModelExecutionError(
            f"unsupported Codex auth mode {auth.unsupported_mode!r}; provide an "
            "OpenAI API key or supported ChatGPT auth"
        )
    return None


def _resolve_unsupported_codex_auth_mode(auth: Mapping[str, Any]) -> str | None:
    mode = _resolve_declared_codex_auth_mode(auth)
    if mode is None:
        if auth.get("personal_access_token") is not None:
            return "personal_access_token"
        if auth.get("agent_identity") is not None:
            return "agent_identity"
        mode = _resolve_codex_auth_mode(auth)
    if mode not in {None, "api_key", "chatgpt"}:
        return mode
    return None


def _resolve_declared_codex_auth_mode(auth: Mapping[str, Any]) -> str | None:
    raw_mode = auth.get("auth_mode")
    if isinstance(raw_mode, str) and raw_mode.strip():
        mode = raw_mode.strip().replace("-", "_").lower()
        if mode in {"api", "apikey"}:
            return "api_key"
        return mode
    return None


def _resolve_codex_auth_mode(auth: Mapping[str, Any]) -> str | None:
    mode = _resolve_declared_codex_auth_mode(auth)
    if mode is not None:
        return mode

    if isinstance(auth.get("OPENAI_API_KEY"), str):
        return "api_key"
    if auth.get("personal_access_token") is not None:
        return "personal_access_token"
    if auth.get("agent_identity") is not None:
        return "agent_identity"
    if auth.get("tokens") is not None:
        return "chatgpt"
    return None


def _declared_auth_mode_is(auth: Mapping[str, Any], expected: str) -> bool:
    return _resolve_declared_codex_auth_mode(auth) == expected


def _provider_config_to_client_kwargs(config: OpenAIProviderConfig) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if config.base_url is not None:
        kwargs["base_url"] = config.base_url
    if config.api_key is not None:
        kwargs["api_key"] = config.api_key
    return kwargs


def _chatgpt_provider_config_to_client_kwargs(
    config: OpenAIProviderConfig,
    token: str,
) -> dict[str, Any]:
    kwargs = _provider_config_to_client_kwargs(config)
    kwargs["api_key"] = token
    if config.chatgpt_account_id is not None:
        kwargs["default_headers"] = {
            "ChatGPT-Account-ID": config.chatgpt_account_id,
        }
    return kwargs
