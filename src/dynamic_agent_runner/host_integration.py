"""Host-facing integration helpers for embedded workflow runtimes."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from dynamic_agent_runner.capabilities import CapabilityStatusReport
from dynamic_agent_runner.errors import ToolRegistryError
from dynamic_agent_runner.models import ToolDefinition
from dynamic_agent_runner.registry import InMemoryToolRegistry, RegisteredTool
from dynamic_agent_runner.tracing import REDACTED_VALUE, TraceEvent

_MODEL_TOOL_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_DEFAULT_INPUT_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}
_DEFAULT_SENSITIVE_FIELDS = frozenset(
    {
        "api_key",
        "authorization",
        "cookie",
        "credentials",
        "password",
        "prompt",
        "secret",
        "token",
    }
)


@dataclass(frozen=True)
class HostToolBinding:
    """Host-owned tool exposed through a provider-safe model-facing id."""

    canonical_id: str
    model_id: str
    handler: Callable[[Mapping[str, Any]], Any]
    label: str | None = None
    description: str | None = None
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    tool_type: str | None = None
    side_effect: str = "read"
    approval_required: str = "no"

    def __post_init__(self) -> None:
        if not self.canonical_id:
            raise ToolRegistryError("host tool binding requires canonical_id")
        if not self.model_id:
            raise ToolRegistryError("host tool binding requires model_id")
        if not callable(self.handler):
            raise ToolRegistryError("host tool binding requires a callable handler")
        _validate_model_tool_id(self.model_id)
        for alias in self.aliases:
            _validate_model_tool_id(alias)
        object.__setattr__(self, "input_schema", dict(self.input_schema))
        object.__setattr__(self, "aliases", tuple(self.aliases))


@dataclass(frozen=True)
class ResolvedModelSelection:
    """Provider-neutral model-selection handoff from a host application."""

    model: str | None = None
    adapters: Sequence[Any] = ()
    coverage: str = "augmented"
    unavailable_reason: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        """Return whether the selection has executable adapters."""

        return bool(self.adapters) and self.unavailable_reason is None

    def to_execution_kwargs(self) -> dict[str, Any]:
        """Return kwargs compatible with workflow execution entry points."""

        payload: dict[str, Any] = {"model_adapter_coverage": self.coverage}
        if self.adapters:
            payload["model_adapter"] = tuple(self.adapters)
        return payload

    def to_diagnostic_payload(self) -> dict[str, Any]:
        """Return a redacted JSON-compatible model-selection summary."""

        payload: dict[str, Any] = {
            "model": self.model,
            "coverage": self.coverage,
            "available": self.available,
        }
        if self.unavailable_reason is not None:
            payload["unavailable_reason"] = self.unavailable_reason
        if self.diagnostics:
            payload["diagnostics"] = _summarize_value(
                self.diagnostics,
                sensitive_fields=_DEFAULT_SENSITIVE_FIELDS,
            )
        return payload


def create_host_tool_registry(
    bindings: Iterable[HostToolBinding],
) -> InMemoryToolRegistry:
    """Create a registry from host-owned tool bindings."""

    tools: list[RegisteredTool] = []
    seen: dict[str, str] = {}
    for binding in bindings:
        ids = (binding.model_id, *binding.aliases)
        for tool_id in ids:
            previous = seen.get(tool_id)
            if previous is not None:
                raise ToolRegistryError(
                    "host tool id collision for "
                    f"{tool_id!r}: {previous!r} and {binding.canonical_id!r}"
                )
            seen[tool_id] = binding.canonical_id
            tools.append(_registered_tool_from_binding(binding, tool_id=tool_id))
    return InMemoryToolRegistry(tools)


def summarize_trace_events(
    events: Iterable[TraceEvent],
    *,
    max_items: int = 50,
    max_sequence_items: int = 5,
) -> list[dict[str, Any]]:
    """Return bounded, redacted summaries for trace events."""

    summaries: list[dict[str, Any]] = []
    for event in events:
        if len(summaries) >= max_items:
            break
        sensitive_fields = _DEFAULT_SENSITIVE_FIELDS | set(event.sensitive_fields)
        summaries.append(
            {
                "sequence": event.sequence,
                "event_type": event.event_type,
                "run_id": event.run_id,
                "node_id": event.node_id,
                "payload": _summarize_value(
                    event.payload,
                    sensitive_fields=sensitive_fields,
                    max_sequence_items=max_sequence_items,
                ),
            }
        )
    return summaries


def summarize_capability_report(
    report: CapabilityStatusReport,
    *,
    max_items: int = 50,
) -> dict[str, Any]:
    """Return a bounded JSON-compatible capability/status summary."""

    items: list[dict[str, Any]] = []
    for item in report.items:
        if len(items) >= max_items:
            break
        items.append(
            {
                "id": item.id,
                "label": item.label,
                "state": item.state.value,
                "category": item.category,
                "summary": item.summary,
                "owner": item.owner,
                "required_collaborator": item.required_collaborator,
                "details": _summarize_value(
                    item.details,
                    sensitive_fields=_DEFAULT_SENSITIVE_FIELDS,
                ),
            }
        )
    return {
        "package_id": report.package_id,
        "valid": report.valid,
        "validation_error": report.validation_error,
        "summary": {
            "total": report.summary.total,
            "counts_by_state": dict(report.summary.counts_by_state),
        },
        "items": items,
    }


def _registered_tool_from_binding(
    binding: HostToolBinding,
    *,
    tool_id: str,
) -> RegisteredTool:
    raw: dict[str, Any] = {
        "id": tool_id,
        "label": binding.label or tool_id.replace("_", " ").title(),
        "description_for_llm": binding.description or binding.label or tool_id,
        "input_schema": dict(binding.input_schema or _DEFAULT_INPUT_SCHEMA),
        "side_effect": binding.side_effect,
        "approval_required": binding.approval_required,
        "exposure": "direct",
        "timeout": "runtime_default",
        "retry_policy": "none",
        "failure_behavior": "error",
        "host_canonical_id": binding.canonical_id,
        "host_model_id": binding.model_id,
    }
    if binding.tool_type is not None:
        raw["tool_type"] = binding.tool_type
    if binding.aliases:
        raw["host_aliases"] = list(binding.aliases)
    return RegisteredTool(ToolDefinition.from_mapping(raw), binding.handler)


def _validate_model_tool_id(tool_id: str) -> None:
    if _MODEL_TOOL_ID_RE.fullmatch(tool_id) is None:
        raise ToolRegistryError(
            f"host model-facing tool id {tool_id!r} must contain only letters, "
            "numbers, underscores, or hyphens"
        )


def _summarize_value(
    value: Any,
    *,
    sensitive_fields: Iterable[str],
    max_sequence_items: int = 5,
) -> Any:
    sensitive = {field.lower() for field in sensitive_fields}
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if key_text.lower() in sensitive:
                result[key_text] = REDACTED_VALUE
            elif isinstance(child, Mapping):
                result[key_text] = {
                    "type": "dict",
                    "keys": sorted(str(child_key) for child_key in child.keys()),
                    "length": len(child),
                }
            elif isinstance(child, (list, tuple)):
                result[key_text] = {
                    "type": type(child).__name__,
                    "length": len(child),
                    "items": [
                        _summarize_scalar(item) for item in child[:max_sequence_items]
                    ],
                }
            else:
                result[key_text] = _summarize_scalar(child)
        return result
    if isinstance(value, (list, tuple)):
        return {
            "type": type(value).__name__,
            "length": len(value),
            "items": [_summarize_scalar(item) for item in value[:max_sequence_items]],
        }
    return _summarize_scalar(value)


def _summarize_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return {"type": type(value).__name__}


__all__ = [
    "HostToolBinding",
    "ResolvedModelSelection",
    "create_host_tool_registry",
    "summarize_capability_report",
    "summarize_trace_events",
]
