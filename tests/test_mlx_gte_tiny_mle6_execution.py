"""Fake-only generic embedding/index coverage for the MLE6 GTE Tiny package."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityContract,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingExecutionBindingError,
    EmbeddingExecutionService,
    EmbeddingProviderCatalog,
    EmbeddingTextItem,
    EmbeddingVector,
    derive_embedding_execution_binding,
)
from dynamic_agent_runner.workflow_host.embedding_index_artifacts import (
    CoverageReport,
    DocumentSnapshot,
    DocumentSnapshotPolicy,
    IndexArtifactBinding,
    IndexBundleManifest,
    SnapshotDocument,
    validate_index_artifacts,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorValidatorRegistry,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BertEncoderMlxV3DescriptorValidator,
    bert_encoder_mlx_v1_embedding_batch_limits,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    derive_model_execution_binding,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)
from dynamic_agent_runner.workflow_host.workflow_support_matrix import (
    MaterialIdentity,
    WorkflowSupportCandidate,
    WorkflowSupportProfile,
    WorkflowSupportReceipt,
    WorkflowSupportStatus,
    classify_workflow_support,
    validate_workflow_support_receipt,
)


_PACKAGE = Path(__file__).parent / "fixtures" / "mlx-gte-tiny" / "mle6-package"


def _package():
    lock = parse_model_dependency_lock(
        json.loads((_PACKAGE / "model-materials.json").read_text(encoding="utf-8"))
    )
    descriptor = parse_execution_descriptor(
        json.loads((_PACKAGE / "execution-descriptor.json").read_text(encoding="utf-8"))
    )
    from dynamic_agent_runner.workflow_host.capabilities import CapabilityRequirements

    requirements = CapabilityRequirements.from_mapping(
        json.loads(
            (_PACKAGE / "capability-requirements.json").read_text(encoding="utf-8")
        )
    )
    model_binding = derive_model_execution_binding(
        lock=lock,
        requirements=requirements,
        execution_descriptor=descriptor,
        descriptor_validators=ExecutionDescriptorValidatorRegistry(
            (BertEncoderMlxV3DescriptorValidator(),)
        ),
    )
    return (
        descriptor,
        requirements,
        derive_embedding_execution_binding(
            model_binding=model_binding, requirements=requirements
        ),
    )


@dataclass
class _FakeProvider:
    contract: CapabilityContract
    model_binding: object
    calls: list[tuple[EmbeddingTextItem, ...]]
    provider_id: str = "fake-gte-tiny-provider"
    deterministic: bool = True

    def embed(
        self, *, binding: object, items: tuple[EmbeddingTextItem, ...]
    ) -> tuple[EmbeddingVector, ...]:
        self.calls.append(items)
        return tuple(EmbeddingVector(item.item_id, (0.0,) * 384) for item in items)


def _provider(binding) -> _FakeProvider:
    return _FakeProvider(
        CapabilityContract(
            binding.capability_id,
            binding.capability_contract_version,
            binding.capability_contract_digest,
            ("deterministic",),
        ),
        binding.model_binding,
        [],
    )


def _matrix_profile() -> tuple[WorkflowSupportProfile, MaterialIdentity]:
    lock = parse_model_dependency_lock(
        json.loads((_PACKAGE / "model-materials.json").read_text(encoding="utf-8"))
    )
    descriptor = parse_execution_descriptor(
        json.loads((_PACKAGE / "execution-descriptor.json").read_text(encoding="utf-8"))
    )
    requirements = CapabilityRequirements.from_mapping(
        json.loads(
            (_PACKAGE / "capability-requirements.json").read_text(encoding="utf-8")
        )
    )
    artifact_digests = {"execution_descriptor": descriptor.digest}
    artifact_digests.update(
        {
            source.role: source.sha256
            for source in lock.sources
            if source.role in descriptor.material_roles
        }
    )
    material_identity = MaterialIdentity(
        package_id=lock.logical_model_id,
        material_lock_digest=lock.digest,
        material_roles=descriptor.material_roles,
        artifact_digests=artifact_digests,
    )
    profile = WorkflowSupportProfile(
        profile_id="embedding-index-synthetic-mle6-v1",
        workflow_family="embedding-index",
        required_adapter_capabilities=("embeddings",),
        required_abi_capabilities=(descriptor.architecture_abi.abi_id,),
        required_provider_capabilities=(requirements.bindings["runner"],),
        required_host_capabilities=(),
        material_identity=material_identity,
        execution_mode="synthetic",
        authorization_required=False,
        implemented=True,
    )
    return profile, material_identity


def _matrix_candidate(
    material_identity: MaterialIdentity | None,
    *,
    abi_capabilities: frozenset[str] = frozenset({"bert-encoder-mlx-v3"}),
) -> WorkflowSupportCandidate:
    return WorkflowSupportCandidate(
        adapter_id="mlx-gte-tiny-fake-provider",
        adapter_capabilities=frozenset({"embeddings"}),
        available_abi_capabilities=abi_capabilities,
        provider_capabilities=frozenset({"embedding.execute.v1"}),
        host_capabilities=frozenset(),
        material_identity=material_identity,
        authorization_granted=False,
    )


def test_gte_tiny_package_runs_fake_embedding_and_opaque_index_workflow() -> None:
    descriptor, _requirements, binding = _package()
    provider = _provider(binding)
    limits = bert_encoder_mlx_v1_embedding_batch_limits(descriptor)
    vectors = EmbeddingExecutionService(
        providers=EmbeddingProviderCatalog((provider,)), host_limits=limits
    ).execute(
        binding=binding,
        selected_provider_ids=(provider.provider_id,),
        package_limits=limits,
        items=(EmbeddingTextItem("document-1", "synthetic document"),),
    )

    assert len(vectors) == 1
    assert provider.calls == [(EmbeddingTextItem("document-1", "synthetic document"),)]
    snapshot = DocumentSnapshot.create(
        (SnapshotDocument("document-1", "text/plain", b"synthetic document"),),
        policy=DocumentSnapshotPolicy(1, 64, 64, ("text/plain",)),
    )
    index_binding = IndexArtifactBinding(
        binding.material_lock_digest,
        binding.capability_contract_digest,
        "a" * 64,
    )
    bundle = b"opaque-index-bundle"
    manifest = IndexBundleManifest.create(
        bundle=bundle,
        snapshot=snapshot,
        binding=index_binding,
        document_count=1,
        chunk_count=1,
        indexed_count=1,
        skipped_count=0,
        deleted_count=0,
        error_count=0,
    )
    report = CoverageReport.create(
        snapshot=snapshot,
        binding=index_binding,
        prior_bundle_digest=None,
        document_count=1,
        chunk_count=1,
        indexed_count=1,
        skipped_count=0,
        deleted_count=0,
        error_count=0,
        error_classifications=(),
    )
    result = validate_index_artifacts(
        bundle=bundle,
        manifest=manifest,
        report=report,
        snapshot=snapshot,
        binding=index_binding,
        max_bundle_bytes=64,
        max_report_bytes=2048,
    )

    assert "synthetic document" not in repr(result)
    assert result.bundle_sha256


def test_gte_tiny_provider_material_mismatch_rejects_before_execution() -> None:
    descriptor, _requirements, binding = _package()
    provider = _provider(binding)
    provider.model_binding = replace(
        binding.model_binding, material_lock_digest="e" * 64
    )
    limits = bert_encoder_mlx_v1_embedding_batch_limits(descriptor)

    with pytest.raises(EmbeddingExecutionBindingError, match="unavailable"):
        EmbeddingExecutionService(
            providers=EmbeddingProviderCatalog((provider,)), host_limits=limits
        ).execute(
            binding=binding,
            selected_provider_ids=(provider.provider_id,),
            package_limits=limits,
            items=(EmbeddingTextItem("document-1", "synthetic document"),),
        )

    assert provider.calls == []


def test_mle6_synthetic_matrix_profile_executes_only_its_supported_row() -> None:
    descriptor, _requirements, binding = _package()
    profile, material_identity = _matrix_profile()
    supported_candidate = _matrix_candidate(material_identity)
    supported_cell = classify_workflow_support(profile, supported_candidate)
    provider = _provider(binding)
    limits = bert_encoder_mlx_v1_embedding_batch_limits(descriptor)

    vectors = EmbeddingExecutionService(
        providers=EmbeddingProviderCatalog((provider,)), host_limits=limits
    ).execute(
        binding=binding,
        selected_provider_ids=(provider.provider_id,),
        package_limits=limits,
        items=(EmbeddingTextItem("document-1", "synthetic document"),),
    )
    supported_receipt = WorkflowSupportReceipt(
        profile_digest=supported_cell.profile_digest,
        adapter_id=supported_cell.adapter_id,
        material_identity=supported_cell.material_identity,
        test_mode="synthetic",
        status=supported_cell.status,
        reason_codes=supported_cell.reason_codes,
        dispatch_count=len(provider.calls),
    )

    assert supported_cell.status is WorkflowSupportStatus.SUPPORTED
    assert len(vectors) == 1
    assert provider.calls == [(EmbeddingTextItem("document-1", "synthetic document"),)]
    validate_workflow_support_receipt(
        profile, supported_candidate, supported_cell, supported_receipt
    )

    missing_abi_candidate = _matrix_candidate(
        material_identity, abi_capabilities=frozenset()
    )
    missing_tokenizer = MaterialIdentity(
        package_id=material_identity.package_id,
        material_lock_digest=material_identity.material_lock_digest,
        material_roles=("weights",),
        artifact_digests=dict(material_identity.artifact_digests),
    )
    other_package = MaterialIdentity(
        package_id="unonboarded-embedding-package",
        material_lock_digest=material_identity.material_lock_digest,
        material_roles=material_identity.material_roles,
        artifact_digests=dict(material_identity.artifact_digests),
    )
    for candidate, status, reasons in (
        (
            missing_abi_candidate,
            WorkflowSupportStatus.BLOCKED,
            ("required_abi_unavailable",),
        ),
        (
            _matrix_candidate(missing_tokenizer),
            WorkflowSupportStatus.BLOCKED,
            ("required_material_missing",),
        ),
        (
            _matrix_candidate(other_package),
            WorkflowSupportStatus.BLOCKED,
            ("material_identity_mismatch",),
        ),
    ):
        cell = classify_workflow_support(profile, candidate)
        receipt = WorkflowSupportReceipt(
            profile_digest=cell.profile_digest,
            adapter_id=cell.adapter_id,
            material_identity=cell.material_identity,
            test_mode="synthetic",
            status=cell.status,
            reason_codes=cell.reason_codes,
            dispatch_count=0,
        )

        assert cell.status is status
        assert cell.reason_codes == reasons
        assert provider.calls == [
            (EmbeddingTextItem("document-1", "synthetic document"),)
        ]
        validate_workflow_support_receipt(profile, candidate, cell, receipt)
