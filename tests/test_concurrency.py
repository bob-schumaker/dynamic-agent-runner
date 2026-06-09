"""Tests for concurrent workflow invocation and run correlation."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import dynamic_agent_runner.openai_client as openai_client
from dynamic_agent_runner.api import run_agent_workflow, run_agent_workflow_async
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.executor import execute_workflow, execute_workflow_async
from dynamic_agent_runner.hooks import (
    NodeHookContext,
    WorkflowHookContext,
    WorkflowLifecycleHooks,
)
from dynamic_agent_runner.models import LoadedAgentWorkflow, ToolDefinition
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    OpenAIClientAdapter,
)
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


class FakeProvider:
    def __init__(self, client: FakeClient) -> None:
        self.client = client

    def get_client(self) -> FakeClient:
        return self.client


class BlockingAsyncResponses:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        self.started.set()
        await asyncio.Event().wait()
        return {"id": "unreachable", "output_text": "unreachable"}


class BlockingAsyncClient:
    def __init__(self) -> None:
        self.responses = BlockingAsyncResponses()


class AsyncFakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        await asyncio.sleep(0)
        prompt = kwargs["input"][-1]["content"]  # type: ignore[index]
        return {"id": f"resp-{prompt}", "output_text": f"done {prompt}"}


class AsyncFakeClient:
    def __init__(self) -> None:
        self.responses = AsyncFakeResponses()


def workflow_from(data: dict[str, object]) -> LoadedAgentWorkflow:
    return LoadedAgentWorkflow(runtime_manifest=load_runtime_manifest(data))


def single_llm_workflow(
    package_id: str = "async-concurrent-agent",
) -> LoadedAgentWorkflow:
    return workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": package_id,
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


def test_async_workflow_cancellation_propagates_and_records_observations() -> None:
    async def run_and_cancel() -> None:
        workflow = single_llm_workflow("async-cancel-agent")
        client = BlockingAsyncClient()
        sink = InMemoryTraceSink()
        workflow_contexts: list[WorkflowHookContext] = []

        def after_workflow(context: WorkflowHookContext) -> None:
            workflow_contexts.append(context)

        task = asyncio.create_task(
            execute_workflow_async(
                workflow,
                prompt="cancel me",
                model_adapter=AsyncOpenAIClientAdapter(client),
                trace_sink=sink,
                lifecycle_hooks=WorkflowLifecycleHooks(after_workflow=after_workflow),
                run_id="async-cancel-run",
            )
        )
        await asyncio.wait_for(client.responses.started.wait(), timeout=1)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:  # pragma: no cover - defensive assertion path
            raise AssertionError("workflow cancellation did not propagate")

        assert client.responses.calls
        assert {event.run_id for event in sink.events} == {"async-cancel-run"}
        assert sink.events[-1].event_type == "workflow_error"
        assert sink.events[-1].payload == {
            "error": "workflow cancelled",
            "cancelled": True,
        }
        assert workflow_contexts == [
            WorkflowHookContext(run_id="async-cancel-run", error="workflow cancelled")
        ]

    asyncio.run(run_and_cancel())


def test_concurrent_async_runs_reusing_context_keep_run_correlation() -> None:
    async def run_concurrently() -> None:
        workflow = single_llm_workflow()
        sink = InMemoryTraceSink()
        hook_contexts: list[NodeHookContext] = []

        async def record_node(context: NodeHookContext) -> None:
            await asyncio.sleep(0)
            hook_contexts.append(context)

        context = WorkflowExecutionContext(
            workflow=workflow,
            model_adapter=AsyncOpenAIClientAdapter(AsyncFakeClient()),
            trace_sink=sink,
            lifecycle_hooks=WorkflowLifecycleHooks(
                before_node=record_node,
                after_node=record_node,
            ),
        )
        runs = (("one", "async-run-1"), ("two", "async-run-2"))

        results = await asyncio.gather(
            *(
                execute_workflow_async(context, prompt=prompt, run_id=run_id)
                for prompt, run_id in runs
            )
        )

        assert {result.state.prompt for result in results} == {"one", "two"}
        assert {result.state.run_id for result in results} == {
            "async-run-1",
            "async-run-2",
        }
        assert {result.final_result for result in results} == {
            "done Answer one",
            "done Answer two",
        }
        assert all(
            {event.run_id for event in result.state.trace_events}
            == {result.state.run_id}
            for result in results
        )
        assert {event.run_id for event in sink.events} == {
            "async-run-1",
            "async-run-2",
        }
        assert {context.run_id for context in hook_contexts} == {
            "async-run-1",
            "async-run-2",
        }

    asyncio.run(run_concurrently())


def test_sync_and_async_public_entry_points_preserve_observable_results() -> None:
    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "sync-async-parity-agent",
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
    sync_sink = InMemoryTraceSink()
    async_sink = InMemoryTraceSink()

    sync_result = run_agent_workflow(
        runtime_manifest=manifest,
        prompt="Hello",
        model_adapter=OpenAIClientAdapter(FakeClient()),
        trace_sink=sync_sink,
        run_id="sync-parity-run",
    )
    async_result = asyncio.run(
        run_agent_workflow_async(
            runtime_manifest=manifest,
            prompt="Hello",
            model_adapter=AsyncOpenAIClientAdapter(AsyncFakeClient()),
            trace_sink=async_sink,
            run_id="async-parity-run",
        )
    )

    assert sync_result == async_result == "done Answer Hello"
    assert [event.event_type for event in sync_sink.events] == [
        event.event_type for event in async_sink.events
    ]
    assert {event.run_id for event in sync_sink.events} == {"sync-parity-run"}
    assert {event.run_id for event in async_sink.events} == {"async-parity-run"}


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

    def create_provider() -> FakeProvider:
        with created_lock:
            client = FakeClient()
            created_clients.append(client)
            return FakeProvider(client)

    def read_client(_index: int) -> FakeClient:
        barrier.wait(timeout=5)
        return adapter.client

    monkeypatch.setattr(
        openai_client, "create_default_openai_provider", create_provider
    )
    adapter = OpenAIClientAdapter()

    with ThreadPoolExecutor(max_workers=8) as pool:
        clients = tuple(pool.map(read_client, range(8)))

    assert len(created_clients) == 1
    assert {id(client) for client in clients} == {id(created_clients[0])}


def _record_value(values: list[str], lock: Lock, value: str) -> str:
    with lock:
        values.append(value)
    return value
