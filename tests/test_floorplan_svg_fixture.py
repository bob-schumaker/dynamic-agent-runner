"""Regression coverage for the workflow-owned floorplan SVG fixture."""

from __future__ import annotations

import base64
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path

from dynamic_agent_runner.workflow_host.catalog import PackageCatalog
from dynamic_agent_runner.workflow_host.local_tools import (
    LocalToolDefinition,
    LocalToolSandbox,
    execute_macos_sandbox_exec,
)
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionPolicy,
)
from dynamic_agent_runner.workflow_host.policy import compile_workflow_policy
from dynamic_agent_runner.workflow_host.staging import PrivatePackageStager
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


NOW = datetime(2026, 9, 6, tzinfo=UTC)
FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "natural-language-workflow-authoring"
    / "floorplan-svg"
)


def test_floorplan_fixture_stages_a_workflow_owned_svg_validator(
    tmp_path: Path,
) -> None:
    source = tmp_path / "packages" / "floorplan-from-image"
    shutil.copytree(FIXTURE, source)
    store = PrivateStateStore(tmp_path / "state")
    handle = PackageSourceSelectionPolicy(
        allowed_root=source.parent, store=store
    ).select_directory(source, now=NOW)
    staged = PrivatePackageStager(store=store, private_root=tmp_path / "staging").stage(
        handle, now=NOW
    )
    revision = PackageCatalog(tmp_path / "catalog").import_staged(staged)

    policy = compile_workflow_policy(revision)

    assert policy.model_profile_requirement == "local-multimodal-model-v1"
    assert policy.workspace.accepted_input_types == ("image/jpeg", "image/png")
    assert policy.input_converter is not None
    assert policy.input_converter.converter_id == "qwen25-vl-3b-grpo-input-v1"
    assert (
        policy.input_converter.compatible_runner_contract_id
        == "transformers-generate-v1"
    )
    assert policy.terminal_output_validator is not None
    asset = revision.package_root / "tools" / "validate_svg"
    assert asset.stat().st_mode & stat.S_IXUSR

    sandbox = LocalToolSandbox(
        package_root=revision.package_root, execute=execute_macos_sandbox_exec
    )
    definition = LocalToolDefinition(
        tool_id="terminal-output-validator",
        asset_path=Path("tools/validate_svg"),
        accepted_artifact_role="terminal_output",
        max_input_bytes=32 * 1024,
        max_output_bytes=512,
        timeout_seconds=1,
    )
    assert sandbox.run(
        definition, artifact_role="terminal_output", artifact_bytes=b"<svg/>"
    ) == {"valid": True}
    assert sandbox.run(
        definition, artifact_role="terminal_output", artifact_bytes=b"not SVG"
    ) == {"valid": False}
    assert sandbox.run(
        definition, artifact_role="terminal_output", artifact_bytes=b"<svg>"
    ) == {"valid": False}

    renderer = LocalToolDefinition(
        tool_id="terminal-output-renderer",
        asset_path=Path("tools/render_floorplan_json"),
        accepted_artifact_role="terminal_output",
        max_input_bytes=32 * 1024,
        max_output_bytes=32 * 1024,
        timeout_seconds=1,
    )
    rendered = sandbox.run(
        renderer,
        artifact_role="terminal_output",
        artifact_bytes=(
            b'{"walls":[{"id":"wall_1","start":[10,20],"end":[90,20],'
            b'"thickness":4,"curvature":0,"openings":[{"type":"window",'
            b'"center":50,"width":20}]}],"rooms":[{"label":"outdoor",'
            b'"walls":["wall_1"]}]}'
        ),
    )
    assert rendered["status"] == "accepted"
    assert b"<svg " in base64.b64decode(rendered["output_base64"])
    assert sandbox.run(
        renderer,
        artifact_role="terminal_output",
        artifact_bytes=b'{"walls":[],"rooms":[],"extra":true}',
    ) == {"status": "rejected"}
    assert sandbox.run(
        renderer,
        artifact_role="terminal_output",
        artifact_bytes=(
            b'{"walls":[{"id":"wall_1","start":[10,20],"end":[90,20],'
            b'"thickness":4,"curvature":0,"openings":[{"type":"arch",'
            b'"center":50,"width":20}]}],"rooms":[]}'
        ),
    ) == {"status": "rejected"}
