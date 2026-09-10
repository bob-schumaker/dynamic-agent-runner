"""Contract tests for ordered atomic sealed-artifact output collection."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactOutput,
    SealedArtifactOutputCollector,
    SealedArtifactOutputCollectorError,
    SealedArtifactLimits,
    SealedArtifactRunnerDescriptor,
)


def _descriptor() -> SealedArtifactRunnerDescriptor:
    return SealedArtifactRunnerDescriptor(
        digest="a" * 64,
        asset_path="assets/runner.py",
        asset_digest="b" * 64,
        capability_requirements_digest="c" * 64,
        profile_digest="d" * 64,
        inputs=(),
        outputs=(
            SealedArtifactOutput(
                role="coverage",
                media_type="text/plain",
                max_bytes=10,
                schema_digest=None,
            ),
            SealedArtifactOutput(
                role="result",
                media_type="application/octet-stream",
                max_bytes=10,
                schema_digest=None,
            ),
        ),
        limits=SealedArtifactLimits(1, 1, 100, 1, 1),
        schema_assets=(),
        child_contract_digests=(),
        callbacks=(),
        output_roles=("coverage", "result"),
    )


def test_collector_seals_only_all_declared_outputs_in_order() -> None:
    collector = SealedArtifactOutputCollector(descriptor=_descriptor())

    collector.write(role="coverage", media_type="text/plain", content=b"ready")
    collector.write(
        role="result", media_type="application/octet-stream", content=b"payload"
    )

    sealed = collector.seal()
    assert sealed == (
        ("coverage", "text/plain", b"ready"),
        ("result", "application/octet-stream", b"payload"),
    )


def test_invalid_write_destroys_all_unsealed_candidates() -> None:
    collector = SealedArtifactOutputCollector(descriptor=_descriptor())
    collector.write(role="coverage", media_type="text/plain", content=b"ready")

    with pytest.raises(SealedArtifactOutputCollectorError, match="invalid"):
        collector.write(
            role="result", media_type="application/json", content=b"payload"
        )

    with pytest.raises(SealedArtifactOutputCollectorError, match="unavailable"):
        collector.seal()


def test_partial_collection_cannot_seal_or_be_reused() -> None:
    collector = SealedArtifactOutputCollector(descriptor=_descriptor())
    collector.write(role="coverage", media_type="text/plain", content=b"ready")

    with pytest.raises(SealedArtifactOutputCollectorError, match="unavailable"):
        collector.seal()

    with pytest.raises(SealedArtifactOutputCollectorError, match="unavailable"):
        collector.write(
            role="result", media_type="application/octet-stream", content=b"payload"
        )
