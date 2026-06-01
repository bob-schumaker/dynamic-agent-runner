"""Tests for workflow executor behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dynamic_agent_runner.api import (
    compile_agent_workflow,
    load_agent_package_workflow,
    run_agent_workflow,
    run_agent_workflow_async,
)
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.errors import ModelExecutionError, WorkflowExecutionError
from dynamic_agent_runner.executor import (
    execute_workflow,
    execute_workflow_async,
    WorkflowExecutionState,
    prepare_model_input,
)
from dynamic_agent_runner.hooks import NodeHookContext, WorkflowLifecycleHooks
from dynamic_agent_runner.models import (
    LoadedAgentWorkflow,
    ToolDefinition,
    prepare_execution_plan,
)
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    OpenAIClientAdapter,
    OpenAIMessage,
)
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
                    "retry_policy": {"max_attempts": 2},
                    "token_budget": {"max_prompt_tokens": 100},
                }
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
    assert lookup.inputs == {"query": "static"}
    assert lookup.inputs_from == {"extra": "answer"}
    assert lookup.outputs == {"state_key": "lookup_summary"}
    assert lookup.failure_behavior == "continue"
    route = plan.nodes_by_id["route"]
    assert route.route_from == "answer"
    assert route.allowed_routes == frozenset({"done"})


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
    assert first_call["tools"][0]["function"]["name"] == "search_repo"


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
