"""Operator-gated, redacted live Fastmail support-probe boundary."""

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


class FastmailLiveProbeError(ValueError):
    """Raised when an operator-gated Fastmail probe cannot start safely."""


_REFERENCE = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_SECRET_MARKERS = ("api_key", "authorization", "cookie", "password", "secret", "token")


@dataclass(frozen=True)
class FastmailLiveProbeRequest:
    """One explicit target, authorization, and exact support cell request."""

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
                raise FastmailLiveProbeError("Fastmail probe authorization is invalid")
        if not isinstance(self.profile, WorkflowSupportProfile) or not isinstance(
            self.candidate, WorkflowSupportCandidate
        ):
            raise FastmailLiveProbeError("Fastmail probe request is invalid")


def run_fastmail_live_probe(
    request: FastmailLiveProbeRequest, *, dispatch: Callable[[], object]
) -> dict[str, object]:
    """Dispatch once only after exact live support and authorization admission."""

    if not isinstance(request, FastmailLiveProbeRequest) or not callable(dispatch):
        raise FastmailLiveProbeError("Fastmail probe request is invalid")
    if (
        request.profile.profile_id != "fastmail-triage-live-v1"
        or request.profile.workflow_family != "fastmail-triage"
        or request.profile.execution_mode != "live"
        or request.profile.authorization_required is not True
    ):
        raise FastmailLiveProbeError("Fastmail probe profile is invalid")
    cell = classify_workflow_support(request.profile, request.candidate)
    if cell.status is not WorkflowSupportStatus.SUPPORTED:
        raise FastmailLiveProbeError("Fastmail probe support cell is unavailable")
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
    dispatch()
    return _render_receipt(request, receipt)


def _render_receipt(
    request: FastmailLiveProbeRequest, receipt: WorkflowSupportReceipt
) -> dict[str, object]:
    """Render only fixed, non-content facts for one completed probe."""

    return {
        "adapter_id": receipt.adapter_id,
        "authorization_reference_digest": _digest(request.authorization_reference),
        "dispatch_count": receipt.dispatch_count,
        "format_version": 1,
        "material_identity": (
            receipt.material_identity.to_mapping()
            if receipt.material_identity is not None
            else None
        ),
        "profile_digest": receipt.profile_digest,
        "profile_id": request.profile.profile_id,
        "reason_codes": list(receipt.reason_codes),
        "status": receipt.status.value,
        "target_digest": _digest(request.target),
        "test_mode": receipt.test_mode,
    }


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
