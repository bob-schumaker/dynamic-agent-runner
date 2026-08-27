"""Tests for the provider-facing tool invocation boundary."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.errors import ToolRegistryError
from dynamic_agent_runner.hooks import WorkflowLifecycleHooks
from dynamic_agent_runner.models import ToolDefinition
from dynamic_agent_runner.registry import (
    InMemoryToolRegistry,
    RegisteredTool,
    ToolResult,
)
from dynamic_agent_runner.retry import RetryPolicy
from dynamic_agent_runner.tool_invocation import (
    ActiveAdapterToolContext,
    ApprovalInterruption,
    ApprovalInterruptionState,
    ProviderCallbackBudget,
    ProviderDecisionRequest,
    ProviderDecisionState,
    ProviderToolDecision,
    ProviderToolDecisionTerminalOutcome,
    ProviderToolInterruption,
    coordinate_tool_invocation_async,
    provider_invocation_fingerprint,
    request_provider_tool_decision,
    tool_context,
    unwrap_provider_tool_interruption,
)
from dynamic_agent_runner.tracing import WorkflowTracer


def _tool(
    tool_id: str,
    *,
    approval_required: bool = False,
    input_schema: dict[str, object] | None = None,
) -> RegisteredTool:
    definition: dict[str, object] = {"id": tool_id}
    if approval_required:
        definition["approval_required"] = "yes"
    if input_schema is not None:
        definition["input_schema"] = input_schema
    return RegisteredTool(ToolDefinition.from_mapping(definition), lambda _: {})


def _context(registry: InMemoryToolRegistry, tool: RegisteredTool):
    return tool_context(
        plan=SimpleNamespace(),
        node=SimpleNamespace(id="node"),
        tools=(tool,),
        registry=registry,
        state=SimpleNamespace(run_id="run", tool_results={}),
        tracer=WorkflowTracer(events=[]),
        lifecycle_hooks=None,
        retry_policy=RetryPolicy(),
    )


def _approval_context(
    registry: InMemoryToolRegistry,
    tool: RegisteredTool,
    collaborator: object,
    *,
    hooks: WorkflowLifecycleHooks | None = None,
):
    state = SimpleNamespace(run_id="run", tool_results={}, trace_events=[])
    return tool_context(
        plan=SimpleNamespace(
            workflow=SimpleNamespace(
                runtime_manifest=SimpleNamespace(package_id="workflow")
            )
        ),
        node=SimpleNamespace(id="node"),
        tools=(tool,),
        registry=registry,
        state=state,
        tracer=WorkflowTracer(events=state.trace_events),
        lifecycle_hooks=hooks,
        retry_policy=RetryPolicy(),
        decision_collaborator=collaborator,  # type: ignore[arg-type]
    )


def test_tool_context_rejects_raw_model_tool_descriptor() -> None:
    tool = _tool("search")
    registry = InMemoryToolRegistry([tool])

    with pytest.raises(ToolRegistryError, match="RegisteredTool"):
        tool_context(
            plan=SimpleNamespace(),
            node=SimpleNamespace(id="node"),
            tools=({"name": "search", "parameters": {}},),  # type: ignore[arg-type]
            registry=registry,
            state=SimpleNamespace(run_id="run", tool_results={}),
            tracer=WorkflowTracer(events=[]),
            lifecycle_hooks=None,
            retry_policy=RetryPolicy(),
        )


def test_active_tool_context_rejects_raw_model_tool_descriptor() -> None:
    tool = _tool("search")
    registry = InMemoryToolRegistry([tool])

    with pytest.raises(ToolRegistryError, match="RegisteredTool"):
        ActiveAdapterToolContext(
            plan=SimpleNamespace(),
            node=SimpleNamespace(id="node"),
            tools=({"name": "search", "parameters": {}},),  # type: ignore[arg-type]
            registry=registry,
            state=SimpleNamespace(run_id="run", tool_results={}),
            tracer=WorkflowTracer(events=[]),
            lifecycle_hooks=None,
            retry_policy=RetryPolicy(),
        )


def test_stale_tool_context_fails_before_invocation_closure_runs() -> None:
    original = _tool("search")
    registry = InMemoryToolRegistry([original])
    original = registry.get_tool("search")
    context = _context(registry, original)
    registry.register(_tool("search"), replace=True)
    invoked: list[object] = []

    with pytest.raises(ToolRegistryError, match="no longer matches"):
        asyncio.run(
            coordinate_tool_invocation_async(
                context.request(
                    tool_id="search",
                    arguments={},
                    result_key="node.call",
                    invoke=lambda _prepared: _record_invocation(invoked),
                    approval_reason="test",
                )
            )
        )

    assert invoked == []


async def _record_invocation(invoked: list[object]):
    invoked.append(True)
    raise AssertionError("stale invocation closure must not run")


def test_provider_interruption_redacts_approval_arguments() -> None:
    approval = ApprovalInterruption(
        interruption_id="approval-1",
        run_id="run-1",
        workflow_id="workflow-1",
        node_id="node-1",
        tool_id="send_email",
        action_id="call-1",
        arguments={"recipient": "private@example.com"},
        policy={"approval_required": "yes"},
        reason="approval required",
    )
    interruption = ProviderToolInterruption(approval)

    assert interruption.interruption_id == "approval-1"
    assert interruption.tool_id == "send_email"
    assert interruption.state is ApprovalInterruptionState.PENDING
    assert "private@example.com" not in repr(interruption)
    assert "private@example.com" not in str(interruption)
    assert not hasattr(interruption, "approval")
    assert unwrap_provider_tool_interruption(interruption) is approval


def test_provider_decision_binds_a_canonical_normalized_fingerprint() -> None:
    tool = _tool("send_email")
    registry = InMemoryToolRegistry([tool])
    fingerprint = provider_invocation_fingerprint(
        run_id="run-1",
        workflow_id="workflow-1",
        node_id="node-1",
        action_id="call-1",
        prepared=registry.prepare_tool_invocation(
            "send_email",
            {"subject": "Hello", "recipients": ["a@example.com"]},
        ),
    )
    equivalent_fingerprint = provider_invocation_fingerprint(
        run_id="run-1",
        workflow_id="workflow-1",
        node_id="node-1",
        action_id="call-1",
        prepared=registry.prepare_tool_invocation(
            "send_email",
            {"recipients": ["a@example.com"], "subject": "Hello"},
        ),
    )
    request = ProviderDecisionRequest(
        invocation_id="provider-call-1", fingerprint=fingerprint
    )
    received: list[ProviderDecisionRequest] = []

    class Collaborator:
        def decide(self, supplied: ProviderDecisionRequest) -> ProviderToolDecision:
            received.append(supplied)
            return ProviderToolDecision(
                state=ProviderDecisionState.APPROVED,
                invocation_id=supplied.invocation_id,
                fingerprint=supplied.fingerprint,
            )

    decision = request_provider_tool_decision(Collaborator(), request)

    assert fingerprint == equivalent_fingerprint
    assert received == [request]
    assert decision.state is ProviderDecisionState.APPROVED
    assert decision.fingerprint == fingerprint

    class MismatchedCollaborator:
        def decide(self, supplied: ProviderDecisionRequest) -> ProviderToolDecision:
            return ProviderToolDecision(
                state=ProviderDecisionState.APPROVED,
                invocation_id="different-call",
                fingerprint=supplied.fingerprint,
            )

    with pytest.raises(ToolRegistryError, match="does not match"):
        request_provider_tool_decision(
            MismatchedCollaborator(),
            request,
        )

    class MismatchedFingerprintCollaborator:
        def decide(self, supplied: ProviderDecisionRequest) -> ProviderToolDecision:
            return ProviderToolDecision(
                state=ProviderDecisionState.APPROVED,
                invocation_id=supplied.invocation_id,
                fingerprint="0" * 64,
            )

    with pytest.raises(ToolRegistryError, match="does not match"):
        request_provider_tool_decision(MismatchedFingerprintCollaborator(), request)

    with pytest.raises(ToolRegistryError, match="PreparedToolInvocation"):
        provider_invocation_fingerprint(
            run_id="run-1",
            workflow_id="workflow-1",
            node_id="node-1",
            action_id="call-1",
            prepared=SimpleNamespace(
                arguments={}, tool=SimpleNamespace(id="send_email")
            ),
        )


def test_provider_callback_budget_claims_a_bounded_number_of_callbacks() -> None:
    budget = ProviderCallbackBudget(limit=3)

    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(lambda _: budget.claim(), range(8)))

    assert sum(claims) == 3
    assert claims.count(False) == 5
    assert budget.claimed == 3


def test_active_context_carries_provider_decision_collaborator() -> None:
    tool = _tool("search")
    registry = InMemoryToolRegistry([tool])
    tool = registry.get_tool("search")

    class Collaborator:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            return ProviderToolDecision(
                state=ProviderDecisionState.UNRESOLVED,
                invocation_id=request.invocation_id,
                fingerprint=request.fingerprint,
            )

    context = tool_context(
        plan=SimpleNamespace(),
        node=SimpleNamespace(id="node"),
        tools=(tool,),
        registry=registry,
        state=SimpleNamespace(run_id="run", tool_results={}),
        tracer=WorkflowTracer(events=[]),
        lifecycle_hooks=None,
        retry_policy=RetryPolicy(),
        decision_collaborator=Collaborator(),
    )

    assert context.decision_collaborator is not None


@pytest.mark.parametrize(
    "decision_state",
    [
        ProviderDecisionState.DENIED,
        ProviderDecisionState.CANCELLED,
        ProviderDecisionState.EXPIRED,
        ProviderDecisionState.UNRESOLVED,
    ],
)
def test_non_approved_provider_decisions_stop_before_hooks_or_dispatch(
    decision_state: ProviderDecisionState,
) -> None:
    tool = _tool("write", approval_required=True)
    registry = InMemoryToolRegistry([tool])
    tool = registry.get_tool("write")
    order: list[str] = []
    invoked: list[object] = []
    hooks: list[str] = []

    class Collaborator:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            order.append("decision")
            return ProviderToolDecision(
                state=decision_state,
                invocation_id=request.invocation_id,
                fingerprint=request.fingerprint,
            )

    context = _approval_context(
        registry,
        tool,
        Collaborator(),
        hooks=WorkflowLifecycleHooks(
            before_tool=lambda _context: hooks.append("before"),
            after_tool=lambda _context: hooks.append("after"),
        ),
    )

    result = asyncio.run(
        coordinate_tool_invocation_async(
            context.request(
                tool_id="write",
                arguments={"path": "notes.txt"},
                result_key="node.call-1",
                action_id="call-1",
                approval_reason="test",
                guardrail_runner=lambda _prepared: order.append("guardrail"),
                invoke=lambda _prepared: _record_result(invoked),
            )
        )
    )

    assert order == ["guardrail", "decision"]
    assert hooks == []
    assert invoked == []
    assert context.state.tool_results == {}
    if decision_state is ProviderDecisionState.UNRESOLVED:
        assert isinstance(result, ApprovalInterruption)
        assert result.state is ApprovalInterruptionState.PENDING
        assert [event.event_type for event in context.state.trace_events] == [
            "approval_requested",
            "approval_paused",
        ]
    else:
        assert isinstance(result, ProviderToolDecisionTerminalOutcome)
        assert result.state is decision_state
        assert context.state.trace_events == []


def test_approved_provider_decision_dispatches_prepared_arguments_once() -> None:
    tool = _tool(
        "write",
        approval_required=True,
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
    registry = InMemoryToolRegistry([tool])
    tool = registry.get_tool("write")
    decisions: list[ProviderDecisionRequest] = []
    invoked: list[object] = []
    hooks: list[str] = []

    class Collaborator:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            decisions.append(request)
            return ProviderToolDecision(
                state=ProviderDecisionState.APPROVED,
                invocation_id=request.invocation_id,
                fingerprint=request.fingerprint,
            )

    context = _approval_context(
        registry,
        tool,
        Collaborator(),
        hooks=WorkflowLifecycleHooks(
            before_tool=lambda _context: hooks.append("before"),
            after_tool=lambda _context: hooks.append("after"),
        ),
    )
    result = asyncio.run(
        coordinate_tool_invocation_async(
            context.request(
                tool_id="write",
                arguments={"path": "notes.txt"},
                result_key="node.call-1",
                action_id="call-1",
                approval_reason="test",
                invoke=lambda prepared: _record_prepared_result(invoked, prepared),
            )
        )
    )

    assert result.success
    assert len(decisions) == 1
    assert decisions[0].invocation_id == "call-1"
    assert decisions[0].fingerprint == provider_invocation_fingerprint(
        run_id="run",
        workflow_id="workflow",
        node_id="node",
        action_id="call-1",
        prepared=registry.prepare_tool_invocation("write", {"path": "notes.txt"}),
    )
    assert invoked == [{"path": "notes.txt"}]
    assert hooks == ["before", "after"]
    assert context.state.tool_results == {"node.call-1": result}


def test_provider_decision_requires_valid_arguments_before_collaborator() -> None:
    tool = _tool(
        "write",
        approval_required=True,
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
    registry = InMemoryToolRegistry([tool])
    tool = registry.get_tool("write")
    decisions: list[ProviderDecisionRequest] = []

    class Collaborator:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            decisions.append(request)
            raise AssertionError("invalid arguments must not reach collaborator")

    context = _approval_context(registry, tool, Collaborator())

    with pytest.raises(ToolRegistryError, match="missing required"):
        asyncio.run(
            coordinate_tool_invocation_async(
                context.request(
                    tool_id="write",
                    arguments={},
                    result_key="node.call-1",
                    action_id="call-1",
                    approval_reason="test",
                    invoke=lambda _prepared: _record_result([]),
                )
            )
        )

    assert decisions == []


def test_provider_decision_replay_and_mismatch_fail_closed() -> None:
    tool = _tool("write", approval_required=True)
    registry = InMemoryToolRegistry([tool])
    tool = registry.get_tool("write")
    decisions: list[ProviderDecisionRequest] = []
    invoked: list[object] = []

    class Collaborator:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            decisions.append(request)
            return ProviderToolDecision(
                state=ProviderDecisionState.APPROVED,
                invocation_id=request.invocation_id,
                fingerprint=request.fingerprint,
            )

    context = _approval_context(registry, tool, Collaborator())
    request = context.request(
        tool_id="write",
        arguments={"path": "notes.txt"},
        result_key="node.call-1",
        action_id="call-1",
        approval_reason="test",
        invoke=lambda _prepared: _record_result(invoked),
    )

    asyncio.run(coordinate_tool_invocation_async(request))

    with pytest.raises(ToolRegistryError, match="already used"):
        asyncio.run(coordinate_tool_invocation_async(request))

    assert len(decisions) == 1
    assert invoked == [True]


@pytest.mark.parametrize("invalid_response", [False, True])
def test_mismatched_or_unknown_provider_decision_fails_before_dispatch(
    invalid_response: bool,
) -> None:
    tool = _tool("write", approval_required=True)
    registry = InMemoryToolRegistry([tool])
    tool = registry.get_tool("write")
    invoked: list[object] = []
    hooks: list[str] = []

    class Collaborator:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            if invalid_response:
                return object()  # type: ignore[return-value]
            return ProviderToolDecision(
                state=ProviderDecisionState.APPROVED,
                invocation_id="other-call",
                fingerprint=request.fingerprint,
            )

    context = _approval_context(
        registry,
        tool,
        Collaborator(),
        hooks=WorkflowLifecycleHooks(
            before_tool=lambda _context: hooks.append("before"),
            after_tool=lambda _context: hooks.append("after"),
        ),
    )

    with pytest.raises(ToolRegistryError, match="invalid value|does not match"):
        asyncio.run(
            coordinate_tool_invocation_async(
                context.request(
                    tool_id="write",
                    arguments={"path": "notes.txt"},
                    result_key="node.call-1",
                    action_id="call-1",
                    approval_reason="test",
                    invoke=lambda _prepared: _record_result(invoked),
                )
            )
        )

    assert hooks == []
    assert invoked == []
    assert context.state.tool_results == {}


def test_unexposed_provider_tool_fails_before_decision_resolution() -> None:
    read = _tool("read")
    write = _tool("write", approval_required=True)
    registry = InMemoryToolRegistry([read, write])
    read = registry.get_tool("read")
    decisions: list[ProviderDecisionRequest] = []

    class Collaborator:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            decisions.append(request)
            raise AssertionError("unexposed tool must not reach collaborator")

    context = _approval_context(registry, read, Collaborator())

    with pytest.raises(ToolRegistryError, match="not active"):
        asyncio.run(
            coordinate_tool_invocation_async(
                context.request(
                    tool_id="write",
                    arguments={"path": "notes.txt"},
                    result_key="node.call-1",
                    action_id="call-1",
                    approval_reason="test",
                    invoke=lambda _prepared: _record_result([]),
                )
            )
        )

    assert decisions == []


def test_continuation_guard_rejects_result_after_handler_before_state_write() -> None:
    invocations: list[object] = []
    hook_events: list[str] = []
    active = True
    tool = _tool("write")
    registry = InMemoryToolRegistry([tool])
    state = SimpleNamespace(run_id="run", tool_results={}, trace_events=[])
    context = tool_context(
        plan=SimpleNamespace(),
        node=SimpleNamespace(id="node"),
        tools=(registry.get_tool("write"),),
        registry=registry,
        state=state,
        tracer=WorkflowTracer(events=state.trace_events),
        lifecycle_hooks=WorkflowLifecycleHooks(
            before_tool=lambda _context: hook_events.append("before"),
            after_tool=lambda _context: hook_events.append("after"),
        ),
        retry_policy=RetryPolicy(),
    )

    def require_active() -> None:
        if not active:
            raise ToolRegistryError("Apple callback session is no longer active")

    async def invoke(_prepared: object) -> ToolResult:
        nonlocal active
        invocations.append(True)
        active = False
        return ToolResult(tool_id="write", success=True, output={"ok": True})

    with pytest.raises(ToolRegistryError, match="session is no longer active"):
        asyncio.run(
            coordinate_tool_invocation_async(
                context.request(
                    tool_id="write",
                    arguments={},
                    result_key="node.call-1",
                    approval_reason="test",
                    continuation_guard=require_active,
                    invoke=invoke,
                )
            )
        )

    assert invocations == [True]
    assert hook_events == ["before"]
    assert state.tool_results == {}
    assert [event.event_type for event in state.trace_events] == ["tool_started"]


def test_continuation_guard_rejects_cancellation_before_handler_dispatch() -> None:
    invocations: list[object] = []
    active = True
    tool = _tool("write")
    registry = InMemoryToolRegistry([tool])
    state = SimpleNamespace(run_id="run", tool_results={}, trace_events=[])

    def require_active() -> None:
        if not active:
            raise ToolRegistryError("Apple callback session is no longer active")

    def cancel_before_dispatch(_context: object) -> None:
        nonlocal active
        active = False

    async def invoke(_prepared: object) -> ToolResult:
        invocations.append(True)
        return ToolResult(tool_id="write", success=True, output={"ok": True})

    context = tool_context(
        plan=SimpleNamespace(),
        node=SimpleNamespace(id="node"),
        tools=(registry.get_tool("write"),),
        registry=registry,
        state=state,
        tracer=WorkflowTracer(events=state.trace_events),
        lifecycle_hooks=WorkflowLifecycleHooks(before_tool=cancel_before_dispatch),
        retry_policy=RetryPolicy(),
    )

    with pytest.raises(ToolRegistryError, match="session is no longer active"):
        asyncio.run(
            coordinate_tool_invocation_async(
                context.request(
                    tool_id="write",
                    arguments={},
                    result_key="node.call-1",
                    approval_reason="test",
                    continuation_guard=require_active,
                    invoke=invoke,
                )
            )
        )

    assert invocations == []
    assert state.tool_results == {}
    assert [event.event_type for event in state.trace_events] == ["tool_started"]


def test_result_commit_guard_rejects_closure_before_state_and_trace_writes() -> None:
    invocations: list[object] = []
    hook_events: list[str] = []
    tool = _tool("write")
    registry = InMemoryToolRegistry([tool])
    state = SimpleNamespace(run_id="run", tool_results={}, trace_events=[])

    @contextmanager
    def closed_result_commit_guard():
        raise ToolRegistryError("Apple callback session is no longer active")
        yield

    async def invoke(_prepared: object) -> ToolResult:
        invocations.append(True)
        return ToolResult(tool_id="write", success=True, output={"ok": True})

    context = tool_context(
        plan=SimpleNamespace(),
        node=SimpleNamespace(id="node"),
        tools=(registry.get_tool("write"),),
        registry=registry,
        state=state,
        tracer=WorkflowTracer(events=state.trace_events),
        lifecycle_hooks=WorkflowLifecycleHooks(
            before_tool=lambda _context: hook_events.append("before"),
            after_tool=lambda _context: hook_events.append("after"),
        ),
        retry_policy=RetryPolicy(),
    )

    with pytest.raises(ToolRegistryError, match="session is no longer active"):
        asyncio.run(
            coordinate_tool_invocation_async(
                context.request(
                    tool_id="write",
                    arguments={},
                    result_key="node.call-1",
                    approval_reason="test",
                    result_commit_guard=closed_result_commit_guard,
                    invoke=invoke,
                )
            )
        )

    assert invocations == [True]
    assert hook_events == ["before"]
    assert state.tool_results == {}
    assert [event.event_type for event in state.trace_events] == ["tool_started"]


async def _record_result(invoked: list[object]) -> ToolResult:
    invoked.append(True)
    return ToolResult(tool_id="write", success=True, output={"ok": True})


async def _record_prepared_result(
    invoked: list[object], prepared: object
) -> ToolResult:
    assert prepared is not None
    invoked.append(dict(prepared.arguments))  # type: ignore[union-attr]
    return ToolResult(tool_id="write", success=True, output={"ok": True})
