"""Internal tool-invocation coordination shared by executor and providers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from hashlib import sha256
import json
from threading import Lock
from typing import Any, Protocol
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


class ProviderToolInterruption(Exception):
    """Provider-safe typed escape carrying an approval interruption privately."""

    __slots__ = ("_approval", "provider")

    def __init__(
        self, approval: ApprovalInterruption, *, provider: str | None = None
    ) -> None:
        Exception.__init__(self, "provider tool invocation interrupted")
        self._approval = approval
        self.provider = provider

    @property
    def interruption_id(self) -> str:
        """Return the opaque DAR interruption identity."""

        return self._approval.interruption_id

    @property
    def tool_id(self) -> str | None:
        """Return the interrupted tool identity without arguments."""

        return self._approval.tool_id

    @property
    def state(self) -> ApprovalInterruptionState:
        """Return the DAR approval state."""

        return self._approval.state

    def __str__(self) -> str:
        return "provider tool invocation interrupted"


def unwrap_provider_tool_interruption(
    interruption: ProviderToolInterruption,
) -> ApprovalInterruption:
    """Return the DAR approval record only inside trusted runtime code."""

    if not isinstance(interruption, ProviderToolInterruption):
        raise ToolRegistryError("provider interruption is invalid")
    return interruption._approval


class ProviderDecisionState(StrEnum):
    """Synchronous provider approval decision states."""

    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ProviderDecisionRequest:
    """One callback's opaque approval-binding request."""

    invocation_id: str
    fingerprint: str

    def __post_init__(self) -> None:
        _non_empty_string(self.invocation_id, "invocation_id")
        _fingerprint(self.fingerprint)


@dataclass(frozen=True)
class ProviderToolDecision:
    """Typed decision returned synchronously by a trusted collaborator."""

    state: ProviderDecisionState
    invocation_id: str
    fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.state, ProviderDecisionState):
            raise ToolRegistryError("provider decision state is invalid")
        _non_empty_string(self.invocation_id, "invocation_id")
        _fingerprint(self.fingerprint)


class ProviderDecisionCollaborator(Protocol):
    """Trusted synchronous resolver for one exact provider callback decision."""

    def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
        """Return one typed decision without awaiting or dispatching tools."""


def request_provider_tool_decision(
    collaborator: ProviderDecisionCollaborator,
    request: ProviderDecisionRequest,
) -> ProviderToolDecision:
    """Invoke a synchronous decision collaborator at the provider boundary."""

    decision = collaborator.decide(request)
    if not isinstance(decision, ProviderToolDecision):
        raise ToolRegistryError(
            "provider decision collaborator returned an invalid value"
        )
    if (
        decision.invocation_id != request.invocation_id
        or decision.fingerprint != request.fingerprint
    ):
        raise ToolRegistryError("provider decision does not match its request")
    return decision


def provider_invocation_fingerprint(
    *,
    run_id: str,
    workflow_id: str,
    node_id: str,
    action_id: str | None,
    prepared: PreparedToolInvocation,
) -> str:
    """Hash one normalized provider invocation without exposing its arguments."""

    if not isinstance(prepared, PreparedToolInvocation):
        raise ToolRegistryError(
            "provider invocation fingerprint requires PreparedToolInvocation"
        )
    payload = {
        "action_id": action_id,
        "arguments": dict(prepared.arguments),
        "node_id": node_id,
        "run_id": run_id,
        "tool_id": prepared.tool.id,
        "workflow_id": workflow_id,
    }
    try:
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ToolRegistryError(
            "provider invocation arguments are not fingerprintable"
        ) from error
    return sha256(serialized.encode("utf-8")).hexdigest()


class ProviderCallbackBudget:
    """Thread-safe bounded callback claims for one future provider session."""

    def __init__(self, *, limit: int) -> None:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ToolRegistryError("provider callback budget limit is invalid")
        self._limit = limit
        self._claimed = 0
        self._lock = Lock()

    @property
    def limit(self) -> int:
        """Return the configured callback limit."""

        return self._limit

    @property
    def claimed(self) -> int:
        """Return the number of successful claims."""

        with self._lock:
            return self._claimed

    def claim(self) -> bool:
        """Atomically claim one callback slot."""

        with self._lock:
            if self._claimed >= self._limit:
                return False
            self._claimed += 1
            return True


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
    decision_collaborator: ProviderDecisionCollaborator | None = None
    callback_budget: ProviderCallbackBudget | None = None

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
    decision_collaborator: ProviderDecisionCollaborator | None = None,
    callback_budget: ProviderCallbackBudget | None = None,
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
        decision_collaborator=decision_collaborator,
        callback_budget=callback_budget,
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


def _non_empty_string(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ToolRegistryError(f"provider decision {field_name} is invalid")


def _fingerprint(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ToolRegistryError("provider decision fingerprint is invalid")
