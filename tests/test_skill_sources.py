"""Tests for opt-in package-local skill source resolution."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dynamic_agent_runner.artifacts import load_agent_package
from dynamic_agent_runner.errors import WorkflowValidationError
from dynamic_agent_runner.skill_sources import (
    SkillSourceResolutionPolicy,
    resolve_package_bundled_skill_source,
)
from dynamic_agent_runner.validation import validate_agent_workflow


def _write_skill_package(
    package_dir: Path,
    *,
    skill_entries: str,
    node_skill_refs: str = '["demo"]',
    max_skill_bytes: int = 65_536,
    max_node_skill_bytes: int = 262_144,
) -> None:
    package_dir.mkdir(exist_ok=True)
    (package_dir / "skill-bundle").mkdir(exist_ok=True)
    (package_dir / "agent-design.md").write_text(
        "Runtime manifest: `agent-runtime.yaml`\nMermaid graph: `agent-graph.mmd`\n",
        encoding="utf-8",
    )
    (package_dir / "agent-graph.mmd").write_text("flowchart TD\n", encoding="utf-8")
    (package_dir / "agent-runtime.yaml").write_text(
        f"""
format_version: 1
package_type: dynamic_agent_design
package_id: skill-source-package
entrypoint: analyze_request
packaging:
  mode: hybrid_bundle
  skill_bundle_dir: skill-bundle
runtime:
  execution_policy:
    model: gpt-test
    skill_source_resolution:
      enabled: true
      allowed_sources:
        - package_bundle
      max_skill_bytes: {max_skill_bytes}
      max_node_skill_bytes: {max_node_skill_bytes}
      load_support_files: false
      prompt_role: developer
skills:
{skill_entries}
nodes:
  - id: analyze_request
    kind: llm_step
    skill_refs: {node_skill_refs}
    prompt:
      user_template: Analyze {{prompt}}
edges: []
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_package_local_bundled_skill_source_passes_validation(tmp_path) -> None:
    """Enabled source resolution accepts package-local bundled SKILL.md bodies."""

    package_dir = tmp_path / "skill-source-ok"
    skill_path = package_dir / "skill-bundle" / "skills" / "demo" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("# Demo\nUse package-local instructions.\n", encoding="utf-8")
    _write_skill_package(
        package_dir,
        skill_entries="  - id: demo\n    bundled_path: skills/demo/SKILL.md",
    )

    workflow = load_agent_package(package_dir)

    validate_agent_workflow(workflow)
    skill = workflow.runtime_manifest.skills[0]
    resolved = resolve_package_bundled_skill_source(
        skill_id="demo",
        raw_skill=skill.raw,
        package_id=workflow.runtime_manifest.package_id,
        skill_bundle_root=workflow.skill_bundle_root or "",
        policy=SkillSourceResolutionPolicy.from_mapping(
            workflow.runtime_manifest.skill_source_resolution_policy.raw
        ),
    )
    assert resolved.body.startswith("# Demo")
    assert resolved.redacted_metadata()["content_hash"].startswith("sha256:")


def test_disabled_skill_source_policy_does_not_require_body(tmp_path) -> None:
    """Bundled-path metadata remains metadata-only when source loading is disabled."""

    package_dir = tmp_path / "skill-source-disabled"
    package_dir.mkdir()
    (package_dir / "skill-bundle").mkdir()
    (package_dir / "agent-design.md").write_text(
        "Runtime manifest: `agent-runtime.yaml`\nMermaid graph: `agent-graph.mmd`\n",
        encoding="utf-8",
    )
    (package_dir / "agent-graph.mmd").write_text("flowchart TD\n", encoding="utf-8")
    (package_dir / "agent-runtime.yaml").write_text(
        """
format_version: 1
package_type: dynamic_agent_design
package_id: skill-source-disabled
entrypoint: analyze_request
packaging:
  mode: hybrid_bundle
  skill_bundle_dir: skill-bundle
runtime:
  execution_policy:
    model: gpt-test
skills:
  - id: demo
    instructions: Inline instructions still work.
nodes:
  - id: analyze_request
    kind: llm_step
    skill_refs: ["demo"]
    prompt:
      user_template: Analyze {prompt}
edges: []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    validate_agent_workflow(load_agent_package(package_dir))


def test_enabled_skill_source_policy_never_reads_source_path(tmp_path) -> None:
    """V1 treats source_path as provenance only, not read authorization."""

    package_dir = tmp_path / "skill-source-source-path"
    _write_skill_package(
        package_dir,
        skill_entries="  - id: demo\n    source_path: /tmp/SKILL.md",
    )

    with pytest.raises(WorkflowValidationError, match="requires bundled_path"):
        validate_agent_workflow(load_agent_package(package_dir))


def test_enabled_skill_source_policy_rejects_symlink_escape(tmp_path) -> None:
    """Symlink escapes from skill-bundle fail closed."""

    package_dir = tmp_path / "skill-source-symlink"
    outside = tmp_path / "outside" / "SKILL.md"
    outside.parent.mkdir()
    outside.write_text("# Outside\n", encoding="utf-8")
    link = package_dir / "skill-bundle" / "skills" / "demo" / "SKILL.md"
    link.parent.mkdir(parents=True)
    try:
        os.symlink(outside, link)
    except OSError as exc:  # pragma: no cover - platform dependent
        pytest.skip(f"symlink unavailable: {exc}")
    _write_skill_package(
        package_dir,
        skill_entries="  - id: demo\n    bundled_path: skills/demo/SKILL.md",
    )

    with pytest.raises(WorkflowValidationError, match="escapes package skill-bundle"):
        validate_agent_workflow(load_agent_package(package_dir))


@pytest.mark.parametrize(
    ("body", "match"),
    [
        (b"too long", "exceeds max_skill_bytes"),
        (b"\x00binary", "appears to be binary"),
        (b"\xff\xfe", "must be UTF-8 text"),
    ],
)
def test_enabled_skill_source_policy_rejects_bad_bodies(
    tmp_path,
    body: bytes,
    match: str,
) -> None:
    """Unsafe or unsupported skill bodies fail before execution."""

    package_dir = tmp_path / f"skill-source-{match.split()[0]}"
    skill_path = package_dir / "skill-bundle" / "skills" / "demo" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_bytes(body)
    _write_skill_package(
        package_dir,
        skill_entries="  - id: demo\n    bundled_path: skills/demo/SKILL.md",
        max_skill_bytes=4 if match == "exceeds max_skill_bytes" else 65_536,
    )

    with pytest.raises(WorkflowValidationError, match=match):
        validate_agent_workflow(load_agent_package(package_dir))


def test_enabled_skill_source_policy_enforces_node_budget(tmp_path) -> None:
    """Resolved skill bodies must fit the combined per-node budget."""

    package_dir = tmp_path / "skill-source-node-budget"
    for name in ("one", "two"):
        skill_path = package_dir / "skill-bundle" / "skills" / name / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("123456\n", encoding="utf-8")
    _write_skill_package(
        package_dir,
        skill_entries=(
            "  - id: one\n"
            "    bundled_path: skills/one/SKILL.md\n"
            "  - id: two\n"
            "    bundled_path: skills/two/SKILL.md"
        ),
        node_skill_refs='["one", "two"]',
        max_skill_bytes=8,
        max_node_skill_bytes=10,
    )

    with pytest.raises(WorkflowValidationError, match="exceed max_node_skill_bytes"):
        validate_agent_workflow(load_agent_package(package_dir))
