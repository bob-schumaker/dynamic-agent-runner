"""RED tests for the pure workflow support classifier."""

from __future__ import annotations

from dynamic_agent_runner.workflow_host.workflow_support_matrix import (
    MaterialIdentity,
    WorkflowSupportCandidate,
    WorkflowSupportProfile,
    WorkflowSupportStatus,
    classify_workflow_support,
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
    provider_capabilities: frozenset[str] = frozenset({"embedding.execute.v1"}),
    host_capabilities: frozenset[str] = frozenset({"darwin-arm64"}),
    material_identity: MaterialIdentity | None = None,
) -> WorkflowSupportCandidate:
    return WorkflowSupportCandidate(
        adapter_id="mlx-local-embedding",
        adapter_capabilities=adapter_capabilities,
        provider_capabilities=provider_capabilities,
        host_capabilities=host_capabilities,
        material_identity=material_identity or _material_identity(),
        authorization_granted=False,
    )


def test_profile_digest_is_canonical_across_unicode_and_mapping_order() -> None:
    profile = _profile()
    reordered = WorkflowSupportProfile(
        profile_id="embedding-index-sealed-v1",
        workflow_family="embedding-index",
        required_adapter_capabilities=("embeddings",),
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


def test_matching_immutable_facts_are_supported_without_reasons() -> None:
    profile = _profile()

    cell = classify_workflow_support(profile, _candidate())

    assert cell.profile_digest == profile.digest
    assert cell.adapter_id == "mlx-local-embedding"
    assert cell.status is WorkflowSupportStatus.SUPPORTED
    assert cell.reason_codes == ()
