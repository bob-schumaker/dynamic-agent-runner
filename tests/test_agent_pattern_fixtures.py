"""Fixture coverage for all documented agent pattern runtime packages."""

from __future__ import annotations

from pathlib import Path

import yaml

from dynamic_agent_runner import load_agent_workflow
from dynamic_agent_runner.models import SUPPORTED_AGENT_PATTERNS

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "agent-patterns"
AGENT_DEVELOPMENT_SKILL_SOURCE = "corpus/capabilities/agent-development/SKILL.md"
VALID_EXIT_ON_EXHAUSTION = {
    "finalize_with_caveats",
    "escalate",
    "fail_closed",
    "return_partial",
}
VALID_AUTONOMY_LEVELS = {
    "assistive",
    "supervised_agent",
    "bounded_autonomous",
    "high_autonomy",
}
VALID_TOOL_TYPES = {
    "file_read",
    "file_write",
    "web_search",
    "web_fetch",
    "shell_command",
    "code_execution",
    "structured_data_query",
    "external_api",
    "agent_tool",
    "human_approval",
}


def test_all_supported_patterns_have_hello_world_runtime_packages() -> None:
    pattern_dirs = sorted(path.name for path in FIXTURE_ROOT.iterdir() if path.is_dir())

    assert pattern_dirs == sorted(SUPPORTED_AGENT_PATTERNS)


def test_hello_world_agent_pattern_packages_load_and_validate() -> None:
    for pattern_id in SUPPORTED_AGENT_PATTERNS:
        package_dir = FIXTURE_ROOT / pattern_id
        workflow = load_agent_workflow(
            runtime_manifest=package_dir / "agent-runtime.yaml",
            agent_design=package_dir / "agent-design.md",
        )

        assert workflow.runtime_manifest.patterns_present == (pattern_id,)
        assert workflow.runtime_manifest.package_id == f"hello-world-{pattern_id}"
        assert workflow.agent_design is not None
        assert workflow.agent_design.references_runtime_manifest is True
        assert workflow.agent_design.references_mermaid_graph is True
        assert workflow.mermaid_graph is not None
        assert "flowchart TD" in workflow.mermaid_graph


def test_hello_world_agent_pattern_packages_match_upstream_contract() -> None:
    for pattern_id in SUPPORTED_AGENT_PATTERNS:
        package_dir = FIXTURE_ROOT / pattern_id
        manifest = yaml.safe_load((package_dir / "agent-runtime.yaml").read_text())
        node_ids = {
            node["id"]
            for node in manifest["nodes"]
            if isinstance(node, dict) and node.get("id")
        }

        execution_policy = manifest.get("runtime", {}).get("execution_policy")
        assert isinstance(execution_policy, dict), pattern_id
        assert execution_policy.get("autonomy_level") in VALID_AUTONOMY_LEVELS
        exit_strategy = execution_policy.get("exit_strategy")
        assert isinstance(exit_strategy, dict), pattern_id
        assert exit_strategy.get("on_exhaustion") in VALID_EXIT_ON_EXHAUSTION
        terminal_conditions = exit_strategy.get("terminal_conditions")
        assert isinstance(terminal_conditions, list), pattern_id
        assert all(
            isinstance(condition, str) and condition.strip()
            for condition in terminal_conditions
        )
        assert isinstance(exit_strategy.get("ambiguous_completion"), str), pattern_id
        assert exit_strategy["ambiguous_completion"].strip(), pattern_id

        agent_development_skill = next(
            skill
            for skill in manifest.get("skills", [])
            if skill.get("id") == "agent-development"
        )
        assert (
            agent_development_skill.get("source_path") == AGENT_DEVELOPMENT_SKILL_SOURCE
        ), pattern_id

        for tool in manifest.get("tools", []):
            assert tool.get("tool_type") in VALID_TOOL_TYPES, (
                pattern_id,
                tool.get("id"),
            )

        for node in manifest["nodes"]:
            if node.get("decision_subtype") == "llm_route":
                assert isinstance(node.get("prompt"), dict), (pattern_id, node["id"])

        for edge in manifest["edges"]:
            assert "from" in edge, (pattern_id, edge)
            assert "to" in edge, (pattern_id, edge)
            assert edge["from"] in node_ids, (pattern_id, edge)
            assert edge["to"] in node_ids, (pattern_id, edge)
            assert "source" not in edge, (pattern_id, edge)
            assert "target" not in edge, (pattern_id, edge)

        if any(edge.get("edge_kind") == "loopback" for edge in manifest["edges"]):
            assert execution_policy.get("max_iterations") > 0, pattern_id
            assert execution_policy.get("max_steps") > 0, pattern_id
