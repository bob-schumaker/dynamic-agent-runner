"""Tests for durable reviewed-capability publication ordering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dynamic_agent_runner.workflow_host.reviewed_capability_publication import (
    ReviewedCapabilityPublicationCoordinator,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactLimits,
    SealedArtifactOutput,
    SealedArtifactOutputHandleService,
    SealedArtifactRunnerDescriptor,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


NOW = datetime(2026, 9, 15, tzinfo=UTC)


class _FakeHost:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def begin_pending_publication(
        self, *, reservation_id: str, generation_id: str
    ) -> None:
        self.calls.append(("pending", reservation_id))

    def acknowledge_visibility(self, *, reservation_id: str) -> None:
        self.calls.append(("visible", reservation_id))


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
                "index_generation", "application/octet-stream", 10, None
            ),
            SealedArtifactOutput("index_manifest", "application/json", 10, None),
            SealedArtifactOutput("coverage_report", "application/json", 10, None),
        ),
        limits=SealedArtifactLimits(1, 1, 100, 1, 1),
        schema_assets=(),
        child_contract_digests=(),
        callbacks=(),
        output_roles=("index_generation", "index_manifest", "coverage_report"),
    )


def test_publication_records_all_states_before_exposing_handles(tmp_path) -> None:
    store = PrivateStateStore(tmp_path / "state")
    artifacts = SealedArtifactOutputHandleService(store=store, owner="host")
    private = artifacts.stage(
        descriptor=_descriptor(),
        receiver_id="principal",
        revision_digest="e" * 64,
        invocation_id="run-1",
        sealed=(
            ("index_generation", "application/octet-stream", b"index"),
            ("index_manifest", "application/json", b"{}"),
            ("coverage_report", "application/json", b"{}"),
        ),
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )
    host = _FakeHost()
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store, owner="host", artifacts=artifacts, host=host
    )

    receipt = coordinator.complete(
        reservation_id="v1.reservation",
        private=private,
        generation_id="generation-1",
        counts={"source_records": 1},
        now=NOW,
    )

    assert receipt.status == "published"
    assert [handle.role for handle in receipt.artifacts] == [
        "index_generation",
        "index_manifest",
        "coverage_report",
    ]
    assert host.calls == [("pending", "v1.reservation"), ("visible", "v1.reservation")]
    state = (tmp_path / "state" / "records.json").read_text(encoding="utf-8")
    assert '"status":"completed"' in state


def test_pending_publication_error_marks_the_same_attempt_for_recovery(
    tmp_path,
) -> None:
    store = PrivateStateStore(tmp_path / "state")
    artifacts = SealedArtifactOutputHandleService(store=store, owner="host")
    private = artifacts.stage(
        descriptor=_descriptor(),
        receiver_id="principal",
        revision_digest="e" * 64,
        invocation_id="run-1",
        sealed=(
            ("index_generation", "application/octet-stream", b"index"),
            ("index_manifest", "application/json", b"{}"),
            ("coverage_report", "application/json", b"{}"),
        ),
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )
    host = _FakeHost()

    def fail_pending(*, reservation_id: str, generation_id: str) -> None:
        del reservation_id, generation_id
        raise RuntimeError("host unavailable")

    host.begin_pending_publication = fail_pending  # type: ignore[method-assign]
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store, owner="host", artifacts=artifacts, host=host
    )

    with pytest.raises(Exception, match="publication"):
        coordinator.complete(
            reservation_id="v1.reservation",
            private=private,
            generation_id="generation-1",
            counts={"source_records": 1},
            now=NOW,
        )

    state = (tmp_path / "state" / "records.json").read_text(encoding="utf-8")
    assert '"status":"recovery_required"' in state
    assert '"kind":"sealed_artifact_output_set"' not in state
