"""Operator-gated, redacted floorplan MPS completion-probe boundary."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass

from dynamic_agent_runner.workflow_host.workflow_support_matrix import (
    WorkflowSupportCandidate,
    WorkflowSupportProfile,
    WorkflowSupportReceipt,
    WorkflowSupportStatus,
    classify_workflow_support,
    validate_workflow_support_receipt,
)


class FloorplanMpsCompletionProbeError(ValueError):
    """Raised when an MPS completion probe cannot start or complete safely."""


_REFERENCE = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_SECRET_MARKERS = ("api_key", "authorization", "cookie", "password", "secret", "token")
_REQUIRED_ARTIFACTS = frozenset(
    {
        "execution_descriptor",
        "input_converter",
        "json_admission_processor",
        "json_to_svg_renderer",
        "terminal_svg_validator",
    }
)


@dataclass(frozen=True)
class FloorplanMpsCompletionEvidence:
    """Scalar completion facts that may cross the live-probe boundary."""

    execution_descriptor_digest: str
    packed_context_tokens: int
    aggregate_generated_tokens: int
    aggregate_output_bytes: int
    worker_reaped: bool
    model_json_admitted: bool
    terminal_svg_validated: bool

    def __post_init__(self) -> None:
        if (
            not _digest(self.execution_descriptor_digest)
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.packed_context_tokens,
                    self.aggregate_generated_tokens,
                    self.aggregate_output_bytes,
                )
            )
            or not all(
                isinstance(value, bool)
                for value in (
                    self.worker_reaped,
                    self.model_json_admitted,
                    self.terminal_svg_validated,
                )
            )
        ):
            raise FloorplanMpsCompletionProbeError(
                "floorplan probe evidence is invalid"
            )


@dataclass(frozen=True)
class FloorplanMpsCompletionProbeRequest:
    """One explicit authorization and exact support cell for the MPS probe."""

    target: str
    authorization_reference: str
    profile: WorkflowSupportProfile
    candidate: WorkflowSupportCandidate

    def __post_init__(self) -> None:
        for value in (self.target, self.authorization_reference):
            if (
                not isinstance(value, str)
                or not _REFERENCE.fullmatch(value)
                or any(marker in value.lower() for marker in _SECRET_MARKERS)
            ):
                raise FloorplanMpsCompletionProbeError(
                    "floorplan probe authorization is invalid"
                )
        if not isinstance(self.profile, WorkflowSupportProfile) or not isinstance(
            self.candidate, WorkflowSupportCandidate
        ):
            raise FloorplanMpsCompletionProbeError("floorplan probe request is invalid")


def run_floorplan_mps_completion_probe(
    request: FloorplanMpsCompletionProbeRequest,
    *,
    dispatch: Callable[[], FloorplanMpsCompletionEvidence],
) -> dict[str, object]:
    """Dispatch once after exact MPS admission and project only redacted facts."""

    if not isinstance(request, FloorplanMpsCompletionProbeRequest) or not callable(
        dispatch
    ):
        raise FloorplanMpsCompletionProbeError("floorplan probe request is invalid")
    _validate_profile(request.profile)
    cell = classify_workflow_support(request.profile, request.candidate)
    if cell.status is not WorkflowSupportStatus.SUPPORTED:
        raise FloorplanMpsCompletionProbeError(
            "floorplan probe support cell is unavailable"
        )
    receipt = WorkflowSupportReceipt(
        profile_digest=cell.profile_digest,
        adapter_id=cell.adapter_id,
        material_identity=cell.material_identity,
        test_mode="live",
        status=cell.status,
        reason_codes=cell.reason_codes,
        dispatch_count=1,
    )
    validate_workflow_support_receipt(request.profile, request.candidate, cell, receipt)
    evidence = dispatch()
    _validate_completion(evidence, receipt)
    return _render_receipt(request, receipt, evidence)


def _validate_profile(profile: WorkflowSupportProfile) -> None:
    material = profile.material_identity
    if (
        profile.profile_id != "floorplan-svg-mps-completion-v1"
        or profile.workflow_family != "floorplan-svg"
        or profile.execution_mode != "live"
        or profile.authorization_required is not True
        or material is None
        or not _REQUIRED_ARTIFACTS.issubset(material.artifact_digests)
    ):
        raise FloorplanMpsCompletionProbeError("floorplan probe profile is invalid")


def _validate_completion(evidence: object, receipt: WorkflowSupportReceipt) -> None:
    if not isinstance(evidence, FloorplanMpsCompletionEvidence):
        raise FloorplanMpsCompletionProbeError("floorplan probe completion is invalid")
    material = receipt.material_identity
    if (
        material is None
        or evidence.execution_descriptor_digest
        != material.artifact_digests["execution_descriptor"]
        or not evidence.worker_reaped
        or not evidence.model_json_admitted
        or not evidence.terminal_svg_validated
    ):
        raise FloorplanMpsCompletionProbeError("floorplan probe completion is invalid")


def _render_receipt(
    request: FloorplanMpsCompletionProbeRequest,
    receipt: WorkflowSupportReceipt,
    evidence: FloorplanMpsCompletionEvidence,
) -> dict[str, object]:
    return {
        "adapter_id": receipt.adapter_id,
        "aggregate_generated_tokens": evidence.aggregate_generated_tokens,
        "aggregate_output_bytes": evidence.aggregate_output_bytes,
        "authorization_reference_digest": _digest_value(
            request.authorization_reference
        ),
        "dispatch_count": receipt.dispatch_count,
        "execution_descriptor_digest": evidence.execution_descriptor_digest,
        "format_version": 1,
        "material_identity": receipt.material_identity.to_mapping(),
        "packed_context_tokens": evidence.packed_context_tokens,
        "profile_digest": receipt.profile_digest,
        "profile_id": request.profile.profile_id,
        "reason_codes": list(receipt.reason_codes),
        "status": receipt.status.value,
        "target_digest": _digest_value(request.target),
        "test_mode": receipt.test_mode,
        "worker_reaped": evidence.worker_reaped,
    }


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _digest_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
