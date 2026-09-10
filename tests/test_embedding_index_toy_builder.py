"""End-to-end fake-host tests for the workflow-local toy index-builder asset."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingTextItem,
    EmbeddingVector,
)
from dynamic_agent_runner.workflow_host.embedding_index_artifacts import (
    DocumentSnapshot,
    DocumentSnapshotPolicy,
    IndexArtifactBinding,
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


def _toy_builder() -> object:
    path = (
        Path(__file__).parent
        / "fixtures"
        / "embedding-index-toy-builder"
        / "toy_builder.py"
    )
    spec = importlib.util.spec_from_file_location("embedding_index_toy_builder", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ToyIndexBuilder()


def _descriptor() -> IndexBuilderDescriptor:
    return IndexBuilderDescriptor(
        package_digest="a" * 64,
        asset_digest="b" * 64,
        result_artifacts=(
            DeclaredResultArtifact("coverage_report", 4096),
            DeclaredResultArtifact("index_bundle", 4096),
            DeclaredResultArtifact("index_manifest", 4096),
        ),
        max_prior_bundle_bytes=4096,
    )


def _snapshot() -> DocumentSnapshot:
    return DocumentSnapshot.create(
        (SnapshotDocument("note_1", "text/plain", b"alpha"),),
        policy=DocumentSnapshotPolicy(1, 32, 32, ("text/plain",)),
    )


def _embed(items: tuple[EmbeddingTextItem, ...]) -> tuple[EmbeddingVector, ...]:
    assert items == (EmbeddingTextItem("note_1", "alpha"),)
    return (EmbeddingVector("note_1", (0.25, 0.75)),)


def _run(
    *,
    prior_bundle: bytes | None = None,
    descriptor: IndexBuilderDescriptor | None = None,
):
    descriptor = descriptor or _descriptor()
    return run_owner_authorized_builder(
        profile=OwnerAuthorizedBuilderProfile("a" * 64, "b" * 64),
        descriptor=descriptor,
        catalog=ExperimentalBuilderCatalog(
            (ExperimentalBuilderBinding("b" * 64, _toy_builder()),)
        ),
        snapshot=_snapshot(),
        prior_bundle=prior_bundle,
        binding=IndexArtifactBinding("c" * 64, "d" * 64, descriptor.digest),
        embed=_embed,
    )


def test_toy_builder_has_deterministic_initial_and_incremental_identity() -> None:
    initial = _run()
    repeated_initial = _run()

    assert initial.read("index_bundle") == repeated_initial.read("index_bundle")
    assert initial.read("coverage_report") == repeated_initial.read("coverage_report")
    incremental = _run(prior_bundle=initial.read("index_bundle"))
    repeated_incremental = _run(prior_bundle=initial.read("index_bundle"))
    assert incremental.read("index_bundle") == initial.read("index_bundle")
    assert incremental.read("coverage_report") == repeated_incremental.read(
        "coverage_report"
    )
    assert incremental.read("coverage_report") != initial.read("coverage_report")
    assert "alpha" not in repr(initial)
    assert "0.25" not in repr(initial)


def test_changed_builder_identity_is_a_rebuild_boundary() -> None:
    descriptor = IndexBuilderDescriptor(
        package_digest="a" * 64,
        asset_digest="e" * 64,
        result_artifacts=_descriptor().result_artifacts,
        max_prior_bundle_bytes=4096,
    )

    with pytest.raises(IndexBuilderError, match="admission"):
        _run(descriptor=descriptor)
