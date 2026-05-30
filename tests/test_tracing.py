"""Tests for workflow trace event behavior."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.errors import ModelExecutionError, WorkflowExecutionError
from dynamic_agent_runner.executor import execute_workflow
from dynamic_agent_runner.models import (
    LoadedAgentWorkflow,
    ToolDefinition,
    ToolSource,
    ToolSourceKind,
)
from dynamic_agent_runner.openai_client import OpenAIClientAdapter
from dynamic_agent_runner.registry import InMemoryToolRegistry, RegisteredTool
from dynamic_agent_runner.tracing import InMemoryTraceSink


class FakeResponses:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)

    def create(self, **_kwargs: object) -> object:
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


def make_tool(tool_id: str, outputs: list[object]) -> RegisteredTool:
    tool_raw: dict[str, object] = {
        "id": tool_id,
        "description_for_llm": f"Use {tool_id}",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }

    def handler(_args: object) -> object:
        output = outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output

    return RegisteredTool(ToolDefinition.from_mapping(tool_raw), handler)


def test_execute_workflow_emits_success_trace_events_in_order() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "trace-success-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "token_budget": {
                        "model": "gpt-4o-mini",
                        "max_prompt_tokens": 1000,
                    },
                }
            },
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

    result = execute_workflow(
        workflow,
        prompt="secret prompt",
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
        trace_sink=sink,
    )

    event_types = [event.event_type for event in result.state.trace_events]
    assert event_types == [
        "workflow_started",
        "node_started",
        "token_budget_checked",
        "model_request",
        "retry_recorded",
        "model_response",
        "node_completed",
        "workflow_completed",
    ]
    assert [event.sequence for event in result.state.trace_events] == list(range(1, 9))
    assert sink.events == result.state.trace_events
    assert result.state.trace_events[0].redacted_payload()["prompt"] == "[REDACTED]"
    assert (
        result.state.trace_events[-1].redacted_payload()["final_result"] == "[REDACTED]"
    )


def test_model_request_trace_includes_model_exposed_tool_sources() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "trace-tool-source-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "available_tools": ["search_repo"],
                }
            ],
            "edges": [],
        }
    )
    tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "search_repo",
                "description_for_llm": "Search repository files.",
                "input_schema": {"type": "object", "properties": {}},
                "source": {
                    "kind": "caller_registered",
                    "source_id": "test-suite",
                    "detail": "fixture",
                },
            }
        ),
        lambda _args: {"ok": True},
    )

    result = execute_workflow(
        workflow,
        prompt="Run",
        tool_registry=InMemoryToolRegistry([tool]),
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
    )

    model_request = next(
        event
        for event in result.state.trace_events
        if event.event_type == "model_request"
    )
    assert model_request.payload["tool_sources"] == {
        "search_repo": ToolSource(
            kind=ToolSourceKind.CALLER_REGISTERED,
            source_id="test-suite",
            detail="fixture",
        ).to_mapping()
    }


def test_execute_workflow_traces_tool_failure() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "trace-tool-failure-agent",
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
    registry = InMemoryToolRegistry(
        [make_tool("search_repo", [RuntimeError("tool exploded")])]
    )
    sink = InMemoryTraceSink()

    with pytest.raises(WorkflowExecutionError, match="tool exploded"):
        execute_workflow(
            workflow,
            prompt="Run",
            tool_registry=registry,
            trace_sink=sink,
        )

    event_types = [event.event_type for event in sink.events]
    assert event_types == [
        "workflow_started",
        "node_started",
        "tool_started",
        "tool_invocation",
        "retry_recorded",
        "tool_result",
        "tool_finished",
        "node_error",
    ]
    assert sink.events[-4].payload["operation"] == "tool"
    assert sink.events[-4].payload["outcome"] == "success"
    assert sink.events[-3].payload["success"] is False
    assert sink.events[-3].payload["error"] == "tool exploded"
    assert sink.events[-2].payload == {
        "tool_id": "search_repo",
        "success": False,
        "error": "tool exploded",
    }
    assert sink.events[-1].payload["error"] == "tool exploded"


def test_execute_workflow_emits_tool_lifecycle_trace_events() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "trace-tool-lifecycle-agent",
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
    registry = InMemoryToolRegistry([make_tool("search_repo", [{"answer": "42"}])])

    result = execute_workflow(workflow, prompt="Run", tool_registry=registry)

    event_types = [event.event_type for event in result.state.trace_events]
    assert event_types == [
        "workflow_started",
        "node_started",
        "tool_started",
        "tool_invocation",
        "retry_recorded",
        "tool_result",
        "tool_finished",
        "node_completed",
        "workflow_completed",
    ]
    tool_started = result.state.trace_events[2]
    tool_finished = result.state.trace_events[6]
    assert tool_started.payload == {
        "tool_id": "search_repo",
        "arguments": {"query": "agents"},
    }
    assert tool_started.sensitive_fields == ("arguments",)
    assert tool_finished.payload == {
        "tool_id": "search_repo",
        "success": True,
        "error": None,
    }


def test_execute_workflow_emits_status_notice_for_fallback_tool_failure() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "trace-tool-fallback-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                    "failure_behavior": "fallback",
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [make_tool("search_repo", [RuntimeError("tool exploded")])]
    )

    result = execute_workflow(workflow, prompt="Run", tool_registry=registry)

    status_events = [
        event
        for event in result.state.trace_events
        if event.event_type == "status_notice"
    ]
    assert len(status_events) == 1
    assert status_events[0].node_id == "lookup"
    assert status_events[0].payload == {
        "severity": "warning",
        "code": "tool_failure_fallback",
        "message": "tool 'search_repo' failed; continuing due to fallback behavior",
        "tool_id": "search_repo",
        "error": "tool exploded",
    }


def test_execute_workflow_traces_model_failure() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "trace-model-failure-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer"},
                }
            ],
            "edges": [],
        }
    )
    sink = InMemoryTraceSink()

    with pytest.raises(ModelExecutionError, match="model exploded"):
        execute_workflow(
            workflow,
            prompt="Run",
            model_adapter=make_adapter([RuntimeError("model exploded")]),
            trace_sink=sink,
        )

    event_types = [event.event_type for event in sink.events]
    assert event_types == [
        "workflow_started",
        "node_started",
        "model_request",
        "retry_recorded",
        "node_error",
    ]
    assert sink.events[-2].payload["operation"] == "model"
    assert sink.events[-2].payload["outcome"] == "failure"
    assert "model exploded" in str(sink.events[-2].payload["final_error"])


def test_execute_workflow_traces_retry_attempt_count() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "trace-retry-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "model_retry_policy": {
                        "max_attempts": 3,
                        "retry_on": ["model_error"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer"},
                }
            ],
            "edges": [],
        }
    )

    result = execute_workflow(
        workflow,
        prompt="Run",
        model_adapter=make_adapter(
            [RuntimeError("temporary outage"), {"id": "resp", "output_text": "done"}]
        ),
    )

    retry_events = [
        event
        for event in result.state.trace_events
        if event.event_type == "retry_recorded"
    ]
    assert len(retry_events) == 1
    assert retry_events[0].payload["operation"] == "model"
    assert retry_events[0].payload["attempts"] == 2
    assert retry_events[0].payload["outcome"] == "success"
