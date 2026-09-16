"""Contract tests for atomic sealed-artifact output publication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactHandleError,
    SealedArtifactLimits,
    SealedArtifactOutput,
    SealedArtifactOutputHandleService,
    SealedArtifactRunnerDescriptor,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


NOW = datetime(2026, 9, 10, tzinfo=UTC)


class _CountingStore(PrivateStateStore):
    def __init__(self, root) -> None:
        super().__init__(root)
        self.issue_calls = 0

    def issue(self, **kwargs):  # type: ignore[no-untyped-def]
        self.issue_calls += 1
        return super().issue(**kwargs)


def _descriptor() -> SealedArtifactRunnerDescriptor:
    return SealedArtifactRunnerDescriptor(
        digest="a" * 64,
        asset_path="assets/runner.py",
        asset_digest="b" * 64,
        capability_requirements_digest="c" * 64,
        profile_digest="d" * 64,
        inputs=(),
        outputs=(
            SealedArtifactOutput("coverage", "text/plain", 10, None),
            SealedArtifactOutput("result", "application/octet-stream", 10, None),
        ),
        limits=SealedArtifactLimits(1, 1, 100, 1, 1),
        schema_assets=(),
        child_contract_digests=(),
        callbacks=(),
        output_roles=("coverage", "result"),
    )


def _service(tmp_path):
    store = _CountingStore(tmp_path / "state")
    return SealedArtifactOutputHandleService(store=store, owner="test-owner"), store


def test_output_publication_issues_one_atomic_set_handle(tmp_path) -> None:
    service, store = _service(tmp_path)

    handles = service.publish(
        descriptor=_descriptor(),
        receiver_id="receiver",
        revision_digest="e" * 64,
        invocation_id="invocation",
        sealed=(
            ("coverage", "text/plain", b"ready"),
            ("result", "application/octet-stream", b"output"),
        ),
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )

    assert store.issue_calls == 1
    assert [handle.role for handle in handles] == ["coverage", "result"]
    assert len({handle.output_set_id for handle in handles}) == 1
    assert all("ready" not in repr(handle) for handle in handles)


def test_invalid_output_set_publishes_nothing(tmp_path) -> None:
    service, store = _service(tmp_path)

    with pytest.raises(SealedArtifactHandleError, match="invalid"):
        service.publish(
            descriptor=_descriptor(),
            receiver_id="receiver",
            revision_digest="e" * 64,
            invocation_id="invocation",
            sealed=(("coverage", "text/plain", b"ready"),),
            expires_at=NOW + timedelta(minutes=1),
            now=NOW,
        )

    assert store.issue_calls == 0


def test_private_output_set_has_no_handles_until_atomic_promotion(tmp_path) -> None:
    service, store = _service(tmp_path)

    private = service.stage(
        descriptor=_descriptor(),
        receiver_id="receiver",
        revision_digest="e" * 64,
        invocation_id="invocation",
        sealed=(
            ("coverage", "text/plain", b"ready"),
            ("result", "application/octet-stream", b"output"),
        ),
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )

    assert store.issue_calls == 1
    assert "ready" not in repr(private)
    handles = service.promote(private, now=NOW)

    assert [handle.role for handle in handles] == ["coverage", "result"]
    assert len({handle.output_set_id for handle in handles}) == 1


def test_private_output_promotion_replays_its_existing_output_set(tmp_path) -> None:
    service, _ = _service(tmp_path)
    private = service.stage(
        descriptor=_descriptor(),
        receiver_id="receiver",
        revision_digest="e" * 64,
        invocation_id="invocation",
        sealed=(
            ("coverage", "text/plain", b"ready"),
            ("result", "application/octet-stream", b"output"),
        ),
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )

    first = service.promote(private, now=NOW)
    replayed = service.promote(private, now=NOW)

    assert replayed == first


def test_declared_outputs_stage_privately_without_a_runner_descriptor(tmp_path) -> None:
    service, store = _service(tmp_path)

    private = service.stage_declared(
        declaration_digest="f" * 64,
        outputs=(
            SealedArtifactOutput("coverage", "text/plain", 10, None),
            SealedArtifactOutput("result", "application/octet-stream", 10, None),
        ),
        receiver_id="receiver",
        revision_digest="e" * 64,
        invocation_id="invocation",
        sealed=(
            ("coverage", "text/plain", b"ready"),
            ("result", "application/octet-stream", b"output"),
        ),
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )

    assert store.issue_calls == 1
    assert "ready" not in repr(private)
    handles = service.promote(private, now=NOW)

    assert [handle.role for handle in handles] == ["coverage", "result"]
    assert len({handle.output_set_id for handle in handles}) == 1
