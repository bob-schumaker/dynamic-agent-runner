"""Offline contract tests for the operator-gated Fastmail support probe."""

from __future__ import annotations

import hashlib

import pytest

from dynamic_agent_runner.workflow_host.fastmail_live_probe import (
    FastmailLiveProbeError,
    FastmailLiveProbeRequest,
    run_fastmail_live_probe,
)
from dynamic_agent_runner.workflow_host.workflow_support_matrix import (
    MaterialIdentity,
    WorkflowSupportCandidate,
    WorkflowSupportProfile,
)


_MATERIAL = MaterialIdentity(
    package_id="fastmail-triage-qwen-v4",
    material_lock_digest="a" * 64,
    material_roles=("reviewed_search_email_surface", "weights"),
    artifact_digests={"reviewed_search_email_surface": "b" * 64},
)


def _profile() -> WorkflowSupportProfile:
    return WorkflowSupportProfile(
        profile_id="fastmail-triage-live-v1",
        workflow_family="fastmail-triage",
        required_adapter_capabilities=("search_email", "tool_use"),
        required_abi_capabilities=("llama-cpp-function-calling-v1",),
        required_provider_capabilities=("fastmail.search_email.read.v1",),
        required_host_capabilities=(),
        material_identity=_MATERIAL,
        execution_mode="live",
        authorization_required=True,
        implemented=True,
    )


def _candidate(*, authorization_granted: bool = True) -> WorkflowSupportCandidate:
    return WorkflowSupportCandidate(
        adapter_id="fastmail-triage-llama-cpp-adapter-v1",
        adapter_capabilities=frozenset({"search_email", "tool_use"}),
        available_abi_capabilities=frozenset({"llama-cpp-function-calling-v1"}),
        provider_capabilities=frozenset({"fastmail.search_email.read.v1"}),
        host_capabilities=frozenset(),
        material_identity=_MATERIAL,
        authorization_granted=authorization_granted,
    )


def _request(
    *, authorization_reference: str = "operator-20260913"
) -> FastmailLiveProbeRequest:
    return FastmailLiveProbeRequest(
        target="fastmail-primary",
        authorization_reference=authorization_reference,
        profile=_profile(),
        candidate=_candidate(),
    )


def test_fastmail_probe_rejects_missing_authorization_before_dispatch() -> None:
    calls: list[object] = []

    with pytest.raises(FastmailLiveProbeError, match="authorization"):
        run_fastmail_live_probe(
            _request(authorization_reference=""),
            dispatch=lambda: calls.append("must-not-run"),
        )

    assert calls == []


def test_fastmail_probe_rejects_non_supported_cell_before_dispatch() -> None:
    calls: list[object] = []
    request = FastmailLiveProbeRequest(
        target="fastmail-primary",
        authorization_reference="operator-20260913",
        profile=_profile(),
        candidate=_candidate(authorization_granted=False),
    )

    with pytest.raises(FastmailLiveProbeError, match="support cell"):
        run_fastmail_live_probe(request, dispatch=lambda: calls.append("must-not-run"))

    assert calls == []


def test_fastmail_probe_rejects_stale_material_before_dispatch() -> None:
    calls: list[object] = []
    stale_material = MaterialIdentity(
        package_id=_MATERIAL.package_id,
        material_lock_digest=_MATERIAL.material_lock_digest,
        material_roles=_MATERIAL.material_roles,
        artifact_digests={"reviewed_search_email_surface": "c" * 64},
    )
    request = FastmailLiveProbeRequest(
        target="fastmail-primary",
        authorization_reference="operator-20260913",
        profile=_profile(),
        candidate=WorkflowSupportCandidate(
            adapter_id="fastmail-triage-llama-cpp-adapter-v1",
            adapter_capabilities=frozenset({"search_email", "tool_use"}),
            available_abi_capabilities=frozenset({"llama-cpp-function-calling-v1"}),
            provider_capabilities=frozenset({"fastmail.search_email.read.v1"}),
            host_capabilities=frozenset(),
            material_identity=stale_material,
            authorization_granted=True,
        ),
    )

    with pytest.raises(FastmailLiveProbeError, match="support cell"):
        run_fastmail_live_probe(request, dispatch=lambda: calls.append("must-not-run"))

    assert calls == []


def test_fastmail_probe_dispatches_once_and_renders_only_redacted_receipt() -> None:
    calls: list[object] = []
    secret_reference = "operator-20260913"
    secret_target = "fastmail-primary"
    secret_result = {"subject": "confidential mailbox content"}

    receipt = run_fastmail_live_probe(
        _request(authorization_reference=secret_reference),
        dispatch=lambda: calls.append(secret_result),
    )

    assert calls == [secret_result]
    assert receipt == {
        "adapter_id": "fastmail-triage-llama-cpp-adapter-v1",
        "authorization_reference_digest": hashlib.sha256(
            secret_reference.encode("utf-8")
        ).hexdigest(),
        "dispatch_count": 1,
        "format_version": 1,
        "material_identity": _MATERIAL.to_mapping(),
        "profile_digest": _profile().digest,
        "profile_id": "fastmail-triage-live-v1",
        "reason_codes": [],
        "status": "supported",
        "target_digest": hashlib.sha256(secret_target.encode("utf-8")).hexdigest(),
        "test_mode": "live",
    }
    rendered = repr(receipt)
    assert secret_reference not in rendered
    assert secret_target not in rendered
    assert "confidential mailbox content" not in rendered
