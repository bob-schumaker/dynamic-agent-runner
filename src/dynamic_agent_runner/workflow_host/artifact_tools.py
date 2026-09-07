"""Host bindings for reviewed tools that inspect sealed opaque artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol

from dynamic_agent_runner import HostToolBinding

from dynamic_agent_runner.workflow_host.descriptor import DeclaredArtifactTool
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (
    ReviewedToolPackageBinding,
    ReviewedToolPackageControlPlane,
    ReviewedToolPackageError,
)
from dynamic_agent_runner.workflow_host.workspace_ingress import (
    OpaqueBinaryArtifactReference,
)


class ArtifactToolBindingError(ValueError):
    """Raised when a reviewed opaque-artifact binding is unsafe."""


class OpaqueArtifactReader(Protocol):
    """Read the one host-sealed artifact named by a verified reference."""

    def read(self, reference: OpaqueBinaryArtifactReference) -> bytes:
        """Return verified bytes only for the supplied sealed reference."""


class ReviewedArtifactToolExecutor(Protocol):
    """One host-configured implementation of an exact reviewed package binding."""

    @property
    def binding(self) -> ReviewedToolPackageBinding:
        """Return the exact binding that this executor implements."""

    def execute(
        self,
        *,
        tool_id: str,
        artifact: OpaqueBinaryArtifactReference,
        reader: OpaqueArtifactReader,
    ) -> object:
        """Return bounded evidence after inspecting the sealed artifact."""


def create_reviewed_artifact_tool_binding(
    *,
    declaration: DeclaredArtifactTool,
    artifact: OpaqueBinaryArtifactReference,
    packages: ReviewedToolPackageControlPlane,
    executor: ReviewedArtifactToolExecutor,
    reader: OpaqueArtifactReader,
) -> HostToolBinding:
    """Bind one reviewed tool to one sealed artifact without model-selected inputs."""

    _validate_inputs(declaration, artifact, packages, executor, reader)

    def handler(arguments: Mapping[str, object]) -> Mapping[str, object]:
        if arguments:
            raise ArtifactToolBindingError("artifact tool arguments are invalid")
        try:
            packages.require_artifact_tool(
                package_name=declaration.reviewed_package_name,
                tool_id=declaration.tool_id,
                current_binding=executor.binding,
            )
            evidence = executor.execute(
                tool_id=declaration.tool_id, artifact=artifact, reader=reader
            )
        except ReviewedToolPackageError as error:
            raise ArtifactToolBindingError(
                "reviewed artifact tool is unavailable"
            ) from error
        return _bounded_evidence(evidence, declaration.max_result_bytes)

    return HostToolBinding(
        canonical_id=(
            f"artifact:{declaration.reviewed_package_name}:{declaration.tool_id}"
        ),
        model_id=declaration.tool_id,
        handler=handler,
        label=declaration.tool_id,
        description="Inspect the workflow's sealed opaque binary artifact.",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        side_effect="read",
        approval_required="no",
    )


def _validate_inputs(
    declaration: DeclaredArtifactTool,
    artifact: OpaqueBinaryArtifactReference,
    packages: ReviewedToolPackageControlPlane,
    executor: ReviewedArtifactToolExecutor,
    reader: OpaqueArtifactReader,
) -> None:
    if (
        artifact.role != declaration.accepted_artifact_role
        or artifact.role != "opaque_binary_artifact"
        or not isinstance(packages, ReviewedToolPackageControlPlane)
        or not callable(getattr(reader, "read", None))
    ):
        raise ArtifactToolBindingError("opaque binary artifact is unavailable")
    try:
        packages.require_artifact_tool(
            package_name=declaration.reviewed_package_name,
            tool_id=declaration.tool_id,
            current_binding=executor.binding,
        )
    except (AttributeError, ReviewedToolPackageError) as error:
        raise ArtifactToolBindingError(
            "reviewed artifact tool is unavailable"
        ) from error


def _bounded_evidence(value: object, maximum_bytes: int) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ArtifactToolBindingError("artifact tool evidence is invalid")
    evidence = dict(value)
    try:
        encoded = json.dumps(
            evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ArtifactToolBindingError("artifact tool evidence is invalid") from error
    if len(encoded) > maximum_bytes:
        raise ArtifactToolBindingError("artifact tool evidence exceeds its limit")
    return evidence
