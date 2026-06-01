"""Repository-owned tool registry for dynamic-agent workflow execution."""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

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
            tool, args = self._prepare_tool_invocation(tool_id, arguments)
            if tool.handler_is_async:
                output = _run_async_tool_handler_from_sync(tool.handler, args)
            else:
                output = tool.handler(args)
        except Exception as exc:  # noqa: BLE001 - convert all tool failures.
            return ToolResult(tool_id=tool_id, success=False, error=str(exc))
        return _tool_result_from_output(tool_id, output)

    async def invoke_tool_async(
        self,
        tool_id: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> ToolResult:
        """Invoke a registered tool without blocking the event loop."""

        try:
            tool, args = self._prepare_tool_invocation(tool_id, arguments)
            if tool.handler_is_async:
                output = await tool.handler(args)
            else:
                output = await asyncio.to_thread(tool.handler, args)
        except Exception as exc:  # noqa: BLE001 - convert all tool failures.
            return ToolResult(tool_id=tool_id, success=False, error=str(exc))
        return _tool_result_from_output(tool_id, output)

    def _prepare_tool_invocation(
        self,
        tool_id: str,
        arguments: Mapping[str, Any] | None,
    ) -> tuple[RegisteredTool, dict[str, Any]]:
        args = dict(arguments or {})
        tool = self.get_tool(tool_id)
        _require_direct_callable(tool.definition)
        _validate_input_schema(tool.definition, args)
        return tool, args


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
        "function": {
            "name": definition.id,
            "description": str(description),
            "parameters": parameters,
        },
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


def _builtin_tool(
    tool_id: str,
    label: str,
    description: str,
    properties: Mapping[str, Any],
    required: Sequence[str],
    handler: ToolHandler,
) -> RegisteredTool:
    raw = {
        "id": tool_id,
        "label": label,
        "description_for_llm": description,
        "input_schema": {
            "type": "object",
            "properties": dict(properties),
            "required": list(required),
        },
        "side_effect": "read",
        "approval_required": "no",
        "timeout": "runtime_default",
        "retry_policy": "none",
        "failure_behavior": "error",
    }
    definition = replace(
        ToolDefinition.from_mapping(raw),
        source=ToolSource(
            kind=ToolSourceKind.BUILT_IN,
            origin=ToolOriginKind.BUILT_IN,
            source_id="local_workspace",
            detail=tool_id,
        ),
    )
    return RegisteredTool(definition, handler)


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
