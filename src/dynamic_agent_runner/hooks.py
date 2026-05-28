"""Lifecycle hook protocols for dynamic-agent workflow execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NodeHookContext:
    """Stable observation context for node lifecycle hooks."""

    node_id: str
    kind: str
    output: Any = None
    error: str | None = None


@dataclass(frozen=True)
class ModelHookContext:
    """Stable observation context for model-call lifecycle hooks."""

    node_id: str
    model: str
    request: Mapping[str, Any] | None = None
    response: Any = None
    error: str | None = None


@dataclass(frozen=True)
class ToolHookContext:
    """Stable observation context for direct tool-call lifecycle hooks."""

    node_id: str
    tool_id: str
    arguments: Mapping[str, Any] | None = None
    result: Any = None
    error: str | None = None


@dataclass(frozen=True)
class PermissionHookContext:
    """Reserved observation context for future permission-boundary hooks."""

    node_id: str
    boundary: str
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WorkflowHookContext:
    """Stable observation context for workflow-level lifecycle hooks."""

    final_result: Any = None
    error: str | None = None


@dataclass(frozen=True)
class WorkflowLifecycleHooks:
    """Optional in-process callbacks for stable workflow lifecycle points.

    Hooks are intentionally Python callables supplied by trusted callers. They are
    observational in the initial scope: a hook may inspect the supplied context or
    abort execution by raising a project exception, but hooks do not receive shell
    commands, plugin loading, or untrusted extension behavior.
    """

    before_node: Callable[[NodeHookContext], None] | None = None
    after_node: Callable[[NodeHookContext], None] | None = None
    before_model: Callable[[ModelHookContext], None] | None = None
    after_model: Callable[[ModelHookContext], None] | None = None
    before_tool: Callable[[ToolHookContext], None] | None = None
    after_tool: Callable[[ToolHookContext], None] | None = None
    after_workflow: Callable[[WorkflowHookContext], None] | None = None


__all__ = [
    "ModelHookContext",
    "NodeHookContext",
    "PermissionHookContext",
    "ToolHookContext",
    "WorkflowHookContext",
    "WorkflowLifecycleHooks",
]
