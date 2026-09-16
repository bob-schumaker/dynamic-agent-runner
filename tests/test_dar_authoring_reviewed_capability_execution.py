"""Tests for approval-gated sealed reviewed-capability dispatch."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.action_ledger import WorkflowActionLedger
from dynamic_agent_runner.workflow_host.approvals import WorkflowApprovalStore
from dynamic_agent_runner.workflow_host.authorized_tools import LocalApprovalDecision
from dynamic_agent_runner.workflow_host.reviewed_capability_execution import (
    ReviewedCapabilityDispatchError,
    ReviewedCapabilityDispatchRequest,
    ReviewedCapabilityExecutor,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_jobs import (
    SealedReviewedCapabilityJob,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


NOW = datetime(2026, 9, 15, tzinfo=UTC)


class _FakeJobResolver:
    def __init__(self, job: SealedReviewedCapabilityJob) -> None:
        self.job = job
        self.revalidated = job

    def resolve(self, *, job_handle: str, principal: str, now: datetime):
        del job_handle, principal, now
        return self.job

    def revalidate(self, *, job: SealedReviewedCapabilityJob, now: datetime):
        del job, now
        return self.revalidated


class _FakeApprovalBroker:
    def __init__(self) -> None:
        self.digests: list[str] = []

    def decide(self, *, approval, reservation_digest: str):
        del approval
        self.digests.append(reservation_digest)
        return LocalApprovalDecision.APPROVED


class _FakeHost:
    def __init__(self) -> None:
        self.calls: list[tuple[SealedReviewedCapabilityJob, str]] = []
        self.failure: Exception | None = None

    def dispatch(
        self, *, job: SealedReviewedCapabilityJob, reservation_id: str
    ) -> None:
        self.calls.append((job, reservation_id))
        if self.failure is not None:
            raise self.failure


def _job() -> SealedReviewedCapabilityJob:
    return SealedReviewedCapabilityJob(
        job_handle="sealed:vector-index-job:job-1",
        issuer_id="host-local",
        opaque_id="job-1",
        revision="1",
        digest="a" * 64,
        principal="local-os-user-v1:501:ada",
        expires_at=NOW + timedelta(minutes=5),
        template_capability_id="vector_index.build.v1",
        template_contract_version="1",
        template_digest="b" * 64,
        extension_binding="host-vector-index-v1",
        dependency_capability_id="embedding.execute.v1",
        dependency_binding_digest="c" * 64,
        member_binding_digest="d" * 64,
    )


def _executor(tmp_path: Path, resolver: _FakeJobResolver, host: _FakeHost):
    store = PrivateStateStore(tmp_path / "state")
    return ReviewedCapabilityExecutor(
        resolver=resolver,
        host=host,
        ledger=WorkflowActionLedger(store=store, owner="local-os-user-v1:501:ada"),
        approvals=WorkflowApprovalStore(store=store, owner="local-os-user-v1:501:ada"),
        approval_broker=_FakeApprovalBroker(),
        extension_binding="host-vector-index-v1",
        dependency_binding_digest="c" * 64,
        nonce_factory=lambda: "v1.approval.nonce",
    )


def _request() -> ReviewedCapabilityDispatchRequest:
    return ReviewedCapabilityDispatchRequest(
        run_id="run-1",
        package_registration_digest="e" * 64,
        package_revision_digest="f" * 64,
        declared_call_site_id="build_vector_index",
        principal="local-os-user-v1:501:ada",
        arguments={"job_handle": "sealed:vector-index-job:job-1"},
        template_capability_id="vector_index.build.v1",
        template_contract_version="1",
        template_digest="b" * 64,
    )


def test_executor_approves_revalidates_and_dispatches_one_sealed_job_once(
    tmp_path: Path,
) -> None:
    resolver = _FakeJobResolver(_job())
    host = _FakeHost()
    executor = _executor(tmp_path, resolver, host)

    dispatched = executor.dispatch(_request(), now=NOW)
    replayed = executor.dispatch(_request(), now=NOW)

    assert dispatched.status == "dispatched"
    assert replayed.status == "replayed"
    assert len(host.calls) == 1


def test_executor_aborts_without_dispatch_when_revalidation_changes_job(
    tmp_path: Path,
) -> None:
    resolver = _FakeJobResolver(_job())
    resolver.revalidated = replace(_job(), dependency_binding_digest="d" * 64)
    host = _FakeHost()
    executor = _executor(tmp_path, resolver, host)

    with pytest.raises(ReviewedCapabilityDispatchError, match="unavailable"):
        executor.dispatch(_request(), now=NOW)

    assert host.calls == []


def test_executor_aborts_a_failed_host_attempt_and_does_not_redispatch_it(
    tmp_path: Path,
) -> None:
    resolver = _FakeJobResolver(_job())
    host = _FakeHost()
    host.failure = RuntimeError("host failure")
    executor = _executor(tmp_path, resolver, host)

    with pytest.raises(ReviewedCapabilityDispatchError, match="unavailable"):
        executor.dispatch(_request(), now=NOW)
    replayed = executor.dispatch(_request(), now=NOW)

    assert replayed.status == "replayed"
    assert len(host.calls) == 1
    state = (tmp_path / "state" / "records.json").read_text(encoding="utf-8")
    assert '"state":"revoked"' in state
