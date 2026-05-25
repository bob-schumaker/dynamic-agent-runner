"""Fixture coverage for all documented agent pattern runtime packages."""

from __future__ import annotations

from pathlib import Path

from dynamic_agent_runner import load_agent_workflow
from dynamic_agent_runner.models import SUPPORTED_AGENT_PATTERNS

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "agent-patterns"


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
