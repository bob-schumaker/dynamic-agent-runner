"""Tests for the receiver-owned sealed embedding callback bridge."""

from __future__ import annotations

import json
from hashlib import sha256
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingBatchLimits,
    EmbeddingExecutionBinding,
    EmbeddingLimitProjectorBinding,
    EmbeddingLimitProjectorRegistry,
    EmbeddingTextItem,
    EmbeddingVector,
)
from dynamic_agent_runner.workflow_host.embedding_index_artifacts import (
    CoverageReport,
    DocumentSnapshot,
    DocumentSnapshotPolicy,
    IndexArtifactBinding,
    IndexBundleManifest,
    SnapshotDocument,
)
from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityRequirement,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.embedding_sealed_artifact_callback import (
    EmbeddingSealedArtifactCallbackError,
    EmbeddingSealedArtifactCallbackProvider,
    EmbeddingSealedArtifactCallbackResolver,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorAbi,
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactCallback,
    SealedArtifactChildContract,
    SealedArtifactInput,
    SealedArtifactLimits,
    SealedArtifactOutput,
    SealedArtifactRunnerDescriptor,
    SealedArtifactSchemaAsset,
)


def test_sealed_embedding_callback_translates_only_canonical_bounded_json() -> None:
    calls: list[object] = []

    class Execution:
        def execute(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(kwargs)
            return (EmbeddingVector("chunk-1", (0.25, 0.75)),)

    callback = SealedArtifactCallback(
        "embed", "embedding.execute.v1", "a" * 64, 1, 1, 256, 256, 256, 256, 1
    )
    binding = EmbeddingExecutionBinding(
        ModelExecutionBinding(
            "locked",
            "runner",
            "1",
            None,
            None,
            "b" * 64,
            "c" * 64,
            "runner.capability",
            "1",
            "d" * 64,
        ),
        "embedding.execute.v1",
        "1",
        "e" * 64,
    )
    provider = EmbeddingSealedArtifactCallbackProvider(
        callback=callback,
        execution=Execution(),
        binding=binding,
        selected_provider_ids=("receiver-private",),
        limits=EmbeddingBatchLimits(1, 16, 16, 2, 1),
        request_schema=_embedding_request_schema(),
        response_schema=_embedding_response_schema(),
    )

    response = provider.invoke("embed", b'{"items":[{"id":"chunk-1","text":"note"}]}')

    assert json.loads(response) == {
        "items": [{"id": "chunk-1", "vector": [0.25, 0.75]}]
    }
    assert calls[0]["items"] == (EmbeddingTextItem("chunk-1", "note"),)


def test_sealed_embedding_callback_rejects_a_response_outside_its_schema() -> None:
    class Execution:
        def execute(self, **_kwargs):  # type: ignore[no-untyped-def]
            return (EmbeddingVector("chunk-1", (0.25, 0.75)),)

    provider = EmbeddingSealedArtifactCallbackProvider(
        callback=SealedArtifactCallback(
            "embed", "embedding.execute.v1", "a" * 64, 1, 1, 256, 256, 256, 256, 1
        ),
        execution=Execution(),
        binding=_binding(),
        selected_provider_ids=("receiver-private",),
        limits=EmbeddingBatchLimits(1, 16, 16, 2, 1),
        request_schema=_embedding_request_schema(),
        response_schema={"type": "object", "required": ["missing"]},
    )

    with pytest.raises(EmbeddingSealedArtifactCallbackError, match="unavailable"):
        provider.invoke("embed", b'{"items":[{"id":"chunk-1","text":"note"}]}')


def test_embedding_resolver_uses_the_sealed_request_schema_before_execution() -> None:
    calls: list[object] = []

    class Execution:
        def execute(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(kwargs)
            return ()

    identity = ExecutionDescriptorAbi("example-encoder-v1", "1", "d" * 64)
    request_schema = _embedding_request_schema()
    request_schema["properties"]["items"]["minItems"] = 2  # type: ignore[index]
    resolver = EmbeddingSealedArtifactCallbackResolver(
        execution=Execution(),
        limit_projectors=EmbeddingLimitProjectorRegistry(
            (
                EmbeddingLimitProjectorBinding(
                    identity, lambda _descriptor: EmbeddingBatchLimits(2, 16, 16, 2, 2)
                ),
            )
        ),
    )
    provider = resolver.resolve(
        _descriptor_with_schemas(request_schema, _embedding_response_schema()),
        _policy(identity),
        object(),
    )

    with pytest.raises(EmbeddingSealedArtifactCallbackError, match="unavailable"):
        provider.invoke("embed", b'{"items":[{"id":"chunk-1","text":"note"}]}')

    assert calls == []


def test_embedding_resolver_rejects_an_incomplete_sealed_child_contract() -> None:
    class Execution:
        def execute(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("execution must not be reached")

    identity = ExecutionDescriptorAbi("example-encoder-v1", "1", "d" * 64)
    resolver = EmbeddingSealedArtifactCallbackResolver(
        execution=Execution(),
        limit_projectors=EmbeddingLimitProjectorRegistry(
            (
                EmbeddingLimitProjectorBinding(
                    identity, lambda _descriptor: EmbeddingBatchLimits(1, 16, 16, 2, 1)
                ),
            )
        ),
    )

    with pytest.raises(EmbeddingSealedArtifactCallbackError, match="unavailable"):
        resolver.resolve(
            _descriptor_with_schemas(
                _embedding_request_schema(),
                _embedding_response_schema(),
                child_body={"embed_request_schema_digest": "1" * 64},
            ),
            _policy(identity),
            object(),
        )


def test_embedding_callback_validates_the_private_index_output_triple() -> None:
    class Execution:
        def execute(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("embedding execution is not part of output validation")

    callback = SealedArtifactCallback(
        "embed", "embedding.execute.v1", "a" * 64, 1, 1, 256, 256, 256, 256, 1
    )
    binding = _binding()
    descriptor = _index_output_descriptor(callback)
    provider = EmbeddingSealedArtifactCallbackProvider(
        callback=callback,
        execution=Execution(),
        binding=binding,
        selected_provider_ids=("receiver-private",),
        limits=EmbeddingBatchLimits(1, 16, 16, 2, 1),
        request_schema=_embedding_request_schema(),
        response_schema=_embedding_response_schema(),
        output_descriptor=descriptor,
    )
    snapshot = DocumentSnapshot.create(
        (SnapshotDocument("document-a", "text/plain", b"note"),),
        policy=DocumentSnapshotPolicy(1, 16, 16, ("text/plain",)),
    )
    assert sha256(snapshot.wire_bytes).hexdigest() != snapshot.snapshot_digest
    index_binding = IndexArtifactBinding(
        binding.material_lock_digest,
        binding.capability_contract_digest,
        _builder_digest(descriptor, callback),
    )
    bundle = b"opaque-index"
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
    contents = {"snapshot": snapshot.wire_bytes}

    provider.validate_sealed_outputs(
        (
            ("coverage_report", "application/json", report.canonical_bytes),
            ("index_bundle", "application/octet-stream", bundle),
            ("index_manifest", "application/json", manifest.canonical_bytes),
        ),
        {"snapshot": sha256(snapshot.wire_bytes).hexdigest()},
        contents,
    )

    with pytest.raises(EmbeddingSealedArtifactCallbackError, match="unavailable"):
        provider.validate_sealed_outputs(
            (
                ("coverage_report", "application/json", report.canonical_bytes),
                ("index_bundle", "application/octet-stream", b"tampered"),
                ("index_manifest", "application/json", manifest.canonical_bytes),
            ),
            {"snapshot": sha256(snapshot.wire_bytes).hexdigest()},
            contents,
        )


def test_embedding_resolver_rejects_a_policy_without_the_exact_callback() -> None:
    class Execution:
        def execute(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("execution must not be reached")

    identity = ExecutionDescriptorAbi("example-encoder-v1", "1", "d" * 64)
    resolver = EmbeddingSealedArtifactCallbackResolver(
        execution=Execution(),
        limit_projectors=EmbeddingLimitProjectorRegistry(
            (
                EmbeddingLimitProjectorBinding(
                    identity, lambda _descriptor: EmbeddingBatchLimits(1, 1, 1, 1, 1)
                ),
            )
        ),
    )
    descriptor = SealedArtifactRunnerDescriptor(
        "a" * 64,
        "asset.py",
        "b" * 64,
        "c" * 64,
        "d" * 64,
        (),
        (),
        SimpleNamespace(),
        (),
        (),
        (),
        (),
    )
    policy = SimpleNamespace(
        embedding_execution_binding=None,
        execution_descriptor=parse_execution_descriptor(
            {
                "format_version": 1,
                "architecture_abi": identity.to_mapping(),
                "material_roles": ["weights"],
                "abi_fields": {},
            }
        ),
        capability_requirements=None,
        selected_capability_provider_ids=(),
    )

    with pytest.raises(EmbeddingSealedArtifactCallbackError, match="unavailable"):
        resolver.resolve(descriptor, policy, object())


def _binding() -> EmbeddingExecutionBinding:
    return EmbeddingExecutionBinding(
        ModelExecutionBinding(
            "locked",
            "runner",
            "1",
            None,
            None,
            "b" * 64,
            "c" * 64,
            "runner.capability",
            "1",
            "d" * 64,
        ),
        "embedding.execute.v1",
        "1",
        "e" * 64,
    )


def _embedding_request_schema() -> dict[str, object]:
    return {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "text"],
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            }
        },
        "additionalProperties": False,
    }


def _embedding_response_schema() -> dict[str, object]:
    return {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "vector"],
                    "properties": {
                        "id": {"type": "string"},
                        "vector": {"type": "array", "items": {"type": "number"}},
                    },
                    "additionalProperties": False,
                },
            }
        },
        "additionalProperties": False,
    }


def _descriptor_with_schemas(
    request_schema: object,
    response_schema: object,
    *,
    child_body: dict[str, str] | None = None,
) -> SealedArtifactRunnerDescriptor:
    request_digest = "1" * 64
    response_digest = "2" * 64
    child = {
        "body": child_body
        or {
            "embed_request_schema_digest": request_digest,
            "embed_response_schema_digest": response_digest,
        },
        "callback_name": "embed",
        "capability_requirement": "embedding.execute.v1",
        "format_version": 1,
    }
    canonical_child = json.dumps(child, separators=(",", ":"), sort_keys=True).encode()
    child_digest = sha256(canonical_child).hexdigest()
    callback = SealedArtifactCallback(
        "embed", "embedding.execute.v1", child_digest, 1, 1, 256, 256, 256, 256, 1
    )
    return SealedArtifactRunnerDescriptor(
        "a" * 64,
        "asset.py",
        "b" * 64,
        "c" * 64,
        "d" * 64,
        (
            SealedArtifactInput("snapshot", "application/json", 1024, True, None),
            SealedArtifactInput(
                "prior_bundle", "application/octet-stream", 1024, False, None
            ),
            SealedArtifactInput(
                "prior_index_manifest", "application/json", 1024, False, None
            ),
        ),
        (
            SealedArtifactOutput("coverage_report", "application/json", 1024, None),
            SealedArtifactOutput(
                "index_bundle", "application/octet-stream", 1024, None
            ),
            SealedArtifactOutput("index_manifest", "application/json", 1024, None),
        ),
        SealedArtifactLimits(1, 1, 1, 1, 1),
        (
            SealedArtifactSchemaAsset(
                "schemas/request.json", request_digest, request_schema
            ),
            SealedArtifactSchemaAsset(
                "schemas/response.json", response_digest, response_schema
            ),
        ),
        (child_digest,),
        (callback,),
        ("coverage_report", "index_bundle", "index_manifest"),
        (SealedArtifactChildContract(child_digest, canonical_child),),
    )


def _policy(identity: ExecutionDescriptorAbi) -> SimpleNamespace:
    return SimpleNamespace(
        embedding_execution_binding=_binding(),
        execution_descriptor=parse_execution_descriptor(
            {
                "format_version": 1,
                "architecture_abi": identity.to_mapping(),
                "material_roles": ["weights"],
                "abi_fields": {},
            }
        ),
        capability_requirements=CapabilityRequirements(
            (CapabilityRequirement("embedding.execute.v1", "1", "e" * 64, ()),)
        ),
        selected_capability_provider_ids=("receiver-private",),
    )


def _index_output_descriptor(
    callback: SealedArtifactCallback,
) -> SealedArtifactRunnerDescriptor:
    return SealedArtifactRunnerDescriptor(
        "a" * 64,
        "asset.py",
        "b" * 64,
        "c" * 64,
        "d" * 64,
        (SealedArtifactInput("snapshot", "application/json", 1024, True, None),),
        (
            SealedArtifactOutput("coverage_report", "application/json", 1024, None),
            SealedArtifactOutput(
                "index_bundle", "application/octet-stream", 1024, None
            ),
            SealedArtifactOutput("index_manifest", "application/json", 1024, None),
        ),
        SealedArtifactLimits(1, 1, 1, 1, 1),
        (),
        (callback.child_contract_digest,),
        (callback,),
        ("coverage_report", "index_bundle", "index_manifest"),
    )


def _builder_digest(
    descriptor: SealedArtifactRunnerDescriptor, callback: SealedArtifactCallback
) -> str:
    return sha256(
        json.dumps(
            {
                "asset_digest": descriptor.asset_digest,
                "builder_contract_digest": callback.child_contract_digest,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
