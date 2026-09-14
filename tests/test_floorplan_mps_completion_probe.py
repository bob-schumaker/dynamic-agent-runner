"""Offline contract tests for the operator-gated floorplan MPS probe."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from dynamic_agent_runner.workflow_host.floorplan_mps_completion_probe import (
    FloorplanMpsCompletionEvidence,
    FloorplanMpsCompletionProbeError,
    FloorplanMpsCompletionProbeRequest,
    run_floorplan_mps_completion_probe,
)
from dynamic_agent_runner.workflow_host.workflow_support_matrix import (
    MaterialIdentity,
    WorkflowSupportCandidate,
    WorkflowSupportProfile,
)


_MATERIAL = MaterialIdentity(
    package_id="floorplan-from-image",
    material_lock_digest="a" * 64,
    material_roles=("adapter_weights", "base_config", "processor_config"),
    artifact_digests={
        "execution_descriptor": "b" * 64,
        "input_converter": "c" * 64,
        "json_admission_processor": "d" * 64,
        "json_to_svg_renderer": "e" * 64,
        "terminal_svg_validator": "f" * 64,
    },
)


def _profile() -> WorkflowSupportProfile:
    return WorkflowSupportProfile(
        profile_id="floorplan-svg-mps-completion-v1",
        workflow_family="floorplan-svg",
        required_adapter_capabilities=("structured_output",),
        required_abi_capabilities=("transformers-peft-generation-v1",),
        required_provider_capabilities=("transformers-generate-v1",),
        required_host_capabilities=("mps",),
        material_identity=_MATERIAL,
        execution_mode="live",
        authorization_required=True,
        implemented=True,
    )


def _candidate(*, authorization_granted: bool = True) -> WorkflowSupportCandidate:
    return WorkflowSupportCandidate(
        adapter_id="floorplan-fixture-runner",
        adapter_capabilities=frozenset({"structured_output"}),
        available_abi_capabilities=frozenset({"transformers-peft-generation-v1"}),
        provider_capabilities=frozenset({"transformers-generate-v1"}),
        host_capabilities=frozenset({"mps"}),
        material_identity=_MATERIAL,
        authorization_granted=authorization_granted,
    )


def _request(
    *, authorization_reference: str = "operator-20260913"
) -> FloorplanMpsCompletionProbeRequest:
    return FloorplanMpsCompletionProbeRequest(
        target="floorplan-mps",
        authorization_reference=authorization_reference,
        profile=_profile(),
        candidate=_candidate(),
    )


def _evidence() -> FloorplanMpsCompletionEvidence:
    return FloorplanMpsCompletionEvidence(
        execution_descriptor_digest="b" * 64,
        packed_context_tokens=128,
        aggregate_generated_tokens=64,
        aggregate_output_bytes=512,
        worker_reaped=True,
        model_json_admitted=True,
        terminal_svg_validated=True,
    )


def test_floorplan_probe_rejects_an_unauthorized_cell_before_dispatch() -> None:
    calls: list[object] = []
    request = FloorplanMpsCompletionProbeRequest(
        target="floorplan-mps",
        authorization_reference="operator-20260913",
        profile=_profile(),
        candidate=_candidate(authorization_granted=False),
    )

    with pytest.raises(FloorplanMpsCompletionProbeError, match="support cell"):
        run_floorplan_mps_completion_probe(
            request, dispatch=lambda: calls.append("must-not-run")
        )

    assert calls == []


def test_floorplan_probe_requires_a_complete_reaped_svg_result() -> None:
    calls: list[object] = []

    with pytest.raises(FloorplanMpsCompletionProbeError, match="completion"):
        run_floorplan_mps_completion_probe(
            _request(),
            dispatch=lambda: calls.append(replace(_evidence(), worker_reaped=False)),
        )

    assert len(calls) == 1


def test_floorplan_probe_renders_only_the_fixed_redacted_receipt() -> None:
    secret_reference = "operator-20260913"
    secret_target = "floorplan-mps"
    secret_result = {"model_json": "secret", "svg": "<svg>secret</svg>"}

    receipt = run_floorplan_mps_completion_probe(
        _request(authorization_reference=secret_reference),
        dispatch=lambda: (_evidence(), secret_result)[0],
    )

    assert receipt == {
        "adapter_id": "floorplan-fixture-runner",
        "aggregate_generated_tokens": 64,
        "aggregate_output_bytes": 512,
        "authorization_reference_digest": hashlib.sha256(
            secret_reference.encode("utf-8")
        ).hexdigest(),
        "dispatch_count": 1,
        "execution_descriptor_digest": "b" * 64,
        "format_version": 1,
        "material_identity": _MATERIAL.to_mapping(),
        "packed_context_tokens": 128,
        "profile_digest": _profile().digest,
        "profile_id": "floorplan-svg-mps-completion-v1",
        "reason_codes": [],
        "status": "supported",
        "target_digest": hashlib.sha256(secret_target.encode("utf-8")).hexdigest(),
        "test_mode": "live",
        "worker_reaped": True,
    }
    rendered = repr(receipt)
    assert "secret" not in rendered
    assert secret_reference not in rendered
    assert secret_target not in rendered
