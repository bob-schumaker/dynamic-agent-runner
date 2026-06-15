"""Lifecycle hook protocols for dynamic-agent workflow execution."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


HookCallback = Callable[[Any], None | Awaitable[None]]


@dataclass(frozen=True)
class NodeHookContext:
    """Stable observation context for node lifecycle hooks."""

    node_id: str
    kind: str
    output: Any = None
    error: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class ModelHookContext:
    """Stable observation context for model-call lifecycle hooks."""

    node_id: str
    model: str
    request: Mapping[str, Any] | None = None
    response: Any = None
    error: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class ToolHookContext:
    """Stable observation context for direct tool-call lifecycle hooks."""

    node_id: str
    tool_id: str
    arguments: Mapping[str, Any] | None = None
    result: Any = None
    error: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class PermissionHookContext:
    """Reserved observation context for future permission-boundary hooks."""

    node_id: str
    boundary: str
    metadata: Mapping[str, Any] | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class WorkflowHookContext:
    """Stable observation context for workflow-level lifecycle hooks."""

    final_result: Any = None
    error: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class RegisteredLifecycleHook:
    """Lifecycle hook callback plus its recorded callable shape."""

    name: str
    callback: HookCallback
    callback_is_async: bool


@dataclass(frozen=True)
class WorkflowLifecycleHooks:
    """Optional in-process callbacks for stable workflow lifecycle points.

    Hooks are intentionally Python callables supplied by trusted callers. They are
    observational in the initial scope: a hook may inspect the supplied context or
    abort execution by raising a project exception, but hooks do not receive shell
    commands, plugin loading, or untrusted extension behavior.
    """

    before_node: HookCallback | None = None
    after_node: HookCallback | None = None
    before_model: HookCallback | None = None
    after_model: HookCallback | None = None
    before_tool: HookCallback | None = None
    after_tool: HookCallback | None = None
    after_workflow: HookCallback | None = None
    _registered_hooks: Mapping[str, RegisteredLifecycleHook] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        """Record configured hook callable shapes once at setup time."""

        registered: dict[str, RegisteredLifecycleHook] = {}
        for name in (
            "before_node",
            "after_node",
            "before_model",
            "after_model",
            "before_tool",
            "after_tool",
            "after_workflow",
        ):
            callback = getattr(self, name)
            if callback is None:
                continue
            registered[name] = RegisteredLifecycleHook(
                name=name,
                callback=callback,
                callback_is_async=inspect.iscoroutinefunction(callback),
            )
        object.__setattr__(self, "_registered_hooks", registered)

    def registered_hook(self, name: str) -> RegisteredLifecycleHook | None:
        """Return configured hook metadata by lifecycle hook name."""

        return self._registered_hooks.get(name)


async def invoke_lifecycle_hook_async(
    hook: RegisteredLifecycleHook | None,
    context: Any,
) -> None:
    """Invoke a lifecycle hook through the async dispatch boundary."""

    if hook is None:
        return
    if hook.callback_is_async:
        await hook.callback(context)
        return
    hook.callback(context)


__all__ = [
    "ModelHookContext",
    "NodeHookContext",
    "PermissionHookContext",
    "RegisteredLifecycleHook",
    "ToolHookContext",
    "WorkflowHookContext",
    "WorkflowLifecycleHooks",
    "invoke_lifecycle_hook_async",
]
