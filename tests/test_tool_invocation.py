"""Tests for the provider-facing tool invocation boundary."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.errors import ToolRegistryError
from dynamic_agent_runner.models import ToolDefinition
from dynamic_agent_runner.registry import InMemoryToolRegistry, RegisteredTool
from dynamic_agent_runner.retry import RetryPolicy
from dynamic_agent_runner.tool_invocation import (
    ActiveAdapterToolContext,
    ApprovalInterruption,
    ApprovalInterruptionState,
    ProviderCallbackBudget,
    ProviderDecisionRequest,
    ProviderDecisionState,
    ProviderToolDecision,
    ProviderToolInterruption,
    coordinate_tool_invocation_async,
    provider_invocation_fingerprint,
    request_provider_tool_decision,
    tool_context,
    unwrap_provider_tool_interruption,
)
from dynamic_agent_runner.tracing import WorkflowTracer


def _tool(tool_id: str) -> RegisteredTool:
    return RegisteredTool(ToolDefinition.from_mapping({"id": tool_id}), lambda _: {})


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


def test_active_context_carries_provider_decision_and_callback_budget() -> None:
    tool = _tool("search")
    registry = InMemoryToolRegistry([tool])
    tool = registry.get_tool("search")
    budget = ProviderCallbackBudget(limit=2)

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
        callback_budget=budget,
    )

    assert context.decision_collaborator is not None
    assert context.callback_budget is budget
