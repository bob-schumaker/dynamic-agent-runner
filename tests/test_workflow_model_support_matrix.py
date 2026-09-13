"""RED tests for the pure workflow support classifier."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, replace
from pathlib import Path

from dynamic_agent_runner.workflow_host.workflow_support_matrix import (
    MaterialIdentity,
    WorkflowSupportCandidate,
    WorkflowSupportProfile,
    WorkflowSupportReceipt,
    WorkflowSupportStatus,
    classify_workflow_support,
    validate_workflow_support_receipt,
)
from pytest import raises


_FASTMAIL_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "workflow-model-support-matrix"
    / "fastmail-triage-synthetic-v1.json"
)


def _material_identity(*, package_id: str = "embedding-package") -> MaterialIdentity:
    return MaterialIdentity(
        package_id=package_id,
        material_lock_digest="a" * 64,
        material_roles=("tokenizer", "weights"),
        artifact_digests={
            "execution_descriptor": "b" * 64,
            "tokenizer": "c" * 64,
        },
    )


def _profile(*, implemented: bool = True) -> WorkflowSupportProfile:
    return WorkflowSupportProfile(
        profile_id="embedding-index-sealed-v1",
        workflow_family="embedding-index",
        required_adapter_capabilities=("embeddings",),
        required_abi_capabilities=("bert-encoder-mlx-v3",),
        required_provider_capabilities=("embedding.execute.v1",),
        required_host_capabilities=("darwin-arm64",),
        material_identity=_material_identity(),
        execution_mode="synthetic",
        authorization_required=False,
        implemented=implemented,
    )


def _candidate(
    *,
    adapter_capabilities: frozenset[str] = frozenset({"embeddings"}),
    available_abi_capabilities: frozenset[str] = frozenset({"bert-encoder-mlx-v3"}),
    provider_capabilities: frozenset[str] = frozenset({"embedding.execute.v1"}),
    host_capabilities: frozenset[str] = frozenset({"darwin-arm64"}),
    material_identity: MaterialIdentity | None = None,
) -> WorkflowSupportCandidate:
    return WorkflowSupportCandidate(
        adapter_id="mlx-local-embedding",
        adapter_capabilities=adapter_capabilities,
        available_abi_capabilities=available_abi_capabilities,
        provider_capabilities=provider_capabilities,
        host_capabilities=host_capabilities,
        material_identity=material_identity or _material_identity(),
        authorization_granted=False,
    )


def _fastmail_fixture() -> dict[str, object]:
    return json.loads(_FASTMAIL_FIXTURE_PATH.read_text(encoding="utf-8"))


def _fastmail_material_identity(fixture: dict[str, object]) -> MaterialIdentity:
    material = fixture["material"]
    assert isinstance(material, dict)
    artifact_digests = material["artifact_digests"]
    assert isinstance(artifact_digests, dict)
    material_roles = material["material_roles"]
    assert isinstance(material_roles, list)
    lock_bytes = json.dumps(
        {
            "package_id": fixture["package_id"],
            "package_digest": fixture["package_digest"],
            "artifact_digests": artifact_digests,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return MaterialIdentity(
        package_id=str(fixture["package_id"]),
        material_lock_digest=hashlib.sha256(lock_bytes).hexdigest(),
        material_roles=tuple(str(role) for role in material_roles),
        artifact_digests={
            str(name): str(digest) for name, digest in artifact_digests.items()
        },
    )


def _fastmail_profile(fixture: dict[str, object]) -> WorkflowSupportProfile:
    return WorkflowSupportProfile(
        profile_id="fastmail-triage-synthetic-v1",
        workflow_family="fastmail-triage",
        required_adapter_capabilities=("search_email", "tool_use"),
        required_abi_capabilities=("llama-cpp-function-calling-v1",),
        required_provider_capabilities=("fastmail.search_email.read.v1",),
        required_host_capabilities=(),
        material_identity=_fastmail_material_identity(fixture),
        execution_mode="synthetic",
        authorization_required=False,
        implemented=True,
    )


def _fastmail_candidate(
    *,
    adapter_capabilities: frozenset[str] = frozenset({"search_email", "tool_use"}),
    material_identity: MaterialIdentity | None = None,
) -> WorkflowSupportCandidate:
    return WorkflowSupportCandidate(
        adapter_id="llama-cpp-fastmail-fixture",
        adapter_capabilities=adapter_capabilities,
        available_abi_capabilities=frozenset({"llama-cpp-function-calling-v1"}),
        provider_capabilities=frozenset({"fastmail.search_email.read.v1"}),
        host_capabilities=frozenset(),
        material_identity=material_identity,
        authorization_granted=False,
    )


def test_profile_digest_is_canonical_across_unicode_and_mapping_order() -> None:
    profile = replace(_profile(), workflow_family="caf\u00e9-embedding")
    reordered = WorkflowSupportProfile(
        profile_id="embedding-index-sealed-v1",
        workflow_family="cafe\u0301-embedding",
        required_adapter_capabilities=("embeddings",),
        required_abi_capabilities=("bert-encoder-mlx-v3",),
        required_provider_capabilities=("embedding.execute.v1",),
        required_host_capabilities=("darwin-arm64",),
        material_identity=MaterialIdentity(
            package_id="embedding-package",
            material_lock_digest="a" * 64,
            material_roles=("tokenizer", "weights"),
            artifact_digests={
                "tokenizer": "c" * 64,
                "execution_descriptor": "b" * 64,
            },
        ),
        execution_mode="synthetic",
        authorization_required=False,
        implemented=True,
    )

    assert profile.digest == reordered.digest


def test_missing_adapter_capability_is_not_applicable_before_other_facts() -> None:
    cell = classify_workflow_support(
        _profile(),
        _candidate(
            adapter_capabilities=frozenset(),
            host_capabilities=frozenset(),
        ),
    )

    assert cell.status is WorkflowSupportStatus.NOT_APPLICABLE
    assert cell.reason_codes == ("adapter_capability_missing",)


def test_unimplemented_profile_is_deferred_before_adapter_admission() -> None:
    cell = classify_workflow_support(
        _profile(implemented=False), _candidate(adapter_capabilities=frozenset())
    )

    assert cell.status is WorkflowSupportStatus.DEFERRED
    assert cell.reason_codes == ("profile_unimplemented",)


def test_blocked_reasons_are_complete_and_lexically_ordered() -> None:
    cell = classify_workflow_support(
        _profile(),
        _candidate(
            host_capabilities=frozenset(),
            provider_capabilities=frozenset(),
            material_identity=_material_identity(package_id="other-package"),
        ),
    )

    assert cell.status is WorkflowSupportStatus.BLOCKED
    assert cell.reason_codes == (
        "material_identity_mismatch",
        "required_host_capability_missing",
        "required_provider_unavailable",
    )


def test_missing_required_abi_is_blocked_before_provider_execution() -> None:
    cell = classify_workflow_support(
        _profile(), _candidate(available_abi_capabilities=frozenset())
    )

    assert cell.status is WorkflowSupportStatus.BLOCKED
    assert cell.reason_codes == ("required_abi_unavailable",)


def test_missing_material_and_authorization_are_blocked_in_reason_order() -> None:
    profile = replace(_profile(), authorization_required=True)
    candidate = WorkflowSupportCandidate(
        adapter_id="mlx-local-embedding",
        adapter_capabilities=frozenset({"embeddings"}),
        available_abi_capabilities=frozenset({"bert-encoder-mlx-v3"}),
        provider_capabilities=frozenset({"embedding.execute.v1"}),
        host_capabilities=frozenset({"darwin-arm64"}),
        material_identity=None,
        authorization_granted=False,
    )

    cell = classify_workflow_support(profile, candidate)

    assert cell.status is WorkflowSupportStatus.BLOCKED
    assert cell.reason_codes == (
        "authorization_missing",
        "required_material_missing",
    )


def test_matching_immutable_facts_are_supported_without_reasons() -> None:
    profile = _profile()

    cell = classify_workflow_support(profile, _candidate())

    assert cell.profile_digest == profile.digest
    assert cell.adapter_id == "mlx-local-embedding"
    assert cell.status is WorkflowSupportStatus.SUPPORTED
    assert cell.reason_codes == ()


def test_receipt_is_accepted_only_for_its_exact_evaluated_cell() -> None:
    profile = _profile()
    candidate = _candidate()
    cell = classify_workflow_support(profile, candidate)
    receipt = WorkflowSupportReceipt(
        profile_digest=cell.profile_digest,
        adapter_id=cell.adapter_id,
        material_identity=_material_identity(),
        test_mode="synthetic",
        status=cell.status,
        reason_codes=cell.reason_codes,
        dispatch_count=1,
    )

    validate_workflow_support_receipt(profile, candidate, cell, receipt)


def test_receipt_cannot_transfer_to_a_different_profile_adapter_or_material() -> None:
    profile = _profile()
    candidate = _candidate()
    cell = classify_workflow_support(profile, candidate)
    receipt = WorkflowSupportReceipt(
        profile_digest=cell.profile_digest,
        adapter_id=cell.adapter_id,
        material_identity=_material_identity(),
        test_mode="synthetic",
        status=cell.status,
        reason_codes=cell.reason_codes,
        dispatch_count=1,
    )

    for changed_receipt in (
        replace(receipt, profile_digest="d" * 64),
        replace(receipt, adapter_id="other-adapter"),
        replace(receipt, test_mode="live"),
        replace(
            receipt,
            status=WorkflowSupportStatus.BLOCKED,
            reason_codes=("required_provider_unavailable",),
            dispatch_count=0,
        ),
        replace(
            receipt,
            material_identity=_material_identity(package_id="other-package"),
        ),
    ):
        with raises(ValueError, match="receipt does not match support cell"):
            validate_workflow_support_receipt(profile, candidate, cell, changed_receipt)


def test_receipt_binds_dispatch_count_without_runtime_payloads() -> None:
    profile = _profile()
    candidate = _candidate()
    cell = classify_workflow_support(profile, candidate)
    receipt = WorkflowSupportReceipt(
        profile_digest=cell.profile_digest,
        adapter_id=cell.adapter_id,
        material_identity=_material_identity(),
        test_mode="synthetic",
        status=cell.status,
        reason_codes=cell.reason_codes,
        dispatch_count=1,
    )

    assert receipt.dispatch_count == 1
    assert {field.name for field in fields(receipt)} == {
        "profile_digest",
        "adapter_id",
        "material_identity",
        "test_mode",
        "status",
        "reason_codes",
        "dispatch_count",
    }

    for dispatch_count in (-1, True):
        with raises(ValueError, match="dispatch_count is invalid"):
            replace(receipt, dispatch_count=dispatch_count)

    with raises(ValueError, match="dispatch_count is invalid"):
        replace(
            receipt,
            status=WorkflowSupportStatus.BLOCKED,
            reason_codes=("required_provider_unavailable",),
            dispatch_count=1,
        )


def test_fastmail_synthetic_profile_requires_fixture_bound_tool_material() -> None:
    fixture = _fastmail_fixture()
    profile = _fastmail_profile(fixture)
    matching_material = _fastmail_material_identity(fixture)

    missing_tool_cell = classify_workflow_support(
        profile,
        _fastmail_candidate(
            adapter_capabilities=frozenset({"tool_use"}),
            material_identity=matching_material,
        ),
    )
    assert missing_tool_cell.status is WorkflowSupportStatus.NOT_APPLICABLE
    assert missing_tool_cell.reason_codes == ("adapter_capability_missing",)

    stale_artifacts = dict(matching_material.artifact_digests)
    stale_artifacts["reviewed_search_email_surface"] = "f" * 64
    stale_material = MaterialIdentity(
        package_id=matching_material.package_id,
        material_lock_digest=matching_material.material_lock_digest,
        material_roles=matching_material.material_roles,
        artifact_digests=stale_artifacts,
    )
    stale_cell = classify_workflow_support(
        profile, _fastmail_candidate(material_identity=stale_material)
    )
    assert stale_cell.status is WorkflowSupportStatus.BLOCKED
    assert stale_cell.reason_codes == ("material_identity_mismatch",)

    for cell in (missing_tool_cell, stale_cell):
        receipt = WorkflowSupportReceipt(
            profile_digest=cell.profile_digest,
            adapter_id=cell.adapter_id,
            material_identity=cell.material_identity,
            test_mode="synthetic",
            status=cell.status,
            reason_codes=cell.reason_codes,
            dispatch_count=0,
        )
        validate_workflow_support_receipt(
            profile,
            _fastmail_candidate(
                adapter_capabilities=(
                    frozenset({"tool_use"})
                    if cell is missing_tool_cell
                    else frozenset({"search_email", "tool_use"})
                ),
                material_identity=cell.material_identity,
            ),
            cell,
            receipt,
        )

    assert fixture["synthetic_search_email_result"] == {"items": []}
