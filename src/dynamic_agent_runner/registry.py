"""Repository-owned tool registry for dynamic-agent workflow execution."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, get_args, get_origin, get_type_hints
from urllib.parse import urlparse

from dynamic_agent_runner.errors import ToolRegistryError
from dynamic_agent_runner.models import (
    RuntimeManifest,
    RuntimeNode,
    ToolDefinition,
    ToolOriginKind,
    ToolExposure,
    ToolSource,
    ToolSourceKind,
)
from dynamic_agent_runner.token_budget import estimate_text_tokens

ToolHandler = Callable[[Mapping[str, Any]], Any]

_EMPTY_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}


class ToolRegistry(Protocol):
    """Protocol for caller-provided and built-in tool registries."""

    def get_tool(self, tool_id: str) -> RegisteredTool:
        """Return a registered tool by id or raise ``ToolRegistryError``."""

    def list_tools_for_node(self, node: RuntimeNode) -> tuple[RegisteredTool, ...]:
        """Return tools exposed to an LLM node."""

    def to_openai_tools(
        self,
        tool_ids: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Convert registered tools to OpenAI tool schema entries."""

    def invoke_tool(
        self,
        tool_id: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> ToolResult:
        """Invoke a registered tool and return a structured result."""

    async def invoke_tool_async(
        self,
        tool_id: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> ToolResult:
        """Invoke a registered tool through the async dispatch path."""

    def prepare_tool_invocation(
        self,
        tool_id: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> PreparedToolInvocation:
        """Prepare a registered tool invocation without calling its handler."""

    async def invoke_prepared_tool_async(
        self,
        prepared: PreparedToolInvocation,
    ) -> ToolResult:
        """Invoke one registry-prepared tool invocation."""


@dataclass(frozen=True)
class ToolResult:
    """Structured result returned by tool invocation."""

    tool_id: str
    success: bool
    output: Any = None
    error: str | None = None
    model_output: Any | None = None
    raw_output: Any | None = None
    log_preview: str | None = None
    event_payload: Mapping[str, Any] | None = None
    sensitive_fields: tuple[str, ...] = ()

    @property
    def model_facing_output(self) -> Any:
        """Return the output intended for prompts and state references."""

        return self.output if self.model_output is None else self.model_output

    def trace_payload(self) -> dict[str, Any]:
        """Return the structured payload emitted for tool-result trace events."""

        payload: dict[str, Any] = {
            "tool_id": self.tool_id,
            "success": self.success,
            "error": self.error,
            "output": self.model_facing_output,
        }
        if self.raw_output is not None:
            payload["raw_output"] = self.raw_output
        if self.log_preview is not None:
            payload["log_preview"] = self.log_preview
        if self.event_payload is not None:
            payload["event_payload"] = dict(self.event_payload)
        return payload


@dataclass(frozen=True)
class RegisteredTool:
    """Runtime-callable tool adapter plus its metadata definition."""

    definition: ToolDefinition
    handler: ToolHandler
    handler_is_async: bool = field(init=False)

    def __post_init__(self) -> None:
        """Record handler callable shape at construction time."""

        object.__setattr__(
            self,
            "handler_is_async",
            inspect.iscoroutinefunction(self.handler),
        )

    @property
    def id(self) -> str:
        """Return the non-empty tool id."""

        if not self.definition.id:
            raise ToolRegistryError("registered tool definition is missing id")
        return self.definition.id


@dataclass(frozen=True)
class PreparedToolInvocation:
    """Registry-owned resolved tool and normalized input for one invocation."""

    tool: RegisteredTool
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class ToolDescriptorBudgetPolicy:
    """Opt-in policy for selecting model-facing tool descriptors."""

    enabled: bool = False
    max_tokens: int | None = None
    max_tools: int | None = None
    model: str | None = None
    strategy: str = "deterministic_metadata"
    low_confidence_behavior: str = "include_all_within_budget"
    required_tools: tuple[str, ...] = ()
    diagnostics: str = "redacted"


@dataclass(frozen=True)
class ToolDescriptorBudgetDiagnosticItem:
    """Trace-safe diagnostic for one selected or omitted descriptor."""

    tool_id: str
    reason: str
    token_count: int
    score: int

    def to_payload(self) -> dict[str, Any]:
        """Return a redacted trace payload for this descriptor."""

        return {
            "tool_id": self.tool_id,
            "reason": self.reason,
            "token_count": self.token_count,
            "score": self.score,
        }


@dataclass(frozen=True)
class ToolDescriptorBudgetDiagnostics:
    """Trace-safe descriptor budgeting result metadata."""

    selected_tool_ids: tuple[str, ...]
    included: tuple[ToolDescriptorBudgetDiagnosticItem, ...]
    omitted: tuple[ToolDescriptorBudgetDiagnosticItem, ...]
    estimated_tokens: int
    max_tokens: int | None
    max_tools: int | None
    strategy: str
    encoding_name: str | None = None
    used_fallback_encoding: bool = False

    def to_trace_payload(self) -> dict[str, Any]:
        """Return redacted diagnostics for workflow traces."""

        return {
            "selected_tool_ids": list(self.selected_tool_ids),
            "included": [item.to_payload() for item in self.included],
            "omitted": [item.to_payload() for item in self.omitted],
            "estimated_tokens": self.estimated_tokens,
            "max_tokens": self.max_tokens,
            "max_tools": self.max_tools,
            "strategy": self.strategy,
            "encoding_name": self.encoding_name,
            "used_fallback_encoding": self.used_fallback_encoding,
        }


@dataclass(frozen=True)
class ToolSelectionResult:
    """Selected OpenAI-compatible tool descriptors and diagnostics."""

    tools: list[dict[str, Any]]
    diagnostics: ToolDescriptorBudgetDiagnostics


@dataclass(frozen=True)
class _ToolCandidate:
    tool: RegisteredTool
    schema: dict[str, Any]
    token_count: int
    score: int
    order: int
    encoding_name: str
    used_fallback_encoding: bool


class ToolSelector:
    """Select and pack model-facing tool descriptors within a policy budget."""

    def select(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[RegisteredTool],
        policy: ToolDescriptorBudgetPolicy,
        model: str,
    ) -> ToolSelectionResult:
        """Return selected descriptor schemas and redacted diagnostics."""

        effective_model = policy.model or model
        required_ids = set(policy.required_tools)
        exposed_by_id = {tool.id: tool for tool in tools}
        missing = sorted(
            tool_id for tool_id in required_ids if tool_id not in exposed_by_id
        )
        if missing:
            raise ToolRegistryError(f"required tool {missing[0]!r} is not exposed")

        prompt_terms = _normalized_terms(_messages_text(messages))
        candidates = [
            self._candidate(tool, index, prompt_terms, effective_model)
            for index, tool in enumerate(tools)
        ]
        candidates_by_id = {candidate.tool.id: candidate for candidate in candidates}

        selected: list[_ToolCandidate] = []
        omitted: list[ToolDescriptorBudgetDiagnosticItem] = []
        used_tokens = 0
        encoding_name: str | None = None
        used_fallback_encoding = False

        for candidate in sorted(
            (candidates_by_id[tool_id] for tool_id in required_ids),
            key=lambda item: item.order,
        ):
            if policy.max_tokens is not None and (
                used_tokens + candidate.token_count > policy.max_tokens
            ):
                raise ToolRegistryError(
                    f"required tool {candidate.tool.id!r} cannot fit descriptor budget"
                )
            selected.append(candidate)
            used_tokens += candidate.token_count
            encoding_name = encoding_name or candidate.encoding_name
            used_fallback_encoding = (
                used_fallback_encoding or candidate.used_fallback_encoding
            )

        remaining = [
            candidate
            for candidate in candidates
            if candidate.tool.id not in required_ids
        ]
        remaining.sort(key=lambda item: (-item.score, item.order))

        for candidate in remaining:
            if policy.max_tools is not None and len(selected) >= policy.max_tools:
                omitted.append(_diagnostic_item(candidate, "max_tools"))
                continue
            if policy.max_tokens is not None and (
                used_tokens + candidate.token_count > policy.max_tokens
            ):
                omitted.append(_diagnostic_item(candidate, "over_budget"))
                continue
            selected.append(candidate)
            used_tokens += candidate.token_count
            encoding_name = encoding_name or candidate.encoding_name
            used_fallback_encoding = (
                used_fallback_encoding or candidate.used_fallback_encoding
            )

        included = tuple(
            _diagnostic_item(candidate, "selected") for candidate in selected
        )
        diagnostics = ToolDescriptorBudgetDiagnostics(
            selected_tool_ids=tuple(candidate.tool.id for candidate in selected),
            included=included,
            omitted=tuple(omitted),
            estimated_tokens=used_tokens,
            max_tokens=policy.max_tokens,
            max_tools=policy.max_tools,
            strategy=policy.strategy,
            encoding_name=encoding_name,
            used_fallback_encoding=used_fallback_encoding,
        )
        return ToolSelectionResult(
            tools=[candidate.schema for candidate in selected],
            diagnostics=diagnostics,
        )

    def _candidate(
        self,
        tool: RegisteredTool,
        order: int,
        prompt_terms: set[str],
        model: str,
    ) -> _ToolCandidate:
        schema = openai_tool_schema(tool.definition)
        estimate = estimate_text_tokens(
            json.dumps(schema, sort_keys=True, separators=(",", ":")),
            model=model,
        )
        return _ToolCandidate(
            tool=tool,
            schema=schema,
            token_count=estimate.token_count,
            score=_tool_score(tool.definition, prompt_terms),
            order=order,
            encoding_name=estimate.encoding_name,
            used_fallback_encoding=estimate.used_fallback_encoding,
        )


def tool_descriptor_budget_policy_from_values(
    runtime_value: Any,
    node_value: Any = None,
) -> ToolDescriptorBudgetPolicy:
    """Parse runtime and node-local descriptor budgeting metadata."""

    runtime_policy = _policy_mapping(runtime_value)
    node_policy = _policy_mapping(node_value)
    if runtime_policy is None and node_policy is None:
        return ToolDescriptorBudgetPolicy()

    merged: dict[str, Any] = {}
    if runtime_policy is not None:
        merged.update(runtime_policy)
    if node_policy is not None:
        for key, value in node_policy.items():
            if key == "required_tools":
                continue
            merged[key] = value
    required_tools = _dedupe(
        [
            *_string_sequence(
                runtime_policy.get("required_tools") if runtime_policy else None
            ),
            *_string_sequence(
                node_policy.get("required_tools") if node_policy else None
            ),
        ]
    )
    if runtime_policy is None and node_policy is not None:
        enabled = True
    else:
        enabled = bool(merged.get("enabled", False))
    return ToolDescriptorBudgetPolicy(
        enabled=enabled,
        max_tokens=_optional_positive_int(merged.get("max_tokens")),
        max_tools=_optional_positive_int(merged.get("max_tools")),
        model=str(merged["model"]) if merged.get("model") is not None else None,
        strategy=str(merged.get("strategy") or "deterministic_metadata"),
        low_confidence_behavior=str(
            merged.get("low_confidence_behavior") or "include_all_within_budget"
        ),
        required_tools=required_tools,
        diagnostics=str(merged.get("diagnostics") or "redacted"),
    )


@dataclass(frozen=True)
class ToolExposureOverride:
    """Per-node tool exposure changes layered over manifest references."""

    add: tuple[str, ...] = ()
    remove: tuple[str, ...] = ()
    only: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ToolRegistryOverrides:
    """Runtime tool override bundle for registry preparation."""

    added_tools: tuple[RegisteredTool, ...] = ()
    replacement_tools: tuple[RegisteredTool, ...] = ()
    disabled_tools: tuple[str, ...] = ()
    node_overrides: Mapping[str, ToolExposureOverride] = field(default_factory=dict)


@dataclass(frozen=True)
class WebToolPolicy:
    """Policy for the opt-in built-in web tool pack."""

    allowed_schemes: tuple[str, ...] = ("https",)
    allowed_domains: tuple[str, ...] = ()
    max_search_results: int = 10
    max_fetch_chars: int = 4000


@dataclass(frozen=True)
class WorkspaceDataToolPolicy:
    """Policy for the opt-in built-in workspace_data tool pack."""

    max_item_bytes: int = 128_000
    default_search_limit: int = 20
    require_delete_approval: bool = True


class InMemoryToolRegistry:
    """Simple registry implementation for tests and direct callers."""

    def __init__(
        self,
        tools: Iterable[RegisteredTool] | None = None,
        *,
        node_overrides: Mapping[str, ToolExposureOverride] | None = None,
        disabled_tools: Iterable[str] | None = None,
    ) -> None:
        self._lock = RLock()
        self._tools: dict[str, RegisteredTool] = {}
        self._node_overrides = dict(node_overrides or {})
        self._disabled_tools = set(disabled_tools or ())
        for tool in tools or ():
            self.register(tool)

    def register(self, tool: RegisteredTool, *, replace: bool = False) -> None:
        """Register a callable tool."""

        tool_id = tool.id
        with self._lock:
            if tool_id in self._tools and not replace:
                raise ToolRegistryError(f"tool {tool_id!r} is already registered")
            self._tools[tool_id] = _tool_with_default_source(tool)

    def with_overrides(
        self,
        overrides: ToolRegistryOverrides,
        *,
        manifest: RuntimeManifest | None = None,
    ) -> InMemoryToolRegistry:
        """Return a new registry with runtime overrides applied."""

        with self._lock:
            validate_tool_overrides(overrides, self, manifest=manifest)
            tools = dict(self._tools)
            for tool in overrides.added_tools:
                if tool.id in tools:
                    raise ToolRegistryError(f"added tool {tool.id!r} already exists")
                tools[tool.id] = _tool_with_source(
                    tool,
                    ToolSource(
                        kind=ToolSourceKind.RUNTIME_OVERRIDE,
                        origin=ToolOriginKind.OVERRIDE,
                        source_id="added",
                        detail="tool_registry_overrides",
                    ),
                )
            for tool in overrides.replacement_tools:
                if tool.id not in tools:
                    raise ToolRegistryError(
                        f"replacement tool {tool.id!r} does not exist"
                    )
                tools[tool.id] = _tool_with_source(
                    tool,
                    ToolSource(
                        kind=ToolSourceKind.RUNTIME_OVERRIDE,
                        origin=ToolOriginKind.OVERRIDE,
                        source_id="replacement",
                        detail="tool_registry_overrides",
                    ),
                )
            disabled = self._disabled_tools | set(overrides.disabled_tools)
            node_overrides = {**self._node_overrides, **overrides.node_overrides}
        return InMemoryToolRegistry(
            tools.values(),
            node_overrides=node_overrides,
            disabled_tools=disabled,
        )

    def has_tool(self, tool_id: str) -> bool:
        """Return whether a callable, non-disabled tool exists."""

        with self._lock:
            return tool_id in self._tools and tool_id not in self._disabled_tools

    def get_tool(self, tool_id: str) -> RegisteredTool:
        """Return a registered tool by id."""

        with self._lock:
            if tool_id in self._disabled_tools:
                raise ToolRegistryError(f"tool {tool_id!r} is disabled")
            try:
                return self._tools[tool_id]
            except KeyError as exc:
                raise ToolRegistryError(f"tool {tool_id!r} is not registered") from exc

    def list_tools_for_node(self, node: RuntimeNode) -> tuple[RegisteredTool, ...]:
        """Return callable tools exposed to an LLM node."""

        if node.kind != "llm_step":
            raise ToolRegistryError(
                f"tool exposure is only defined for llm_step nodes, got {node.kind!r}"
            )
        tool_ids = list(node.available_tools)
        if node.id in self._node_overrides:
            override = self._node_overrides[node.id]
            tool_ids = list(override.only) if override.only is not None else tool_ids
            tool_ids.extend(override.add)
            remove = set(override.remove)
            tool_ids = [tool_id for tool_id in tool_ids if tool_id not in remove]
        return tuple(
            tool
            for tool in (self.get_tool(tool_id) for tool_id in _dedupe(tool_ids))
            if _is_model_exposable(tool.definition)
        )

    def to_openai_tools(
        self,
        tool_ids: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Convert registered tools to OpenAI function tool schema entries."""

        if tool_ids is None:
            with self._lock:
                selected_ids = tuple(
                    tool_id
                    for tool_id, tool in self._tools.items()
                    if _is_model_exposable(tool.definition)
                )
        else:
            selected_ids = tuple(tool_ids)
        return [
            openai_tool_schema(self.get_tool(tool_id).definition)
            for tool_id in selected_ids
        ]

    def invoke_tool(
        self,
        tool_id: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> ToolResult:
        """Invoke a registered tool with simple input validation."""

        try:
            prepared = self.prepare_tool_invocation(tool_id, arguments)
            return self._invoke_prepared_tool(prepared)
        except Exception as exc:  # noqa: BLE001 - convert all tool failures.
            return ToolResult(tool_id=tool_id, success=False, error=str(exc))

    async def invoke_tool_async(
        self,
        tool_id: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> ToolResult:
        """Invoke a registered tool without blocking the event loop."""

        try:
            prepared = self.prepare_tool_invocation(tool_id, arguments)
            return await self.invoke_prepared_tool_async(prepared)
        except Exception as exc:  # noqa: BLE001 - convert all tool failures.
            return ToolResult(tool_id=tool_id, success=False, error=str(exc))

    def prepare_tool_invocation(
        self,
        tool_id: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> PreparedToolInvocation:
        """Resolve and validate a tool invocation without calling its handler."""

        args = dict(arguments or {})
        tool = self.get_tool(tool_id)
        _validate_input_schema(tool.definition, args)
        return PreparedToolInvocation(tool=tool, arguments=args)

    async def invoke_prepared_tool_async(
        self,
        prepared: PreparedToolInvocation,
    ) -> ToolResult:
        """Invoke one prepared tool while preserving direct-callability checks."""

        try:
            _require_direct_callable(prepared.tool.definition)
            if prepared.tool.handler_is_async:
                output = await prepared.tool.handler(prepared.arguments)
            else:
                output = await asyncio.to_thread(
                    prepared.tool.handler, prepared.arguments
                )
        except Exception as exc:  # noqa: BLE001 - convert all tool failures.
            return ToolResult(
                tool_id=prepared.tool.id,
                success=False,
                error=str(exc),
            )
        return _tool_result_from_output(prepared.tool.id, output)

    def _invoke_prepared_tool(self, prepared: PreparedToolInvocation) -> ToolResult:
        _require_direct_callable(prepared.tool.definition)
        if prepared.tool.handler_is_async:
            output = _run_async_tool_handler_from_sync(
                prepared.tool.handler,
                prepared.arguments,
            )
        else:
            output = prepared.tool.handler(prepared.arguments)
        return _tool_result_from_output(prepared.tool.id, output)

    def _prepare_tool_invocation(
        self,
        tool_id: str,
        arguments: Mapping[str, Any] | None,
    ) -> tuple[RegisteredTool, dict[str, Any]]:
        prepared = self.prepare_tool_invocation(tool_id, arguments)
        _require_direct_callable(prepared.tool.definition)
        return prepared.tool, dict(prepared.arguments)


def tool_from_function(
    function: Callable[..., Any],
    *,
    metadata: Mapping[str, Any] | None = None,
    source: ToolSource | None = None,
) -> RegisteredTool:
    """Build a registered tool from a Python callable.

    Explicit metadata wins when provided. Missing or incomplete metadata falls
    back to conservative inference from the callable name, docstring, and
    signature.
    """

    raw_metadata = dict(metadata or {})
    inferred = _infer_tool_metadata(function)
    merged = _merge_tool_metadata(inferred, raw_metadata)
    definition = ToolDefinition.from_mapping(merged)
    if source is not None:
        definition = replace(definition, source=source)
    return RegisteredTool(definition, _mapping_handler_for_function(function))


def _run_async_tool_handler_from_sync(
    handler: ToolHandler,
    args: Mapping[str, Any],
) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(handler(args))
    raise ToolRegistryError(
        "cannot invoke async tool handler from synchronous registry path while an "
        "event loop is running; use invoke_tool_async(...) instead"
    )


def _tool_result_from_output(tool_id: str, output: Any) -> ToolResult:
    if isinstance(output, ToolResult):
        return output
    return ToolResult(tool_id=tool_id, success=True, output=output)


def _mapping_handler_for_function(function: Callable[..., Any]) -> ToolHandler:
    signature = inspect.signature(function)
    parameters = tuple(signature.parameters.values())
    _validate_function_signature(function, parameters)

    def handler(arguments: Mapping[str, Any]) -> Any:
        kwargs = {
            parameter.name: arguments[parameter.name]
            for parameter in parameters
            if parameter.name in arguments
        }
        return function(**kwargs)

    return handler


def _infer_tool_metadata(function: Callable[..., Any]) -> dict[str, Any]:
    signature = inspect.signature(function)
    parameters = tuple(signature.parameters.values())
    _validate_function_signature(function, parameters)
    tool_id = _inferred_tool_id(function)
    return {
        "id": tool_id,
        "label": tool_id.replace("_", " ").title(),
        "description_for_llm": _inferred_tool_description(function, tool_id),
        "input_schema": _infer_input_schema(function, parameters),
    }


def _validate_function_signature(
    function: Callable[..., Any],
    parameters: Sequence[inspect.Parameter],
) -> None:
    unsupported = [
        parameter.name
        for parameter in parameters
        if parameter.kind
        not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    ]
    if unsupported:
        raise ToolRegistryError(
            "tool_from_function(...) only supports positional-or-keyword and "
            "keyword-only parameters; unsupported parameters: "
            + ", ".join(repr(name) for name in unsupported)
        )
    if not callable(function):
        raise ToolRegistryError("tool_from_function(...) requires a callable")


def _inferred_tool_id(function: Callable[..., Any]) -> str:
    raw_name = getattr(function, "__name__", None)
    if raw_name and raw_name != "<lambda>":
        return str(raw_name)
    raise ToolRegistryError(
        "tool_from_function(...) could not infer a stable tool id; provide "
        "metadata['id'] for lambdas or anonymous callables"
    )


def _inferred_tool_description(function: Callable[..., Any], tool_id: str) -> str:
    doc = inspect.getdoc(function)
    if doc:
        return doc.strip().splitlines()[0]
    return f"Use {tool_id}"


def _infer_input_schema(
    function: Callable[..., Any],
    parameters: Sequence[inspect.Parameter],
) -> dict[str, Any]:
    type_hints = get_type_hints(function)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in parameters:
        annotation = type_hints.get(parameter.name, parameter.annotation)
        properties[parameter.name] = _schema_for_annotation(annotation)
        if parameter.default is inspect._empty:
            required.append(parameter.name)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _schema_for_annotation(annotation: Any) -> dict[str, Any]:
    if annotation is inspect._empty:
        return {}
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is None:
        return _schema_for_simple_annotation(annotation)
    if origin in (list, tuple, Sequence):
        item_schema = _schema_for_annotation(args[0]) if args else {}
        return {"type": "array", "items": item_schema}
    if origin in (dict, Mapping):
        return {"type": "object"}
    if origin is Callable:
        return {}
    if str(origin) in {"typing.Union", "types.UnionType"}:
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) == 1:
            return _schema_for_annotation(non_none[0])
        return {}
    return {}


def _schema_for_simple_annotation(annotation: Any) -> dict[str, Any]:
    mapping = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        dict: {"type": "object"},
        list: {"type": "array"},
    }
    return dict(mapping.get(annotation, {}))


def _merge_tool_metadata(
    inferred: Mapping[str, Any],
    explicit: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(inferred)
    for key, value in explicit.items():
        if key == "input_schema" and isinstance(value, Mapping):
            merged[key] = _merge_input_schema(
                inferred.get("input_schema"),
                value,
            )
            continue
        if value is not None:
            merged[key] = value
    return merged


def _merge_input_schema(
    inferred: Any,
    explicit: Mapping[str, Any],
) -> dict[str, Any]:
    inferred_schema = dict(inferred) if isinstance(inferred, Mapping) else {}
    merged = dict(inferred_schema)
    explicit_properties = explicit.get("properties")
    inferred_properties = inferred_schema.get("properties")
    if isinstance(inferred_properties, Mapping) or isinstance(
        explicit_properties, Mapping
    ):
        properties = dict(inferred_properties or {})
        if isinstance(explicit_properties, Mapping):
            for key, value in explicit_properties.items():
                properties[str(key)] = value
        merged["properties"] = properties
    inferred_required = inferred_schema.get("required")
    explicit_required = explicit.get("required")
    if isinstance(inferred_required, list) or isinstance(explicit_required, list):
        merged["required"] = (
            list(explicit_required)
            if isinstance(explicit_required, list)
            else list(inferred_required or [])
        )
    for key, value in explicit.items():
        if key in {"properties", "required"}:
            continue
        merged[key] = value
    return merged


def _tool_with_source(tool: RegisteredTool, source: ToolSource) -> RegisteredTool:
    if tool.definition.source == source:
        return tool
    return RegisteredTool(replace(tool.definition, source=source), tool.handler)


def _tool_with_default_source(tool: RegisteredTool) -> RegisteredTool:
    if tool.definition.source is not None:
        return tool
    return _tool_with_source(
        tool,
        ToolSource(
            kind=ToolSourceKind.CALLER_REGISTERED,
            origin=ToolOriginKind.REGISTERED,
        ),
    )


def openai_tool_schema(definition: ToolDefinition) -> dict[str, Any]:
    """Convert a tool definition to an OpenAI function-tool schema."""

    if not definition.id:
        raise ToolRegistryError("cannot convert tool without id to OpenAI schema")
    _require_model_exposable(definition)
    raw = dict(definition.raw)
    description = raw.get("description_for_llm") or definition.label or definition.id
    parameters = _normalized_input_schema(definition)
    return {
        "type": "function",
        "name": definition.id,
        "description": str(description),
        "parameters": parameters,
    }


def validate_registry_tool_references(
    manifest: RuntimeManifest,
    registry: ToolRegistry,
) -> None:
    """Validate tool-use nodes against the callable registry."""

    errors: list[str] = []
    for node in manifest.nodes:
        if node.kind != "tool_use_step":
            continue
        if not node.tool_id:
            errors.append(f"tool_use_step node {node.id!r} is missing tool_id")
            continue
        try:
            tool = registry.get_tool(node.tool_id)
            if isinstance(tool.definition, ToolDefinition):
                _require_direct_callable(tool.definition)
        except ToolRegistryError as exc:
            errors.append(
                f"tool_use_step node {node.id!r} references unavailable registry "
                f"tool {node.tool_id!r}: {exc}"
            )
    if errors:
        raise ToolRegistryError(
            "Invalid registry tool references: " + "; ".join(errors)
        )


def validate_tool_overrides(
    overrides: ToolRegistryOverrides,
    registry: InMemoryToolRegistry,
    *,
    manifest: RuntimeManifest | None = None,
) -> None:
    """Validate runtime tool overrides before applying them."""

    errors: list[str] = []
    with registry._lock:
        known_ids = set(registry._tools)
    _extend(errors, _override_tool_definition_errors(overrides, known_ids))
    _extend(errors, _disabled_tool_errors(overrides.disabled_tools, known_ids))
    if manifest is not None:
        _extend(errors, _manifest_override_errors(overrides, known_ids, manifest))
    if errors:
        raise ToolRegistryError("Invalid tool overrides: " + "; ".join(errors))


def _override_tool_definition_errors(
    overrides: ToolRegistryOverrides,
    known_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    for tool in (*overrides.added_tools, *overrides.replacement_tools):
        try:
            _require_tool_id(tool)
            _tool_exposure(tool.definition)
            _normalized_input_schema(tool.definition)
        except ToolRegistryError as exc:
            errors.append(str(exc))
    for tool in overrides.replacement_tools:
        if tool.id not in known_ids:
            errors.append(f"replacement tool {tool.id!r} does not exist")
    return errors


def _require_tool_id(tool: RegisteredTool) -> str:
    return tool.id


def _disabled_tool_errors(
    disabled_tools: Iterable[str],
    known_ids: set[str],
) -> list[str]:
    return [
        f"disabled tool {tool_id!r} does not exist"
        for tool_id in disabled_tools
        if tool_id not in known_ids
    ]


def _manifest_override_errors(
    overrides: ToolRegistryOverrides,
    known_ids: set[str],
    manifest: RuntimeManifest,
) -> list[str]:
    errors: list[str] = []
    llm_node_ids = {node.id for node in manifest.nodes if node.kind == "llm_step"}
    disabled = set(overrides.disabled_tools)
    required_tool_ids = {
        node.tool_id
        for node in manifest.nodes
        if node.kind == "tool_use_step" and node.tool_id
    }
    for tool_id in sorted(required_tool_ids & disabled):
        errors.append(f"required tool_use_step tool {tool_id!r} is disabled")
    effective_ids = (known_ids | {tool.id for tool in overrides.added_tools}) - disabled
    effective_ids |= {tool.id for tool in overrides.replacement_tools}
    _extend(errors, _node_override_errors(overrides, llm_node_ids, effective_ids))
    return errors


def _node_override_errors(
    overrides: ToolRegistryOverrides,
    llm_node_ids: set[str | None],
    effective_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    for node_id, override in overrides.node_overrides.items():
        if node_id not in llm_node_ids:
            errors.append(f"tool override targets non-llm_step node {node_id!r}")
        for tool_id in sorted(_referenced_override_ids(override) - effective_ids):
            errors.append(
                f"tool override for node {node_id!r} references unknown tool {tool_id!r}"
            )
    return errors


def _referenced_override_ids(override: ToolExposureOverride) -> set[str]:
    referenced_ids = set(override.add) | set(override.remove)
    if override.only is not None:
        referenced_ids.update(override.only)
    return referenced_ids


def _extend(target: list[str], values: Iterable[str]) -> None:
    target.extend(values)


def create_local_workspace_registry(
    roots: Sequence[str | Path],
) -> InMemoryToolRegistry:
    """Create the opt-in read-only local workspace built-in tool pack."""

    workspace = _WorkspaceGuard(roots)
    return InMemoryToolRegistry(
        [
            _builtin_tool(
                "read_file",
                "Read file",
                "Read a UTF-8 text file under an approved workspace root.",
                {"path": {"type": "string"}},
                ("path",),
                lambda args: workspace.read_file(str(args["path"])),
            ),
            _builtin_tool(
                "list_files",
                "List files",
                "List files under an approved workspace root.",
                {
                    "path": {"type": "string"},
                    "recursive": {"type": "boolean"},
                },
                ("path",),
                lambda args: workspace.list_files(
                    str(args["path"]), bool(args.get("recursive", False))
                ),
            ),
            _builtin_tool(
                "search_files",
                "Search files",
                "Regex-search UTF-8 text files under an approved workspace root.",
                {"path": {"type": "string"}, "regex": {"type": "string"}},
                ("path", "regex"),
                lambda args: workspace.search_files(
                    str(args["path"]), str(args["regex"])
                ),
            ),
            _builtin_tool(
                "inspect_path",
                "Inspect path",
                "Return existence and metadata for a path under an approved root.",
                {"path": {"type": "string"}},
                ("path",),
                lambda args: workspace.inspect_path(str(args["path"])),
            ),
        ]
    )


def create_web_registry(
    *,
    search_client: Any | None = None,
    fetch_client: Any | None = None,
    policy: WebToolPolicy | None = None,
) -> InMemoryToolRegistry:
    """Create the opt-in read-only web search/fetch built-in tool pack."""

    if search_client is None:
        raise ToolRegistryError("web tool pack requires search_client")
    if fetch_client is None:
        raise ToolRegistryError("web tool pack requires fetch_client")
    web = _WebToolGuard(search_client, fetch_client, policy or WebToolPolicy())
    return InMemoryToolRegistry(
        [
            _builtin_tool(
                "web_search",
                "Web search",
                "Search the web and return bounded source metadata.",
                {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                ("query",),
                lambda args: web.search(
                    str(args["query"]),
                    limit=int(args.get("limit") or web.policy.max_search_results),
                ),
                tool_type="web_search",
                source_id="web",
            ),
            _builtin_tool(
                "web_fetch",
                "Web fetch",
                "Fetch a URL and return bounded normalized content.",
                {"url": {"type": "string"}},
                ("url",),
                lambda args: web.fetch(str(args["url"])),
                tool_type="web_fetch",
                source_id="web",
            ),
        ]
    )


def create_workspace_data_registry(
    *,
    store: Any | None = None,
    policy: WorkspaceDataToolPolicy | None = None,
) -> InMemoryToolRegistry:
    """Create the opt-in workspace_data built-in tool pack."""

    if store is None:
        raise ToolRegistryError("workspace_data tool pack requires store")
    workspace_data = _WorkspaceDataGuard(store, policy or WorkspaceDataToolPolicy())
    return InMemoryToolRegistry(
        [
            _builtin_tool(
                "workspace_data_write",
                "Workspace data write",
                "Create or update one JSON-compatible workspace data item.",
                {
                    "id": {"type": "string"},
                    "kind": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "data": {},
                },
                (),
                workspace_data.write,
                tool_type="structured_data_query",
                source_id="workspace_data",
                side_effect="write",
            ),
            _builtin_tool(
                "workspace_data_read",
                "Workspace data read",
                "Read one workspace data item by id.",
                {"id": {"type": "string"}},
                ("id",),
                workspace_data.read,
                tool_type="structured_data_query",
                source_id="workspace_data",
            ),
            _builtin_tool(
                "workspace_data_search",
                "Workspace data search",
                "Search workspace data items with metadata-first results.",
                {
                    "query": {"type": "string"},
                    "include_data": {"type": "boolean"},
                    "limit": {"type": "integer"},
                },
                ("query",),
                workspace_data.search,
                tool_type="structured_data_query",
                source_id="workspace_data",
            ),
            _builtin_tool(
                "workspace_data_list",
                "Workspace data list",
                "List workspace data item metadata.",
                {
                    "include_data": {"type": "boolean"},
                    "limit": {"type": "integer"},
                },
                (),
                workspace_data.list_items,
                tool_type="structured_data_query",
                source_id="workspace_data",
            ),
            _builtin_tool(
                "workspace_data_delete",
                "Workspace data delete",
                "Delete one workspace data item by id.",
                {"id": {"type": "string"}},
                ("id",),
                workspace_data.delete,
                tool_type="structured_data_query",
                source_id="workspace_data",
                side_effect="write",
                approval_required=(
                    "yes" if workspace_data.policy.require_delete_approval else "no"
                ),
            ),
        ]
    )


def _builtin_tool(
    tool_id: str,
    label: str,
    description: str,
    properties: Mapping[str, Any],
    required: Sequence[str],
    handler: ToolHandler,
    *,
    tool_type: str = "file_read",
    source_id: str = "local_workspace",
    side_effect: str = "read",
    approval_required: str = "no",
) -> RegisteredTool:
    raw = {
        "id": tool_id,
        "label": label,
        "description_for_llm": description,
        "tool_type": tool_type,
        "input_schema": {
            "type": "object",
            "properties": dict(properties),
            "required": list(required),
        },
        "side_effect": side_effect,
        "approval_required": approval_required,
        "timeout": "runtime_default",
        "retry_policy": "none",
        "failure_behavior": "error",
    }
    definition = replace(
        ToolDefinition.from_mapping(raw),
        source=ToolSource(
            kind=ToolSourceKind.BUILT_IN,
            origin=ToolOriginKind.BUILT_IN,
            source_id=source_id,
            detail=tool_id,
        ),
    )
    return RegisteredTool(definition, handler)


class _WebToolGuard:
    def __init__(
        self,
        search_client: Any,
        fetch_client: Any,
        policy: WebToolPolicy,
    ) -> None:
        self.search_client = search_client
        self.fetch_client = fetch_client
        self.policy = policy

    def search(self, query: str, *, limit: int) -> dict[str, Any]:
        limit = max(1, min(limit, self.policy.max_search_results))
        rows = self.search_client.search(query, limit=limit)
        results: list[dict[str, Any]] = []
        for rank, row in enumerate(rows or (), start=1):
            if not isinstance(row, Mapping):
                continue
            url = str(row.get("url") or "")
            self._validate_url(url)
            results.append(
                {
                    "rank": rank,
                    "title": str(row.get("title") or ""),
                    "url": url,
                    "snippet": str(row.get("snippet") or ""),
                }
            )
        return {"query": query, "results": results}

    def fetch(self, url: str) -> dict[str, Any]:
        self._validate_url(url)
        raw = self.fetch_client.fetch(url)
        if not isinstance(raw, Mapping):
            raise ToolRegistryError("web_fetch client returned a non-mapping result")
        text = str(raw.get("text") or "")
        max_chars = max(0, self.policy.max_fetch_chars)
        truncated = len(text) > max_chars
        return {
            "url": str(raw.get("url") or url),
            "status": int(raw.get("status") or 0),
            "content_type": str(raw.get("content_type") or ""),
            "title": str(raw.get("title") or ""),
            "text": text[:max_chars],
            "truncated": truncated,
        }

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in self.policy.allowed_schemes:
            raise ToolRegistryError(f"URL scheme {parsed.scheme!r} is not allowed")
        host = parsed.hostname or ""
        if self.policy.allowed_domains and host not in self.policy.allowed_domains:
            raise ToolRegistryError(f"URL host {host!r} is not allowed")


class _WorkspaceDataGuard:
    def __init__(self, store: Any, policy: WorkspaceDataToolPolicy) -> None:
        self.store = store
        self.policy = policy

    def write(self, args: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(args)
        self._validate_json_item(item)
        stored = self.store.write(item)
        if not isinstance(stored, Mapping):
            raise ToolRegistryError(
                "workspace_data_write store returned a non-mapping item"
            )
        return {"status": "ok", "item": _workspace_data_item(stored)}

    def read(self, args: Mapping[str, Any]) -> dict[str, Any]:
        item_id = str(args["id"])
        item = self.store.read(item_id)
        if item is None:
            return {
                "status": "not_found",
                "id": item_id,
                "next_steps": ["write the item before reading it"],
            }
        if not isinstance(item, Mapping):
            raise ToolRegistryError(
                "workspace_data_read store returned a non-mapping item"
            )
        return {"status": "ok", "item": _workspace_data_item(item)}

    def search(self, args: Mapping[str, Any]) -> dict[str, Any]:
        query = str(args["query"])
        limit = self._limit(args.get("limit"))
        include_data = bool(args.get("include_data", False))
        rows = self.store.search(query, limit=limit)
        return {
            "status": "ok",
            "items": [
                _workspace_data_item(row, include_data=include_data)
                for row in rows or ()
                if isinstance(row, Mapping)
            ],
        }

    def list_items(self, args: Mapping[str, Any]) -> dict[str, Any]:
        limit = self._limit(args.get("limit"))
        include_data = bool(args.get("include_data", False))
        rows = self.store.list(limit=limit)
        return {
            "status": "ok",
            "items": [
                _workspace_data_item(row, include_data=include_data)
                for row in rows or ()
                if isinstance(row, Mapping)
            ],
        }

    def delete(self, args: Mapping[str, Any]) -> dict[str, Any]:
        item_id = str(args["id"])
        deleted = bool(self.store.delete(item_id))
        if not deleted:
            return {"status": "not_found", "id": item_id}
        return {"status": "deleted", "id": item_id}

    def _limit(self, value: Any) -> int:
        if value is None:
            return self.policy.default_search_limit
        return max(1, min(int(value), self.policy.default_search_limit))

    def _validate_json_item(self, item: Mapping[str, Any]) -> None:
        try:
            encoded = json.dumps(item, sort_keys=True, separators=(",", ":")).encode()
        except (TypeError, ValueError) as exc:
            raise ToolRegistryError(
                "workspace_data_write payload must be JSON-compatible"
            ) from exc
        if len(encoded) > self.policy.max_item_bytes:
            raise ToolRegistryError(
                "workspace_data_write payload exceeds max_item_bytes "
                f"({self.policy.max_item_bytes})"
            )


def _workspace_data_item(
    item: Mapping[str, Any],
    *,
    include_data: bool = True,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in (
        "id",
        "kind",
        "title",
        "description",
        "tags",
        "labels",
        "created_at",
        "updated_at",
        "actor",
        "content_type",
    ):
        if key in item:
            result[key] = item[key]
    if include_data and "data" in item:
        result["data"] = item["data"]
    return result


class _WorkspaceGuard:
    def __init__(self, roots: Sequence[str | Path]) -> None:
        if not roots:
            raise ToolRegistryError(
                "local_workspace tool pack requires at least one root"
            )
        self.roots = tuple(Path(root).resolve() for root in roots)

    def resolve(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.roots[0] / path
        resolved = path.resolve()
        if not any(_is_relative_to(resolved, root) for root in self.roots):
            raise ToolRegistryError(
                f"path {value!r} is outside approved workspace roots"
            )
        return resolved

    def read_file(self, path: str) -> str:
        return self.resolve(path).read_text(encoding="utf-8")

    def list_files(self, path: str, recursive: bool) -> list[str]:
        root = self.resolve(path)
        if not root.is_dir():
            raise ToolRegistryError(f"path {path!r} is not a directory")
        iterator = root.rglob("*") if recursive else root.iterdir()
        return sorted(str(item.relative_to(root)) for item in iterator)

    def search_files(self, path: str, regex: str) -> list[dict[str, Any]]:
        root = self.resolve(path)
        pattern = re.compile(regex)
        files = (
            [root]
            if root.is_file()
            else [item for item in root.rglob("*") if item.is_file()]
        )
        matches: list[dict[str, Any]] = []
        for file_path in files:
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if pattern.search(line):
                    matches.append(
                        {
                            "path": str(file_path.relative_to(self.roots[0])),
                            "line": line_number,
                            "text": line,
                        }
                    )
        return matches

    def inspect_path(self, path: str) -> dict[str, Any]:
        resolved = self.resolve(path)
        exists = resolved.exists()
        info: dict[str, Any] = {
            "path": str(resolved),
            "exists": exists,
            "is_file": resolved.is_file(),
            "is_dir": resolved.is_dir(),
        }
        if exists:
            stat = resolved.stat()
            info.update({"size": stat.st_size, "modified_time": stat.st_mtime})
        return info


def _validate_input_schema(
    definition: ToolDefinition, arguments: Mapping[str, Any]
) -> None:
    schema = _normalized_input_schema(definition)
    required = schema.get("required", [])
    for field_name in required:
        if field_name not in arguments:
            raise ToolRegistryError(
                f"tool {definition.id!r} missing required input {field_name!r}"
            )


def _normalized_input_schema(definition: ToolDefinition) -> dict[str, Any]:
    schema = definition.raw.get("input_schema") or _EMPTY_PARAMETERS
    if not isinstance(schema, Mapping):
        raise ToolRegistryError(
            f"tool {definition.id!r} input_schema must be a mapping"
        )
    for combinator in ("oneOf", "anyOf", "allOf"):
        if combinator in schema:
            raise ToolRegistryError(
                f"tool {definition.id!r} input_schema must not use top-level "
                f"{combinator}"
            )
    schema_type = schema.get("type")
    if schema_type is not None and schema_type != "object":
        raise ToolRegistryError(
            f"tool {definition.id!r} input_schema must be an object schema"
        )
    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, Mapping):
        raise ToolRegistryError(
            f"tool {definition.id!r} input_schema properties must be a mapping"
        )
    required = schema.get("required", [])
    if not isinstance(required, list):
        raise ToolRegistryError(
            f"tool {definition.id!r} input_schema required must be a list"
        )
    if not all(isinstance(item, str) for item in required):
        raise ToolRegistryError(
            f"tool {definition.id!r} input_schema required entries must be strings"
        )
    normalized = {key: value for key, value in schema.items() if key != "$schema"}
    normalized.setdefault("type", "object")
    return dict(normalized)


def _require_model_exposable(definition: ToolDefinition) -> None:
    exposure = _tool_exposure(definition)
    if exposure not in (ToolExposure.DIRECT, ToolExposure.DIRECT_MODEL_ONLY):
        raise ToolRegistryError(
            f"tool {definition.id!r} exposure {exposure.value!r} is not model-exposable"
        )


def _is_model_exposable(definition: ToolDefinition) -> bool:
    exposure = _tool_exposure(definition)
    return exposure in (ToolExposure.DIRECT, ToolExposure.DIRECT_MODEL_ONLY)


def _require_direct_callable(definition: ToolDefinition) -> None:
    exposure = _tool_exposure(definition)
    if exposure not in (ToolExposure.DIRECT, ToolExposure.HIDDEN):
        raise ToolRegistryError(
            f"tool {definition.id!r} exposure {exposure.value!r} is not callable "
            "for direct execution"
        )


def _tool_exposure(definition: ToolDefinition) -> ToolExposure:
    exposure = definition.exposure
    if isinstance(exposure, ToolExposure):
        return exposure
    raise ToolRegistryError(
        f"tool {definition.id!r} has unsupported exposure {exposure!r}"
    )


def _diagnostic_item(
    candidate: _ToolCandidate,
    reason: str,
) -> ToolDescriptorBudgetDiagnosticItem:
    return ToolDescriptorBudgetDiagnosticItem(
        tool_id=candidate.tool.id,
        reason=reason,
        token_count=candidate.token_count,
        score=candidate.score,
    )


def _tool_score(definition: ToolDefinition, prompt_terms: set[str]) -> int:
    metadata_terms = _normalized_terms(
        " ".join(
            str(value)
            for value in (
                definition.id,
                definition.label,
                definition.tool_type,
                definition.raw.get("description_for_llm"),
            )
            if value is not None
        )
    )
    schema = _normalized_input_schema(definition)
    metadata_terms.update(_schema_terms(schema))
    overlap = metadata_terms & prompt_terms
    score = len(overlap)
    if definition.id and str(definition.id).lower() in _terms_text(prompt_terms):
        score += 4
    return score


def _schema_terms(value: Any) -> set[str]:
    terms: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            terms.update(_normalized_terms(str(key)))
            terms.update(_schema_terms(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            terms.update(_schema_terms(item))
    elif isinstance(value, str):
        terms.update(_normalized_terms(value))
    return terms


def _messages_text(messages: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        if isinstance(message, Mapping):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, Sequence) and not isinstance(
            content, (bytes, bytearray)
        ):
            parts.extend(str(item) for item in content)
        elif content is not None:
            parts.append(str(content))
    return " ".join(parts)


def _normalized_terms(value: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", value.lower()) if term}


def _terms_text(terms: set[str]) -> str:
    return " ".join(sorted(terms))


def _policy_mapping(value: Any) -> Mapping[str, Any] | None:
    if value in (None, False, "", "none"):
        return None
    if not isinstance(value, Mapping):
        raise ToolRegistryError(f"unsupported tool descriptor budget policy {value!r}")
    return value


def _string_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ToolRegistryError("tool descriptor budget required_tools must be a list")
    return tuple(str(item) for item in value)


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed < 1:
        raise ToolRegistryError(
            "tool descriptor budget integer values must be positive"
        )
    return parsed


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
