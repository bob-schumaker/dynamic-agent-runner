"""Tests for durable reviewed-capability publication ordering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dynamic_agent_runner.workflow_host.reviewed_capability_publication import (
    ReviewedCapabilityPublicationCoordinator,
    ReviewedCapabilityPublicationError,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactHandleError,
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
        self.current = True

    def begin_pending_publication(
        self, *, reservation_id: str, generation_id: str
    ) -> None:
        self.calls.append(("pending", reservation_id))

    def acknowledge_visibility(self, *, reservation_id: str) -> None:
        self.calls.append(("visible", reservation_id))

    def query_current_outcome(self, *, reservation_id: str) -> str:
        self.calls.append(("query", reservation_id))
        return "pending"

    def compensate(self, *, reservation_id: str) -> None:
        self.calls.append(("compensate", reservation_id))

    def assert_generation_current(
        self, *, reservation_id: str, generation_id: str
    ) -> bool:
        del generation_id
        self.calls.append(("current", reservation_id))
        return self.current

    def unpublish_generation_atomically(
        self, *, reservation_id: str, generation_id: str
    ) -> None:
        del generation_id
        self.calls.append(("unpublish", reservation_id))


class _CountingArtifacts(SealedArtifactOutputHandleService):
    def __init__(self, *, store: PrivateStateStore, owner: str) -> None:
        super().__init__(store=store, owner=owner)
        self.promotions = 0

    def promote(self, private, *, now):  # type: ignore[no-untyped-def]
        self.promotions += 1
        return super().promote(private, now=now)


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


def _counts(**overrides: int) -> dict[str, int]:
    return {
        "source_records": 0,
        "embedding_units": 0,
        "indexed": 0,
        "skipped": 0,
        "deleted": 0,
        "errored": 0,
    } | overrides


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
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )

    receipt = coordinator.complete(
        reservation_id="v1.reservation",
        private=private,
        generation_id="generation-1",
        counts=_counts(source_records=1),
        now=NOW,
    )

    assert receipt.status == "published"
    assert [handle.role for handle in receipt.artifacts] == [
        "index_generation",
        "index_manifest",
        "coverage_report",
    ]
    assert receipt.to_mapping() == {
        "status": "published",
        "generation_id": "generation-1",
        "published_at": "2026-09-15T00:00:00Z",
        "artifacts": {
            "index_generation": receipt.artifacts[0].output_set_id,
            "index_manifest": receipt.artifacts[1].output_set_id,
            "coverage_report": receipt.artifacts[2].output_set_id,
        },
        "counts": _counts(source_records=1),
    }
    assert host.calls == [("pending", "v1.reservation"), ("visible", "v1.reservation")]
    state = (tmp_path / "state" / "records.json").read_text(encoding="utf-8")
    assert '"status":"completed"' in state


@pytest.mark.parametrize(
    ("receiver_id", "invocation_id"),
    (("foreign-principal", "run-1"), ("principal", "foreign-run")),
)
def test_vector_publication_denies_all_roles_to_a_foreign_access_binding(
    tmp_path, receiver_id: str, invocation_id: str
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
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )
    receipt = coordinator.complete(
        reservation_id="v1.reservation",
        private=private,
        generation_id="generation-1",
        counts=_counts(source_records=1),
        now=NOW,
    )

    for handle in receipt.artifacts:
        with pytest.raises(SealedArtifactHandleError, match="unavailable"):
            artifacts.read(
                handle,
                receiver_id=receiver_id,
                revision_digest="e" * 64,
                invocation_id=invocation_id,
                now=NOW,
            )


@pytest.mark.parametrize(
    "counts",
    (
        {"source_records": 1},
        {
            "source_records": 1,
            "embedding_units": 0,
            "indexed": 0,
            "skipped": 0,
            "deleted": 0,
            "errored": -1,
        },
    ),
)
def test_publication_rejects_noncanonical_aggregate_counts_before_host_effect(
    tmp_path, counts: dict[str, int]
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
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )

    with pytest.raises(ReviewedCapabilityPublicationError):
        coordinator.complete(
            reservation_id="v1.reservation",
            private=private,
            generation_id="generation-1",
            counts=counts,
            now=NOW,
        )

    assert host.calls == []


def test_publication_rejects_counts_above_the_template_ceiling_before_host_effect(
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
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1,
    )

    with pytest.raises(ReviewedCapabilityPublicationError):
        coordinator.complete(
            reservation_id="v1.reservation",
            private=private,
            generation_id="generation-1",
            counts=_counts(source_records=2),
            now=NOW,
        )

    assert host.calls == []


def test_publication_rejects_a_generation_id_beyond_the_registered_limit(
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
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
        generation_id_max_bytes=1,
    )

    with pytest.raises(ReviewedCapabilityPublicationError, match="publication"):
        coordinator.complete(
            reservation_id="v1.reservation",
            private=private,
            generation_id="too-long",
            counts=_counts(source_records=1),
            now=NOW,
        )

    assert host.calls == []


def test_current_generation_retention_renews_all_output_roles(tmp_path) -> None:
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
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )
    receipt = coordinator.complete(
        reservation_id="v1.reservation",
        private=private,
        generation_id="generation-1",
        counts=_counts(source_records=1),
        now=NOW,
    )

    assert (
        coordinator.maintain_retention(
            reservation_id="v1.reservation",
            expires_at=NOW + timedelta(minutes=2),
            now=NOW + timedelta(seconds=30),
        )
        == "retained"
    )
    assert host.calls[-1] == ("current", "v1.reservation")
    assert store.load(
        receipt.artifacts[0].output_set_id,
        expected_kind="sealed_artifact_output_set",
        owner="host",
        now=NOW + timedelta(minutes=1, seconds=1),
    ).expires_at == NOW + timedelta(minutes=2)


def test_noncurrent_generation_unpublishes_before_output_set_revocation(
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
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )
    receipt = coordinator.complete(
        reservation_id="v1.reservation",
        private=private,
        generation_id="generation-1",
        counts=_counts(source_records=1),
        now=NOW,
    )
    host.current = False

    assert (
        coordinator.maintain_retention(
            reservation_id="v1.reservation",
            expires_at=NOW + timedelta(minutes=2),
            now=NOW + timedelta(seconds=30),
        )
        == "retired"
    )
    assert host.calls[-2:] == [
        ("current", "v1.reservation"),
        ("unpublish", "v1.reservation"),
    ]
    assert (
        store.active_records(
            kind="sealed_artifact_output_set",
            owner="host",
            now=NOW + timedelta(seconds=30),
        )
        == ()
    )
    assert receipt.artifacts


@pytest.mark.parametrize("operation", ("current", "unpublish"))
def test_retention_host_errors_leave_completed_output_set_active(
    tmp_path, operation: str
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
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )
    receipt = coordinator.complete(
        reservation_id="v1.reservation",
        private=private,
        generation_id="generation-1",
        counts=_counts(source_records=1),
        now=NOW,
    )
    if operation == "current":
        host.assert_generation_current = _raise_retention_host_error  # type: ignore[method-assign]
    else:
        host.current = False
        host.unpublish_generation_atomically = _raise_retention_host_error  # type: ignore[method-assign]

    with pytest.raises(ReviewedCapabilityPublicationError):
        coordinator.maintain_retention(
            reservation_id="v1.reservation",
            expires_at=NOW + timedelta(minutes=2),
            now=NOW + timedelta(seconds=30),
        )

    assert store.load(
        receipt.artifacts[0].output_set_id,
        expected_kind="sealed_artifact_output_set",
        owner="host",
        now=NOW + timedelta(seconds=45),
    ).expires_at == NOW + timedelta(minutes=1)


def _raise_retention_host_error(**_kwargs: object) -> None:
    raise RuntimeError("host unavailable")


def test_completed_publication_replays_its_stored_receipt_without_host_calls(
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
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )

    first = coordinator.complete(
        reservation_id="v1.reservation",
        private=private,
        generation_id="generation-1",
        counts=_counts(source_records=1),
        now=NOW,
    )
    calls_after_first = list(host.calls)

    replayed = coordinator.complete(
        reservation_id="v1.reservation",
        private=private,
        generation_id="generation-1",
        counts=_counts(source_records=1),
        now=NOW + timedelta(seconds=1),
    )

    assert replayed == first
    assert host.calls == calls_after_first


def test_conflicting_completion_request_never_reenters_the_host(tmp_path) -> None:
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
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )
    coordinator.complete(
        reservation_id="v1.reservation",
        private=private,
        generation_id="generation-1",
        counts=_counts(source_records=1),
        now=NOW,
    )
    calls_after_first = list(host.calls)

    with pytest.raises(ReviewedCapabilityPublicationError):
        coordinator.complete(
            reservation_id="v1.reservation",
            private=private,
            generation_id="other-generation",
            counts=_counts(source_records=1),
            now=NOW + timedelta(seconds=1),
        )

    assert host.calls == calls_after_first


def test_pre_pending_publication_error_aborts_and_discards_candidates(
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
    host.query_current_outcome = lambda *, reservation_id: "absent"  # type: ignore[method-assign]
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )

    with pytest.raises(Exception, match="publication"):
        coordinator.complete(
            reservation_id="v1.reservation",
            private=private,
            generation_id="generation-1",
            counts=_counts(source_records=1),
            now=NOW,
        )

    state = (tmp_path / "state" / "records.json").read_text(encoding="utf-8")
    assert '"status":"aborted"' in state
    assert '"kind":"sealed_artifact_output_set"' not in state
    assert (
        store.active_records(
            kind="sealed_artifact_private_output_set", owner="host", now=NOW
        )
        == ()
    )


def test_pending_recovery_promotes_the_same_staged_set_without_rebuild(
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
    calls = 0

    def fail_once(*, reservation_id: str, generation_id: str) -> None:
        nonlocal calls
        del reservation_id, generation_id
        calls += 1
        if calls == 1:
            raise RuntimeError("lost acknowledgement")

    host.begin_pending_publication = fail_once  # type: ignore[method-assign]
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )
    with pytest.raises(ReviewedCapabilityPublicationError):
        coordinator.complete(
            reservation_id="v1.reservation",
            private=private,
            generation_id="generation-1",
            counts=_counts(source_records=1),
            now=NOW,
        )

    receipt = coordinator.recover(reservation_id="v1.reservation", now=NOW)

    assert receipt.status == "published"
    assert calls == 1
    assert ("query", "v1.reservation") in host.calls


def test_visibility_recovery_reuses_the_already_promoted_output_set(tmp_path) -> None:
    store = PrivateStateStore(tmp_path / "state")
    artifacts = _CountingArtifacts(store=store, owner="host")
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
    visibility_calls = 0

    def fail_visibility_once(*, reservation_id: str) -> None:
        nonlocal visibility_calls
        visibility_calls += 1
        if visibility_calls == 1:
            raise RuntimeError("lost visibility acknowledgement")
        host.calls.append(("visible", reservation_id))

    host.acknowledge_visibility = fail_visibility_once  # type: ignore[method-assign]
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )

    with pytest.raises(ReviewedCapabilityPublicationError):
        coordinator.complete(
            reservation_id="v1.reservation",
            private=private,
            generation_id="generation-1",
            counts=_counts(source_records=1),
            now=NOW,
        )

    receipt = coordinator.recover(reservation_id="v1.reservation", now=NOW)

    assert receipt.status == "published"
    assert host.calls.count(("pending", "v1.reservation")) == 1
    assert visibility_calls == 2
    assert artifacts.promotions == 1


def test_unrecoverable_pending_publication_compensates_and_aborts(tmp_path) -> None:
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

    def fail_visibility(*, reservation_id: str) -> None:
        del reservation_id
        raise RuntimeError("lost visibility acknowledgement")

    host.acknowledge_visibility = fail_visibility  # type: ignore[method-assign]
    host.query_current_outcome = lambda *, reservation_id: "unknown"  # type: ignore[method-assign]
    coordinator = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="host_failure",
        failure_classifications=("host_failure",),
        count_ceiling=1024,
    )
    with pytest.raises(ReviewedCapabilityPublicationError):
        coordinator.complete(
            reservation_id="v1.reservation",
            private=private,
            generation_id="generation-1",
            counts=_counts(source_records=1),
            now=NOW,
        )

    receipt = coordinator.recover(reservation_id="v1.reservation", now=NOW)

    assert receipt.to_mapping() == {
        "status": "failed",
        "classification": "host_failure",
        "receipt_id": receipt.receipt_id,
    }
    assert coordinator.recover(reservation_id="v1.reservation", now=NOW) == receipt
    recovered = ReviewedCapabilityPublicationCoordinator(
        store=store,
        owner="host",
        artifacts=artifacts,
        host=host,
        failure_classification="other_failure",
        failure_classifications=("host_failure", "other_failure"),
        count_ceiling=1024,
    )

    assert recovered.recover(reservation_id="v1.reservation", now=NOW) == receipt
    assert host.calls == [
        ("pending", "v1.reservation"),
        ("compensate", "v1.reservation"),
    ]
    assert (
        store.active_records(kind="sealed_artifact_output_set", owner="host", now=NOW)
        == ()
    )
    state = (tmp_path / "state" / "records.json").read_text(encoding="utf-8")
    assert '"status":"aborted"' in state
