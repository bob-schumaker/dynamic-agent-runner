"""Tests for the opt-in subagent tool pack."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.errors import ToolRegistryError
from dynamic_agent_runner.models import (
    ToolOriginKind,
    ToolSource,
    ToolSourceKind,
    ToolType,
)
from dynamic_agent_runner.subagents import (
    SubagentPreset,
    SubagentResult,
    SubagentToolPolicy,
    create_subagent_registry,
)


class FakeSubagentRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run_subagent(self, *, preset: SubagentPreset, prompt: str) -> SubagentResult:
        self.calls.append({"preset": preset.id, "prompt": prompt})
        return SubagentResult(
            child_id=f"{preset.id}-1",
            preset_id=preset.id,
            status="completed",
            summary=f"{preset.label}: {prompt}",
            elapsed_ms=12,
        )


def test_subagent_tool_pack_runs_one_child_through_injected_runner() -> None:
    runner = FakeSubagentRunner()
    registry = create_subagent_registry(
        runner=runner,
        presets={
            "reviewer": SubagentPreset(
                id="reviewer",
                label="Reviewer",
                tool_ids=("workspace_data_read",),
                max_iterations=1,
            )
        },
    )

    tool = registry.get_tool("run_subagent")
    result = registry.invoke_tool(
        "run_subagent",
        {"preset_id": "reviewer", "prompt": "Check the plan."},
    )

    assert tool.definition.tool_type is ToolType.AGENT_TOOL
    assert tool.definition.source == ToolSource(
        kind=ToolSourceKind.BUILT_IN,
        origin=ToolOriginKind.BUILT_IN,
        source_id="subagent",
        detail="run_subagent",
    )
    assert result.success is True
    assert result.output == {
        "status": "completed",
        "children": [
            {
                "child_id": "reviewer-1",
                "preset_id": "reviewer",
                "status": "completed",
                "summary": "Reviewer: Check the plan.",
                "elapsed_ms": 12,
            }
        ],
    }
    assert runner.calls == [{"preset": "reviewer", "prompt": "Check the plan."}]


def test_subagent_tool_pack_runs_bounded_batch_in_order() -> None:
    runner = FakeSubagentRunner()
    registry = create_subagent_registry(
        runner=runner,
        presets={"research": SubagentPreset(id="research", label="Research")},
        policy=SubagentToolPolicy(max_children=2),
    )

    result = registry.invoke_tool(
        "run_subagents",
        {
            "children": [
                {"preset_id": "research", "prompt": "A"},
                {"preset_id": "research", "prompt": "B"},
            ]
        },
    )

    assert result.success is True
    assert result.output["status"] == "completed"
    assert [child["summary"] for child in result.output["children"]] == [
        "Research: A",
        "Research: B",
    ]


def test_subagent_tool_pack_rejects_missing_runner_unknown_preset_and_over_limit() -> (
    None
):
    with pytest.raises(ToolRegistryError, match="requires runner"):
        create_subagent_registry(presets={})

    registry = create_subagent_registry(
        runner=FakeSubagentRunner(),
        presets={"research": SubagentPreset(id="research")},
        policy=SubagentToolPolicy(max_children=1),
    )

    missing = registry.invoke_tool(
        "run_subagent", {"preset_id": "missing", "prompt": "Nope"}
    )
    over_limit = registry.invoke_tool(
        "run_subagents",
        {
            "children": [
                {"preset_id": "research", "prompt": "A"},
                {"preset_id": "research", "prompt": "B"},
            ]
        },
    )

    assert missing.success is False
    assert "unknown subagent preset 'missing'" in str(missing.error)
    assert over_limit.success is False
    assert "at most 1 children" in str(over_limit.error)
