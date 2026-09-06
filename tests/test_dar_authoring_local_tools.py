"""Tests for declared deterministic workflow-local tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.local_tools import (
    LocalToolDefinition,
    LocalToolSandbox,
    LocalToolSandboxError,
)


def test_local_tool_sandbox_runs_only_a_declared_asset_with_bounded_io(
    tmp_path: Path,
) -> None:
    asset = tmp_path / "tools" / "summarize.sh"
    asset.parent.mkdir()
    asset.write_text("placeholder", encoding="utf-8")
    definition = LocalToolDefinition(
        tool_id="summarize",
        asset_path=asset,
        accepted_artifact_role="source_image",
        max_input_bytes=1024,
        max_output_bytes=512,
        timeout_seconds=1,
    )
    sandbox = LocalToolSandbox(
        package_root=tmp_path,
        execute=lambda command, input_bytes, timeout_seconds: b"bounded result",
    )

    result = sandbox.run(
        definition,
        artifact_role="source_image",
        artifact_bytes=b"sealed input",
    )

    assert result == b"bounded result"


@pytest.mark.parametrize(
    ("asset_path", "role", "body"),
    [
        (Path("/bin/sh"), "source_image", b"sealed input"),
        (Path("tools/summarize.sh"), "other", b"sealed input"),
        (Path("tools/summarize.sh"), "source_image", b"x" * 1025),
    ],
)
def test_local_tool_sandbox_rejects_undeclared_access_and_oversized_input(
    tmp_path: Path, asset_path: Path, role: str, body: bytes
) -> None:
    package_root = tmp_path / "package"
    (package_root / "tools").mkdir(parents=True)
    (package_root / "tools" / "summarize.sh").write_text("placeholder")
    definition = LocalToolDefinition(
        tool_id="summarize",
        asset_path=asset_path,
        accepted_artifact_role="source_image",
        max_input_bytes=1024,
        max_output_bytes=512,
        timeout_seconds=1,
    )
    sandbox = LocalToolSandbox(
        package_root=package_root,
        execute=lambda command, input_bytes, timeout_seconds: b"bounded result",
    )

    with pytest.raises(LocalToolSandboxError):
        sandbox.run(definition, artifact_role=role, artifact_bytes=body)
