"""OpenAI client adapter boundary for dynamic-agent workflow execution."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol

from dynamic_agent_runner.errors import ModelExecutionError


class OpenAIResponsesResource(Protocol):
    """Minimal subset of the OpenAI Responses API used by the runtime."""

    def create(self, **kwargs: Any) -> Any:
        """Create a model response."""


class OpenAIClientProtocol(Protocol):
    """Protocol-compatible OpenAI client for default and fake clients."""

    responses: OpenAIResponsesResource


class AsyncOpenAIResponsesResource(Protocol):
    """Minimal async OpenAI Responses API subset used by the runtime."""

    async def create(self, **kwargs: Any) -> Any:
        """Create a model response asynchronously."""


class AsyncOpenAIClientProtocol(Protocol):
    """Protocol-compatible async OpenAI client for default and fake clients."""

    responses: AsyncOpenAIResponsesResource


@dataclass(frozen=True)
class OpenAIProviderConfig:
    """Repository-owned configuration for an OpenAI-compatible provider."""

    base_url: str | None = None
    api_key: str | None = None
    provider_name: str | None = None


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

    def to_kwargs(self) -> dict[str, Any]:
        """Return keyword arguments for ``client.responses.create``."""

        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": list(self.messages),
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


@dataclass(frozen=True)
class ModelResponse:
    """Normalized model response returned by the adapter."""

    content: str | None
    tool_calls: tuple[ModelToolCall, ...] = ()
    response_id: str | None = None
    raw: Any = None


class OpenAIClientAdapter:
    """Small adapter around a repository-owned OpenAI-compatible client boundary."""

    def __init__(
        self,
        client: OpenAIClientProtocol | None = None,
        *,
        provider: OpenAIClientProvider | None = None,
        models: Sequence[str] | None = None,
        is_local: bool = False,
    ) -> None:
        if client is not None and provider is not None:
            raise ValueError("OpenAIClientAdapter accepts either client or provider")
        self._client = client
        self._provider = provider
        self._client_lock = RLock()
        self._models = tuple(str(model) for model in models or ())
        self._is_local = is_local

    @property
    def client(self) -> OpenAIClientProtocol:
        """Return the injected or lazily constructed OpenAI-compatible client."""

        with self._client_lock:
            if self._client is None:
                if self._provider is not None:
                    self._client = self._provider.get_client()
                else:
                    self._client = create_default_openai_client()
            return self._client

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Send a request and normalize the returned model response."""

        try:
            raw_response = self.client.responses.create(**request.to_kwargs())
        except Exception as exc:  # noqa: BLE001 - normalize SDK/client failures.
            raise ModelExecutionError(f"OpenAI model request failed: {exc}") from exc
        return normalize_openai_response(raw_response)

    @property
    def models(self) -> tuple[str, ...]:
        """Return advertised model names for capability-aware selection."""

        return self._models

    @property
    def is_local(self) -> bool:
        """Return whether this adapter should be treated as local-only."""

        return self._is_local


class AsyncOpenAIClientAdapter:
    """Async adapter around a repository-owned OpenAI-compatible client boundary."""

    def __init__(
        self,
        client: AsyncOpenAIClientProtocol | None = None,
        *,
        provider: AsyncOpenAIClientProvider | None = None,
        models: Sequence[str] | None = None,
        is_local: bool = False,
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

    @property
    def client(self) -> AsyncOpenAIClientProtocol:
        """Return the injected or lazily constructed async OpenAI-compatible client."""

        with self._client_lock:
            if self._client is None:
                if self._provider is not None:
                    self._client = self._provider.get_client()
                else:
                    self._client = create_default_async_openai_client()
            return self._client

    async def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Send a request asynchronously and normalize the model response."""

        try:
            raw_response = await self.client.responses.create(**request.to_kwargs())
        except Exception as exc:  # noqa: BLE001 - normalize SDK/client failures.
            raise ModelExecutionError(f"OpenAI model request failed: {exc}") from exc
        return normalize_openai_response(raw_response)

    @property
    def models(self) -> tuple[str, ...]:
        """Return advertised model names for capability-aware selection."""

        return self._models

    @property
    def is_local(self) -> bool:
        """Return whether this adapter should be treated as local-only."""

        return self._is_local


def create_default_openai_provider(
    config: OpenAIProviderConfig | None = None,
) -> OpenAIClientProvider:
    """Construct the default sync SDK-backed provider facade."""

    return SDKBackedOpenAIClientProvider(config or OpenAIProviderConfig())


def create_default_openai_client(
    config: OpenAIProviderConfig | None = None,
) -> OpenAIClientProtocol:
    """Construct the official OpenAI client from environment/default config."""

    return create_default_openai_provider(config).get_client()


def create_default_async_openai_provider(
    config: OpenAIProviderConfig | None = None,
) -> AsyncOpenAIClientProvider:
    """Construct the default async SDK-backed provider facade."""

    return SDKBackedAsyncOpenAIClientProvider(config or OpenAIProviderConfig())


def create_default_async_openai_client(
    config: OpenAIProviderConfig | None = None,
) -> AsyncOpenAIClientProtocol:
    """Construct the official async OpenAI client from environment/default config."""

    return create_default_async_openai_provider(config).get_client()


def build_openai_request(
    *,
    model: str,
    messages: Sequence[OpenAIMessage | Mapping[str, Any]],
    tools: Iterable[Mapping[str, Any]] | None = None,
    tool_choice: str | Mapping[str, Any] | None = None,
    response_format: Mapping[str, Any] | None = None,
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


def _provider_config_to_client_kwargs(config: OpenAIProviderConfig) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if config.base_url is not None:
        kwargs["base_url"] = config.base_url
    if config.api_key is not None:
        kwargs["api_key"] = config.api_key
    return kwargs
