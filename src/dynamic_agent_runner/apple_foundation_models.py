"""Optional in-process adapter for Apple's Foundation Models SDK."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import asyncio
import importlib
import json
import keyword
import secrets
import sys
import warnings
from threading import Lock
from typing import Annotated, Any
from uuid import uuid4

from jsonschema import FormatChecker, SchemaError, ValidationError
from jsonschema.validators import validator_for

from dynamic_agent_runner.errors import (
    GuardrailExecutionError,
    ModelExecutionError,
    ToolRegistryError,
)
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    ModelResponse,
    OpenAIModelRequest,
    normalize_openai_response,
)
from dynamic_agent_runner.registry import (
    PreparedToolInvocation,
    RegisteredTool,
    ToolResult,
)
from dynamic_agent_runner.tool_invocation import (
    ActiveAdapterToolContext,
    ApprovalInterruption,
    ProviderToolDecisionTerminalOutcome,
    ProviderToolInterruption,
    ProviderToolTerminalError,
    ProviderCallbackBudget,
    ToolInvocationRequest,
    coordinate_tool_invocation_async,
)


AvailabilityChecker = Callable[[], tuple[bool, str | None]]
SessionFactory = Callable[[str | None], Any]
_APPLE_CALLBACK_RESULT_MAX_CHARS = 2_048
_APPLE_CALLBACK_RESULT_MAX_STRING_CHARS = 64
_APPLE_CALLBACK_RESULT_MAX_ITEMS = 5
_APPLE_CALLBACK_RESULT_MAX_FIELDS = 4
_APPLE_CALLBACK_RESULT_MAX_DEPTH = 6
_APPLE_CALLBACK_RESULT_PRIORITY_FIELDS = (
    "subject",
    "title",
    "name",
    "summary",
    "id",
)


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


@dataclass(frozen=True)
class AppleToolSchemaPreflight:
    """Redacted Apple-tool schema mode for one current tool definition."""

    mode: str


@dataclass(frozen=True)
class _AppleGatewayTarget:
    """One response-local fallback target retained behind an opaque token."""

    tool: RegisteredTool
    validator: Any


@dataclass(frozen=True)
class _AppleCallbackResultBudget:
    """One active Apple model's safe callback-result token allowance."""

    limit: int
    token_count: Callable[[str], Any]


class _AppleGatewayCapabilities:
    """One-shot gateway targets that disappear with their Apple response."""

    def __init__(self, targets: Mapping[str, _AppleGatewayTarget]) -> None:
        self._targets = dict(targets)
        self._lock = Lock()

    def resolve(
        self,
        token: str,
        *,
        context: ActiveAdapterToolContext,
        callback_session: "_AppleCallbackSessionState",
    ) -> _AppleGatewayTarget:
        """Atomically revalidate and consume one response-local target."""

        with self._lock:
            callback_session.require_active()
            target = self._targets.pop(token, None)
            if target is None:
                raise ToolRegistryError("Apple gateway capability is unavailable")
            context.require_current_tool(target.tool)
            return target

    def clear(self) -> None:
        """Discard every unconsumed target when the response ends."""

        with self._lock:
            self._targets.clear()


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


def preflight_apple_foundation_models(
    config: AppleFoundationModelConfig | None = None,
) -> None:
    """Verify platform, SDK, and system-model availability without a session."""

    _require_macos()
    resolved = config or AppleFoundationModelConfig()
    sdk = _load_sdk() if resolved.availability_checker is None else None
    available, reason = _check_availability(resolved, sdk)
    if not available:
        raise ModelExecutionError(
            f"Apple Foundation Models are unavailable: {reason or 'unknown reason'}"
        )


def preflight_apple_tool_schema(
    schema: Mapping[str, Any], *, sdk: Any | None = None
) -> AppleToolSchemaPreflight:
    """Classify one in-memory schema without creating an Apple session."""

    if not isinstance(schema, Mapping):
        raise ModelExecutionError("Apple tool preflight schema is invalid")
    return AppleToolSchemaPreflight(
        mode=_apple_tool_schema_mode(schema, sdk or _load_sdk())
    )


def _apple_tool_schema_mode(schema: Mapping[str, Any], sdk: Any) -> str:
    """Classify one active schema for direct, gateway, or blocked use."""

    try:
        _apple_generated_object_type(
            schema,
            sdk,
            type_name="DarPreflightArguments",
        )
    except ModelExecutionError:
        if _is_gateway_schema(schema):
            return "gateway"
        return "blocked"
    return "direct"


def _is_gateway_schema(schema: Mapping[str, Any]) -> bool:
    """Return whether jsonschema accepts an otherwise non-direct tool schema."""

    try:
        _gateway_validator(schema)
    except SchemaError:
        return False
    return True


def _gateway_validator(schema: Mapping[str, Any]) -> Any:
    """Build the exact-json-schema validator retained for one gateway target."""

    formats = _gateway_formats(schema)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        validator_type = validator_for(schema)
    declared_dialect = schema.get("$schema")
    if declared_dialect is not None and (
        not isinstance(declared_dialect, str)
        or validator_type.META_SCHEMA.get("$id") != declared_dialect
    ):
        raise SchemaError("gateway schema dialect is unsupported")
    validator_type.check_schema(schema)
    return validator_type(schema, format_checker=FormatChecker(formats=formats))


def _gateway_formats(schema: Mapping[str, Any]) -> frozenset[str]:
    """Reject unresolved resources and unsupported format semantics."""

    formats: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            if any(
                key in value for key in ("$ref", "$dynamicRef", "$recursiveRef", "$id")
            ):
                raise SchemaError("gateway schema references are unsupported")
            format_name = value.get("format")
            if format_name is not None:
                if (
                    not isinstance(format_name, str)
                    or format_name not in FormatChecker.checkers
                ):
                    raise SchemaError("gateway schema format is unsupported")
                formats.add(format_name)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(schema)
    return frozenset(formats)


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
    def execution_profile_adapter_id(self) -> str:
        """Identify the concrete Apple adapter factory for profile admission."""

        return "apple-foundation-models-adapter-v1"

    @property
    def capabilities(self) -> Mapping[str, Any]:
        return {
            "provider": "apple_foundation_models",
            "execution": "in_process",
            "local": True,
            "model_identity": "system_managed",
            "text_generation": True,
            "structured_output": True,
            "streaming": False,
            "tool_calling": True,
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
        callback_session = _AppleCallbackSessionState()
        try:
            callback_result_budget = (
                _apple_callback_result_budget(sdk) if sdk is not None else None
            )
            wrappers = _apple_tool_wrappers(
                request,
                sdk,
                callback_session,
                callback_result_budget=callback_result_budget,
            )
            _validate_request(request, tool_bridge_active=bool(wrappers))
            available, reason = _check_availability(self._config, sdk)
            if not available:
                raise ModelExecutionError(
                    "Apple Foundation Models are unavailable: "
                    f"{reason or 'unknown reason'}"
                )
            if self._config.session_factory is None:
                sdk = sdk or _load_sdk()
            prompt, instructions = _render_messages(request.messages)
            instructions = _append_apple_gateway_instruction(instructions, wrappers)
            session = _make_session(
                self._config,
                sdk,
                request,
                instructions,
                tools=wrappers,
            )
        except BaseException:
            callback_session.close()
            raise
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
        except (
            asyncio.CancelledError,
            ProviderToolInterruption,
            ProviderToolTerminalError,
        ):
            raise
        except Exception as exc:  # noqa: BLE001 - SDK errors vary by release.
            raise ModelExecutionError(
                "Apple Foundation Models generation failed"
            ) from exc
        finally:
            callback_session.close()
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
    callback_session: "_AppleCallbackSessionState",
    *,
    callback_result_budget: _AppleCallbackResultBudget | None = None,
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
    callback_budget = _apple_callback_budget(context)
    wrappers: list[object] = []
    gateway_targets: dict[str, _AppleGatewayTarget] = {}
    for index, tool in enumerate(context.tools):
        try:
            context.require_current_tool(tool)
        except ToolRegistryError as exc:
            raise ModelExecutionError(
                "Apple tool bridge active tool context is stale"
            ) from exc
        schema = _tool_input_schema(tool.definition.raw)
        mode = _apple_tool_schema_mode(schema, sdk)
        if mode == "direct":
            arguments_type = _apple_generated_object_type(
                schema,
                sdk,
                type_name=f"DarTool{index}Arguments",
            )
            wrappers.append(
                _apple_tool_wrapper(
                    sdk,
                    context=context,
                    callback_budget=callback_budget,
                    callback_result_budget=callback_result_budget,
                    callback_session=callback_session,
                    tool_id=tool.id,
                    name=f"dar_tool_{index}",
                    description=_apple_tool_description(tool.definition.raw, tool.id),
                    arguments_type=arguments_type,
                )
            )
            continue
        if mode != "gateway" or not _is_gateway_mcp_tool(tool):
            raise ModelExecutionError("Apple tool has an untranslatable schema")
        gateway_targets[secrets.token_hex(24)] = _AppleGatewayTarget(
            tool=tool,
            validator=_gateway_validator(schema),
        )
    if gateway_targets:
        capabilities = _AppleGatewayCapabilities(gateway_targets)
        callback_session.add_close_callback(capabilities.clear)
        wrappers.append(
            _apple_gateway_wrapper(
                sdk,
                context=context,
                callback_budget=callback_budget,
                callback_result_budget=callback_result_budget,
                callback_session=callback_session,
                capabilities=capabilities,
                description=_apple_gateway_description(gateway_targets),
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


def _is_gateway_mcp_tool(tool: RegisteredTool) -> bool:
    """Limit the A4 fallback to current reviewed read-only MCP bindings."""

    canonical_id = tool.definition.raw.get("host_canonical_id")
    return (
        tool.definition.side_effect == "read"
        and isinstance(canonical_id, str)
        and canonical_id.startswith(("authorized-mcp:", "mcp:"))
    )


def _apple_gateway_description(
    targets: Mapping[str, _AppleGatewayTarget],
) -> str:
    """Return the bounded, opaque capability catalog visible to Apple."""

    entries: list[str] = []
    for token, target in targets.items():
        raw = target.tool.definition.raw
        description = raw.get("description_for_llm") or raw.get("label")
        if not isinstance(description, str) or not description.strip():
            raise ModelExecutionError("Apple gateway tool description is invalid")
        entries.append(f"{token}: {description.strip()}")
    catalog = "Use one opaque tool token for one reviewed capability:\n" + "\n".join(
        entries
    )
    if len(catalog.encode("utf-8")) > 16 * 1024:
        raise ModelExecutionError("Apple gateway capability catalog is too large")
    return catalog


def _append_apple_gateway_instruction(
    instructions: str | None, wrappers: Sequence[object]
) -> str | None:
    """Tell Apple how to select the fixed gateway without exposing MCP schemas."""

    descriptions = tuple(
        description
        for wrapper in wrappers
        if getattr(wrapper, "name", None) == "dar_gateway"
        and isinstance((description := getattr(wrapper, "description", None)), str)
    )
    if not descriptions:
        return instructions
    gateway_instruction = (
        "Call dar_gateway for fallback capabilities; do not call a logical tool name "
        "from the task instructions. Its arguments must contain tool_token and "
        "arguments_json; arguments_json is a JSON object encoded as a string. Use "
        "only the opaque capability token in this catalog:\n" + "\n".join(descriptions)
    )
    return (
        f"{instructions}\n{gateway_instruction}"
        if instructions
        else gateway_instruction
    )


def _apple_tool_wrapper(
    sdk: Any,
    *,
    context: ActiveAdapterToolContext,
    callback_budget: ProviderCallbackBudget,
    callback_result_budget: _AppleCallbackResultBudget | None,
    callback_session: "_AppleCallbackSessionState",
    tool_id: str,
    name: str,
    description: str,
    arguments_type: type[object],
) -> object:
    """Build one SDK wrapper that enters DAR through its coordinator."""

    async def call(_self: object, arguments: object) -> str:
        try:
            action_id = f"apple-{uuid4().hex}"
            callback_session.require_active()
            if not callback_budget.claim():
                await _emit_apple_callback_budget_exhausted(
                    context,
                    tool_id=tool_id,
                    action_id=action_id,
                    callback_budget=callback_budget,
                )
                raise ProviderToolTerminalError(
                    "Apple provider callback budget is exhausted"
                )
            callback_arguments = _apple_callback_arguments(arguments)
            guardrail_runner = _apple_guardrail_runner(context, action_id)
            request = context.request(
                tool_id=tool_id,
                arguments=callback_arguments,
                result_key=f"{context.node.id}.{action_id}",
                action_id=action_id,
                approval_reason=f"Apple tool {tool_id!r} requires approval",
                guardrail_runner=guardrail_runner,
                continuation_guard=callback_session.require_active,
                result_commit_guard=callback_session.result_commit_guard,
                invoke=lambda prepared: _invoke_apple_tool_async(
                    context,
                    tool_id,
                    callback_arguments,
                    prepared,
                ),
            )
            coordinated = await _coordinate_apple_callback_async(context, request)
            if isinstance(coordinated, ApprovalInterruption):
                raise ProviderToolInterruption(
                    coordinated,
                    provider="apple_foundation_models",
                )
            if isinstance(coordinated, ProviderToolDecisionTerminalOutcome):
                raise ProviderToolTerminalError(
                    f"provider tool decision is {coordinated.state.value}"
                )
            if not coordinated.success:
                raise ProviderToolTerminalError(
                    coordinated.error or f"tool {tool_id!r} failed"
                )
            return await _apple_tool_result_output(
                coordinated,
                callback_result_budget=callback_result_budget,
            )
        except (GuardrailExecutionError, ToolRegistryError) as exc:
            raise ProviderToolTerminalError(str(exc)) from exc

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


def _apple_gateway_wrapper(
    sdk: Any,
    *,
    context: ActiveAdapterToolContext,
    callback_budget: ProviderCallbackBudget,
    callback_result_budget: _AppleCallbackResultBudget | None,
    callback_session: "_AppleCallbackSessionState",
    capabilities: _AppleGatewayCapabilities,
    description: str,
) -> object:
    """Build the one fixed-schema Apple gateway wrapper for fallback tools."""

    envelope_type = _apple_generated_object_type(
        {
            "type": "object",
            "properties": {
                "tool_token": {"type": "string"},
                "arguments_json": {"type": "string"},
            },
            "required": ["tool_token", "arguments_json"],
            "additionalProperties": False,
        },
        sdk,
        type_name="DarGatewayArguments",
    )

    async def call(_self: object, arguments: object) -> str:
        try:
            action_id = f"apple-{uuid4().hex}"
            callback_session.require_active()
            if not callback_budget.claim():
                await _emit_apple_callback_budget_exhausted(
                    context,
                    tool_id="dar_gateway",
                    action_id=action_id,
                    callback_budget=callback_budget,
                )
                raise ProviderToolTerminalError(
                    "Apple provider callback budget is exhausted"
                )
            tool_id, callback_arguments = _apple_gateway_callback_arguments(
                arguments,
                capabilities=capabilities,
                context=context,
                callback_session=callback_session,
            )
            guardrail_runner = _apple_guardrail_runner(context, action_id)
            request = context.request(
                tool_id=tool_id,
                arguments=callback_arguments,
                result_key=f"{context.node.id}.{action_id}",
                action_id=action_id,
                approval_reason=f"Apple tool {tool_id!r} requires approval",
                guardrail_runner=guardrail_runner,
                continuation_guard=callback_session.require_active,
                result_commit_guard=callback_session.result_commit_guard,
                invoke=lambda prepared: _invoke_apple_tool_async(
                    context,
                    tool_id,
                    callback_arguments,
                    prepared,
                ),
            )
            coordinated = await _coordinate_apple_callback_async(context, request)
            if isinstance(coordinated, ApprovalInterruption):
                raise ProviderToolInterruption(
                    coordinated,
                    provider="apple_foundation_models",
                )
            if isinstance(coordinated, ProviderToolDecisionTerminalOutcome):
                raise ProviderToolTerminalError(
                    f"provider tool decision is {coordinated.state.value}"
                )
            if not coordinated.success:
                raise ProviderToolTerminalError(
                    coordinated.error or f"tool {tool_id!r} failed"
                )
            return await _apple_tool_result_output(
                coordinated,
                callback_result_budget=callback_result_budget,
            )
        except (GuardrailExecutionError, ToolRegistryError) as exc:
            raise ProviderToolTerminalError(str(exc)) from exc

    def arguments_schema(_self: object) -> object:
        return envelope_type.generation_schema()

    wrapper_type = type(
        "DarGatewayTool",
        (sdk.Tool,),
        {
            "name": "dar_gateway",
            "description": description,
            "arguments_schema": property(arguments_schema),
            "call": call,
        },
    )
    return wrapper_type()


class _AppleCallbackSessionState:
    """Thread-safe liveness guard for callbacks owned by one Apple response."""

    def __init__(self) -> None:
        self._active = True
        self._lock = Lock()
        self._close_callbacks: list[Callable[[], None]] = []

    def add_close_callback(self, callback: Callable[[], None]) -> None:
        """Register response-local cleanup before Apple session construction."""

        with self._lock:
            if not self._active:
                callback()
                return
            self._close_callbacks.append(callback)

    def close(self) -> None:
        """Prevent any later callback from entering or completing DAR work."""

        with self._lock:
            self._active = False
            callbacks = tuple(self._close_callbacks)
            self._close_callbacks.clear()
        for callback in callbacks:
            callback()

    def require_active(self) -> None:
        """Fail closed once the owning Apple response has completed or cancelled."""

        with self._lock:
            if not self._active:
                raise ToolRegistryError("Apple callback session is no longer active")

    @contextmanager
    def result_commit_guard(self):
        """Keep closure from racing DAR's result-state and trace finalization."""

        with self._lock:
            if not self._active:
                raise ToolRegistryError("Apple callback session is no longer active")
            yield


def _apple_callback_budget(context: ActiveAdapterToolContext) -> ProviderCallbackBudget:
    """Create one callback budget for one Apple provider session."""

    limit = getattr(context.plan, "max_steps", None) or 8
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ModelExecutionError("Apple callback tool-call limit is invalid")
    return ProviderCallbackBudget(limit=limit)


def _apple_callback_result_budget(sdk: Any) -> _AppleCallbackResultBudget | None:
    """Reserve three quarters of the active model context for the session itself."""

    try:
        model = sdk.SystemLanguageModel()
        context_size = model.context_size
        token_count = model.token_count
    except Exception:  # noqa: BLE001 - older SDKs expose neither API consistently.
        return None
    if (
        not isinstance(context_size, int)
        or isinstance(context_size, bool)
        or context_size < 4
        or not callable(token_count)
    ):
        return None
    return _AppleCallbackResultBudget(limit=context_size // 4, token_count=token_count)


async def _emit_apple_callback_budget_exhausted(
    context: ActiveAdapterToolContext,
    *,
    tool_id: str,
    action_id: str,
    callback_budget: ProviderCallbackBudget,
) -> None:
    """Record callback exhaustion on DAR's executor loop without arguments."""

    async def emit() -> None:
        context.tracer.emit(
            "provider_callback_budget_exhausted",
            node_id=str(context.node.id),
            payload={
                "tool_id": tool_id,
                "tool_call_id": action_id,
                "limit": callback_budget.limit,
                "claimed": callback_budget.claimed,
            },
        )

    executor_loop = context.executor_loop
    if executor_loop is None or executor_loop is asyncio.get_running_loop():
        await emit()
        return
    if not executor_loop.is_running():
        raise ProviderToolTerminalError(
            "executor loop is unavailable for Apple callback"
        )
    future = asyncio.run_coroutine_threadsafe(emit(), executor_loop)
    await asyncio.wrap_future(future)


async def _coordinate_apple_callback_async(
    context: ActiveAdapterToolContext,
    request: ToolInvocationRequest,
) -> ToolResult | ApprovalInterruption | ProviderToolDecisionTerminalOutcome:
    """Run one Apple callback on the executor loop when it differs from Apple's."""

    executor_loop = context.executor_loop
    if executor_loop is None or executor_loop is asyncio.get_running_loop():
        return await coordinate_tool_invocation_async(request)
    if not executor_loop.is_running():
        raise ProviderToolTerminalError(
            "executor loop is unavailable for Apple callback"
        )
    future = asyncio.run_coroutine_threadsafe(
        coordinate_tool_invocation_async(request), executor_loop
    )
    return await asyncio.wrap_future(future)


def _apple_guardrail_runner(
    context: ActiveAdapterToolContext,
    action_id: str,
) -> Callable[[PreparedToolInvocation], None] | None:
    """Bind DAR's active guardrail runner to one Apple callback action."""

    if context.provider_guardrail_runner is None:
        return None

    def run(prepared: PreparedToolInvocation) -> None:
        context.provider_guardrail_runner(prepared, action_id)

    return run


def _apple_callback_arguments(arguments: object) -> dict[str, Any]:
    try:
        value = arguments.to_json()
    except Exception as exc:  # noqa: BLE001 - SDK content objects vary by release.
        raise ToolRegistryError("Apple tool callback arguments are invalid") from exc
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ToolRegistryError("Apple tool callback arguments are invalid") from exc
    if not isinstance(parsed, Mapping):
        raise ToolRegistryError("Apple tool callback arguments must be an object")
    return _canonicalize_apple_provenance_envelope(dict(parsed))


def _apple_gateway_callback_arguments(
    arguments: object,
    *,
    capabilities: _AppleGatewayCapabilities,
    context: ActiveAdapterToolContext,
    callback_session: _AppleCallbackSessionState,
) -> tuple[str, dict[str, Any]]:
    """Resolve and validate one strict gateway callback before coordinator entry."""

    envelope = _apple_gateway_json_object(arguments)
    if set(envelope) != {"tool_token", "arguments_json"}:
        raise ToolRegistryError("Apple gateway envelope is invalid")
    token = envelope["tool_token"]
    arguments_json = envelope["arguments_json"]
    if not isinstance(token, str) or not isinstance(arguments_json, str):
        raise ToolRegistryError("Apple gateway envelope is invalid")
    target = capabilities.resolve(
        token,
        context=context,
        callback_session=callback_session,
    )
    decoded = _apple_gateway_json_object(arguments_json, bounded=True)
    try:
        target.validator.validate(decoded)
    except ValidationError as exc:
        raise ToolRegistryError("Apple gateway arguments are invalid") from exc
    return target.tool.id, _canonicalize_apple_provenance_envelope(decoded)


def _canonicalize_apple_provenance_envelope(
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Normalize Apple JSON transport without relaxing provenance verification."""

    serialized = arguments.get("provenance_envelope")
    if not isinstance(serialized, str):
        return arguments
    try:
        envelope = json.loads(
            serialized,
            object_pairs_hook=_apple_gateway_object_pairs,
            parse_constant=_reject_apple_gateway_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError, RecursionError):
        return arguments
    if not isinstance(envelope, dict):
        return arguments
    normalized = dict(arguments)
    normalized["provenance_envelope"] = json.dumps(
        envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return normalized


def _apple_gateway_json_object(
    value: object,
    *,
    bounded: bool = False,
) -> dict[str, Any]:
    """Decode JSON without duplicate or non-finite values."""

    text = _apple_gateway_json_text(value)
    if bounded and len(_apple_gateway_utf8(text)) > 16 * 1024:
        raise ToolRegistryError("Apple gateway arguments are too large")
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_apple_gateway_object_pairs,
            parse_constant=_reject_apple_gateway_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError, RecursionError) as exc:
        raise ToolRegistryError("Apple gateway arguments are invalid") from exc
    if not isinstance(parsed, dict):
        raise ToolRegistryError("Apple gateway arguments must be an object")
    if bounded and (_json_depth(parsed) > 16 or _json_object_keys(parsed) > 64):
        raise ToolRegistryError("Apple gateway arguments exceed limits")
    return parsed


def _apple_gateway_json_text(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        text = value.to_json()
    except Exception as exc:  # noqa: BLE001 - SDK content objects vary by release.
        raise ToolRegistryError("Apple gateway arguments are invalid") from exc
    if not isinstance(text, str):
        raise ToolRegistryError("Apple gateway arguments are invalid")
    return text


def _apple_gateway_utf8(value: str) -> bytes:
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ToolRegistryError("Apple gateway arguments are invalid") from exc


def _apple_gateway_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = item
    return result


def _reject_apple_gateway_constant(_value: str) -> None:
    raise ValueError("non-finite value")


def _json_depth(value: object) -> int:
    if isinstance(value, dict):
        return 1 + max((_json_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_json_depth(item) for item in value), default=0)
    return 0


def _json_object_keys(value: object) -> int:
    if isinstance(value, dict):
        return len(value) + sum(_json_object_keys(item) for item in value.values())
    if isinstance(value, list):
        return sum(_json_object_keys(item) for item in value)
    return 0


async def _invoke_apple_tool_async(
    context: ActiveAdapterToolContext,
    tool_id: str,
    arguments: Mapping[str, Any],
    prepared: PreparedToolInvocation | None,
) -> ToolResult:
    if prepared is not None:
        return await context.registry.invoke_prepared_tool_async(prepared)
    return await context.registry.invoke_tool_async(tool_id, arguments)


async def _apple_tool_result_output(
    result: ToolResult,
    *,
    callback_result_budget: _AppleCallbackResultBudget | None = None,
) -> str:
    try:
        serialized = json.dumps(result.model_facing_output)
    except (TypeError, ValueError) as exc:
        raise ProviderToolTerminalError(
            "Apple tool result is not JSON serializable"
        ) from exc
    if await _apple_callback_result_fits(serialized, callback_result_budget):
        return serialized
    bounded = {
        "truncated": True,
        "result": _bounded_apple_callback_result(json.loads(serialized)),
    }
    serialized = json.dumps(bounded, separators=(",", ":"))
    if await _apple_callback_result_fits(serialized, callback_result_budget):
        return serialized
    return json.dumps(
        {
            "truncated": True,
            "result": "Tool result exceeds the Apple callback result limit.",
        },
        separators=(",", ":"),
    )


async def _apple_callback_result_fits(
    serialized: str,
    callback_result_budget: _AppleCallbackResultBudget | None,
) -> bool:
    """Use native token counting when available, with a stable fallback."""

    if callback_result_budget is None:
        return len(serialized) <= _APPLE_CALLBACK_RESULT_MAX_CHARS
    try:
        token_count = await callback_result_budget.token_count(serialized)
    except Exception:  # noqa: BLE001 - token counting is an optional SDK feature.
        return len(serialized) <= _APPLE_CALLBACK_RESULT_MAX_CHARS
    if (
        not isinstance(token_count, int)
        or isinstance(token_count, bool)
        or token_count < 0
    ):
        return len(serialized) <= _APPLE_CALLBACK_RESULT_MAX_CHARS
    return token_count <= callback_result_budget.limit


def _bounded_apple_callback_result(value: Any, *, depth: int = 0) -> Any:
    """Return a compact JSON-safe result for Apple's bounded callback context."""

    if depth >= _APPLE_CALLBACK_RESULT_MAX_DEPTH:
        return "[truncated]"
    if isinstance(value, Mapping):
        if "structuredContent" in value:
            fields = [("structuredContent", value["structuredContent"])]
        else:
            priorities = {
                field_name: index
                for index, field_name in enumerate(
                    _APPLE_CALLBACK_RESULT_PRIORITY_FIELDS
                )
            }
            fields = sorted(
                value.items(),
                key=lambda item: priorities.get(str(item[0]).lower(), len(priorities)),
            )[:_APPLE_CALLBACK_RESULT_MAX_FIELDS]
        return {
            str(key): _bounded_apple_callback_result(item, depth=depth + 1)
            for key, item in fields
        }
    if isinstance(value, list):
        return [
            _bounded_apple_callback_result(item, depth=depth + 1)
            for item in value[:_APPLE_CALLBACK_RESULT_MAX_ITEMS]
        ]
    if isinstance(value, str) and len(value) > _APPLE_CALLBACK_RESULT_MAX_STRING_CHARS:
        return value[:_APPLE_CALLBACK_RESULT_MAX_STRING_CHARS] + "…"
    return value


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
