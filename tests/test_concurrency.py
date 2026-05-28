"""Tests for concurrent workflow invocation and run correlation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import dynamic_agent_runner.openai_client as openai_client
from dynamic_agent_runner.api import run_agent_workflow
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.executor import execute_workflow
from dynamic_agent_runner.hooks import NodeHookContext, WorkflowLifecycleHooks
from dynamic_agent_runner.models import LoadedAgentWorkflow, ToolDefinition
from dynamic_agent_runner.openai_client import OpenAIClientAdapter
from dynamic_agent_runner.registry import InMemoryToolRegistry, RegisteredTool
from dynamic_agent_runner.tracing import InMemoryTraceSink


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._lock = Lock()

    def create(self, **kwargs: object) -> object:
        with self._lock:
            self.calls.append(kwargs)
        prompt = kwargs["input"][-1]["content"]  # type: ignore[index]
        return {"id": f"resp-{prompt}", "output_text": f"done {prompt}"}


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def workflow_from(data: dict[str, object]) -> LoadedAgentWorkflow:
    return LoadedAgentWorkflow(runtime_manifest=load_runtime_manifest(data))


def test_concurrent_runs_reusing_context_keep_run_state_and_trace_ids_isolated() -> (
    None
):
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "concurrent-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
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
    sink = InMemoryTraceSink()
    hook_contexts: list[NodeHookContext] = []
    hook_lock = Lock()

    def record_node(context: NodeHookContext) -> None:
        with hook_lock:
            hook_contexts.append(context)

    context = WorkflowExecutionContext(
        workflow=workflow,
        model_adapter=OpenAIClientAdapter(FakeClient()),
        trace_sink=sink,
        lifecycle_hooks=WorkflowLifecycleHooks(before_node=record_node),
    )
    run_ids = ("qt-thread-agent-1", "qt-thread-agent-2")
    barrier = Barrier(len(run_ids))

    def run(prompt: str, run_id: str) -> object:
        barrier.wait(timeout=5)
        return execute_workflow(context, prompt=prompt, run_id=run_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(
                lambda item: run(*item),
                (("one", run_ids[0]), ("two", run_ids[1])),
            )
        )

    assert {result.state.prompt for result in results} == {"one", "two"}
    assert {result.state.run_id for result in results} == set(run_ids)
    assert all(
        {event.run_id for event in result.state.trace_events} == {result.state.run_id}
        for result in results
    )
    assert {event.run_id for event in sink.events} == set(run_ids)
    assert {context.run_id for context in hook_contexts} == set(run_ids)


def test_in_memory_registry_allows_concurrent_invocation_and_registration() -> None:
    registry = InMemoryToolRegistry()
    observed: list[str] = []
    observed_lock = Lock()

    def make_recording_tool(tool_id: str) -> RegisteredTool:
        return RegisteredTool(
            ToolDefinition.from_mapping(
                {
                    "id": tool_id,
                    "input_schema": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "required": ["value"],
                    },
                }
            ),
            lambda args: _record_value(observed, observed_lock, str(args["value"])),
        )

    def register_and_invoke(index: int) -> object:
        tool_id = f"tool_{index}"
        registry.register(make_recording_tool(tool_id))
        return registry.invoke_tool(tool_id, {"value": tool_id})

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = tuple(pool.map(register_and_invoke, range(12)))

    assert all(result.success for result in results)
    assert set(observed) == {f"tool_{index}" for index in range(12)}


def test_run_agent_workflow_forwards_run_id_to_trace_events() -> None:
    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "api-run-id-agent",
        "entrypoint": "answer",
        "packaging": {"mode": "hybrid_bundle"},
        "execution_policy": {"model": "gpt-test"},
        "nodes": [
            {
                "id": "answer",
                "kind": "llm_step",
                "prompt": {"user_template": "Answer {prompt}"},
            }
        ],
        "edges": [],
    }
    sink = InMemoryTraceSink()

    result = run_agent_workflow(
        runtime_manifest=manifest,
        prompt="Hello",
        model_adapter=OpenAIClientAdapter(FakeClient()),
        trace_sink=sink,
        run_id="qt-thread-agent-3",
    )

    assert result == "done Answer Hello"
    assert {event.run_id for event in sink.events} == {"qt-thread-agent-3"}


def test_openai_client_adapter_initializes_default_client_once_across_threads(
    monkeypatch,
) -> None:
    created_clients: list[FakeClient] = []
    created_lock = Lock()
    barrier = Barrier(8)

    def create_client() -> FakeClient:
        with created_lock:
            client = FakeClient()
            created_clients.append(client)
            return client

    def read_client(_index: int) -> FakeClient:
        barrier.wait(timeout=5)
        return adapter.client

    monkeypatch.setattr(openai_client, "create_default_openai_client", create_client)
    adapter = OpenAIClientAdapter()

    with ThreadPoolExecutor(max_workers=8) as pool:
        clients = tuple(pool.map(read_client, range(8)))

    assert len(created_clients) == 1
    assert {id(client) for client in clients} == {id(created_clients[0])}


def _record_value(values: list[str], lock: Lock, value: str) -> str:
    with lock:
        values.append(value)
    return value
