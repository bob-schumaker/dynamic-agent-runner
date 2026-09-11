"""Tests for sealed embedding-index ingress and opaque egress artifacts."""

from __future__ import annotations

from hashlib import sha256

import pytest

from dynamic_agent_runner.workflow_host.embedding_index_artifacts import (
    CoverageReport,
    DocumentSnapshot,
    DocumentSnapshotError,
    DocumentSnapshotPolicy,
    IndexArtifactBinding,
    IndexArtifactError,
    IndexBundleManifest,
    SnapshotDocument,
    validate_index_artifacts,
)


def _policy() -> DocumentSnapshotPolicy:
    return DocumentSnapshotPolicy(
        max_documents=2,
        max_document_bytes=32,
        max_snapshot_bytes=48,
        accepted_media_types=("text/plain",),
    )


def _snapshot() -> DocumentSnapshot:
    return DocumentSnapshot.create(
        (
            SnapshotDocument("document-a", "text/plain", b"alpha"),
            SnapshotDocument("document-b", "text/plain", b"beta"),
        ),
        policy=_policy(),
    )


def _binding() -> IndexArtifactBinding:
    return IndexArtifactBinding(
        embedding_material_lock_digest="a" * 64,
        embedding_capability_contract_digest="b" * 64,
        index_builder_digest="c" * 64,
    )


def test_document_snapshot_is_canonical_and_opaque() -> None:
    snapshot = _snapshot()

    assert (
        snapshot.snapshot_digest
        == DocumentSnapshot.create(
            (
                SnapshotDocument("document-a", "text/plain", b"alpha"),
                SnapshotDocument("document-b", "text/plain", b"beta"),
            ),
            policy=_policy(),
        ).snapshot_digest
    )
    assert snapshot.documents[0].content_hash == sha256(b"alpha").hexdigest()
    assert "alpha" not in repr(snapshot)
    assert "beta" not in repr(snapshot)


def test_document_snapshot_round_trips_through_canonical_sealed_wire_bytes() -> None:
    snapshot = _snapshot()

    restored = DocumentSnapshot.from_wire_bytes(snapshot.wire_bytes, policy=_policy())

    assert restored == snapshot
    assert restored.snapshot_digest == snapshot.snapshot_digest


@pytest.mark.parametrize(
    "content",
    (
        b'{"documents":[{"content_base64":"YWxwaGE","document_id":"document-a","media_type":"text/plain"}],"format_version":1}',
        b'{"format_version":1,"documents":[{"content_base64":"YWxwaGE","document_id":"document-a","media_type":"text/plain"}]} ',
    ),
)
def test_document_snapshot_rejects_noncanonical_sealed_wire_bytes(
    content: bytes,
) -> None:
    with pytest.raises(DocumentSnapshotError):
        DocumentSnapshot.from_wire_bytes(content, policy=_policy())


@pytest.mark.parametrize(
    "documents",
    [
        (
            SnapshotDocument("document-b", "text/plain", b"beta"),
            SnapshotDocument("document-a", "text/plain", b"alpha"),
        ),
        (SnapshotDocument("document/a", "text/plain", b"alpha"),),
        (SnapshotDocument("document-a", "text/html", b"alpha"),),
        (SnapshotDocument("document-a", "text/plain", b"x" * 33),),
    ],
)
def test_document_snapshot_rejects_invalid_or_excess_input(
    documents: tuple[SnapshotDocument, ...],
) -> None:
    with pytest.raises(DocumentSnapshotError):
        DocumentSnapshot.create(documents, policy=_policy())


def test_document_snapshot_rejects_duplicate_document_ids() -> None:
    with pytest.raises(DocumentSnapshotError, match="unique"):
        DocumentSnapshot.create(
            (
                SnapshotDocument("document-a", "text/plain", b"alpha"),
                SnapshotDocument("document-a", "text/plain", b"beta"),
            ),
            policy=_policy(),
        )


def test_index_artifacts_bind_bundle_and_report_to_one_snapshot() -> None:
    snapshot = _snapshot()
    binding = _binding()
    bundle = b"opaque index bytes"
    manifest = IndexBundleManifest.create(
        bundle=bundle,
        snapshot=snapshot,
        binding=binding,
        document_count=2,
        chunk_count=2,
        indexed_count=2,
        skipped_count=0,
        deleted_count=0,
        error_count=0,
    )
    report = CoverageReport.create(
        snapshot=snapshot,
        binding=binding,
        prior_bundle_digest=None,
        document_count=2,
        chunk_count=2,
        indexed_count=2,
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
        binding=binding,
        max_bundle_bytes=64,
        max_report_bytes=2048,
    )

    assert result.bundle_sha256 == sha256(bundle).hexdigest()
    assert "opaque index bytes" not in repr(result)


def test_index_artifacts_reject_mismatched_bundle_or_report_content() -> None:
    snapshot = _snapshot()
    binding = _binding()
    bundle = b"opaque index bytes"
    manifest = IndexBundleManifest.create(
        bundle=bundle,
        snapshot=snapshot,
        binding=binding,
        document_count=2,
        chunk_count=2,
        indexed_count=2,
        skipped_count=0,
        deleted_count=0,
        error_count=0,
    )
    report = CoverageReport.create(
        snapshot=snapshot,
        binding=binding,
        prior_bundle_digest=None,
        document_count=2,
        chunk_count=2,
        indexed_count=2,
        skipped_count=0,
        deleted_count=0,
        error_count=0,
        error_classifications=(),
    )

    with pytest.raises(IndexArtifactError, match="bundle"):
        validate_index_artifacts(
            bundle=b"changed bytes",
            manifest=manifest,
            report=report,
            snapshot=snapshot,
            binding=binding,
            max_bundle_bytes=64,
            max_report_bytes=2048,
        )
    with pytest.raises(IndexArtifactError, match="report"):
        CoverageReport.from_mapping({"unexpected": "document content"})
    with pytest.raises(IndexArtifactError, match="report"):
        CoverageReport.from_mapping(
            {
                "format_version": 1,
                "snapshot_digest": snapshot.snapshot_digest,
                **binding.to_mapping(),
                "prior_bundle_digest": None,
                "document_count": 2,
                "chunk_count": 2,
                "indexed_count": 2,
                "skipped_count": 0,
                "deleted_count": 0,
                "error_count": 0,
                "error_classifications": "not-a-list",
            }
        )
