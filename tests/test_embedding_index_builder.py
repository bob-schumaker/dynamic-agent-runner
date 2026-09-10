"""Tests for the owner-authorized experimental index-builder bridge."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from dynamic_agent_runner.workflow_host.embedding_execution import (
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
from dynamic_agent_runner.workflow_host.embedding_index_builder import (
    ExperimentalBuilderBinding,
    ExperimentalBuilderCatalog,
    IndexBuilderDescriptor,
    IndexBuilderError,
    OwnerAuthorizedBuilderProfile,
    run_owner_authorized_builder,
)
from dynamic_agent_runner.workflow_host.sandbox_result_location import (
    DeclaredResultArtifact,
)


def _snapshot() -> DocumentSnapshot:
    return DocumentSnapshot.create(
        (SnapshotDocument("note_1", "text/plain", b"alpha"),),
        policy=DocumentSnapshotPolicy(1, 16, 16, ("text/plain",)),
    )


def _descriptor() -> IndexBuilderDescriptor:
    return IndexBuilderDescriptor(
        package_digest="a" * 64,
        asset_digest="b" * 64,
        result_artifacts=(
            DeclaredResultArtifact("coverage_report", 2048),
            DeclaredResultArtifact("index_bundle", 128),
            DeclaredResultArtifact("index_manifest", 2048),
        ),
        max_prior_bundle_bytes=128,
    )


@dataclass
class _FakeBuilder:
    calls: list[dict[str, object]] = field(default_factory=list)

    def run(
        self,
        *,
        snapshot: DocumentSnapshot,
        prior_bundle: bytes | None,
        binding: IndexArtifactBinding,
        embed: object,
        results: object,
    ) -> None:
        self.calls.append(
            {
                "snapshot": snapshot,
                "prior_bundle": prior_bundle,
                "binding": binding,
                "embed": embed,
                "results": results,
            }
        )
        bundle = b"index"
        manifest = IndexBundleManifest.create(
            bundle=bundle,
            snapshot=snapshot,
            binding=binding,
            document_count=1,
            chunk_count=1,
            indexed_count=1,
            skipped_count=0,
            deleted_count=0,
            error_count=0,
        )
        report = CoverageReport.create(
            snapshot=snapshot,
            binding=binding,
            prior_bundle_digest=None,
            document_count=1,
            chunk_count=1,
            indexed_count=1,
            skipped_count=0,
            deleted_count=0,
            error_count=0,
            error_classifications=(),
        )
        results.write("coverage_report", report.canonical_bytes)
        results.write("index_bundle", bundle)
        results.write("index_manifest", manifest.canonical_bytes)


def _embed(items: tuple[EmbeddingTextItem, ...]) -> tuple[EmbeddingVector, ...]:
    return tuple(EmbeddingVector(item.item_id, (0.25, 0.75)) for item in items)


def _binding(descriptor: IndexBuilderDescriptor) -> IndexArtifactBinding:
    return IndexArtifactBinding("c" * 64, "d" * 64, descriptor.digest)


def test_owner_authorized_builder_receives_only_narrow_data_abi() -> None:
    builder = _FakeBuilder()
    descriptor = _descriptor()
    result = run_owner_authorized_builder(
        profile=OwnerAuthorizedBuilderProfile("a" * 64, "b" * 64),
        descriptor=descriptor,
        catalog=ExperimentalBuilderCatalog(
            (ExperimentalBuilderBinding("b" * 64, builder),)
        ),
        snapshot=_snapshot(),
        prior_bundle=None,
        binding=_binding(descriptor),
        embed=_embed,
    )

    assert result.builder_digest == descriptor.digest
    assert result.artifacts[0].name == "coverage_report"
    assert result.read("index_bundle") == b"index"
    assert len(builder.calls) == 1
    assert set(builder.calls[0]) == {
        "snapshot",
        "prior_bundle",
        "binding",
        "embed",
        "results",
    }
    assert not hasattr(builder.calls[0]["results"], "path")


@pytest.mark.parametrize(
    "profile,prior_bundle",
    [
        (OwnerAuthorizedBuilderProfile("c" * 64, "b" * 64), None),
        (OwnerAuthorizedBuilderProfile("a" * 64, "c" * 64), None),
        (OwnerAuthorizedBuilderProfile("a" * 64, "b" * 64), b"x" * 129),
    ],
)
def test_rejected_builder_admission_never_calls_builder(
    profile: OwnerAuthorizedBuilderProfile, prior_bundle: bytes | None
) -> None:
    builder = _FakeBuilder()

    with pytest.raises(IndexBuilderError):
        run_owner_authorized_builder(
            profile=profile,
            descriptor=_descriptor(),
            catalog=ExperimentalBuilderCatalog(
                (ExperimentalBuilderBinding("b" * 64, builder),)
            ),
            snapshot=_snapshot(),
            prior_bundle=prior_bundle,
            binding=_binding(_descriptor()),
            embed=_embed,
        )

    assert builder.calls == []


def test_builder_cannot_write_an_undeclared_result_slot() -> None:
    class InvalidBuilder(_FakeBuilder):
        def run(self, **kwargs: object) -> None:
            kwargs["results"].write("arbitrary_destination", b"data")

    builder = InvalidBuilder()
    with pytest.raises(IndexBuilderError, match="failed"):
        run_owner_authorized_builder(
            profile=OwnerAuthorizedBuilderProfile("a" * 64, "b" * 64),
            descriptor=_descriptor(),
            catalog=ExperimentalBuilderCatalog(
                (ExperimentalBuilderBinding("b" * 64, builder),)
            ),
            snapshot=_snapshot(),
            prior_bundle=None,
            binding=_binding(_descriptor()),
            embed=_embed,
        )


def test_builder_rejects_a_result_manifest_with_wrong_binding() -> None:
    class MismatchedManifestBuilder(_FakeBuilder):
        def run(self, **kwargs: object) -> None:
            snapshot = kwargs["snapshot"]
            binding = IndexArtifactBinding("e" * 64, "d" * 64, "f" * 64)
            bundle = b"index"
            manifest = IndexBundleManifest.create(
                bundle=bundle,
                snapshot=snapshot,
                binding=binding,
                document_count=1,
                chunk_count=1,
                indexed_count=1,
                skipped_count=0,
                deleted_count=0,
                error_count=0,
            )
            report = CoverageReport.create(
                snapshot=snapshot,
                binding=binding,
                prior_bundle_digest=None,
                document_count=1,
                chunk_count=1,
                indexed_count=1,
                skipped_count=0,
                deleted_count=0,
                error_count=0,
                error_classifications=(),
            )
            kwargs["results"].write("coverage_report", report.canonical_bytes)
            kwargs["results"].write("index_bundle", bundle)
            kwargs["results"].write("index_manifest", manifest.canonical_bytes)

    descriptor = _descriptor()
    with pytest.raises(IndexBuilderError, match="artifact"):
        run_owner_authorized_builder(
            profile=OwnerAuthorizedBuilderProfile("a" * 64, "b" * 64),
            descriptor=descriptor,
            catalog=ExperimentalBuilderCatalog(
                (ExperimentalBuilderBinding("b" * 64, MismatchedManifestBuilder()),)
            ),
            snapshot=_snapshot(),
            prior_bundle=None,
            binding=_binding(descriptor),
            embed=_embed,
        )
