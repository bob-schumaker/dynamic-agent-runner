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
    """Small adapter around the official OpenAI Python client."""

    def __init__(self, client: OpenAIClientProtocol | None = None) -> None:
        self._client = client
        self._client_lock = RLock()

    @property
    def client(self) -> OpenAIClientProtocol:
        """Return the injected or lazily constructed official OpenAI client."""

        with self._client_lock:
            if self._client is None:
                self._client = create_default_openai_client()
            return self._client

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Send a request and normalize the returned model response."""

        try:
            raw_response = self.client.responses.create(**request.to_kwargs())
        except Exception as exc:  # noqa: BLE001 - normalize SDK/client failures.
            raise ModelExecutionError(f"OpenAI model request failed: {exc}") from exc
        return normalize_openai_response(raw_response)


def create_default_openai_client() -> OpenAIClientProtocol:
    """Construct the official OpenAI client from environment/default config."""

    try:
        from openai import OpenAI
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise ModelExecutionError("official openai package is not available") from exc
    return OpenAI()


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
