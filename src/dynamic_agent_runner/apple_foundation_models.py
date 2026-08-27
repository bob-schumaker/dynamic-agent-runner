"""Optional in-process adapter for Apple's Foundation Models SDK."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import asyncio
import importlib
import json
import keyword
import sys
from typing import Annotated, Any
from uuid import uuid4

from dynamic_agent_runner.errors import ModelExecutionError, ToolRegistryError
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    ModelResponse,
    OpenAIModelRequest,
    normalize_openai_response,
)
from dynamic_agent_runner.tool_invocation import ActiveAdapterToolContext


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

    async def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Preserve trusted Apple tool context outside OpenAI wire kwargs."""

        if request.adapter_context is None:
            return await super().create_response(request)
        try:
            raw_response = await self.client.responses.create_request(request)
        except ModelExecutionError as exc:
            raise ModelExecutionError(f"OpenAI model request failed: {exc}") from exc
        return normalize_openai_response(raw_response)

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
        return await self.create_request(_request_from_kwargs(kwargs))

    async def create_request(self, request: OpenAIModelRequest) -> Mapping[str, Any]:
        """Create one Apple response while retaining non-wire adapter context."""

        _require_macos()
        sdk = _load_sdk() if self._config.availability_checker is None else None
        wrappers = _apple_tool_wrappers(request, sdk)
        _validate_request(request, tool_bridge_active=bool(wrappers))
        available, reason = _check_availability(self._config, sdk)
        if not available:
            raise ModelExecutionError(
                f"Apple Foundation Models are unavailable: {reason or 'unknown reason'}"
            )
        if self._config.session_factory is None:
            sdk = sdk or _load_sdk()
        prompt, instructions = _render_messages(request.messages)
        session = _make_session(
            self._config,
            sdk,
            request,
            instructions,
            tools=wrappers,
        )
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


def _apple_tool_wrappers(
    request: OpenAIModelRequest,
    sdk: Any | None,
) -> tuple[object, ...]:
    """Translate the trusted active DAR tool snapshot into Apple SDK wrappers."""

    context = _active_apple_tool_context(request)
    if context is None:
        return ()
    if sdk is None:
        raise ModelExecutionError("Apple Foundation Models SDK is unavailable")
    tool_ids = [tool.id for tool in context.tools]
    if len(set(tool_ids)) != len(tool_ids):
        raise ModelExecutionError("Apple tool bridge has duplicate active tool ids")
    wrappers: list[object] = []
    for index, tool in enumerate(context.tools):
        try:
            context.require_current_tool(tool)
        except ToolRegistryError as exc:
            raise ModelExecutionError(
                "Apple tool bridge active tool context is stale"
            ) from exc
        arguments_type = _apple_generated_object_type(
            _tool_input_schema(tool.definition.raw),
            sdk,
            type_name=f"DarTool{index}Arguments",
        )
        wrappers.append(
            _apple_tool_wrapper(
                sdk,
                tool_id=tool.id,
                name=f"dar_tool_{index}",
                description=_apple_tool_description(tool.definition.raw, tool.id),
                arguments_type=arguments_type,
            )
        )
    return tuple(wrappers)


def _active_apple_tool_context(
    request: OpenAIModelRequest,
) -> ActiveAdapterToolContext | None:
    context = request.adapter_context
    if isinstance(context, ActiveAdapterToolContext) and context.tools:
        return context
    if request.tools:
        raise ModelExecutionError("Apple tool bridge requires an active tool context")
    return None


def _tool_input_schema(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    schema = raw.get("input_schema")
    if schema is None:
        return {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }
    if not isinstance(schema, Mapping):
        raise ModelExecutionError("Apple tool has an untranslatable input schema")
    return schema


def _apple_tool_description(raw: Mapping[str, Any], tool_id: str) -> str:
    value = raw.get("description_for_llm") or raw.get("label") or tool_id
    description = str(value).strip()
    if not description:
        raise ModelExecutionError("Apple tool has an invalid description")
    return description


def _apple_tool_wrapper(
    sdk: Any,
    *,
    tool_id: str,
    name: str,
    description: str,
    arguments_type: type[object],
) -> object:
    """Build one inert SDK wrapper; B3 supplies its DAR callback behavior."""

    async def call(_self: object, _arguments: object) -> str:
        raise ModelExecutionError("Apple tool callbacks are not available until B3")

    def arguments_schema(_self: object) -> object:
        return arguments_type.generation_schema()

    wrapper_type = type(
        f"{arguments_type.__name__}Tool",
        (sdk.Tool,),
        {
            "name": name,
            "description": description,
            "dar_tool_id": tool_id,
            "arguments_schema": property(arguments_schema),
            "call": call,
        },
    )
    return wrapper_type()


def _apple_generated_object_type(
    schema: Mapping[str, Any],
    sdk: Any,
    *,
    type_name: str,
) -> type[object]:
    """Translate an admitted finite object schema into an SDK-generable class."""

    _require_schema_keys(
        schema,
        {"type", "properties", "required", "additionalProperties"},
    )
    if schema.get("type") != "object":
        raise ModelExecutionError("Apple tool has an untranslatable object schema")
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, Mapping) or not isinstance(required, list):
        raise ModelExecutionError("Apple tool has an untranslatable object schema")
    property_names = tuple(properties)
    if (
        not all(
            isinstance(name, str)
            and name.isidentifier()
            and not keyword.iskeyword(name)
            for name in property_names
        )
        or not all(isinstance(name, str) for name in required)
        or set(required) != set(property_names)
        or schema.get("additionalProperties") is not False
    ):
        raise ModelExecutionError("Apple tool has an untranslatable object schema")
    annotations: dict[str, object] = {}
    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, Mapping):
            raise ModelExecutionError("Apple tool has an untranslatable schema")
        annotations[field_name] = _apple_annotation(
            field_schema,
            sdk,
            type_name=f"{type_name}{field_name.title()}",
        )
    generated_type = type(type_name, (), {"__annotations__": annotations})
    try:
        return sdk.generable(f"DAR tool arguments for {type_name}")(generated_type)
    except Exception as exc:  # noqa: BLE001 - SDK construction errors vary.
        raise ModelExecutionError("Apple tool has an untranslatable schema") from exc


def _apple_annotation(schema: Mapping[str, Any], sdk: Any, *, type_name: str) -> object:
    schema_type = schema.get("type")
    if schema_type == "object":
        return _apple_generated_object_type(schema, sdk, type_name=type_name)
    if schema_type == "array":
        return _apple_array_annotation(schema, sdk, type_name=type_name)
    if isinstance(schema_type, str) and schema_type in {
        "string",
        "integer",
        "number",
        "boolean",
    }:
        return _apple_scalar_annotation(schema, sdk)
    raise ModelExecutionError("Apple tool has an untranslatable schema")


def _apple_scalar_annotation(schema: Mapping[str, Any], sdk: Any) -> object:
    schema_type = str(schema["type"])
    allowed = {"type"}
    constraints: dict[str, object] = {}
    if schema_type == "string":
        allowed.add("enum")
        enum = schema.get("enum")
        if enum is not None:
            if (
                not isinstance(enum, list)
                or not enum
                or not all(isinstance(value, str) for value in enum)
            ):
                raise ModelExecutionError("Apple tool has an untranslatable schema")
            constraints["anyOf"] = list(enum)
        annotation: object = str
    elif schema_type in {"integer", "number"}:
        allowed.update({"minimum", "maximum"})
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        for key, value in (("minimum", minimum), ("maximum", maximum)):
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ModelExecutionError("Apple tool has an untranslatable schema")
                constraints[key] = value
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ModelExecutionError("Apple tool has an untranslatable schema")
        annotation = int if schema_type == "integer" else float
    else:
        annotation = bool
    _require_schema_keys(schema, allowed)
    return _guided_annotation(annotation, sdk, constraints)


def _apple_array_annotation(
    schema: Mapping[str, Any], sdk: Any, *, type_name: str
) -> object:
    _require_schema_keys(schema, {"type", "items", "minItems", "maxItems"})
    items = schema.get("items")
    if not isinstance(items, Mapping):
        raise ModelExecutionError("Apple tool has an untranslatable schema")
    constraints: dict[str, object] = {}
    minimum = schema.get("minItems")
    maximum = schema.get("maxItems")
    for key, value in (("minItems", minimum), ("maxItems", maximum)):
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ModelExecutionError("Apple tool has an untranslatable schema")
            constraints[key] = value
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ModelExecutionError("Apple tool has an untranslatable schema")
    item_annotation = _apple_annotation(items, sdk, type_name=f"{type_name}Item")
    return _guided_annotation(list[item_annotation], sdk, constraints)


def _guided_annotation(
    annotation: object,
    sdk: Any,
    constraints: Mapping[str, object],
) -> object:
    if not constraints:
        return annotation
    try:
        return Annotated[annotation, sdk.guide(**dict(constraints))]
    except Exception as exc:  # noqa: BLE001 - SDK guide construction errors vary.
        raise ModelExecutionError("Apple tool has an untranslatable schema") from exc


def _require_schema_keys(schema: Mapping[str, Any], allowed: set[str]) -> None:
    if set(schema) - allowed:
        raise ModelExecutionError("Apple tool has an untranslatable schema")


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
    *,
    tools: Sequence[object] = (),
) -> Any:
    try:
        if config.session_factory is not None:
            if tools:
                raise ModelExecutionError(
                    "Apple Foundation Models tool bridge requires native session setup"
                )
            return config.session_factory(instructions)
        if sdk is None:
            raise ModelExecutionError("Apple Foundation Models SDK is unavailable")
        return sdk.LanguageModelSession(instructions=instructions, tools=list(tools))
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


def _validate_request(
    request: OpenAIModelRequest,
    *,
    tool_bridge_active: bool = False,
) -> None:
    if (request.tools and not tool_bridge_active) or request.tool_choice is not None:
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
