"""Tests for the provider-facing tool invocation boundary."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.errors import ToolRegistryError
from dynamic_agent_runner.models import ToolDefinition
from dynamic_agent_runner.registry import InMemoryToolRegistry, RegisteredTool
from dynamic_agent_runner.retry import RetryPolicy
from dynamic_agent_runner.tool_invocation import (
    ActiveAdapterToolContext,
    coordinate_tool_invocation_async,
    tool_context,
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
