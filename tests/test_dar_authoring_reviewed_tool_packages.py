"""Tests for host-owned named reviewed tool-package resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (
    ReviewedToolPackageBinding,
    ReviewedToolPackageControlPlane,
    ReviewedToolPackageError,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


def _binding() -> ReviewedToolPackageBinding:
    return ReviewedToolPackageBinding(
        binding_id="reviewed-binding-1",
        binding_digest="a" * 64,
        allowed_tool_ids=("packet_summary", "packet_filter"),
        artifact_aware_tool_ids=("packet_summary",),
    )


def test_named_reviewed_package_captures_its_exact_binding_and_allowlists(
    tmp_path: Path,
) -> None:
    packages = ReviewedToolPackageControlPlane(
        store=PrivateStateStore(tmp_path / "state"),
        owner="local-user",
    )

    created = packages.create(package_name="network-tools", binding=_binding())
    resolved = packages.resolve(
        package_name="network-tools", current_binding=_binding()
    )

    assert created.package_name == "network-tools"
    assert resolved.binding_id == "reviewed-binding-1"
    assert resolved.allowed_tool_ids == ("packet_summary", "packet_filter")
    assert resolved.artifact_aware_tool_ids == ("packet_summary",)


def test_reviewed_package_rejects_unknown_or_stale_bindings(tmp_path: Path) -> None:
    packages = ReviewedToolPackageControlPlane(
        store=PrivateStateStore(tmp_path / "state"),
        owner="local-user",
    )
    packages.create(package_name="network-tools", binding=_binding())

    with pytest.raises(ReviewedToolPackageError, match="unavailable"):
        packages.resolve(package_name="missing-tools", current_binding=_binding())
    with pytest.raises(ReviewedToolPackageError, match="unavailable"):
        packages.resolve(
            package_name="network-tools",
            current_binding=ReviewedToolPackageBinding(
                binding_id="reviewed-binding-1",
                binding_digest="b" * 64,
                allowed_tool_ids=("packet_summary", "packet_filter"),
                artifact_aware_tool_ids=("packet_summary",),
            ),
        )


def test_reviewed_package_rejects_non_artifact_aware_tool_selection(
    tmp_path: Path,
) -> None:
    packages = ReviewedToolPackageControlPlane(
        store=PrivateStateStore(tmp_path / "state"),
        owner="local-user",
    )
    packages.create(package_name="network-tools", binding=_binding())

    with pytest.raises(ReviewedToolPackageError, match="not artifact-aware"):
        packages.require_artifact_tool(
            package_name="network-tools",
            tool_id="packet_filter",
            current_binding=_binding(),
        )
