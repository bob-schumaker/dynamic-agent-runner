"""Tests for workflow executor behavior."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from dynamic_agent_runner.api import (
    compile_agent_workflow,
    load_agent_package_workflow,
    run_agent_workflow,
    run_agent_workflow_async,
)
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.errors import (
    GuardrailExecutionError,
    ModelExecutionError,
    WorkflowExecutionError,
)
from dynamic_agent_runner.executor import (
    ApprovalInterruption,
    ApprovalInterruptionState,
    execute_workflow,
    execute_workflow_async,
    WorkflowInterruptedResult,
    WorkflowExecutionState,
    prepare_model_input,
)
from dynamic_agent_runner.guardrails import (
    GuardrailDecision,
    GuardrailResult,
    InMemoryGuardrailRegistry,
)
from dynamic_agent_runner.hooks import NodeHookContext, WorkflowLifecycleHooks
from dynamic_agent_runner.local_models import (
    LlamaCppLocalModelConfig,
    create_llama_cpp_local_adapter,
)
from dynamic_agent_runner.mlx_models import (
    MLXLocalModelConfig,
    create_mlx_local_adapter,
)
from dynamic_agent_runner.models import (
    LoadedAgentWorkflow,
    ToolDefinition,
    prepare_execution_plan,
)
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    ModelResponse,
    OpenAIClientAdapter,
    OpenAIMessage,
)
from dynamic_agent_runner.registry import (
    InMemoryToolRegistry,
    RegisteredTool,
    ToolResult,
)
from dynamic_agent_runner.tracing import WorkflowTracer


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
    def __init__(self, responses: list[object], models: object | None = None):
        self.responses = FakeResponses(responses)
        if models is not None:
            self.models = models


class FakeModels:
    def __init__(self, models: object):
        self.models = models
        self.calls: list[dict[str, object]] = []

    def list(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        return self.models


class AsyncFakeResponses:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        await asyncio.sleep(0)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AsyncFakeClient:
    def __init__(self, responses: list[object]):
        self.responses = AsyncFakeResponses(responses)


class FakeMLXBackend:
    def __init__(self, content: str = "mlx local") -> None:
        self.content = content
        self.requests: list[object] = []

    def generate(self, request: object) -> str:
        self.requests.append(request)
        return self.content


class FakeLlamaCppBackend:
    def __init__(self, content: str = "llama.cpp local") -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    def create_chat_completion(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return {"choices": [{"message": {"content": self.content}}]}


def test_approval_interruption_contract_shape() -> None:
    """Approval interruptions expose stable, inspectable pause metadata."""

    state = WorkflowExecutionState(prompt="Run", run_id="run-1")
    interruption = ApprovalInterruption(
        interruption_id="approval-1",
        run_id="run-1",
        workflow_id="approval-agent",
        node_id="write",
        tool_id="workspace_write",
        arguments={"path": "notes.txt", "content": "hello"},
        policy={"approval_required": "yes", "side_effect": "write"},
        reason="tool requires approval",
    )
    result = WorkflowInterruptedResult(
        final_result=None,
        state=state,
        interruption=interruption,
    )

    assert interruption.schema_version == 1
    assert interruption.state is ApprovalInterruptionState.PENDING
    assert result.final_result is None
    assert result.interruption.tool_id == "workspace_write"


def package_fixture_path(pattern_id: str = "basic-reasoning-agent") -> Path:
    return Path(__file__).parent / "fixtures" / "agent-patterns" / pattern_id


def make_adapter(responses: list[object]) -> OpenAIClientAdapter:
    return OpenAIClientAdapter(FakeClient(responses))


def make_async_adapter(responses: list[object]) -> AsyncOpenAIClientAdapter:
    return AsyncOpenAIClientAdapter(AsyncFakeClient(responses))


def make_named_adapter(
    responses: list[object],
    *,
    models: list[str],
    is_local: bool = False,
) -> OpenAIClientAdapter:
    return OpenAIClientAdapter(FakeClient(responses), models=models, is_local=is_local)


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


def make_async_tool(
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

    async def handler(args: object) -> object:
        await asyncio.sleep(0)
        return output if output is not None else {"result": args["query"]}

    return RegisteredTool(ToolDefinition.from_mapping(tool_raw), handler)


def workflow_from(data: dict[str, object]) -> LoadedAgentWorkflow:
    return LoadedAgentWorkflow(runtime_manifest=load_runtime_manifest(data))


def test_compile_agent_workflow_preserves_base_workflow_and_executes_from_compiled() -> (
    None
):
    """Execution accepts compiled workflows while leaving the base workflow unchanged."""

    base_workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "compiled-execution-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "skills": [{"id": "base-skill", "instructions": "Base skill."}],
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Base {prompt}"},
                    "skill_refs": ["base-skill"],
                }
            ],
            "edges": [],
        }
    )

    compiled = compile_agent_workflow(
        base_workflow,
        runtime_overrides={
            "format_version": 1,
            "override_type": "dynamic_agent_runtime_overrides",
            "skills": {
                "added": [
                    {
                        "id": "added-skill",
                        "prompt_role": "developer",
                        "instructions": "Extra instructions.",
                    }
                ]
            },
            "nodes": {
                "answer": {
                    "prompt": {
                        "replace": {"user_template": "Compiled {prompt}"},
                    },
                    "skill_refs": {"add": ["added-skill"]},
                }
            },
        },
    )

    result = execute_workflow(
        compiled,
        prompt="request",
        model_adapter=make_adapter([{"id": "resp_1", "output_text": "done"}]),
    )

    assert result.final_result == "done"
    assert base_workflow.runtime_overrides is None
    request = result.state.node_inputs["answer"]
    message_texts = [message["content"] for message in request["input"]]
    assert "Extra instructions." in message_texts
    assert "Compiled request" in message_texts


def test_load_agent_package_workflow_returns_compiled_workflow(
    tmp_path,
) -> None:
    """Package-loading API returns compiled workflow form with optional overrides."""

    package_dir = tmp_path / "compiled-package"
    package_dir.mkdir()
    (package_dir / "agent-runtime.yaml").write_text(
        """
format_version: 1
package_type: dynamic_agent_design
package_id: compiled-package
entrypoint: answer
packaging:
  mode: hybrid_bundle
skills:
  - id: base-skill
    instructions: Base skill.
nodes:
  - id: answer
    kind: llm_step
    prompt:
      user_template: Base {prompt}
    skill_refs:
      - base-skill
edges: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "agent-graph.mmd").write_text("flowchart TD\n", encoding="utf-8")
    (package_dir / "agent-design.md").write_text(
        "Runtime manifest: `agent-runtime.yaml`\nMermaid graph: `agent-graph.mmd`\n",
        encoding="utf-8",
    )

    compiled = load_agent_package_workflow(
        str(package_dir),
        runtime_overrides={
            "format_version": 1,
            "override_type": "dynamic_agent_runtime_overrides",
            "skills": {
                "added": [
                    {
                        "id": "added-skill",
                        "prompt_role": "developer",
                        "instructions": "Extra instructions.",
                    }
                ]
            },
        },
    )

    assert compiled.base_workflow.package_root == str(package_dir)
    assert compiled.package_root == str(package_dir)
    assert compiled.runtime_overrides is not None
    assert compiled.runtime_overrides.added_skills[0].id == "added-skill"


def test_run_agent_workflow_accepts_package_directory() -> None:
    fixture = package_fixture_path()

    result = run_agent_workflow(
        package_directory=str(fixture),
        prompt="Say hello from package API.",
        model_adapter=make_adapter([{"id": "resp_pkg", "output_text": "package ok"}]),
    )

    assert result == "package ok"


def test_run_agent_workflow_accepts_model_adapter_coverage() -> None:
    fixture = package_fixture_path()

    result = run_agent_workflow(
        package_directory=str(fixture),
        prompt="Say hello from package API.",
        model_adapter=make_adapter(
            [{"id": "resp_coverage", "output_text": "coverage ok"}]
        ),
        model_adapter_coverage="augmented",
    )

    assert result == "coverage ok"


async def _run_agent_workflow_async_keeps_compatibility_artifact_inputs() -> None:
    fixture = package_fixture_path()

    result = await run_agent_workflow_async(
        runtime_manifest=str(fixture / "agent-runtime.yaml"),
        agent_design=str(fixture / "agent-design.md"),
        mermaid_graph=str(fixture / "agent-graph.mmd"),
        prompt="Say hello from compatibility inputs.",
        model_adapter=make_async_adapter(
            [{"id": "resp_compat", "output_text": "compat ok"}]
        ),
    )

    assert result == "compat ok"


def test_run_agent_workflow_async_keeps_compatibility_artifact_inputs() -> None:
    asyncio.run(_run_agent_workflow_async_keeps_compatibility_artifact_inputs())


async def _run_agent_workflow_async_accepts_model_adapter_coverage() -> None:
    fixture = package_fixture_path()

    result = await run_agent_workflow_async(
        runtime_manifest=str(fixture / "agent-runtime.yaml"),
        agent_design=str(fixture / "agent-design.md"),
        mermaid_graph=str(fixture / "agent-graph.mmd"),
        prompt="Say hello from compatibility inputs.",
        model_adapter=make_async_adapter(
            [{"id": "resp_coverage_async", "output_text": "coverage async ok"}]
        ),
        model_adapter_coverage="augmented",
    )

    assert result == "coverage async ok"


def test_run_agent_workflow_async_accepts_model_adapter_coverage() -> None:
    asyncio.run(_run_agent_workflow_async_accepts_model_adapter_coverage())


def test_prepare_execution_plan_resolves_node_indexes_and_defaults() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-default",
                    "max_steps": 8,
                    "tool_use_completion": {
                        "run_again": "required",
                        "stop_on_tool": "enabled",
                        "final_output": "state_field",
                        "final_output_state_key": "lookup_summary",
                    },
                    "async_session": {
                        "mode": "create_or_resume",
                        "persist": "external_checkpoint",
                        "history": "summary",
                        "session_id_state_key": "session_id",
                        "session_messages_state_key": "session_messages",
                    },
                    "retry_policy": {"max_attempts": 2},
                    "token_budget": {"max_prompt_tokens": 100},
                }
            },
            "metadata": {
                "handoffs": [
                    {
                        "id": "handoff_to_reviewer",
                        "target": "reviewer",
                        "on_handoff": "switch_active_profile",
                        "nested_history": "preserve",
                    }
                ]
            },
            "extensions": {"future_optional": {"required": False, "config": {}}},
            "output_contracts": [
                {"id": "answer_contract", "required_fields": ["message"]}
            ],
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "model": "gpt-node",
                    "model_parameters": {"temperature": 0},
                    "tool_choice": "auto",
                    "response_format": {"type": "json_object"},
                    "prompt": {
                        "user_template": "Answer {prompt}",
                        "output_schema_ref": "answer_contract",
                    },
                    "available_tools": ["search_repo"],
                    "retry_policy": {"max_attempts": 3},
                    "token_budget_policy": {"max_prompt_tokens": 50},
                },
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "static"},
                    "inputs_from": {"extra": "answer"},
                    "outputs": {"state_key": "lookup_summary"},
                    "agent_as_tool": {
                        "skill_id": "search-specialist",
                        "task_boundary": "perform a bounded search subtask",
                        "output_mode": "tool_result",
                    },
                    "failure_behavior": "continue",
                    "retry_policy": {"max_attempts": 4},
                },
                {
                    "id": "route",
                    "kind": "decision_step",
                    "decision_subtype": "llm_route",
                    "route_from": "answer",
                    "decision_contract": {"allowed_paths": ["done"]},
                },
            ],
            "edges": [
                {"source": "answer", "target": "lookup", "edge_kind": "sequential"},
                {"source": "lookup", "target": "route", "edge_kind": "sequential"},
            ],
            "tools": [{"id": "search_repo"}],
        }
    )

    plan = prepare_execution_plan(workflow)

    assert plan.entrypoint_id == "answer"
    assert plan.max_steps == 8
    assert plan.tool_use_completion_policy is not None
    assert plan.tool_use_completion_policy.run_again == "required"
    assert plan.tool_use_completion_policy.stop_on_tool == "enabled"
    assert plan.tool_use_completion_policy.final_output == "state_field"
    assert plan.tool_use_completion_policy.final_output_state_key == "lookup_summary"
    assert plan.async_session_policy is not None
    assert plan.async_session_policy.mode == "create_or_resume"
    assert plan.async_session_policy.persist == "external_checkpoint"
    assert plan.async_session_policy.history == "summary"
    assert plan.async_session_policy.session_id_state_key == "session_id"
    assert plan.async_session_policy.session_messages_state_key == "session_messages"
    assert len(plan.handoffs) == 1
    assert plan.handoffs[0].id == "handoff_to_reviewer"
    assert plan.handoffs[0].target == "reviewer"
    assert set(plan.nodes_by_id) == {"answer", "lookup", "route"}
    assert [edge.target for edge in plan.edges_by_source["answer"]] == ["lookup"]
    assert plan.unsupported_extensions == ("future_optional",)
    answer = plan.nodes_by_id["answer"]
    assert answer.model == "gpt-node"
    assert answer.model_parameters == {"temperature": 0}
    assert answer.tool_choice == "auto"
    assert answer.output_schema_ref == "answer_contract"
    assert answer.retry_policy == {"max_attempts": 3}
    assert answer.token_budget_policy == {"max_prompt_tokens": 50}
    lookup = plan.nodes_by_id["lookup"]
    assert lookup.agent_as_tool is not None
    assert lookup.agent_as_tool.skill_id == "search-specialist"
    assert lookup.agent_as_tool.task_boundary == "perform a bounded search subtask"
    assert lookup.agent_as_tool.output_mode == "tool_result"
    assert lookup.inputs == {"query": "static"}
    assert lookup.inputs_from == {"extra": "answer"}
    assert lookup.outputs == {"state_key": "lookup_summary"}
    assert lookup.failure_behavior == "continue"
    route = plan.nodes_by_id["route"]
    assert route.route_from == "answer"
    assert route.allowed_routes == frozenset({"done"})


def test_prepare_execution_plan_keeps_base_workflow_unchanged_for_context_pipeline_nodes() -> (
    None
):
    """Eligible context-pipeline nodes should be prepared without mutating base workflow data."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "graph-mutation-base-immutability",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {prepared_context} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "prepared_context",
                    },
                }
            ],
            "edges": [],
        }
    )
    base_raw_before = deepcopy(workflow.runtime_manifest.nodes[0].raw)

    plan = prepare_execution_plan(workflow)

    assert workflow.runtime_manifest.nodes[0].raw == base_raw_before
    assert getattr(plan, "mutation_bundle", None) is not None


def test_prepare_execution_plan_derives_mutation_preparation_for_eligible_llm_step() -> (
    None
):
    """Eligible llm_step nodes should receive derived mutation preparation metadata."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "graph-mutation-derived-preparation",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {prepared_context} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "prepared_context",
                    },
                }
            ],
            "edges": [],
        }
    )

    plan = prepare_execution_plan(workflow)
    answer = plan.nodes_by_id["answer"]

    assert getattr(answer, "mutation_spec", None) is not None


def test_prepare_model_input_applies_context_pipeline_prepared_context_before_render() -> (
    None
):
    """Eligible llm_step nodes should receive prepared context before prompt rendering."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-context-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {prepared_context} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "prepared_context",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="What changed?",
        session_messages=(
            OpenAIMessage(role="user", content="Earlier question."),
            OpenAIMessage(role="assistant", content="Earlier answer."),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    user_prompt = prepared_input.named_parts["user_prompt"].content
    assert "Earlier question." in user_prompt
    assert "Earlier answer." in user_prompt
    assert "What changed?" in user_prompt


def test_prepare_model_input_respects_context_contract_output_slot_name() -> None:
    """Prepared-input mutation should fill the declared output slot, not a hard-coded key."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-context-output-slot-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {context_window} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "context_window",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Summarize the thread.",
        session_messages=(
            OpenAIMessage(role="user", content="First question."),
            OpenAIMessage(role="assistant", content="First answer."),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    user_prompt = prepared_input.named_parts["user_prompt"].content
    assert "First question." in user_prompt
    assert "First answer." in user_prompt
    assert "Summarize the thread." in user_prompt


def test_prepare_model_input_records_mutation_preparation_diagnostics() -> None:
    """Prepared-input metadata and traces should distinguish transformed inputs."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-context-diagnostics-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {prepared_context} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "prepared_context",
                    },
                },
                {
                    "id": "plain",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                },
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="What changed?",
        session_messages=(
            OpenAIMessage(role="user", content="Earlier question."),
            OpenAIMessage(role="assistant", content="Earlier answer."),
        ),
    )
    tracer = WorkflowTracer(events=state.trace_events, run_id="test-run")

    transformed_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        tracer=tracer,
    )
    unchanged_input = prepare_model_input(
        plan.nodes_by_id["plain"],
        plan,
        state,
        tracer=tracer,
    )

    assert transformed_input.preparation.mutation_applied is True
    assert transformed_input.preparation.mutation_id == "context-pruning-answer"
    assert transformed_input.preparation.mutation_output_slots == ("prepared_context",)
    assert unchanged_input.preparation.mutation_applied is False
    assert unchanged_input.preparation.mutation_id is None
    assert unchanged_input.preparation.mutation_output_slots == ()

    prepared_events = [
        event
        for event in state.trace_events
        if event.event_type == "model_input_prepared"
    ]
    prepared_payloads = {event.node_id: event.payload for event in prepared_events}

    assert prepared_payloads["answer"]["mutation_applied"] is True
    assert prepared_payloads["answer"]["mutation_id"] == "context-pruning-answer"
    assert prepared_payloads["answer"]["mutation_output_slots"] == ("prepared_context",)
    assert prepared_payloads["plain"]["mutation_applied"] is False
    assert prepared_payloads["plain"]["mutation_id"] is None
    assert prepared_payloads["plain"]["mutation_output_slots"] == ()


def test_prepare_model_input_renders_messages_and_named_parts() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-input-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "skills": [
                {
                    "id": "style-guide",
                    "prompt_role": "developer",
                    "instructions": "Use concise style for {prompt}.",
                }
            ],
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "skill_refs": ["style-guide"],
                    "prompt": {
                        "system": "System {prompt}.",
                        "user_template": "Answer {prompt}.",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="question")

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert prepared_input.model == "gpt-test"
    assert prepared_input.part_names == (
        "system",
        "skill_instructions",
        "user_prompt",
    )
    assert [message.content for message in prepared_input.messages] == [
        "System question.",
        "Use concise style for question.",
        "Answer question.",
    ]
    assert prepared_input.named_parts["user_prompt"].content == "Answer question."


def test_prepare_model_input_applies_hierarchy_pruning_and_compaction() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-input-policy-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "prompt_hierarchy": {
                            "system": ["Global safety first."],
                            "developer": ["Workspace rules apply."],
                        },
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "strategy": "summary_message",
                            "summary_role": "developer",
                            "summary_prefix": "Earlier session:",
                            "max_chars_per_message": 18,
                        },
                    },
                }
            },
            "skills": [
                {
                    "id": "style-guide",
                    "prompt_role": "developer",
                    "instructions": "Use concise style for {prompt}.",
                }
            ],
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "skill_refs": ["style-guide"],
                    "prompt": {
                        "system": "System {prompt}.",
                        "user_template": "Answer {prompt}.",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="question",
        session_messages=(
            OpenAIMessage(role="user", content="First older user request."),
            OpenAIMessage(role="assistant", content="First older assistant reply."),
            OpenAIMessage(role="user", content="Most recent user request."),
            OpenAIMessage(role="assistant", content="Most recent assistant reply."),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert prepared_input.part_names == (
        "hierarchy_system_1",
        "system",
        "skill_instructions",
        "hierarchy_developer_1",
        "session_summary",
        "session_message_1",
        "session_message_2",
        "user_prompt",
    )
    assert [message.role for message in prepared_input.messages] == [
        "system",
        "system",
        "developer",
        "developer",
        "developer",
        "user",
        "assistant",
        "user",
    ]
    assert prepared_input.named_parts["session_summary"].content == (
        "Earlier session:\n- user: First older user …\n- assistant: First older assis…"
    )
    assert prepared_input.named_parts["session_message_1"].content == (
        "Most recent user request."
    )
    assert prepared_input.named_parts["session_message_2"].content == (
        "Most recent assistant reply."
    )
    assert prepared_input.preparation.hierarchy_applied is True
    assert prepared_input.preparation.session_messages_included == 2
    assert prepared_input.preparation.session_messages_pruned == 2
    assert prepared_input.preparation.context_compaction_applied is True


def test_prepare_model_input_groups_session_messages_into_turn_units() -> None:
    """prepare_model_input records stable turn/segment diagnostics for sessions."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "turn-grouping-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "context_compaction": {
                            "auto": {
                                "enabled": True,
                                "implementation": "metadata_only",
                                "strategy": "basic",
                            }
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish the work",
        session_messages=(
            OpenAIMessage(role="user", content="first request"),
            OpenAIMessage(role="assistant", content="calling search"),
            OpenAIMessage(role="tool", content="search result"),
            OpenAIMessage(role="assistant", content="first answer"),
            OpenAIMessage(role="user", content="second request"),
            OpenAIMessage(role="assistant", content="second answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert prepared_input.preparation.turn_count == 2
    assert prepared_input.preparation.segment_count == 6
    assert prepared_input.preparation.turns == (
        {
            "turn_id": "turn_1",
            "lane": "recent_turns",
            "message_count": 4,
            "roles": ("user", "assistant", "tool", "assistant"),
            "selection_status": "included",
        },
        {
            "turn_id": "turn_2",
            "lane": "current_turn",
            "message_count": 2,
            "roles": ("user", "assistant"),
            "selection_status": "included",
        },
    )
    assert prepared_input.preparation.segments[0]["segment_id"] == "turn_1_segment_1"
    assert prepared_input.preparation.segments[0]["role"] == "user"
    assert prepared_input.preparation.segments[2]["role"] == "tool"


def test_prepare_model_input_records_auto_compaction_threshold_metadata() -> None:
    """prepare_model_input normalizes auto-compaction threshold diagnostics."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "auto-compact-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "context_compaction": {
                            "auto": {
                                "enabled": True,
                                "threshold_ratio": 0.95,
                                "reserve_tokens": 200,
                                "scope": "current_run",
                                "implementation": "metadata_only",
                                "strategy": "basic",
                                "mode": "auto",
                                "trigger": "reserve_tokens",
                                "lifecycle_stages": ["validate", "segment", "report"],
                                "metrics": ["lane_utilization"],
                            }
                        },
                        "context_compression": {
                            "profile": "fast",
                            "lanes": {
                                "pinned_tokens": 100,
                                "current_turn_tokens": 200,
                            },
                            "selection": {
                                "strategy": "deterministic_overlap",
                                "max_selected_turns": 3,
                                "chronological_reassembly": True,
                            },
                        },
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "model": "gpt-test",
                    "prompt": {"user_template": "Answer {prompt}"},
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    adapter = make_named_adapter(
        [ModelResponse(content="ok")],
        models=["gpt-test"],
    )
    adapter.context_windows = {"gpt-test": 1000}
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="older"),
            OpenAIMessage(role="assistant", content="answer"),
        ),
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(adapter,),
    )

    assert prepared_input.preparation.context_threshold == {
        "enabled": True,
        "threshold_ratio": 0.9,
        "context_window": 1000,
        "threshold_tokens": 900,
        "reserve_tokens": 200,
        "trigger": "reserve_tokens",
        "scope": "current_run",
        "implementation": "metadata_only",
        "strategy": "basic",
        "mode": "auto",
        "status": "metadata_only",
    }
    assert prepared_input.preparation.compression_profile == "fast"
    assert prepared_input.preparation.lane_budgets == {
        "pinned_tokens": 100,
        "current_turn_tokens": 200,
    }
    assert prepared_input.preparation.selection_policy == {
        "strategy": "deterministic_overlap",
        "max_selected_turns": 3,
        "chronological_reassembly": True,
    }
    assert prepared_input.preparation.lifecycle_stages == (
        {"stage": "validate", "status": "complete"},
        {"stage": "segment", "status": "complete"},
        {"stage": "report", "status": "complete"},
    )
    assert prepared_input.preparation.metrics == ("lane_utilization",)


def test_prepare_model_input_basic_compaction_reports_deterministic_metadata() -> None:
    """Basic fallback compaction is deterministic and protects recent turns."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "basic-compaction-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "strategy": "basic",
                            "summary_prefix": "Basic compacted context:",
                            "max_chars_per_message": 12,
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(
                role="user",
                content="older request with many details " * 20,
            ),
            OpenAIMessage(
                role="assistant",
                content="older answer with many details " * 20,
            ),
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert prepared_input.part_names == (
        "session_summary",
        "session_message_1",
        "session_message_2",
        "user_prompt",
    )
    assert prepared_input.named_parts["session_summary"].content == (
        "Basic compacted context:\n- user: older reque…\n- assistant: older answe…"
    )
    assert prepared_input.named_parts["session_message_1"].content == "latest request"
    assert prepared_input.named_parts["session_message_2"].content == "latest answer"
    assert prepared_input.preparation.compaction["strategy"] == "basic"
    assert prepared_input.preparation.compaction["messages_before"] == 2
    assert prepared_input.preparation.compaction["messages_after"] == 1
    assert (
        prepared_input.preparation.compaction["tokens_before"]
        > (prepared_input.preparation.compaction["tokens_after"])
    )
    assert 0 < prepared_input.preparation.compaction["compression_ratio"] < 1


def test_prepare_model_input_basic_compaction_noops_when_under_target() -> None:
    """Basic fallback compaction does not run when no session history is pruned."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "basic-compaction-noop-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 4},
                        "context_compaction": {"strategy": "basic"},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert "session_summary" not in prepared_input.named_parts
    assert prepared_input.preparation.context_compaction_applied is False
    assert prepared_input.preparation.compaction == {}


def test_prepare_model_input_compaction_tool_pairs_preserves_latest_turn() -> None:
    """Whole-turn pruning must not split a latest tool-call/result turn."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-pair-compaction-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 1},
                        "context_compaction": {"strategy": "basic"},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="old request"),
            OpenAIMessage(role="assistant", content="old answer"),
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="calling lookup"),
            OpenAIMessage(role="tool", content="lookup result"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert [
        prepared_input.named_parts[name].content
        for name in prepared_input.part_names
        if name.startswith("session_message_")
    ] == [
        "latest request",
        "calling lookup",
        "lookup result",
        "latest answer",
    ]
    assert "old request" in prepared_input.named_parts["session_summary"].content
    assert prepared_input.preparation.session_messages_included == 4


def test_prepare_model_input_local_compaction_builds_rolling_summary() -> None:
    """Explicit rolling-summary compaction uses structured local preparation."""

    adapter = make_adapter([])
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "rolling-summary-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "strategy": "rolling_summary",
                            "rolling_summary": {
                                "enabled": True,
                                "prior_summary_slot": "rolling_summary",
                                "source_provenance_slot": "source_provenance",
                                "max_retained_turns": 1,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        node_outputs={
            "rolling_summary": "Earlier summary to fold forward.",
            "source_provenance": ["docs/guide.md", "README.md"],
        },
        session_messages=(
            OpenAIMessage(role="user", content="first old request"),
            OpenAIMessage(role="assistant", content="first old answer"),
            OpenAIMessage(role="user", content="second old request"),
            OpenAIMessage(role="assistant", content="second old answer"),
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(adapter,),
    )

    summary = prepared_input.named_parts["session_summary"].content
    assert "## Prior Summary\nEarlier summary to fold forward." in summary
    assert "## Retained Turns\n- user: second old request" in summary
    assert "- assistant: second old answer" in summary
    assert "first old request" not in summary
    assert "## Source Provenance\n- docs/guide.md\n- README.md" in summary
    assert prepared_input.part_names == (
        "session_summary",
        "session_message_1",
        "session_message_2",
        "user_prompt",
    )
    assert prepared_input.preparation.compaction["strategy"] == "rolling_summary"
    assert prepared_input.preparation.compaction["retained_turn_count"] == 1
    assert prepared_input.preparation.compaction["information_retention_proxy"] > 0
    assert adapter.client.responses.calls == []


def test_prepare_model_input_local_compaction_skips_summary_without_eviction() -> None:
    """Rolling-summary compaction is a no-op when no history is evicted."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "rolling-summary-noop-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 4},
                        "context_compaction": {
                            "strategy": "rolling_summary",
                            "rolling_summary": {"enabled": True},
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert "session_summary" not in prepared_input.named_parts
    assert prepared_input.preparation.compaction == {}


def test_prepare_model_input_pre_turn_compaction_replaces_over_threshold_context() -> (
    None
):
    """Injected pre-turn compaction can replace over-threshold prepared input."""

    calls: list[tuple[OpenAIMessage, ...]] = []

    def fake_compactor(
        messages: tuple[OpenAIMessage, ...],
        metadata: Mapping[str, Any],
    ) -> tuple[OpenAIMessage, ...]:
        calls.append(messages)
        assert metadata["phase"] == "pre_turn"
        return (
            OpenAIMessage(role="developer", content="Compacted replacement history."),
            OpenAIMessage(role="user", content="Answer finish."),
        )

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "pre-turn-compaction-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "context_compaction": {
                            "auto": {
                                "enabled": True,
                                "threshold_ratio": 0.01,
                                "implementation": "injected",
                                "trigger": "token_threshold",
                            }
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="finish " * 80)
    adapter = make_adapter([])
    adapter.context_windows = {"gpt-test": 1000}
    tracer = WorkflowTracer(events=state.trace_events, run_id="test-run")

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(adapter,),
        tracer=tracer,
        context_compactor=fake_compactor,
    )

    assert len(calls) == 1
    assert prepared_input.part_names == (
        "pre_turn_compacted_1",
        "pre_turn_compacted_2",
    )
    assert prepared_input.messages[0].content == "Compacted replacement history."
    assert prepared_input.preparation.pre_turn_compaction["status"] == "complete"
    assert (
        prepared_input.preparation.pre_turn_compaction["implementation"] == "injected"
    )
    assert (
        prepared_input.preparation.pre_turn_compaction["tokens_before"]
        > (prepared_input.preparation.pre_turn_compaction["tokens_after"])
    )
    prepared_events = [
        event
        for event in state.trace_events
        if event.event_type == "model_input_prepared"
    ]
    assert prepared_events[0].payload["pre_turn_compaction"]["phase"] == "pre_turn"
    assert "finish finish" not in repr(
        prepared_events[0].payload["pre_turn_compaction"]
    )


def test_prepare_model_input_new_window_reset_does_not_count_as_compaction() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "new-window-reset-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "reset_behavior": "new_window",
                            "reset_reason": "user_requested",
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="old request"),
            OpenAIMessage(role="assistant", content="old answer"),
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert "session_summary" not in prepared_input.named_parts
    assert prepared_input.preparation.context_compaction_applied is False
    assert prepared_input.preparation.context_reset == {
        "reset_behavior": "new_window",
        "reason": "user_requested",
        "session_messages_dropped": 2,
        "compaction_success": False,
    }


def test_prepare_model_input_reports_context_lanes() -> None:
    """prepare_model_input reports ordered context lanes and utilization metadata."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "context-lanes-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "prompt_hierarchy": {
                            "system": ["Pinned system"],
                            "developer": ["Pinned developer"],
                        },
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "strategy": "summary_message",
                            "summary_prefix": "Earlier:",
                            "auto": {"enabled": True},
                        },
                        "context_compression": {
                            "profile": "balanced",
                            "lanes": {
                                "pinned_tokens": 200,
                                "current_turn_tokens": 400,
                                "recent_turn_tokens": 400,
                                "summary_tokens": 100,
                            },
                        },
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "system": "Base system",
                        "user_template": "Answer {prompt}",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="now",
        session_messages=(
            OpenAIMessage(role="user", content="old"),
            OpenAIMessage(role="assistant", content="old answer"),
            OpenAIMessage(role="user", content="recent"),
            OpenAIMessage(role="assistant", content="recent answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert [lane["lane_id"] for lane in prepared_input.preparation.context_lanes] == [
        "pinned",
        "rolling_summary",
        "recent_turns",
        "current_turn",
    ]
    assert prepared_input.preparation.context_lanes[0]["part_count"] == 3
    assert prepared_input.preparation.context_lanes[0]["budget_tokens"] == 200
    assert prepared_input.preparation.context_lanes[1]["part_count"] == 1
    assert prepared_input.preparation.context_lanes[2]["part_count"] == 2
    assert prepared_input.preparation.context_lanes[3]["part_count"] == 1
    assert prepared_input.preparation.context_lanes[3]["budget_tokens"] == 400


def test_prepare_model_input_enforces_recent_turn_lane_budget() -> None:
    """Recent-turn lane budget trimming does not borrow from current-turn budget."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "lane-budget-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 4},
                        "context_compaction": {
                            "auto": {"enabled": True},
                        },
                        "context_compression": {
                            "profile": "fast",
                            "lanes": {
                                "recent_turn_tokens": 1,
                                "current_turn_tokens": 1000,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="protected current prompt",
        session_messages=(
            OpenAIMessage(role="user", content="recent user with many tokens"),
            OpenAIMessage(
                role="assistant", content="recent assistant with many tokens"
            ),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)
    lane_map = {
        lane["lane_id"]: lane for lane in prepared_input.preparation.context_lanes
    }

    assert "session_message_1" not in prepared_input.named_parts
    assert "session_message_2" not in prepared_input.named_parts
    assert prepared_input.named_parts["user_prompt"].content == (
        "Answer protected current prompt"
    )
    assert lane_map["recent_turns"]["trimmed_count"] == 2
    assert lane_map["recent_turns"]["omitted_count"] == 2
    assert lane_map["current_turn"]["part_count"] == 1


def test_prepare_model_input_older_turn_selection_selects_relevant_turns() -> None:
    """Deterministic older-turn selection reports scores and reasons."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "older-turn-selection-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {"auto": {"enabled": True}},
                        "context_compression": {
                            "profile": "balanced",
                            "lanes": {"selected_turn_tokens": 1000},
                            "selection": {
                                "strategy": "deterministic_overlap",
                                "max_selected_turns": 1,
                                "chronological_reassembly": True,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Explain the billing error in src/billing.py",
        session_messages=(
            OpenAIMessage(role="user", content="Discuss src/auth.py login"),
            OpenAIMessage(role="assistant", content="Auth summary"),
            OpenAIMessage(role="user", content="Investigate src/billing.py error"),
            OpenAIMessage(role="assistant", content="Billing stack trace"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert "selected_turn_1" in prepared_input.named_parts
    assert (
        "src/billing.py error" in prepared_input.named_parts["selected_turn_1"].content
    )
    assert prepared_input.preparation.selected_turns == (
        {
            "turn_id": "turn_2",
            "selection_status": "selected",
            "selection_reason": "deterministic_overlap",
            "relevance_score": 2,
        },
    )
    lane_map = {
        lane["lane_id"]: lane for lane in prepared_input.preparation.context_lanes
    }
    assert lane_map["selected_older_turns"]["part_count"] == 1


def test_prepare_model_input_chronological_reassembly_orders_selected_turns() -> None:
    """Selected older turns render in original order even when scores differ."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "chronological-selection-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 0},
                        "context_compaction": {"auto": {"enabled": True}},
                        "context_compression": {
                            "profile": "balanced",
                            "selection": {
                                "strategy": "deterministic_overlap",
                                "max_selected_turns": 2,
                                "chronological_reassembly": True,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="alpha beta beta",
        session_messages=(
            OpenAIMessage(role="user", content="alpha"),
            OpenAIMessage(role="assistant", content="first"),
            OpenAIMessage(role="user", content="beta beta"),
            OpenAIMessage(role="assistant", content="second"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    selected_names = [
        name for name in prepared_input.part_names if name.startswith("selected_turn_")
    ]
    assert selected_names == ["selected_turn_1", "selected_turn_2"]
    assert "alpha" in prepared_input.named_parts["selected_turn_1"].content
    assert "beta beta" in prepared_input.named_parts["selected_turn_2"].content


def test_prepare_model_input_retrieved_context_lane_packs_evidence() -> None:
    """Caller-provided retrieved evidence is packed into a bounded context lane."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "retrieved-context-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "retrieved_context": {
                            "enabled": True,
                            "source_slot": "retrieved_context",
                            "header": "Retrieved evidence:",
                        },
                        "context_compression": {
                            "lanes": {"retrieved_context_tokens": 8}
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Explain billing retries",
        node_outputs={
            "retrieved_context": [
                {
                    "source_id": "kb-billing",
                    "chunk_id": "chunk-required",
                    "citation_handle": "[1]",
                    "content": "Required billing retry rules.",
                    "required": True,
                    "token_estimate": 20,
                    "score": 0.98,
                    "freshness": {"as_of": "2026-06-16"},
                    "packing_hint": {"order": 1},
                },
                {
                    "source_id": "kb-billing",
                    "chunk_id": "chunk-optional",
                    "citation_handle": "[2]",
                    "content": "Optional retry example.",
                    "lane_hint": "optional",
                    "token_estimate": 4,
                    "score": 0.77,
                    "freshness": {"as_of": "2026-06-15"},
                    "packing_hint": {"order": 2},
                },
                {
                    "source_id": "kb-billing",
                    "chunk_id": "chunk-omitted",
                    "citation_handle": "[3]",
                    "content": "Sensitive omitted evidence body.",
                    "lane_hint": "optional",
                    "token_estimate": 6,
                    "score": 0.52,
                    "freshness": {"as_of": "2026-06-14"},
                    "packing_hint": {"order": 3},
                },
            ]
        },
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert "retrieved_context_1" in prepared_input.named_parts
    assert "retrieved_context_2" in prepared_input.named_parts
    assert "retrieved_context_3" not in prepared_input.named_parts
    assert (
        "Required billing retry rules."
        in prepared_input.named_parts["retrieved_context_1"].content
    )
    assert prepared_input.preparation.retrieved_context == (
        {
            "source_id": "kb-billing",
            "chunk_id": "chunk-required",
            "citation_handle": "[1]",
            "required": True,
            "token_estimate": 20,
            "score": 0.98,
            "freshness": {"as_of": "2026-06-16"},
            "packing_hint": {"order": 1},
            "selection_status": "included",
        },
        {
            "source_id": "kb-billing",
            "chunk_id": "chunk-optional",
            "citation_handle": "[2]",
            "required": False,
            "token_estimate": 4,
            "score": 0.77,
            "freshness": {"as_of": "2026-06-15"},
            "packing_hint": {"order": 2},
            "selection_status": "included",
        },
    )
    assert prepared_input.preparation.retrieved_context_omitted == (
        {
            "source_id": "kb-billing",
            "chunk_id": "chunk-omitted",
            "citation_handle": "[3]",
            "required": False,
            "token_estimate": 6,
            "score": 0.52,
            "freshness": {"as_of": "2026-06-14"},
            "packing_hint": {"order": 3},
            "selection_status": "omitted",
            "selection_reason": "retrieved_context_lane_budget_exceeded",
        },
    )
    lane_map = {
        lane["lane_id"]: lane for lane in prepared_input.preparation.context_lanes
    }
    assert lane_map["retrieved_context"]["part_count"] == 2
    assert lane_map["retrieved_context"]["budget_tokens"] == 8
    assert lane_map["retrieved_context"]["omitted_count"] == 1


def test_prepare_model_input_retrieved_context_lane_redacts_trace_content() -> None:
    """Retrieved-context trace metadata must not expose raw evidence content."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "retrieved-context-trace-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "retrieved_context": {"enabled": True},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Explain billing retries",
        node_outputs={
            "retrieved_context": [
                {
                    "source_id": "kb-billing",
                    "chunk_id": "chunk-sensitive",
                    "citation_handle": "[1]",
                    "content": "Do not leak this retrieved body in traces.",
                    "token_estimate": 5,
                }
            ]
        },
    )
    tracer = WorkflowTracer(events=state.trace_events, run_id="test-run")

    prepare_model_input(plan.nodes_by_id["answer"], plan, state, tracer=tracer)

    prepared_events = [
        event
        for event in state.trace_events
        if event.event_type == "model_input_prepared"
    ]
    assert len(prepared_events) == 1
    trace_payload = prepared_events[0].payload
    assert trace_payload["retrieved_context"] == (
        {
            "source_id": "kb-billing",
            "chunk_id": "chunk-sensitive",
            "citation_handle": "[1]",
            "required": False,
            "token_estimate": 5,
            "selection_status": "included",
        },
    )
    assert "Do not leak this retrieved body" not in repr(trace_payload)


def test_prepare_model_input_includes_bounded_file_context_with_provenance(
    tmp_path,
) -> None:
    """File-backed prompt context is opt-in, bounded, and source-tracked."""

    package_dir = tmp_path / "file-context-package"
    package_dir.mkdir()
    (package_dir / "README.md").write_text("Package overview\n", encoding="utf-8")
    docs_dir = package_dir / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("Guide details\n", encoding="utf-8")
    nested_dir = docs_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "ignored.md").write_text("Ignored nested file\n", encoding="utf-8")

    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "file-context-agent",
                "entrypoint": "answer",
                "packaging": {"mode": "hybrid_bundle"},
                "runtime": {
                    "execution_policy": {
                        "model": "gpt-test",
                        "prepare_model_input": {
                            "file_context": {
                                "enabled": True,
                                "roots": ["docs", "README.md"],
                                "max_depth": 1,
                                "max_files": 2,
                                "max_bytes": 4096,
                                "max_tokens": 400,
                                "prompt_role": "developer",
                                "header": "Project context:",
                            }
                        },
                    }
                },
                "nodes": [
                    {
                        "id": "answer",
                        "kind": "llm_step",
                        "prompt": {"user_template": "Answer {prompt}."},
                    }
                ],
                "edges": [],
            }
        ),
        package_root=str(package_dir),
    )
    plan = prepare_execution_plan(workflow)

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        WorkflowExecutionState(prompt="question"),
    )

    assert prepared_input.part_names == (
        "file_context_1",
        "file_context_2",
        "user_prompt",
    )
    assert prepared_input.preparation.file_context_applied is True
    assert prepared_input.preparation.file_context_sources == (
        "README.md",
        "docs/guide.md",
    )
    assert prepared_input.preparation.file_context_files_included == 2
    assert prepared_input.preparation.file_context_bytes > 0
    assert prepared_input.preparation.file_context_estimated_tokens > 0
    assert "Source: README.md" in prepared_input.named_parts["file_context_1"].content
    assert (
        "Source: docs/guide.md" in prepared_input.named_parts["file_context_2"].content
    )
    assert "ignored.md" not in prepared_input.named_parts["file_context_2"].content


def test_prepare_model_input_rejects_file_context_roots_outside_package(
    tmp_path,
) -> None:
    """File-backed prompt context rejects roots that escape the package root."""

    package_dir = tmp_path / "file-context-package"
    package_dir.mkdir()

    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "file-context-agent",
                "entrypoint": "answer",
                "packaging": {"mode": "hybrid_bundle"},
                "runtime": {
                    "execution_policy": {
                        "model": "gpt-test",
                        "prepare_model_input": {
                            "file_context": {
                                "enabled": True,
                                "roots": ["../outside"],
                                "max_depth": 1,
                                "max_files": 1,
                                "max_bytes": 512,
                            }
                        },
                    }
                },
                "nodes": [
                    {
                        "id": "answer",
                        "kind": "llm_step",
                        "prompt": {"user_template": "Answer {prompt}."},
                    }
                ],
                "edges": [],
            }
        ),
        package_root=str(package_dir),
    )
    plan = prepare_execution_plan(workflow)

    with pytest.raises(WorkflowExecutionError) as exc_info:
        prepare_model_input(
            plan.nodes_by_id["answer"],
            plan,
            WorkflowExecutionState(prompt="question"),
        )

    assert "escapes package root" in str(exc_info.value)


def test_execute_workflow_async_runs_async_model_adapter() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "async-model-agent",
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
    adapter = make_async_adapter([{"id": "resp", "output_text": "async done"}])

    result = asyncio.run(
        execute_workflow_async(workflow, prompt="Hello", model_adapter=adapter)
    )

    assert result.final_result == "async done"
    assert adapter.client.responses.calls[0]["model"] == "gpt-test"


def test_execute_workflow_async_awaits_async_direct_tool() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "async-tool-agent",
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
        [make_async_tool("search_repo", output={"answer": "async 42"})]
    )

    result = asyncio.run(
        execute_workflow_async(workflow, prompt="Run", tool_registry=registry)
    )

    assert result.final_result == {"answer": "async 42"}
    assert result.state.tool_results["lookup"].output == {"answer": "async 42"}


def test_execute_workflow_async_awaits_async_lifecycle_hooks() -> None:
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
                }
            ],
            "edges": [],
        }
    )
    observed: list[str] = []

    async def before_node(context: NodeHookContext) -> None:
        await asyncio.sleep(0)
        observed.append(f"before:{context.node_id}:{context.run_id}")

    async def after_node(context: NodeHookContext) -> None:
        await asyncio.sleep(0)
        observed.append(f"after:{context.node_id}:{context.output}:{context.run_id}")

    result = asyncio.run(
        execute_workflow_async(
            workflow,
            prompt="Hello",
            model_adapter=make_async_adapter([{"id": "resp", "output_text": "done"}]),
            lifecycle_hooks=WorkflowLifecycleHooks(
                before_node=before_node,
                after_node=after_node,
            ),
            run_id="async-run-1",
        )
    )

    assert result.final_result == "done"
    assert observed == ["before:answer:async-run-1", "after:answer:done:async-run-1"]


def test_execute_workflow_runs_llm_tool_and_final_llm_steps() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "executor-agent",
            "entrypoint": "analyze",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
    assert first_call["tools"][0]["name"] == "search_repo"


def test_execute_workflow_does_not_loop_model_tool_calls_without_policy() -> None:
    tool_invocations: list[object] = []

    def search_handler(args: object) -> object:
        tool_invocations.append(args)
        return {"answer": "42"}

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "single-call-tool-agent",
            "entrypoint": "analyze",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "analyze",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Question: {prompt}"},
                    "available_tools": ["search_repo"],
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {
                        "id": "search_repo",
                        "description_for_llm": "Search",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    }
                ),
                search_handler,
            )
        ]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            }
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result is None
    assert len(adapter.client.responses.calls) == 1
    assert tool_invocations == []
    assert result.state.node_outputs["analyze"].tool_calls[0].name == "search_repo"


def test_execute_workflow_loops_model_tool_call_with_policy() -> None:
    workflow = loop_tool_workflow()
    registry = InMemoryToolRegistry(
        [
            make_tool(
                "search_repo",
                output=ToolResult(
                    tool_id="search_repo",
                    success=True,
                    output={"raw": "secret raw"},
                    model_output={"summary": "agents found"},
                ),
            )
        ]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
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
    assert len(adapter.client.responses.calls) == 2
    second_input = adapter.client.responses.calls[1]["input"]
    assert second_input[-2]["role"] == "assistant"
    assert second_input[-2]["content"] == "Tool call call_1: search_repo"
    assert second_input[-1] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "search_repo",
        "content": '{"summary": "agents found"}',
    }
    assert result.state.tool_results["analyze.call_1"].model_facing_output == {
        "summary": "agents found"
    }


def test_execute_workflow_mid_turn_compaction_fails_without_compactor() -> None:
    workflow = loop_tool_workflow()
    workflow.runtime_manifest.execution_policy["prepare_model_input"] = {
        "context_compaction": {
            "auto": {
                "enabled": True,
                "threshold_tokens": 20,
                "implementation": "injected",
            }
        }
    }
    registry = InMemoryToolRegistry(
        [make_tool("search_repo", output={"summary": "agents found " * 20})]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="mid-turn context compaction"):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=registry,
            model_adapter=adapter,
        )


def test_execute_workflow_mid_turn_compaction_uses_injected_compactor() -> None:
    workflow = loop_tool_workflow()
    workflow.runtime_manifest.execution_policy["prepare_model_input"] = {
        "context_compaction": {
            "auto": {
                "enabled": True,
                "threshold_tokens": 20,
                "implementation": "injected",
            }
        }
    }
    registry = InMemoryToolRegistry(
        [make_tool("search_repo", output={"summary": "agents found " * 20})]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {"id": "resp_2", "output_text": "final answer"},
        ]
    )

    def fake_compactor(
        _messages: tuple[OpenAIMessage, ...],
        metadata: Mapping[str, Any],
    ) -> tuple[OpenAIMessage, ...]:
        assert metadata["phase"] == "pre_turn"
        return (
            OpenAIMessage(role="developer", content="Mid-turn compacted context."),
            OpenAIMessage(role="user", content="Continue."),
        )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
        context_compactor=fake_compactor,
    )

    assert result.final_result == "final answer"
    second_input = adapter.client.responses.calls[1]["input"]
    assert second_input == [
        {"role": "developer", "content": "Mid-turn compacted context."},
        {"role": "user", "content": "Continue."},
    ]
    compaction_events = [
        event
        for event in result.state.trace_events
        if event.event_type == "mid_turn_compaction"
    ]
    assert compaction_events[0].payload["status"] == "complete"
    assert compaction_events[0].payload["phase"] == "mid_turn"


def test_execute_workflow_traces_iterative_model_tool_loop() -> None:
    workflow = loop_tool_workflow()
    registry = InMemoryToolRegistry(
        [make_tool("search_repo", output={"summary": "agents found"})]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {"id": "resp_2", "output_text": "final answer"},
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
        run_id="loop-run-1",
    )

    loop_events = [
        event
        for event in result.state.trace_events
        if event.event_type.startswith("model_tool_loop")
    ]
    assert [event.event_type for event in loop_events] == [
        "model_tool_loop_started",
        "model_tool_loop_turn_started",
        "model_tool_loop_tool_call",
        "model_tool_loop_stopped",
        "model_tool_loop_final_output",
    ]
    assert {event.run_id for event in loop_events} == {"loop-run-1"}
    assert loop_events[0].payload == {
        "max_iterations": 8,
        "tool_count": 1,
    }
    assert loop_events[1].payload == {
        "iteration": 1,
        "tool_call_count": 1,
    }
    assert loop_events[2].payload == {
        "iteration": 1,
        "tool_call_id": "call_1",
        "tool_id": "search_repo",
        "arguments": {"query": "agents"},
    }
    assert "arguments" in loop_events[2].sensitive_fields
    assert loop_events[3].payload == {
        "iteration": 2,
        "stop_reason": "final_model_output",
    }
    assert loop_events[4].payload == {
        "final_output": "final answer",
        "final_output_policy": "default",
        "stop_reason": "final_model_output",
    }
    assert "final_output" in loop_events[4].sensitive_fields


def test_execute_workflow_rejects_unavailable_model_tool_call() -> None:
    workflow = loop_tool_workflow(available_tools=["search_repo"])
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "write_file",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            }
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="unavailable tool 'write_file'"):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=InMemoryToolRegistry([make_tool("search_repo")]),
            model_adapter=adapter,
        )


def test_execute_workflow_rejects_hidden_model_tool_call() -> None:
    workflow = loop_tool_workflow(
        available_tools=["hidden_search"],
        tools=[{"id": "hidden_search", "exposure": "hidden"}],
    )
    calls: list[object] = []
    hidden_tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "hidden_search",
                "exposure": "hidden",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ),
        lambda args: calls.append(args) or {"answer": "hidden"},
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "hidden_search",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            }
        ]
    )

    with pytest.raises(
        WorkflowExecutionError, match="unavailable tool 'hidden_search'"
    ):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=InMemoryToolRegistry([hidden_tool]),
            model_adapter=adapter,
        )

    assert calls == []


def test_execute_workflow_rejects_malformed_model_tool_arguments() -> None:
    workflow = loop_tool_workflow()
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": "not json",
                    }
                ],
            }
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="arguments must be JSON"):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=InMemoryToolRegistry([make_tool("search_repo")]),
            model_adapter=adapter,
        )


def test_execute_workflow_aborts_failed_model_tool_call() -> None:
    workflow = loop_tool_workflow()
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            }
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="search unavailable"):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=InMemoryToolRegistry(
                [make_flaky_tool("search_repo", [RuntimeError("search unavailable")])]
            ),
            model_adapter=adapter,
        )


def test_execute_workflow_stops_at_model_tool_loop_limit() -> None:
    workflow = loop_tool_workflow(max_steps=1)
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {
                "id": "resp_2",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_2",
                        "name": "search_repo",
                        "arguments": '{"query":"more"}',
                    }
                ],
            },
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="tool loop limit 1"):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=InMemoryToolRegistry([make_tool("search_repo")]),
            model_adapter=adapter,
        )


def test_execute_workflow_pauses_approval_required_model_tool_before_invocation() -> (
    None
):
    calls: list[object] = []
    workflow = loop_tool_workflow(
        tools=[
            {
                "id": "workspace_write",
                "approval_required": "yes",
                "side_effect": "write",
            }
        ],
        available_tools=["workspace_write"],
    )
    tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "workspace_write",
                "approval_required": "yes",
                "side_effect": "write",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ),
        lambda args: calls.append(args) or {"ok": True},
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "workspace_write",
                        "arguments": '{"query":"notes"}',
                    }
                ],
            }
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=InMemoryToolRegistry([tool]),
        model_adapter=adapter,
    )

    assert isinstance(result, WorkflowInterruptedResult)
    assert calls == []
    assert result.interruption.node_id == "analyze"
    assert result.interruption.tool_id == "workspace_write"
    assert result.interruption.action_id == "call_1"
    assert result.interruption.arguments == {"query": "notes"}
    assert result.state.tool_results == {}


def loop_tool_workflow(
    *,
    tools: list[dict[str, object]] | None = None,
    available_tools: list[str] | None = None,
    max_steps: int | None = None,
) -> LoadedAgentWorkflow:
    execution_policy: dict[str, object] = {
        "model": "gpt-test",
        "tool_use_completion": {
            "run_again": "required",
            "stop_on_tool": "disabled",
            "final_output": "default",
        },
    }
    if max_steps is not None:
        execution_policy["max_steps"] = max_steps
    tool_entries = tools or [{"id": "search_repo"}]
    return workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "loop-tool-agent",
            "entrypoint": "analyze",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": execution_policy},
            "nodes": [
                {
                    "id": "analyze",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Question: {prompt}"},
                    "available_tools": (
                        available_tools
                        if available_tools is not None
                        else ["search_repo"]
                    ),
                }
            ],
            "edges": [],
            "tools": tool_entries,
        }
    )


def test_execute_workflow_uses_model_facing_tool_output_in_context_and_trace() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-facet-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
            "output_contracts": [
                {
                    "id": "answer_contract",
                    "required_fields": ["message", "confidence"],
                }
            ],
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
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "output_schema_ref": "answer_contract",
                }
            ],
            "edges": [],
            "output_contracts": [
                {
                    "id": "answer_contract",
                    "required_fields": ["message", "confidence"],
                }
            ],
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
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "output_schema_ref": "answer_contract",
                }
            ],
            "edges": [],
            "output_contracts": [
                {
                    "id": "answer_contract",
                    "required_fields": ["message", "confidence"],
                }
            ],
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
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "output_schema_ref": "missing_contract",
                }
            ],
            "edges": [],
            "output_contracts": [],
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
        "runtime": {"execution_policy": {"model": "gpt-test"}},
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


def test_prepare_model_input_routes_to_adapter_model_by_required_features() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "feature-routing-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "default_model": "remote-basic",
                    "model_map": {
                        "remote-basic": ["tool_calling"],
                        "local-structured": ["tool_calling", "structured_output"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "model_requirements": {
                        "required_capabilities": ["structured_output"]
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")
    remote = make_named_adapter(
        [{"id": "unused", "output_text": "remote"}], models=["remote-basic"]
    )
    local = make_named_adapter(
        [{"id": "unused-2", "output_text": "local"}],
        models=["local-structured"],
        is_local=True,
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=[remote, local],
    )

    assert prepared_input.model == "local-structured"
    assert prepared_input.adapter is local


def test_execute_workflow_fails_when_no_adapter_matches_required_features() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "fallback-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "default_model": "local-structured",
                    "model_map": {
                        "remote-basic": ["tool_calling"],
                        "local-structured": ["structured_output"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "model_requirements": {
                        "required_capabilities": ["structured_output"]
                    },
                }
            ],
            "edges": [],
        }
    )
    remote = make_named_adapter(
        [{"id": "remote", "output_text": "remote-result"}],
        models=["remote-basic"],
    )

    with pytest.raises(WorkflowExecutionError, match="requires capabilities"):
        execute_workflow(workflow, prompt="Hello", model_adapter=[remote])

    assert remote.client.responses.calls == []


def test_execute_workflow_strict_fails_with_no_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-empty-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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

    def fail_default_adapter(*args, **kwargs):
        raise AssertionError("strict coverage must not create a default adapter")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor.AsyncOpenAIClientAdapter",
        fail_default_adapter,
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=None,
            model_adapter_coverage="strict",
        )


def test_execute_workflow_strict_fails_with_empty_adapter_list() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-empty-list-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=[],
            model_adapter_coverage="strict",
        )


def test_execute_workflow_strict_fails_with_nonmatching_adapter() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-nonmatching-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    adapter = make_named_adapter(
        [{"id": "unused", "output_text": "wrong"}],
        models=["other-model"],
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=[adapter],
            model_adapter_coverage="strict",
        )

    assert adapter.client.responses.calls == []


def test_execute_workflow_strict_with_mlx_adapter_prevents_default_openai(
    tmp_path: Path,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-mlx-nonmatching-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    backend = FakeMLXBackend()
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "mlx-model",
        ),
        backend=backend,
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=[adapter],
            model_adapter_coverage="strict",
        )

    assert backend.requests == []


def test_execute_workflow_strict_fails_when_required_features_are_unavailable() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-feature-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "default_model": "structured-model",
                    "model_map": {
                        "basic-model": ["tool_calling"],
                        "structured-model": ["structured_output"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "model_requirements": {
                        "required_capabilities": ["structured_output"]
                    },
                }
            ],
            "edges": [],
        }
    )
    adapter = make_named_adapter(
        [{"id": "unused", "output_text": "basic"}],
        models=["basic-model"],
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=[adapter],
            model_adapter_coverage="strict",
        )

    assert adapter.client.responses.calls == []


def test_execute_workflow_augmented_uses_default_openai_for_missing_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "augmented-default-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    supplied = make_named_adapter(
        [{"id": "unused", "output_text": "wrong"}],
        models=["other-model"],
    )
    seen_adapters: list[object] = []
    created_kwargs: list[dict[str, object]] = []
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeOfficialAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(AsyncOpenAI=FakeOfficialAsyncOpenAI),
    )

    async def fake_create_model_response(adapter, request):
        seen_adapters.append(adapter)
        _client = adapter.client
        return ModelResponse(response_id="resp-default", content="default ok")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._create_model_response_async",
        fake_create_model_response,
    )

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=[supplied],
        model_adapter_coverage="augmented",
    )

    assert result.final_result == "default ok"
    assert supplied.client.responses.calls == []
    assert isinstance(seen_adapters[0], AsyncOpenAIClientAdapter)
    assert seen_adapters[0].models == ("gpt-test",)
    assert created_kwargs == [{"api_key": "ambient-key"}]


def test_execute_workflow_augmented_default_openai_uses_chatgpt_codex_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "augmented-chatgpt-default-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    supplied = make_named_adapter(
        [{"id": "unused", "output_text": "wrong"}],
        models=["other-model"],
    )
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        '{"auth_mode": "chatgpt", "tokens": {"access_token": "secret-token"}}',
        encoding="utf-8",
    )
    seen_adapters: list[object] = []
    created_kwargs: list[dict[str, object]] = []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    class FakeOfficialAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(AsyncOpenAI=FakeOfficialAsyncOpenAI),
    )

    async def fake_create_model_response(adapter, request):
        seen_adapters.append(adapter)
        _client = adapter.client
        return ModelResponse(response_id="resp-default", content="default ok")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._create_model_response_async",
        fake_create_model_response,
    )

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=[supplied],
        model_adapter_coverage="augmented",
    )

    assert result.final_result == "default ok"
    assert supplied.client.responses.calls == []
    assert isinstance(seen_adapters[0], AsyncOpenAIClientAdapter)
    assert created_kwargs == [
        {
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": "secret-token",
        }
    ]


def test_execute_workflow_augmented_with_mlx_adapter_uses_default_openai(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "augmented-mlx-default-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    backend = FakeMLXBackend("wrong")
    supplied = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "mlx-model",
        ),
        backend=backend,
        platform_system=lambda: "Darwin",
    )
    seen_adapters: list[object] = []

    async def fake_create_model_response(adapter, request):
        seen_adapters.append(adapter)
        return ModelResponse(response_id="resp-default", content="default ok")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._create_model_response_async",
        fake_create_model_response,
    )

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=[supplied],
        model_adapter_coverage="augmented",
    )

    assert result.final_result == "default ok"
    assert backend.requests == []
    assert isinstance(seen_adapters[0], AsyncOpenAIClientAdapter)
    assert seen_adapters[0].models == ("gpt-test",)


def test_execute_workflow_strict_with_llama_cpp_adapter_prevents_default_openai(
    tmp_path: Path,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-llama-cpp-nonmatching-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")
    backend = FakeLlamaCppBackend()
    adapter = create_llama_cpp_local_adapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
        backend=backend,
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=[adapter],
            model_adapter_coverage="strict",
        )

    assert backend.calls == []


def test_execute_workflow_augmented_with_llama_cpp_adapter_uses_default_openai(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "augmented-llama-cpp-default-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")
    backend = FakeLlamaCppBackend("wrong")
    supplied = create_llama_cpp_local_adapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
        backend=backend,
    )
    seen_adapters: list[object] = []

    async def fake_create_model_response(adapter, request):
        seen_adapters.append(adapter)
        return ModelResponse(response_id="resp-default", content="default ok")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._create_model_response_async",
        fake_create_model_response,
    )

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=[supplied],
        model_adapter_coverage="augmented",
    )

    assert result.final_result == "default ok"
    assert backend.calls == []
    assert isinstance(seen_adapters[0], AsyncOpenAIClientAdapter)
    assert seen_adapters[0].models == ("gpt-test",)


def test_execute_workflow_omitted_coverage_defaults_to_augmented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "augmented-default-omitted-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    supplied = make_named_adapter(
        [{"id": "unused", "output_text": "wrong"}],
        models=["other-model"],
    )
    seen_adapters: list[object] = []

    async def fake_create_model_response(adapter, request):
        seen_adapters.append(adapter)
        return ModelResponse(response_id="resp-default", content="default ok")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._create_model_response_async",
        fake_create_model_response,
    )

    result = execute_workflow(workflow, prompt="Hello", model_adapter=[supplied])

    assert result.final_result == "default ok"
    assert supplied.client.responses.calls == []
    assert isinstance(seen_adapters[0], AsyncOpenAIClientAdapter)


def test_execute_workflow_rejects_unknown_model_adapter_coverage() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "invalid-coverage-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter_coverage="best_effort",
        )


def test_execution_context_applies_model_adapter_coverage() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "context-strict-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    context = WorkflowExecutionContext(
        workflow=workflow,
        model_adapter=[],
        model_adapter_coverage="strict",
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(context, prompt="Hello")


def test_prepare_model_input_uses_openai_model_registry_for_native_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "registry-routing-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-4o-mini"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "model_requirements": {
                        "required_capabilities": ["structured_output"]
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")
    remote = make_named_adapter(
        [{"id": "unused", "output_text": "remote"}],
        models=["custom-remote"],
    )
    local = make_named_adapter(
        [{"id": "unused-2", "output_text": "local"}],
        models=["gpt-4o-mini"],
        is_local=True,
    )

    class FakeCapabilities:
        supports_structured = True
        supports_functions = True
        supports_vision = False
        supports_web_search = False
        context_window = 128000
        input_modalities = ["text"]

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._get_openai_model_capabilities",
        lambda model_name: FakeCapabilities() if model_name == "gpt-4o-mini" else None,
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=[remote, local],
    )

    assert prepared_input.model == "gpt-4o-mini"
    assert prepared_input.adapter is local


def test_prepare_model_input_does_not_route_by_local_only_metadata() -> None:
    from dynamic_agent_runner.local_models import (
        LocalOpenAIEndpointConfig,
        create_local_openai_adapter,
    )

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "local-only-metadata-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "default_model": "qwen-local",
                    "model_map": {
                        "qwen-local": ["structured_output"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "model_requirements": {
                        "operational_preferences": {"data_boundary": "local_only"},
                        "required_capabilities": ["structured_output"],
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")
    remote = make_named_adapter(
        [{"id": "unused", "output_text": "remote"}],
        models=["qwen-local"],
    )
    local = create_local_openai_adapter(
        LocalOpenAIEndpointConfig(
            base_url="http://localhost:11434/v1",
            api_key="local-key",
            model_aliases=["qwen-local", "chat-default"],
            provider_name="llama.cpp",
            expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
        )
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=[remote, local],
    )

    assert prepared_input.model == "qwen-local"
    assert prepared_input.adapter is remote
    assert local.is_local is True
    assert local.models == ("qwen-local", "chat-default")


def test_prepare_model_input_uses_default_openai_adapter_without_capability_routing() -> (
    None
):
    """Without provided adapters or model-map requirements, the default OpenAI adapter is used."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "default-openai-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-4o-mini"}},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(),
    )

    assert prepared_input.model == "gpt-4o-mini"
    assert isinstance(prepared_input.adapter, AsyncOpenAIClientAdapter)
    assert prepared_input.adapter.models == ("gpt-4o-mini",)


def test_prepare_model_input_uses_lowest_supported_model_when_workflow_omits_model() -> (
    None
):
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "missing-model-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")
    models = FakeModels(
        {
            "data": [
                {"id": "gpt-5.5"},
                {"id": "gpt-5.4"},
                {"id": "codex-auto-review"},
            ]
        }
    )
    adapter = OpenAIClientAdapter(FakeClient([{"id": "unused"}], models=models))

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=[adapter],
    )

    assert prepared_input.model == "gpt-5.4"
    assert prepared_input.adapter is adapter
    assert models.calls == [{}]


def test_prepare_model_input_auto_creates_default_adapter_when_workflow_omits_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "missing-model-default-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")

    class FakeDefaultOpenAIClientAdapter:
        def default_model(self) -> str:
            return "gpt-5.4"

    monkeypatch.setattr(
        "dynamic_agent_runner.executor.OpenAIClientAdapter",
        FakeDefaultOpenAIClientAdapter,
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(),
    )

    assert prepared_input.model == "gpt-5.4"
    assert isinstance(prepared_input.adapter, AsyncOpenAIClientAdapter)
    assert prepared_input.adapter.models == ("gpt-5.4",)


def test_execute_workflow_applies_skill_only_remove_and_node_isolation() -> None:
    """Per-node skill binding overrides stay scoped to their target node."""

    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "skill-scope-agent",
        "entrypoint": "first",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": {"model": "gpt-test"}},
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
        "runtime": {"execution_policy": {"model": "gpt-test"}},
        "nodes": [
            {
                "id": "answer",
                "kind": "llm_step",
                "prompt": {"user_template": "Answer {prompt}"},
            }
        ],
        "edges": [],
        "output_contracts": [
            {"id": "strict_answer", "required_fields": ["message", "confidence"]}
        ],
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
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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


def test_execute_workflow_pauses_approval_required_tool_before_invocation() -> None:
    calls: list[object] = []
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "approval-pause-agent",
            "entrypoint": "write",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "write",
                    "kind": "tool_use_step",
                    "tool_id": "workspace_write",
                    "inputs": {"path": "notes.txt", "content": "hello"},
                }
            ],
            "edges": [],
            "tools": [
                {
                    "id": "workspace_write",
                    "approval_required": "yes",
                    "side_effect": "write",
                    "sandbox": "workspace",
                }
            ],
        }
    )
    tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "workspace_write",
                "approval_required": "yes",
                "side_effect": "write",
                "sandbox": "workspace",
            }
        ),
        lambda args: calls.append(args) or {"ok": True},
    )
    registry = InMemoryToolRegistry([tool])

    result = execute_workflow(workflow, prompt="Run", tool_registry=registry)

    assert isinstance(result, WorkflowInterruptedResult)
    assert calls == []
    assert result.final_result is None
    assert result.interruption.run_id == result.state.run_id
    assert result.interruption.workflow_id == "approval-pause-agent"
    assert result.interruption.node_id == "write"
    assert result.interruption.tool_id == "workspace_write"
    assert result.interruption.arguments == {"path": "notes.txt", "content": "hello"}
    assert result.interruption.policy["approval_required"] == "yes"
    assert result.state.tool_results == {}
    assert result.state.executions == []


def input_guardrail_workflow() -> LoadedAgentWorkflow:
    return workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "input-guardrail-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "extensions": {
                "guardrails": {
                    "declarations": [
                        {
                            "id": "no_secrets",
                            "phase": "input",
                            "behavior_on_tripwire": "abort",
                        }
                    ]
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


def test_execute_workflow_fails_closed_for_missing_input_guardrail_adapter() -> None:
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    with pytest.raises(GuardrailExecutionError, match="no_secrets"):
        execute_workflow(
            input_guardrail_workflow(),
            prompt="hello",
            model_adapter=adapter,
        )

    assert adapter.client.responses.calls == []


def test_execute_workflow_aborts_on_input_guardrail_tripwire() -> None:
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])
    guardrails = InMemoryGuardrailRegistry(
        {
            "no_secrets": lambda _subject: GuardrailResult(
                guardrail_id="no_secrets",
                decision=GuardrailDecision.ABORT,
                reason_code="secret_detected",
                message="Secret content is not allowed.",
            )
        }
    )

    with pytest.raises(GuardrailExecutionError, match="secret_detected"):
        execute_workflow(
            input_guardrail_workflow(),
            prompt="secret",
            model_adapter=adapter,
            guardrail_registry=guardrails,
        )

    assert adapter.client.responses.calls == []


def test_run_agent_workflow_returns_final_result() -> None:
    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "api-agent",
        "entrypoint": "answer",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": {"model": "gpt-test"}},
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


def approval_required_tool_manifest() -> dict[str, object]:
    return {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "approval-api-agent",
        "entrypoint": "write",
        "packaging": {"mode": "hybrid_bundle"},
        "nodes": [
            {
                "id": "write",
                "kind": "tool_use_step",
                "tool_id": "workspace_write",
                "inputs": {"path": "notes.txt", "content": "hello"},
            }
        ],
        "edges": [],
        "tools": [{"id": "workspace_write", "approval_required": "yes"}],
    }


def approval_required_tool_registry() -> InMemoryToolRegistry:
    return InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {"id": "workspace_write", "approval_required": "yes"}
                ),
                lambda _args: {"ok": True},
            )
        ]
    )


def test_run_agent_workflow_errors_when_workflow_is_interrupted() -> None:
    with pytest.raises(WorkflowExecutionError, match="interrupted for approval"):
        run_agent_workflow(
            prompt="Run",
            runtime_manifest=approval_required_tool_manifest(),
            tool_registry=approval_required_tool_registry(),
        )


async def _run_agent_workflow_async_errors_when_workflow_is_interrupted() -> None:
    with pytest.raises(WorkflowExecutionError, match="interrupted for approval"):
        await run_agent_workflow_async(
            prompt="Run",
            runtime_manifest=approval_required_tool_manifest(),
            tool_registry=approval_required_tool_registry(),
        )


def test_run_agent_workflow_async_errors_when_workflow_is_interrupted() -> None:
    asyncio.run(_run_agent_workflow_async_errors_when_workflow_is_interrupted())


def test_run_agent_workflow_async_returns_final_result() -> None:
    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "async-api-agent",
        "entrypoint": "answer",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": {"model": "gpt-test"}},
        "nodes": [
            {
                "id": "answer",
                "kind": "llm_step",
                "prompt": {"user_template": "{prompt}"},
            }
        ],
        "edges": [],
    }

    final_result = asyncio.run(
        run_agent_workflow_async(
            runtime_manifest=manifest,
            prompt="Hello",
            model_adapter=make_async_adapter(
                [{"id": "resp", "output_text": "async done"}]
            ),
        )
    )

    assert final_result == "async done"


def test_execute_workflow_sync_wrapper_accepts_async_model_adapter() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "sync-wrapper-async-adapter-agent",
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

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=make_async_adapter([{"id": "resp", "output_text": "done"}]),
    )

    assert result.final_result == "done"


def test_execute_workflow_sync_wrapper_rejects_running_event_loop() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "sync-wrapper-loop-agent",
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

    async def call_sync_wrapper() -> None:
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
        )

    with pytest.raises(WorkflowExecutionError, match="event loop"):
        asyncio.run(call_sync_wrapper())


def test_run_agent_workflow_sync_wrapper_rejects_running_event_loop() -> None:
    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "api-sync-wrapper-loop-agent",
        "entrypoint": "answer",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": {"model": "gpt-test"}},
        "nodes": [
            {
                "id": "answer",
                "kind": "llm_step",
                "prompt": {"user_template": "{prompt}"},
            }
        ],
        "edges": [],
    }

    async def call_sync_wrapper() -> None:
        run_agent_workflow(
            runtime_manifest=manifest,
            prompt="Hello",
            model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
        )

    with pytest.raises(WorkflowExecutionError, match="event loop"):
        asyncio.run(call_sync_wrapper())


def test_run_agent_workflow_accepts_execution_context() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "api-context-agent",
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
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "retry_policy": {"max_attempts": 3, "retry_on": ["tool_failure"]},
                }
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
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "retry_policy": {"max_attempts": 2, "retry_on": ["exception"]},
                }
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
