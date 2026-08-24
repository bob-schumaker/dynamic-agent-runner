"""Static contract tests for DAR authoring target-invocation fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from dynamic_agent_runner import load_agent_package_workflow

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "dar-authoring" / "invocations"
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"
PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.descriptor import WorkflowDescriptor  # noqa: E402

EXPECTED_SKILLS = {
    "agent-development",
    "agent-tool-contract-design",
    "agent-evaluation",
}


def test_target_invocation_fixtures_have_complete_deidentified_contracts() -> None:
    fixtures = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FIXTURE_ROOT.glob("*.json"))
    ]

    assert {fixture["skill"] for fixture in fixtures} == EXPECTED_SKILLS
    for fixture in fixtures:
        assert fixture["schema_version"] == 1
        assert fixture["request"].strip()
        assert fixture["selected_materials"]
        assert fixture["expected_artifacts"]
        assert fixture["expected_capability_or_refusal"]
        assert fixture["private_material_exclusions"]
        for material in fixture["selected_materials"]:
            assert set(material) == {"artifact_id", "digest", "disposition", "role"}
            assert material["disposition"] in {"reference_only", "distributable"}
            assert material["artifact_id"].startswith("authoring-material-")
            assert len(material["digest"]) == 64


def test_no_tool_template_is_a_valid_dar_package() -> None:
    workflow = load_agent_package_workflow(str(TEMPLATE_ROOT))
    descriptor = WorkflowDescriptor.from_mapping(
        yaml.safe_load(
            (TEMPLATE_ROOT / "workflow-descriptor.yaml").read_text(encoding="utf-8")
        )
    )

    assert workflow.runtime_manifest.package_id == "dar-authoring-no-tool-template"
    assert workflow.runtime_manifest.tools == ()
    assert descriptor.package_id == workflow.runtime_manifest.package_id
    assert descriptor.task_invocation.max_total_tool_calls == 0


def test_agent_development_fixture_declares_template_artifacts() -> None:
    fixture = json.loads(
        (FIXTURE_ROOT / "agent-development.json").read_text(encoding="utf-8")
    )

    assert all(
        (TEMPLATE_ROOT / artifact).is_file()
        for artifact in fixture["expected_artifacts"]
    )
