"""Tests for workflow executor behavior."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.api import run_agent_workflow
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.errors import ModelExecutionError, WorkflowExecutionError
from dynamic_agent_runner.executor import execute_workflow
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


def make_tool(
    tool_id: str,
    output: object | None = None,
    *,
    raw: dict[str, object] | None = None,
) -> RegisteredTool:
    tool_raw: dict[str, object] = {
        "id": tool_id,
        "description_for_llm": f"Use {tool_id}",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    tool_raw.update(raw or {})
    return RegisteredTool(
        ToolDefinition.from_mapping(tool_raw),
        lambda args: output if output is not None else {"result": args["query"]},
    )


def make_flaky_tool(
    tool_id: str,
    outputs: list[object | Exception],
    *,
    raw: dict[str, object] | None = None,
) -> RegisteredTool:
    tool_raw: dict[str, object] = {
        "id": tool_id,
        "description_for_llm": f"Use {tool_id}",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    tool_raw.update(raw or {})

    def handler(_args: object) -> object:
        output = outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output

    return RegisteredTool(ToolDefinition.from_mapping(tool_raw), handler)


def workflow_from(data: dict[str, object]) -> LoadedAgentWorkflow:
    return LoadedAgentWorkflow(runtime_manifest=load_runtime_manifest(data))


def test_execute_workflow_runs_llm_tool_and_final_llm_steps() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "executor-agent",
            "entrypoint": "analyze",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
            "nodes": [
                {
                    "id": "analyze",
                    "kind": "llm_step",
                    "prompt": {
                        "system": "Analyze.",
                        "user_template": "Question: {prompt}",
                    },
                    "available_tools": ["search_repo"],
                },
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs_from": {"query": "analyze"},
                },
                {
                    "id": "final",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Use {lookup}"},
                },
            ],
            "edges": [
                {"source": "analyze", "target": "lookup", "edge_kind": "sequential"},
                {"source": "lookup", "target": "final", "edge_kind": "sequential"},
            ],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry([make_tool("search_repo", output={"answer": "42"})])
    adapter = make_adapter(
        [
            {"id": "resp_1", "output_text": "find agents"},
            {"id": "resp_2", "output_text": "final answer"},
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "final answer"
    assert [execution.node_id for execution in result.state.executions] == [
        "analyze",
        "lookup",
        "final",
    ]
    assert result.state.tool_results["lookup"].output == {"answer": "42"}
    first_call = adapter.client.responses.calls[0]
    assert first_call["tools"][0]["function"]["name"] == "search_repo"


def test_execute_workflow_routes_llm_decision_branch() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "branch-agent",
            "entrypoint": "choose",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
            "nodes": [
                {
                    "id": "choose",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Route"},
                },
                {
                    "id": "route",
                    "kind": "decision_step",
                    "decision_subtype": "llm_route",
                    "route_from": "choose",
                },
                {"id": "left", "kind": "llm_step", "prompt": {"user_template": "Left"}},
                {
                    "id": "right",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Right"},
                },
            ],
            "edges": [
                {"source": "choose", "target": "route", "edge_kind": "sequential"},
                {
                    "source": "route",
                    "target": "left",
                    "edge_kind": "branch",
                    "condition": "left",
                },
                {
                    "source": "route",
                    "target": "right",
                    "edge_kind": "branch",
                    "condition": "right",
                },
            ],
        }
    )
    adapter = make_adapter(
        [
            {"id": "route", "output_text": '{"route":"right"}'},
            {"id": "final", "output_text": "right result"},
        ]
    )

    result = execute_workflow(workflow, prompt="Pick", model_adapter=adapter)

    assert result.final_result == "right result"
    assert [execution.node_id for execution in result.state.executions] == [
        "choose",
        "route",
        "right",
    ]


def test_execute_workflow_errors_on_tool_failure_by_default() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-failure-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {},
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry([make_tool("search_repo")])

    with pytest.raises(WorkflowExecutionError, match="missing required input"):
        execute_workflow(workflow, prompt="Run", tool_registry=registry)


def test_run_agent_workflow_returns_final_result() -> None:
    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "api-agent",
        "entrypoint": "answer",
        "packaging": {"mode": "hybrid_bundle"},
        "execution_policy": {"model": "gpt-test"},
        "nodes": [
            {
                "id": "answer",
                "kind": "llm_step",
                "prompt": {"user_template": "{prompt}"},
            }
        ],
        "edges": [],
    }

    final_result = run_agent_workflow(
        runtime_manifest=manifest,
        prompt="Hello",
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
    )

    assert final_result == "done"


def test_execute_workflow_fails_on_step_limit() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "loop-agent",
            "entrypoint": "one",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
            "nodes": [
                {"id": "one", "kind": "llm_step", "prompt": {"user_template": "Loop"}}
            ],
            "edges": [
                {"source": "one", "target": "one", "edge_kind": "sequential"},
            ],
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": "again"}] * 3)

    with pytest.raises(WorkflowExecutionError, match="exceeded maximum step count"):
        execute_workflow(workflow, prompt="Loop", model_adapter=adapter, max_steps=2)


def test_execute_workflow_retries_retryable_model_failures() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "model-retry-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {
                "model": "gpt-test",
                "model_retry_policy": {
                    "max_attempts": 3,
                    "retry_on": ["model_error"],
                },
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter(
        [RuntimeError("temporary outage"), {"id": "resp", "output_text": "done"}]
    )

    result = execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert result.final_result == "done"
    assert len(adapter.client.responses.calls) == 2
    assert result.state.retry_records[-1].attempts == 2
    assert result.state.retry_records[-1].outcome == "success"


def test_execute_workflow_does_not_retry_model_by_default() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "model-no-retry-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter(
        [RuntimeError("temporary outage"), {"id": "resp", "output_text": "done"}]
    )

    with pytest.raises(ModelExecutionError, match="temporary outage"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert len(adapter.client.responses.calls) == 1


def test_execute_workflow_does_not_retry_non_retryable_model_failures() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "model-non-retry-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {
                "model": "gpt-test",
                "retry_policy": {"max_attempts": 3, "retry_on": ["tool_failure"]},
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter(
        [RuntimeError("non-retryable outage"), {"id": "resp", "output_text": "done"}]
    )

    with pytest.raises(ModelExecutionError, match="non-retryable outage"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert len(adapter.client.responses.calls) == 1


def test_execute_workflow_records_model_retry_exhaustion() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "model-retry-exhaustion-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {
                "model": "gpt-test",
                "retry_policy": {"max_attempts": 2, "retry_on": ["exception"]},
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter([RuntimeError("outage 1"), RuntimeError("outage 2")])

    with pytest.raises(ModelExecutionError, match="outage 2"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert len(adapter.client.responses.calls) == 2


def test_execute_workflow_retries_tool_failures_from_registry_metadata() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-retry-agent",
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
        [
            make_flaky_tool(
                "search_repo",
                [RuntimeError("temporary tool failure"), {"answer": "42"}],
                raw={"retry_policy": {"max_attempts": 3, "retry_on": ["failure"]}},
            )
        ]
    )

    result = execute_workflow(workflow, prompt="Run", tool_registry=registry)

    assert result.state.tool_results["lookup"].output == {"answer": "42"}
    assert result.state.retry_records[-1].operation == "tool"
    assert result.state.retry_records[-1].attempts == 2
    assert result.state.retry_records[-1].outcome == "success"


def test_execute_workflow_exhausts_retryable_tool_failures() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-retry-exhaustion-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                    "retry_policy": {"max_attempts": 2, "retry_on": ["tool_failure"]},
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [
            make_flaky_tool(
                "search_repo",
                [RuntimeError("temporary 1"), RuntimeError("temporary 2")],
            )
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="temporary 2"):
        execute_workflow(workflow, prompt="Run", tool_registry=registry)


def test_execute_workflow_does_not_retry_non_retryable_tool_failures() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-non-retry-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                    "retry_policy": {"max_attempts": 3, "retry_on": ["exception"]},
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [
            make_flaky_tool(
                "search_repo",
                [RuntimeError("non-retryable tool failure"), {"answer": "42"}],
            )
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="non-retryable tool failure"):
        execute_workflow(workflow, prompt="Run", tool_registry=registry)
