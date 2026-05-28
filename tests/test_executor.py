"""Tests for workflow executor behavior."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.api import run_agent_workflow
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.errors import ModelExecutionError, WorkflowExecutionError
from dynamic_agent_runner.executor import execute_workflow
from dynamic_agent_runner.models import LoadedAgentWorkflow, ToolDefinition
from dynamic_agent_runner.openai_client import OpenAIClientAdapter
from dynamic_agent_runner.registry import (
    InMemoryToolRegistry,
    RegisteredTool,
    ToolResult,
)


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


def test_execute_workflow_uses_model_facing_tool_output_in_context_and_trace() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-facet-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                    "outputs": {"state_key": "search_summary"},
                },
                {
                    "id": "final",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Use {lookup} and {search_summary}"},
                },
            ],
            "edges": [
                {"source": "lookup", "target": "final", "edge_kind": "sequential"}
            ],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [
            make_tool(
                "search_repo",
                output=ToolResult(
                    tool_id="search_repo",
                    success=True,
                    output={"raw": "full raw result"},
                    model_output={"summary": "safe summary"},
                    raw_output={"raw": "full raw result"},
                    log_preview="safe summary",
                    event_payload={"record_count": 1},
                    sensitive_fields=("raw_output",),
                ),
            )
        ]
    )
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    result = execute_workflow(
        workflow,
        prompt="Run",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "done"
    assert result.state.node_outputs["lookup"].model_output == {
        "summary": "safe summary"
    }
    assert result.state.node_outputs["search_summary"] == {"summary": "safe summary"}
    assert adapter.client.responses.calls[0]["input"][-1]["content"] == (
        "Use {'summary': 'safe summary'} and {'summary': 'safe summary'}"
    )
    tool_result_events = [
        event
        for event in result.state.trace_events
        if event.event_type == "tool_result"
    ]
    assert tool_result_events[0].payload == {
        "tool_id": "search_repo",
        "success": True,
        "error": None,
        "output": {"summary": "safe summary"},
        "raw_output": {"raw": "full raw result"},
        "log_preview": "safe summary",
        "event_payload": {"record_count": 1},
    }
    assert set(tool_result_events[0].sensitive_fields) == {"output", "raw_output"}


def test_execute_workflow_accepts_execution_context() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "context-agent",
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
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])
    context = WorkflowExecutionContext(workflow=workflow, model_adapter=adapter)

    result = execute_workflow(context, prompt="Hello")

    assert result.final_result == "done"
    assert adapter.client.responses.calls[0]["model"] == "gpt-test"


def test_execute_workflow_rejects_context_with_runtime_kwargs() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "context-conflict-agent",
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
    context = WorkflowExecutionContext(workflow=workflow)

    with pytest.raises(WorkflowExecutionError, match="cannot be combined"):
        execute_workflow(
            context,
            prompt="Hello",
            model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
        )


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


def test_execute_workflow_rejects_malformed_route_output() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "route-malformed-agent",
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
                    "decision_contract": {
                        "allowed_paths": [{"id": "left"}, {"id": "right"}]
                    },
                },
            ],
            "edges": [
                {"source": "choose", "target": "route", "edge_kind": "sequential"},
            ],
        }
    )
    adapter = make_adapter([{"id": "route", "output_text": '{"status":"lost"}'}])

    with pytest.raises(WorkflowExecutionError, match="produced no route"):
        execute_workflow(workflow, prompt="Pick", model_adapter=adapter)


def test_execute_workflow_rejects_route_outside_allowed_paths() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "route-unknown-agent",
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
                    "decision_contract": {"allowed_paths": ["left", "right"]},
                },
            ],
            "edges": [
                {"source": "choose", "target": "route", "edge_kind": "sequential"},
            ],
        }
    )
    adapter = make_adapter([{"id": "route", "output_text": '{"route":"middle"}'}])

    with pytest.raises(WorkflowExecutionError, match="outside allowed paths"):
        execute_workflow(workflow, prompt="Pick", model_adapter=adapter)


def test_execute_workflow_validates_llm_output_contract_fields() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "contract-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "{prompt}",
                        "output_schema_ref": "answer_contract",
                    },
                }
            ],
            "edges": [],
            "output_contracts": {
                "answer_contract": {"required_fields": ["message", "confidence"]}
            },
        }
    )
    adapter = make_adapter(
        [
            {
                "id": "resp",
                "output_text": '{"message":"done","confidence":"high"}',
            }
        ]
    )

    result = execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert result.final_result == '{"message":"done","confidence":"high"}'


def test_execute_workflow_rejects_missing_output_contract_fields() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "contract-missing-field-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "output_schema_ref": "answer_contract",
                }
            ],
            "edges": [],
            "output_contracts": {
                "answer_contract": {"required_fields": ["message", "confidence"]}
            },
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": '{"message":"done"}'}])

    with pytest.raises(WorkflowExecutionError, match="missing required field"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)


def test_execute_workflow_rejects_unstructured_contract_output() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "contract-unstructured-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "output_schema_ref": "answer_contract",
                }
            ],
            "edges": [],
            "output_contracts": {
                "answer_contract": {"required_fields": ["message", "confidence"]}
            },
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": "plain answer"}])

    with pytest.raises(WorkflowExecutionError, match="requires structured output"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)


def test_execute_workflow_rejects_unknown_output_contract_ref() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "contract-unknown-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "output_schema_ref": "missing_contract",
                }
            ],
            "edges": [],
            "output_contracts": {},
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": "plain answer"}])

    with pytest.raises(WorkflowExecutionError, match="unknown output contract"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)


def test_execute_workflow_records_token_usage_when_budget_enabled() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "token-budget-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {
                "model": "gpt-test",
                "token_budget": {
                    "model": "gpt-4o-mini",
                    "max_prompt_tokens": 1000,
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

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
    )

    assert result.final_result == "done"
    assert len(result.state.token_usage) == 1
    assert result.state.token_usage[0].node_id == "answer"
    assert result.state.token_usage[0].estimated_prompt_tokens > 0
    assert result.state.token_usage[0].exceeded is False


def test_execute_workflow_applies_prompt_and_skill_overrides() -> None:
    """Runtime overrides alter one LLM node without mutating loaded artifacts."""

    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "behavior-override-agent",
        "entrypoint": "draft",
        "packaging": {"mode": "hybrid_bundle"},
        "execution_policy": {"model": "gpt-test"},
        "nodes": [
            {
                "id": "draft",
                "kind": "llm_step",
                "prompt": {
                    "system": "Base system.",
                    "developer": "Base developer.",
                    "user_template": "Base {prompt}",
                },
                "skill_refs": ["base-skill"],
            }
        ],
        "edges": [],
        "skills": [
            {
                "id": "base-skill",
                "prompt_role": "developer",
                "instructions": "Use base style.",
            }
        ],
    }
    overrides = {
        "format_version": 1,
        "override_type": "dynamic_agent_runtime_overrides",
        "skills": {
            "added": [
                {
                    "id": "concise-writer",
                    "prompt_role": "developer",
                    "instructions": "Write tersely for {prompt}.",
                }
            ]
        },
        "nodes": {
            "draft": {
                "prompt": {
                    "prepend": {"system": "Prepended. "},
                    "append": {"developer": " Appended."},
                    "replace": {"user_template": "Override {prompt}"},
                },
                "skill_refs": {"add": ["concise-writer"]},
            }
        },
    }
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    final_result = run_agent_workflow(
        runtime_manifest=manifest,
        runtime_overrides=overrides,
        prompt="Hello",
        model_adapter=adapter,
    )

    assert final_result == "done"
    call = adapter.client.responses.calls[0]
    assert call["input"] == [
        {"role": "system", "content": "Prepended. Base system."},
        {"role": "developer", "content": "Base developer. Appended."},
        {"role": "developer", "content": "Use base style."},
        {"role": "developer", "content": "Write tersely for Hello."},
        {"role": "user", "content": "Override Hello"},
    ]
    assert manifest["nodes"][0]["prompt"]["user_template"] == "Base {prompt}"


def test_execute_workflow_applies_skill_only_remove_and_node_isolation() -> None:
    """Per-node skill binding overrides stay scoped to their target node."""

    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "skill-scope-agent",
        "entrypoint": "first",
        "packaging": {"mode": "hybrid_bundle"},
        "execution_policy": {"model": "gpt-test"},
        "nodes": [
            {
                "id": "first",
                "kind": "llm_step",
                "prompt": {"user_template": "First {prompt}"},
                "skill_refs": ["base", "extra"],
            },
            {
                "id": "second",
                "kind": "llm_step",
                "prompt": {"user_template": "Second {first}"},
                "skill_refs": ["extra"],
            },
        ],
        "edges": [{"source": "first", "target": "second", "edge_kind": "sequential"}],
        "skills": [
            {"id": "base", "prompt_role": "developer", "instructions": "Base."},
            {"id": "extra", "prompt_role": "developer", "instructions": "Extra."},
            {"id": "only", "prompt_role": "developer", "instructions": "Only."},
        ],
    }
    overrides = {
        "format_version": 1,
        "override_type": "dynamic_agent_runtime_overrides",
        "nodes": {"first": {"skill_refs": {"only": ["only"], "remove": ["base"]}}},
    }
    adapter = make_adapter(
        [
            {"id": "first", "output_text": "first output"},
            {"id": "second", "output_text": "second output"},
        ]
    )

    result = run_agent_workflow(
        runtime_manifest=manifest,
        runtime_overrides=overrides,
        prompt="Hello",
        model_adapter=adapter,
    )

    assert result == "second output"
    first_messages = adapter.client.responses.calls[0]["input"]
    second_messages = adapter.client.responses.calls[1]["input"]
    assert {message["content"] for message in first_messages} == {
        "Only.",
        "First Hello",
    }
    assert {message["content"] for message in second_messages} == {
        "Extra.",
        "Second first output",
    }


def test_execute_workflow_uses_overridden_output_schema_ref() -> None:
    """Prompt replacement of output_schema_ref participates in validation."""

    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "schema-override-agent",
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
        "output_contracts": {
            "strict_answer": {"required_fields": ["message", "confidence"]}
        },
    }
    overrides = {
        "format_version": 1,
        "override_type": "dynamic_agent_runtime_overrides",
        "nodes": {
            "answer": {"prompt": {"replace": {"output_schema_ref": "strict_answer"}}}
        },
    }
    adapter = make_adapter([{"id": "resp", "output_text": '{"message":"done"}'}])

    with pytest.raises(WorkflowExecutionError, match="missing required field"):
        run_agent_workflow(
            runtime_manifest=manifest,
            runtime_overrides=overrides,
            prompt="Hello",
            model_adapter=adapter,
        )


def test_execute_workflow_fails_when_prompt_exceeds_token_budget() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "token-budget-failure-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "execution_policy": {"model": "gpt-test"},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "token_budget": {
                        "model": "gpt-4o-mini",
                        "max_prompt_tokens": 1,
                    },
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    with pytest.raises(WorkflowExecutionError, match="exceeds budget"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert adapter.client.responses.calls == []


def test_execute_workflow_skips_token_usage_when_budget_disabled() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "token-budget-disabled-agent",
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

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
    )

    assert result.state.token_usage == []


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


def test_run_agent_workflow_accepts_execution_context() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "api-context-agent",
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
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])
    context = WorkflowExecutionContext(workflow=workflow, model_adapter=adapter)

    final_result = run_agent_workflow(prompt="Hello", execution_context=context)

    assert final_result == "done"


def test_run_agent_workflow_rejects_context_with_artifact_kwargs() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "api-context-conflict-agent",
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
    context = WorkflowExecutionContext(workflow=workflow)

    with pytest.raises(TypeError, match="cannot be combined"):
        run_agent_workflow(
            prompt="Hello",
            execution_context=context,
            model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
        )


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
