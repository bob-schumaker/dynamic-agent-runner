"""Optional in-process adapter for Apple's Foundation Models SDK."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import asyncio
import importlib
import json
import sys
from typing import Any
from uuid import uuid4

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    OpenAIModelRequest,
)


AvailabilityChecker = Callable[[], tuple[bool, str | None]]
SessionFactory = Callable[[str | None], Any]


@dataclass(frozen=True)
class AppleFoundationModelConfig:
    """Caller configuration for the system-managed Apple model."""

    model_aliases: tuple[str, ...] = ("apple-system-language-model",)
    availability_checker: AvailabilityChecker | None = None
    session_factory: SessionFactory | None = None

    def __post_init__(self) -> None:
        aliases = tuple(str(alias).strip() for alias in self.model_aliases)
        if not aliases or any(not alias for alias in aliases):
            raise ValueError("model_aliases must contain at least one non-empty alias")
        if len(set(aliases)) != len(aliases):
            raise ValueError("model_aliases must not contain duplicates")
        object.__setattr__(self, "model_aliases", aliases)


def create_apple_foundation_model_async_adapter(
    config: AppleFoundationModelConfig | None = None,
):
    """Create DAR's existing async adapter over an Apple Responses facade."""

    resolved = config or AppleFoundationModelConfig()
    client = _AppleAsyncClient(resolved)
    return AppleFoundationModelAsyncAdapter(
        client=client,
        models=resolved.model_aliases,
        is_local=True,
    )


class AppleFoundationModelAsyncAdapter(AsyncOpenAIClientAdapter):
    """Existing DAR async adapter with conservative Apple capability metadata."""

    @property
    def capabilities(self) -> Mapping[str, Any]:
        return {
            "provider": "apple_foundation_models",
            "execution": "in_process",
            "local": True,
            "model_identity": "system_managed",
            "structured_output": True,
            "streaming": False,
            "tool_calling": False,
            "multimodal": False,
            "embeddings": False,
        }


class _AppleAsyncClient:
    def __init__(self, config: AppleFoundationModelConfig) -> None:
        self.responses = _AppleResponsesResource(config)


class _AppleResponsesResource:
    def __init__(self, config: AppleFoundationModelConfig) -> None:
        self._config = config

    async def create(self, **kwargs: Any) -> Mapping[str, Any]:
        _require_macos()
        request = _request_from_kwargs(kwargs)
        _validate_request(request)
        sdk = _load_sdk() if self._config.availability_checker is None else None
        available, reason = _check_availability(self._config, sdk)
        if not available:
            raise ModelExecutionError(
                f"Apple Foundation Models are unavailable: {reason or 'unknown reason'}"
            )
        if self._config.session_factory is None:
            sdk = sdk or _load_sdk()
        prompt, instructions = _render_messages(request.messages)
        session = _make_session(self._config, sdk, request, instructions)
        options = _make_generation_options(sdk, request.extra)
        schema = _extract_json_schema(request.response_format)
        if schema is not None and self._config.session_factory is None:
            schema = _normalize_apple_schema(schema)
        try:
            if schema is None:
                result = await session.respond(prompt, options=options)
            else:
                result = await session.respond(
                    prompt, json_schema=schema, options=options
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - SDK errors vary by release.
            raise ModelExecutionError(
                "Apple Foundation Models generation failed"
            ) from exc
        content = (
            result.to_json()
            if schema is not None and hasattr(result, "to_json")
            else str(result)
        )
        if schema is not None:
            try:
                json.loads(content)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ModelExecutionError(
                    "Apple Foundation Models structured output was not valid JSON"
                ) from exc
        return {"id": f"apple-{uuid4().hex}", "output_text": content}


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise ModelExecutionError("Apple Foundation Models require macOS")


def _load_sdk() -> Any:
    try:
        return importlib.import_module("apple_fm_sdk")
    except Exception as exc:  # noqa: BLE001 - optional native dependency.
        raise ModelExecutionError(
            "apple-fm-sdk is required for Apple Foundation Models generation"
        ) from exc


def _check_availability(
    config: AppleFoundationModelConfig, sdk: Any | None
) -> tuple[bool, str | None]:
    if config.availability_checker is not None:
        return config.availability_checker()
    if sdk is None:
        raise ModelExecutionError("Apple Foundation Models SDK is unavailable")
    try:
        return sdk.SystemLanguageModel().is_available()
    except Exception as exc:  # noqa: BLE001 - SDK errors vary by release.
        raise ModelExecutionError(
            "Apple Foundation Models availability check failed"
        ) from exc


def _make_session(
    config: AppleFoundationModelConfig,
    sdk: Any | None,
    request: OpenAIModelRequest,
    instructions: str | None = None,
) -> Any:
    try:
        if config.session_factory is not None:
            return config.session_factory(instructions)
        if sdk is None:
            raise ModelExecutionError("Apple Foundation Models SDK is unavailable")
        return sdk.LanguageModelSession(instructions=instructions)
    except ModelExecutionError:
        raise
    except Exception as exc:  # noqa: BLE001 - SDK errors vary by release.
        raise ModelExecutionError(
            "Apple Foundation Models session creation failed"
        ) from exc


def _request_from_kwargs(kwargs: Mapping[str, Any]) -> OpenAIModelRequest:
    return OpenAIModelRequest(
        model=str(kwargs.get("model", "")),
        messages=tuple(kwargs.get("input", ())),
        tools=tuple(kwargs.get("tools", ())),
        tool_choice=kwargs.get("tool_choice"),
        response_format=kwargs.get("response_format"),
        extra={
            key: value
            for key, value in kwargs.items()
            if key not in {"model", "input", "tools", "tool_choice", "response_format"}
        },
    )


def _validate_request(request: OpenAIModelRequest) -> None:
    if request.tools or request.tool_choice is not None:
        raise ModelExecutionError("Apple Foundation Models tool calling is unsupported")
    for message in request.messages:
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str):
            raise ModelExecutionError(
                "Apple Foundation Models support text messages only"
            )
    if request.extra.get("stream"):
        raise ModelExecutionError("Apple Foundation Models streaming is unsupported")
    if (
        request.extra.get("max_tokens") is not None
        and request.extra.get("max_output_tokens") is not None
    ):
        raise ModelExecutionError(
            "max_tokens and max_output_tokens cannot both be supplied"
        )
    supported = {"temperature", "max_tokens", "max_output_tokens"}
    unsupported = set(request.extra) - supported
    if unsupported:
        raise ModelExecutionError(
            f"Apple Foundation Models unsupported request fields: {sorted(unsupported)!r}"
        )
    temperature = request.extra.get("temperature")
    if temperature is not None and (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not 0 <= temperature <= 2
    ):
        raise ModelExecutionError(
            "Apple Foundation Models temperature must be between 0 and 2"
        )
    for key in ("max_tokens", "max_output_tokens"):
        value = request.extra.get(key)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise ModelExecutionError(
                f"Apple Foundation Models {key} must be a positive integer"
            )
    _extract_json_schema(request.response_format)


def _extract_json_schema(
    response_format: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if response_format is None:
        return None
    if response_format.get("type") != "json_schema":
        raise ModelExecutionError(
            "Apple Foundation Models require an explicit JSON Schema"
        )
    value = response_format.get("json_schema")
    schema = value.get("schema") if isinstance(value, Mapping) else value
    if not isinstance(schema, Mapping) or not schema:
        raise ModelExecutionError(
            "Apple Foundation Models require a non-empty JSON Schema"
        )
    return dict(schema)


def _normalize_apple_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Add Foundation Models metadata absent from ordinary JSON Schema."""

    normalized = {
        key: value for key, value in schema.items() if key not in {"title", "x-order"}
    }
    if normalized.get("type") == "object":
        properties = normalized.get("properties")
        if isinstance(properties, Mapping):
            normalized["x-order"] = list(properties)
    title = schema.get("title")
    normalized["title"] = str(title or "GeneratedResponse")
    return normalized


def _render_messages(messages: Sequence[Mapping[str, Any]]) -> tuple[str, str | None]:
    instruction_parts: list[str] = []
    conversation: list[str] = []
    for message in messages:
        role = str(message.get("role"))
        content = str(message["content"])
        if role in {"system", "developer"}:
            instruction_parts.append(content)
        else:
            conversation.append(f"{role}: {content}")
    return "\n".join(conversation), "\n".join(instruction_parts) or None


def _make_generation_options(sdk: Any | None, extra: Mapping[str, Any]) -> Any | None:
    values = {
        key: extra[key]
        for key in ("temperature", "max_tokens", "max_output_tokens")
        if key in extra
    }
    if not values:
        return None
    if sdk is None:
        return values
    max_tokens = values.get("max_tokens", values.get("max_output_tokens"))
    return sdk.GenerationOptions(
        temperature=values.get("temperature"),
        maximum_response_tokens=max_tokens,
    )
