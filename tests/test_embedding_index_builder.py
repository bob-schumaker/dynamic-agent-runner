"""Tests for the owner-authorized experimental index-builder bridge."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingTextItem,
    EmbeddingVector,
)
from dynamic_agent_runner.workflow_host.embedding_index_artifacts import (
    DocumentSnapshot,
    DocumentSnapshotPolicy,
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
            DeclaredResultArtifact("coverage_report", 64),
            DeclaredResultArtifact("index_bundle", 128),
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
        embed: object,
        results: object,
    ) -> None:
        self.calls.append(
            {
                "snapshot": snapshot,
                "prior_bundle": prior_bundle,
                "embed": embed,
                "results": results,
            }
        )
        results.write("coverage_report", b'{"status":"ok"}')
        results.write("index_bundle", b"index")


def _embed(items: tuple[EmbeddingTextItem, ...]) -> tuple[EmbeddingVector, ...]:
    return tuple(EmbeddingVector(item.item_id, (0.25, 0.75)) for item in items)


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
        embed=_embed,
    )

    assert result.builder_digest == descriptor.digest
    assert result.artifacts[0].name == "coverage_report"
    assert result.read("index_bundle") == b"index"
    assert len(builder.calls) == 1
    assert set(builder.calls[0]) == {"snapshot", "prior_bundle", "embed", "results"}
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
            embed=_embed,
        )
