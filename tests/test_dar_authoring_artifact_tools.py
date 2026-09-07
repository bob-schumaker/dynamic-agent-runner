"""Tests for reviewed tools that consume sealed opaque binary artifacts."""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from dynamic_agent_runner.workflow_host.artifact_tools import (
    ArtifactToolBindingError,
    OpaqueArtifactReader,
    create_reviewed_artifact_tool_binding,
)
from dynamic_agent_runner.workflow_host.descriptor import DeclaredArtifactTool
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (
    ReviewedToolPackageBinding,
    ReviewedToolPackageControlPlane,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore
from dynamic_agent_runner.workflow_host.workspace_ingress import (
    OpaqueBinaryArtifactReference,
)


def _binding() -> ReviewedToolPackageBinding:
    return ReviewedToolPackageBinding(
        binding_id="network-review-1",
        binding_digest="a" * 64,
        allowed_tool_ids=("packet_summary",),
        artifact_aware_tool_ids=("packet_summary",),
    )


@dataclass
class _Reader:
    payload: bytes
    calls: int = 0

    def read(self, reference: OpaqueBinaryArtifactReference) -> bytes:
        assert reference.artifact_id == "artifact-1"
        self.calls += 1
        return self.payload


@dataclass
class _Executor:
    binding: ReviewedToolPackageBinding
    observed_reference: OpaqueBinaryArtifactReference | None = None

    def execute(
        self,
        *,
        tool_id: str,
        artifact: OpaqueBinaryArtifactReference,
        reader: OpaqueArtifactReader,
    ) -> object:
        assert tool_id == "packet_summary"
        self.observed_reference = artifact
        return {"packet_count": len(reader.read(artifact))}


def _tool() -> DeclaredArtifactTool:
    return DeclaredArtifactTool(
        tool_id="packet_summary",
        reviewed_package_name="network-tools",
        accepted_artifact_role="opaque_binary_artifact",
        max_result_bytes=128,
    )


def _artifact() -> OpaqueBinaryArtifactReference:
    return OpaqueBinaryArtifactReference(
        artifact_id="artifact-1",
        content_hash="sha256:" + "b" * 64,
        byte_count=3,
        role="opaque_binary_artifact",
        media_type="application/octet-stream",
    )


def test_artifact_tool_receives_only_a_sealed_reference_and_returns_evidence(
    tmp_path,
) -> None:
    packages = ReviewedToolPackageControlPlane(
        store=PrivateStateStore(tmp_path / "state"), owner="local-user"
    )
    binding = _binding()
    packages.create(package_name="network-tools", binding=binding)
    executor = _Executor(binding)
    reader = _Reader(b"pcap")

    tool = create_reviewed_artifact_tool_binding(
        declaration=_tool(),
        artifact=_artifact(),
        packages=packages,
        executor=executor,
        reader=reader,
    )

    assert tool.handler({}) == {"packet_count": 4}
    assert executor.observed_reference == _artifact()
    assert reader.calls == 1


def test_artifact_tool_rejects_arguments_and_oversized_evidence(tmp_path) -> None:
    packages = ReviewedToolPackageControlPlane(
        store=PrivateStateStore(tmp_path / "state"), owner="local-user"
    )
    binding = _binding()
    packages.create(package_name="network-tools", binding=binding)
    tool = create_reviewed_artifact_tool_binding(
        declaration=_tool(),
        artifact=_artifact(),
        packages=packages,
        executor=_Executor(binding),
        reader=_Reader(b"pcap"),
    )

    with pytest.raises(ArtifactToolBindingError, match="arguments"):
        tool.handler({"artifact_id": "caller-controlled"})

    oversized = create_reviewed_artifact_tool_binding(
        declaration=replace(_tool(), max_result_bytes=1),
        artifact=_artifact(),
        packages=packages,
        executor=_Executor(binding),
        reader=_Reader(b"x" * 200),
    )
    with pytest.raises(ArtifactToolBindingError, match="evidence"):
        oversized.handler({})
