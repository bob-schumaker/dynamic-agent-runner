"""Internal tool-invocation coordination shared by executor and providers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from dynamic_agent_runner.hooks import (
    ToolHookContext,
    WorkflowLifecycleHooks,
    invoke_lifecycle_hook_async,
)
from dynamic_agent_runner.registry import (
    PreparedToolInvocation,
    RegisteredTool,
    ToolRegistry,
    ToolResult,
)
from dynamic_agent_runner.errors import ToolRegistryError
from dynamic_agent_runner.retry import RetryPolicy
from dynamic_agent_runner.tracing import WorkflowTracer


class ApprovalInterruptionState(str, Enum):
    """Lifecycle state for an approval interruption."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass(frozen=True)
class ApprovalInterruption:
    """Structured pause record for an approval-required runtime action."""

    interruption_id: str
    run_id: str
    workflow_id: str
    node_id: str
    tool_id: str | None = None
    action_id: str | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    policy: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""
    state: ApprovalInterruptionState = ApprovalInterruptionState.PENDING
    schema_version: int = 1


@dataclass(frozen=True)
class ActiveAdapterToolContext:
    """Trusted, non-wire state for one active tool-enabled model node."""

    plan: Any
    node: Any
    tools: tuple[RegisteredTool, ...]
    registry: ToolRegistry
    state: Any
    tracer: WorkflowTracer
    lifecycle_hooks: WorkflowLifecycleHooks | None
    retry_policy: RetryPolicy

    def __post_init__(self) -> None:
        """Reject descriptors and stale registry entries at the trust boundary."""

        if not all(isinstance(tool, RegisteredTool) for tool in self.tools):
            raise ToolRegistryError(
                "active tool context requires RegisteredTool snapshots, not descriptors"
            )
        for tool in self.tools:
            if self.registry.get_tool(tool.id) is not tool:
                raise ToolRegistryError(
                    f"tool {tool.id!r} does not match the active registry snapshot"
                )

    @property
    def allowed_tool_ids(self) -> frozenset[str]:
        """Return the immutable model-facing tool identifier snapshot."""

        return frozenset(tool.id for tool in self.tools)

    def tool_for_id(self, tool_id: str) -> RegisteredTool:
        """Resolve only from the active selected-tool snapshot."""

        for tool in self.tools:
            if tool.id == tool_id:
                return tool
        raise ToolRegistryError(f"tool {tool_id!r} is not active for this node")

    def require_current_tool(self, tool: RegisteredTool) -> None:
        """Fail closed when a registry entry differs from this request snapshot."""

        if self.registry.get_tool(tool.id) is not tool:
            raise ToolRegistryError(
                f"tool {tool.id!r} no longer matches the active invocation context"
            )

    def request(
        self,
        *,
        tool_id: str,
        arguments: Mapping[str, Any],
        result_key: str,
        invoke: Callable[[PreparedToolInvocation | None], Awaitable[ToolResult]],
        approval_reason: str,
        action_id: str | None = None,
        emit_tool_invocation: bool = False,
        guardrail_runner: Callable[[PreparedToolInvocation], None] | None = None,
    ) -> ToolInvocationRequest:
        """Bind one trusted provider or executor tool call to this context."""

        return ToolInvocationRequest(
            context=self,
            tool_id=tool_id,
            arguments=arguments,
            result_key=result_key,
            invoke=invoke,
            approval_reason=approval_reason,
            action_id=action_id,
            emit_tool_invocation=emit_tool_invocation,
            guardrail_runner=guardrail_runner,
        )


@dataclass(frozen=True)
class ToolInvocationRequest:
    """One normalized, allowlisted tool invocation entering DAR coordination."""

    context: ActiveAdapterToolContext
    tool_id: str
    arguments: Mapping[str, Any]
    result_key: str
    invoke: Callable[[PreparedToolInvocation | None], Awaitable[ToolResult]]
    approval_reason: str
    action_id: str | None = None
    emit_tool_invocation: bool = False
    guardrail_runner: Callable[[PreparedToolInvocation], None] | None = None


def tool_context(
    *,
    plan: Any,
    node: Any,
    tools: Sequence[RegisteredTool],
    registry: ToolRegistry,
    state: Any,
    tracer: WorkflowTracer,
    lifecycle_hooks: WorkflowLifecycleHooks | None,
    retry_policy: RetryPolicy,
) -> ActiveAdapterToolContext:
    """Build the trusted non-wire context for one active model or tool node."""

    selected_tools = tuple(tools)
    return ActiveAdapterToolContext(
        plan=plan,
        node=node,
        tools=selected_tools,
        registry=registry,
        state=state,
        tracer=tracer,
        lifecycle_hooks=lifecycle_hooks,
        retry_policy=retry_policy,
    )


async def coordinate_tool_invocation_async(
    request: ToolInvocationRequest,
) -> ToolResult | ApprovalInterruption:
    """Apply DAR approval, lifecycle, state, and tracing to one trusted request."""

    context = request.context
    tool = context.tool_for_id(request.tool_id)
    context.require_current_tool(tool)
    prepared: PreparedToolInvocation | None = None
    if request.guardrail_runner is not None:
        prepared = context.registry.prepare_tool_invocation(tool.id, request.arguments)
        request.guardrail_runner(prepared)
    active_arguments = prepared.arguments if prepared is not None else request.arguments
    event_payload = {"tool_id": tool.id, "arguments": active_arguments}
    if request.action_id is not None:
        event_payload["tool_call_id"] = request.action_id
    if _approval_required(tool):
        prepared = prepared or context.registry.prepare_tool_invocation(
            tool.id, request.arguments
        )
        interruption = ApprovalInterruption(
            interruption_id=str(uuid4()),
            run_id=str(context.state.run_id),
            workflow_id=str(context.plan.workflow.runtime_manifest.package_id),
            node_id=str(context.node.id),
            tool_id=tool.id,
            action_id=request.action_id,
            arguments=prepared.arguments,
            policy=_tool_policy_payload(tool),
            reason=request.approval_reason,
        )
        approval_payload = {
            "interruption_id": interruption.interruption_id,
            "tool_id": tool.id,
            "arguments": prepared.arguments,
            "policy": interruption.policy,
            "reason": interruption.reason,
        }
        if request.action_id is not None:
            approval_payload["tool_call_id"] = request.action_id
        context.tracer.emit(
            "approval_requested",
            node_id=str(context.node.id),
            payload=approval_payload,
            sensitive_fields=("arguments",),
        )
        paused_payload = {
            "interruption_id": interruption.interruption_id,
            "tool_id": tool.id,
            "state": interruption.state.value,
        }
        if request.action_id is not None:
            paused_payload["tool_call_id"] = request.action_id
        context.tracer.emit(
            "approval_paused", node_id=str(context.node.id), payload=paused_payload
        )
        return interruption
    context.tracer.emit(
        "tool_started",
        node_id=str(context.node.id),
        payload=event_payload,
        sensitive_fields=("arguments",),
    )
    if request.emit_tool_invocation:
        context.tracer.emit(
            "tool_invocation",
            node_id=str(context.node.id),
            payload=event_payload,
            sensitive_fields=("arguments",),
        )
    await invoke_lifecycle_hook_async(
        (
            context.lifecycle_hooks.registered_hook("before_tool")
            if context.lifecycle_hooks
            else None
        ),
        ToolHookContext(
            node_id=str(context.node.id),
            tool_id=tool.id,
            arguments=active_arguments,
            run_id=context.state.run_id,
        ),
    )
    context.require_current_tool(tool)
    result = await request.invoke(prepared)
    context.state.tool_results[request.result_key] = result
    trace_payload = result.trace_payload()
    if request.action_id is not None:
        trace_payload = {"tool_call_id": request.action_id, **trace_payload}
    context.tracer.emit(
        "tool_result",
        node_id=str(context.node.id),
        payload=trace_payload,
        sensitive_fields=tuple(dict.fromkeys(("output", *result.sensitive_fields))),
    )
    finished_payload = {
        "tool_id": tool.id,
        "success": result.success,
        "error": result.error,
    }
    if request.action_id is not None:
        finished_payload["tool_call_id"] = request.action_id
    context.tracer.emit(
        "tool_finished", node_id=str(context.node.id), payload=finished_payload
    )
    await invoke_lifecycle_hook_async(
        (
            context.lifecycle_hooks.registered_hook("after_tool")
            if context.lifecycle_hooks
            else None
        ),
        ToolHookContext(
            node_id=str(context.node.id),
            tool_id=tool.id,
            arguments=active_arguments,
            result=result,
            error=result.error,
            run_id=context.state.run_id,
        ),
    )
    return result


def _approval_required(tool: RegisteredTool) -> bool:
    value = (
        tool.definition.policy.approval_required or tool.definition.approval_required
    )
    return str(value).strip().lower() in {"1", "true", "yes", "required"}


def _tool_policy_payload(tool: RegisteredTool) -> dict[str, str]:
    policy = tool.definition.policy
    payload: dict[str, str] = {}
    for key, value in (
        ("approval_required", policy.approval_required),
        ("side_effect", policy.side_effect),
        ("sandbox", policy.sandbox),
        ("timeout", policy.timeout),
        ("retry_policy", policy.retry_policy),
        ("failure_behavior", policy.failure_behavior),
    ):
        if value is not None:
            payload[key] = str(value)
    return payload
