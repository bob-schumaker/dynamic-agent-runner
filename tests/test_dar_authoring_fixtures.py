"""Static contract tests for DAR authoring target-invocation fixtures."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import yaml
from dynamic_agent_runner import load_agent_package_workflow

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "dar-authoring" / "invocations"
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"
TOOL_TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1] / "dar-authoring" / "tool-templates"
)
EVALUATION_TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1] / "dar-authoring" / "evaluation-templates"
)
READ_ONLY_MCP_TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1] / "dar-authoring" / "read-only-mcp-template"
)
SKILL_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "skills"
PROVENANCE_PATH = SKILL_ROOT / "adapted-skill-provenance.yaml"

from dynamic_agent_runner.workflow_host.descriptor import WorkflowDescriptor  # noqa: E402
from dynamic_agent_runner.workflow_host.authoring_output import (  # noqa: E402
    write_authored_package_manifest,
)

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
        assert fixture["artifact_contracts"]
        assert fixture["expected_capability_or_refusal"]
        assert fixture["private_material_exclusions"]
        for material in fixture["selected_materials"]:
            assert set(material) == {"artifact_id", "digest", "disposition", "role"}
            assert material["disposition"] in {"reference_only", "distributable"}
            assert material["artifact_id"].startswith("authoring-material-")
            assert len(material["digest"]) == 64

    development = next(
        fixture for fixture in fixtures if fixture["skill"] == "agent-development"
    )
    descriptor_contract = next(
        contract
        for contract in development["artifact_contracts"]
        if contract["artifact"] == "workflow-descriptor.yaml"
    )
    assert descriptor_contract["required"]["purpose"] == (
        "Answer one bounded question using only supplied text with a local model and no tools."
    )


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


def test_read_only_mcp_template_is_a_bounded_dar_package() -> None:
    workflow = load_agent_package_workflow(str(READ_ONLY_MCP_TEMPLATE_ROOT))
    descriptor = WorkflowDescriptor.from_mapping(
        yaml.safe_load(
            (READ_ONLY_MCP_TEMPLATE_ROOT / "workflow-descriptor.yaml").read_text(
                encoding="utf-8"
            )
        )
    )

    assert (
        workflow.runtime_manifest.package_id == "dar-authoring-read-only-mcp-template"
    )
    assert workflow.runtime_manifest.tools[0].id == "lookup_records"
    assert workflow.runtime_manifest.execution_policy["max_steps"] == 3
    assert descriptor.task_invocation.allowed_tool_ids == ("lookup_records",)
    assert descriptor.task_invocation.max_total_tool_calls == 3
    assert descriptor.declared_tools[0].side_effect == "read"


def test_plugin_ships_tool_and_evaluation_starter_artifacts() -> None:
    tool_index = yaml.safe_load(
        (TOOL_TEMPLATE_ROOT / "tool-index.yaml").read_text(encoding="utf-8")
    )
    evaluation_fixtures = json.loads(
        (EVALUATION_TEMPLATE_ROOT / "evaluation-fixtures.json").read_text(
            encoding="utf-8"
        )
    )
    regression_gate = yaml.safe_load(
        (EVALUATION_TEMPLATE_ROOT / "regression-gate.yaml").read_text(encoding="utf-8")
    )

    assert tool_index == {"format_version": 1, "tools": []}
    assert "## Scope" in (EVALUATION_TEMPLATE_ROOT / "eval-plan.md").read_text(
        encoding="utf-8"
    )
    assert evaluation_fixtures == {"format_version": 1, "cases": []}
    assert regression_gate == {
        "format_version": 1,
        "decision_owner": "human_reviewer",
        "pass_criteria": [],
    }


def test_agent_development_fixture_declares_finalized_package_artifacts(
    tmp_path: Path,
) -> None:
    fixture = json.loads(
        (FIXTURE_ROOT / "agent-development.json").read_text(encoding="utf-8")
    )
    package = tmp_path / "generated-package"
    shutil.copytree(TEMPLATE_ROOT, package)
    write_authored_package_manifest(package)

    assert all(
        (package / artifact).is_file() for artifact in fixture["expected_artifacts"]
    )


def test_adapted_skills_have_complete_immutable_provenance() -> None:
    provenance = yaml.safe_load(PROVENANCE_PATH.read_text(encoding="utf-8"))

    assert provenance["format_version"] == 1
    assert provenance["source_locator"] == "../ai-environment-roschuma"
    assert len(provenance["source_revision"]) == 40
    assert set(provenance["skills"]) == EXPECTED_SKILLS
    for skill_name, record in provenance["skills"].items():
        skill_path = SKILL_ROOT / skill_name / "SKILL.md"

        assert skill_path.is_file()
        assert record["upstream_path"] == (f"corpus/capabilities/{skill_name}/SKILL.md")
        assert record["copied_path"] == f"skills/{skill_name}/SKILL.md"
        assert record["license_or_notice"]
        assert record["redistribution_review"]
        assert record["dar_modification_summary"]


def test_adapted_skills_are_portable_and_cover_fixture_contracts() -> None:
    expected_artifacts_by_skill = {
        fixture["skill"]: set(fixture["expected_artifacts"])
        for fixture in (
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(FIXTURE_ROOT.glob("*.json"))
        )
    }

    for skill_name, expected_artifacts in expected_artifacts_by_skill.items():
        text = (SKILL_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")

        assert "AuthoringMaterialSet" in text
        assert "corpus/" not in text
        assert "../ai-environment-roschuma" not in text
        assert all(artifact in text for artifact in expected_artifacts)
        assert "unselected" in text
        assert "credential" in text

    tool_contract = (SKILL_ROOT / "agent-tool-contract-design" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "host-owned" in tool_contract
    assert "endpoint URL" not in tool_contract
    assert "credential" in tool_contract
    assert "authoring_runtime_unavailable" in (
        SKILL_ROOT / "agent-development" / "SKILL.md"
    ).read_text(encoding="utf-8")


def test_agent_development_skill_calls_the_host_authoring_control_plane() -> None:
    text = (SKILL_ROOT / "agent-development" / "SKILL.md").read_text(encoding="utf-8")

    commands = (
        "issue-authoring-materials",
        "project-authoring-materials",
        "create-authored-package",
        "write-authored-package-file",
        "finalize-authored-package",
    )
    positions = [text.index(command) for command in commands]

    assert positions == sorted(positions)
    assert "Do not stop after a partial output" in text
    assert "skill-bundle/skills/<id>/SKILL.md" in text
    assert "read-only-mcp-template" in text
    assert "entry skill retains ownership of agent-runtime.yaml" in text


def test_companion_skills_use_the_entry_skill_output_handle() -> None:
    for skill_name in ("agent-tool-contract-design", "agent-evaluation"):
        text = (SKILL_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")

        assert "material_set_id" in text
        assert "authoring_output_id" in text
        assert "../../scripts/dar-workflow" in text
        assert "write-authored-package-file" in text
        assert "physical package path" in text
        assert "do not finalize" in " ".join(text.lower().split())
