from __future__ import annotations

import asyncio

import pytest

from dynamic_agent_runner.api import run_agent_workflow
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.errors import WorkflowExecutionError
from dynamic_agent_runner.executor import execute_workflow
from dynamic_agent_runner.hooks import (
    RegisteredLifecycleHook,
    ModelHookContext,
    NodeHookContext,
    ToolHookContext,
    WorkflowHookContext,
    WorkflowLifecycleHooks,
    invoke_lifecycle_hook_async,
)
from dynamic_agent_runner.models import LoadedAgentWorkflow, ToolDefinition
from dynamic_agent_runner.openai_client import OpenAIClientAdapter
from dynamic_agent_runner.registry import InMemoryToolRegistry, RegisteredTool


class FakeResponses:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses: list[object]):
        self.responses = FakeResponses(responses)


def make_adapter(responses: list[object]) -> OpenAIClientAdapter:
    return OpenAIClientAdapter(FakeClient(responses))


def workflow_from(data: dict[str, object]) -> LoadedAgentWorkflow:
    return LoadedAgentWorkflow(runtime_manifest=load_runtime_manifest(data))


def make_tool(tool_id: str, output: object) -> RegisteredTool:
    return RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": tool_id,
                "description_for_llm": f"Use {tool_id}",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ),
        lambda _args: output,
    )


def test_execute_workflow_invokes_lifecycle_hooks_in_order() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "hook-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                },
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                },
            ],
            "edges": [
                {"source": "answer", "target": "lookup", "edge_kind": "sequential"}
            ],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry([make_tool("search_repo", {"answer": "42"})])
    adapter = make_adapter([{"id": "resp", "output_text": "model answer"}])
    calls: list[tuple[str, str | None]] = []

    hooks = WorkflowLifecycleHooks(
        before_node=lambda context: calls.append(("before_node", context.node_id)),
        after_node=lambda context: calls.append(("after_node", context.node_id)),
        before_model=lambda context: calls.append(("before_model", context.node_id)),
        after_model=lambda context: calls.append(("after_model", context.node_id)),
        before_tool=lambda context: calls.append(("before_tool", context.node_id)),
        after_tool=lambda context: calls.append(("after_tool", context.node_id)),
        after_workflow=lambda context: calls.append(("after_workflow", None)),
    )

    result = execute_workflow(
        workflow,
        prompt="Run",
        tool_registry=registry,
        model_adapter=adapter,
        lifecycle_hooks=hooks,
    )

    assert result.final_result == {"answer": "42"}
    assert calls == [
        ("before_node", "answer"),
        ("before_model", "answer"),
        ("after_model", "answer"),
        ("after_node", "answer"),
        ("before_node", "lookup"),
        ("before_tool", "lookup"),
        ("after_tool", "lookup"),
        ("after_node", "lookup"),
        ("after_workflow", None),
    ]


def test_lifecycle_hook_contexts_include_stable_observation_fields() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "hook-context-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry([make_tool("search_repo", {"answer": "42"})])
    seen: dict[str, object] = {}

    def before_node(context: NodeHookContext) -> None:
        seen["before_node"] = context

    def before_tool(context: ToolHookContext) -> None:
        seen["before_tool"] = context

    def after_tool(context: ToolHookContext) -> None:
        seen["after_tool"] = context

    def after_workflow(context: WorkflowHookContext) -> None:
        seen["after_workflow"] = context

    hooks = WorkflowLifecycleHooks(
        before_node=before_node,
        before_tool=before_tool,
        after_tool=after_tool,
        after_workflow=after_workflow,
    )

    result = execute_workflow(
        workflow,
        prompt="Run",
        tool_registry=registry,
        lifecycle_hooks=hooks,
    )
    run_id = result.state.run_id

    assert seen["before_node"] == NodeHookContext(
        node_id="lookup", kind="tool_use_step", run_id=run_id
    )
    assert seen["before_tool"] == ToolHookContext(
        node_id="lookup",
        tool_id="search_repo",
        arguments={"query": "agents"},
        run_id=run_id,
    )
    after_tool_context = seen["after_tool"]
    assert isinstance(after_tool_context, ToolHookContext)
    assert after_tool_context.node_id == "lookup"
    assert after_tool_context.tool_id == "search_repo"
    assert after_tool_context.result is not None
    assert after_tool_context.run_id == run_id
    workflow_context = seen["after_workflow"]
    assert isinstance(workflow_context, WorkflowHookContext)
    assert workflow_context.final_result == {"answer": "42"}
    assert workflow_context.run_id == run_id


def test_run_agent_workflow_accepts_lifecycle_hooks() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "api-hook-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                }
            ],
            "edges": [],
        }
    )
    calls: list[str] = []
    context = WorkflowExecutionContext(
        workflow=workflow,
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
        lifecycle_hooks=WorkflowLifecycleHooks(
            after_workflow=lambda _context: calls.append("after_workflow")
        ),
    )

    result = run_agent_workflow(prompt="Hello", execution_context=context)

    assert result == "done"
    assert calls == ["after_workflow"]


def test_lifecycle_hook_failures_abort_execution() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "hook-failure-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    def fail(_context: ModelHookContext) -> None:
        raise WorkflowExecutionError("hook blocked model")

    with pytest.raises(WorkflowExecutionError, match="hook blocked model"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=adapter,
            lifecycle_hooks=WorkflowLifecycleHooks(before_model=fail),
        )

    assert adapter.client.responses.calls == []


def test_lifecycle_hooks_record_callable_shape_metadata() -> None:
    async def before_node(_context: NodeHookContext) -> None:
        return None

    def after_node(_context: NodeHookContext) -> None:
        return None

    hooks = WorkflowLifecycleHooks(
        before_node=before_node,
        after_node=after_node,
    )

    before_hook = hooks.registered_hook("before_node")
    after_hook = hooks.registered_hook("after_node")

    assert before_hook == RegisteredLifecycleHook(
        name="before_node",
        callback=before_node,
        callback_is_async=True,
    )
    assert after_hook == RegisteredLifecycleHook(
        name="after_node",
        callback=after_node,
        callback_is_async=False,
    )
    assert hooks.registered_hook("before_tool") is None


def test_async_lifecycle_hook_invocation_awaits_async_hook() -> None:
    calls: list[tuple[str, str | None]] = []

    async def before_node(context: NodeHookContext) -> None:
        await asyncio.sleep(0)
        calls.append(("before_node", context.run_id))

    hooks = WorkflowLifecycleHooks(before_node=before_node)

    asyncio.run(
        invoke_lifecycle_hook_async(
            hooks.registered_hook("before_node"),
            NodeHookContext(node_id="answer", kind="llm_step", run_id="run-123"),
        )
    )

    assert calls == [("before_node", "run-123")]


def test_async_lifecycle_hook_invocation_preserves_sync_hook_support() -> None:
    calls: list[tuple[str, str | None]] = []

    def after_tool(context: ToolHookContext) -> None:
        calls.append(("after_tool", context.run_id))

    hooks = WorkflowLifecycleHooks(after_tool=after_tool)

    asyncio.run(
        invoke_lifecycle_hook_async(
            hooks.registered_hook("after_tool"),
            ToolHookContext(
                node_id="lookup",
                tool_id="search_repo",
                run_id="run-456",
            ),
        )
    )

    assert calls == [("after_tool", "run-456")]


def test_async_lifecycle_hook_invocation_propagates_hook_errors() -> None:
    async def after_model(_context: ModelHookContext) -> None:
        raise WorkflowExecutionError("async hook blocked model")

    hooks = WorkflowLifecycleHooks(after_model=after_model)

    with pytest.raises(WorkflowExecutionError, match="async hook blocked model"):
        asyncio.run(
            invoke_lifecycle_hook_async(
                hooks.registered_hook("after_model"),
                ModelHookContext(node_id="answer", model="gpt-test"),
            )
        )


def test_execute_workflow_awaits_async_lifecycle_hooks() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "async-hook-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                },
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                },
            ],
            "edges": [
                {"source": "answer", "target": "lookup", "edge_kind": "sequential"}
            ],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry([make_tool("search_repo", {"answer": "42"})])
    adapter = make_adapter([{"id": "resp", "output_text": "model answer"}])
    calls: list[tuple[str, str | None]] = []

    async def before_node(context: NodeHookContext) -> None:
        await asyncio.sleep(0)
        calls.append(("before_node", context.node_id))

    async def after_node(context: NodeHookContext) -> None:
        await asyncio.sleep(0)
        calls.append(("after_node", context.node_id))

    async def before_model(context: ModelHookContext) -> None:
        await asyncio.sleep(0)
        calls.append(("before_model", context.node_id))

    async def after_model(context: ModelHookContext) -> None:
        await asyncio.sleep(0)
        calls.append(("after_model", context.node_id))

    async def before_tool(context: ToolHookContext) -> None:
        await asyncio.sleep(0)
        calls.append(("before_tool", context.node_id))

    async def after_tool(context: ToolHookContext) -> None:
        await asyncio.sleep(0)
        calls.append(("after_tool", context.node_id))

    hooks = WorkflowLifecycleHooks(
        before_node=before_node,
        after_node=after_node,
        before_model=before_model,
        after_model=after_model,
        before_tool=before_tool,
        after_tool=after_tool,
    )

    result = execute_workflow(
        workflow,
        prompt="Run",
        tool_registry=registry,
        model_adapter=adapter,
        lifecycle_hooks=hooks,
    )

    assert result.final_result == {"answer": "42"}
    assert calls == [
        ("before_node", "answer"),
        ("before_model", "answer"),
        ("after_model", "answer"),
        ("after_node", "answer"),
        ("before_node", "lookup"),
        ("before_tool", "lookup"),
        ("after_tool", "lookup"),
        ("after_node", "lookup"),
    ]
