"""Power-Marimo runtime package fixture coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from dynamic_agent_runner import InMemoryToolRegistry, RegisteredTool, execute_workflow
from dynamic_agent_runner import load_agent_workflow
from dynamic_agent_runner.models import (
    PRIMITIVE_NODE_KINDS,
    ToolDefinition,
    ToolSourceKind,
)
from dynamic_agent_runner.openai_client import OpenAIClientAdapter

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "power-marimo"


def test_power_marimo_runtime_package_loads_and_records_agent_as_tool() -> None:
    workflow = load_agent_workflow(
        runtime_manifest=FIXTURE_ROOT / "agent-runtime.yaml",
        agent_design=FIXTURE_ROOT / "agent-design.md",
    )

    manifest = workflow.runtime_manifest
    node_map = {node.id: node for node in manifest.nodes}
    tool_map = {tool.id: tool for tool in manifest.tools}

    assert manifest.package_id == "power-marimo-runtime-package-fixture"
    assert manifest.patterns_present == ("workflow-orchestration-agent",)
    assert set(manifest.runtime) >= {"execution_policy", "state"}
    assert set(manifest.metadata) >= {"patterns_present", "modes", "phases", "roles"}
    assert manifest.extensions == {
        "marimo_session": {
            "required": False,
            "config": {"live_execution": False},
        }
    }
    assert {node.kind for node in manifest.nodes} <= set(PRIMITIVE_NODE_KINDS)
    assert "invoke_marimo_pair" in node_map
    assert node_map["invoke_marimo_pair"].kind == "tool_use_step"
    assert node_map["invoke_marimo_pair"].tool_id == "marimo_pair_agent"
    assert node_map["invoke_marimo_pair"].raw["agent_as_tool"] == {
        "skill_id": "marimo-pair",
        "skill_path": "../power-marimo/skills/marimo-pair/SKILL.md",
        "task_boundary": "perform a bounded Marimo notebook operation",
    }
    assert node_map["invoke_marimo_pair"].agent_as_tool is not None
    assert node_map["invoke_marimo_pair"].agent_as_tool.skill_id == "marimo-pair"
    assert (
        node_map["invoke_marimo_pair"].agent_as_tool.task_boundary
        == "perform a bounded Marimo notebook operation"
    )
    assert tool_map["marimo_pair_agent"].source is not None
    assert tool_map["marimo_pair_agent"].source.kind is ToolSourceKind.MANIFEST
    assert tool_map["marimo_pair_agent"].approval_required == "true"
    assert workflow.agent_design is not None
    assert workflow.agent_design.references_runtime_manifest is True
    assert workflow.agent_design.references_mermaid_graph is True
    assert workflow.mermaid_graph is not None
    assert "invoke_marimo_pair" in workflow.mermaid_graph


def test_power_marimo_fake_tools_exercise_bounded_happy_path() -> None:
    workflow = load_agent_workflow(
        runtime_manifest=FIXTURE_ROOT / "agent-runtime.yaml",
        agent_design=FIXTURE_ROOT / "agent-design.md",
    )

    node_ids = [node.id for node in workflow.runtime_manifest.nodes]

    assert node_ids == [
        "analyze_experiment_request",
        "discover_placeholder_marimo_server",
        "invoke_marimo_pair",
        "inspect_notebook_state",
        "run_placeholder_power_analysis",
        "prepare_notebook_cell_plan",
        "summarize_power_experiment",
    ]

    result = execute_workflow(
        workflow,
        prompt="Compare a placeholder room power experiment in a Marimo notebook.",
        tool_registry=_power_marimo_registry(),
        model_adapter=_make_adapter(
            [
                {
                    "id": "analysis-response",
                    "output_text": (
                        '{"experiment_goal":"compare placeholder room power",'
                        '"route":"continue"}'
                    ),
                },
                {
                    "id": "cell-plan-response",
                    "output_text": (
                        '{"cell_plan":["inspect placeholder notebook",'
                        '"render placeholder power summary"]}'
                    ),
                },
                {
                    "id": "summary-response",
                    "output_text": (
                        '{"message":"Placeholder Power-Marimo workflow completed '
                        'without live Marimo or SLD access."}'
                    ),
                },
            ]
        ),
    )

    assert result.final_result == (
        '{"message":"Placeholder Power-Marimo workflow completed without live '
        'Marimo or SLD access."}'
    )
    assert [execution.node_id for execution in result.state.executions] == node_ids
    assert result.state.tool_results["invoke_marimo_pair"].success is True
    assert result.state.tool_results["run_placeholder_power_analysis"].success is True


class _FakeResponsesAPI:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class _FakeClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = _FakeResponsesAPI(responses)


def _make_adapter(responses: list[dict[str, Any]]) -> OpenAIClientAdapter:
    return OpenAIClientAdapter(_FakeClient(responses))


def _power_marimo_registry() -> InMemoryToolRegistry:
    return InMemoryToolRegistry(
        [
            _registered_tool(
                "discover_marimo_servers",
                {
                    "server_id": "placeholder-marimo-server",
                    "live_execution": False,
                },
            ),
            _registered_tool(
                "marimo_pair_agent",
                {
                    "skill_id": "marimo-pair",
                    "skill_path": "../power-marimo/skills/marimo-pair/SKILL.md",
                    "notebook_operation": "bounded placeholder notebook update",
                    "live_execution": False,
                },
            ),
            _registered_tool(
                "inspect_notebook_state",
                {
                    "notebook_state": "placeholder-clean",
                    "unsafe_live_access": False,
                },
            ),
            _registered_tool(
                "run_room_power_analysis",
                {
                    "analysis_id": "placeholder-room-power",
                    "data_source": "synthetic-placeholder",
                    "result": "bounded fake analysis complete",
                },
            ),
        ]
    )


def _registered_tool(tool_id: str, output: Mapping[str, Any]) -> RegisteredTool:
    return RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": tool_id,
                "description_for_llm": f"Placeholder {tool_id} tool.",
                "input_schema": {"type": "object", "properties": {}},
            }
        ),
        lambda _args: dict(output),
    )
