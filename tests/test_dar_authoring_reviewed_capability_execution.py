"""Tests for approval-gated sealed reviewed-capability dispatch."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.action_ledger import WorkflowActionLedger
from dynamic_agent_runner.workflow_host.approvals import WorkflowApprovalStore
from dynamic_agent_runner.workflow_host.authorized_tools import LocalApprovalDecision
from dynamic_agent_runner.workflow_host.capabilities import (
    ReviewedCapabilityTemplate,
    ReviewedCapabilityTemplateOutput,
    reviewed_capability_manifest_schema_digest,
    reviewed_capability_template_digest,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_execution import (
    ReviewedCapabilityDispatchError,
    ReviewedCapabilityDispatchRequest,
    ReviewedCapabilityExecutor,
    ReviewedCapabilityHostResult,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_host_extension import (
    ReviewedCapabilityHostExtension,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_outputs import (
    ReviewedCapabilityCandidateOutput,
    ReviewedCapabilityHostContribution,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactOutputHandleService,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_jobs import (
    SealedReviewedCapabilityJob,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (
    ReviewedCapabilityTemplateControlPlane,
)


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


class _FakeExtensionHost(_FakeJobResolver, _FakeHost):
    def __init__(self, job: SealedReviewedCapabilityJob) -> None:
        _FakeJobResolver.__init__(self, job)
        _FakeHost.__init__(self)
        self.visibility_failure = False

    def begin_pending_publication(self, **_kwargs: object) -> None:
        return None

    def query_current_outcome(self, **_kwargs: object) -> str:
        return "pending"

    def acknowledge_visibility(self, **_kwargs: object) -> None:
        if self.visibility_failure:
            raise RuntimeError("visibility unavailable")
        return None

    def compensate(self, **_kwargs: object) -> None:
        return None

    def assert_generation_current(self, **_kwargs: object) -> bool:
        return True

    def unpublish_generation_atomically(self, **_kwargs: object) -> None:
        return None

    def dispatch(
        self, *, job: SealedReviewedCapabilityJob, reservation_id: str
    ) -> ReviewedCapabilityHostResult:
        _FakeHost.dispatch(self, job=job, reservation_id=reservation_id)
        return _host_result()


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
        template_digest=_template().template_digest,
        extension_binding="host-vector-index-v1",
        dependency_capability_id="embedding.execute.v1",
        dependency_binding_digest="c" * 64,
        member_binding_digest="d" * 64,
    )


def _template(
    *,
    extension_binding: str = "host-vector-index-v1",
    canonical_manifest_schema: dict[str, object] | None = None,
) -> ReviewedCapabilityTemplate:
    outputs = (
        ReviewedCapabilityTemplateOutput(
            "index_generation", "application/octet-stream", 1024, 60
        ),
        ReviewedCapabilityTemplateOutput(
            "index_manifest", "application/json", 1024, 60
        ),
        ReviewedCapabilityTemplateOutput(
            "coverage_report", "application/json", 1024, 60
        ),
    )
    manifest_schema = canonical_manifest_schema or {
        "additionalProperties": False,
        "properties": {"index_digest": {"type": "string"}},
        "type": "object",
    }
    values = {
        "capability_id": "vector_index.build.v1",
        "contract_version": "1",
        "input_fields": ("job_handle",),
        "required_dependency": "embedding.execute.v1",
        "outputs": outputs,
        "max_receipt_bytes": 1024,
        "approval_class": "human_write",
        "extension_binding": extension_binding,
        "recovery_operations": (
            "acknowledge_visibility",
            "begin_pending_publication",
            "compensate",
            "query_current_outcome",
        ),
        "success_receipt_schema_digest": "d" * 64,
        "canonical_manifest_schema": manifest_schema,
        "generation_id_max_bytes": 128,
        "artifact_handle_max_bytes": 128,
        "count_ceiling": 1024,
        "failure_classifications": ("host_failure",),
        "enabled": True,
    }
    values["canonical_manifest_schema_digest"] = (
        reviewed_capability_manifest_schema_digest(values["canonical_manifest_schema"])
    )
    return ReviewedCapabilityTemplate(
        template_digest=reviewed_capability_template_digest(**values), **values
    )


def _executor(
    tmp_path: Path,
    resolver: _FakeJobResolver,
    host: _FakeHost,
    template_provider=None,
):
    store = PrivateStateStore(tmp_path / "state")
    template = _template()
    templates = ReviewedCapabilityTemplateControlPlane(
        store=store, owner="local-os-user-v1:501:ada"
    )
    templates.create(template=template)
    return ReviewedCapabilityExecutor(
        resolver=resolver,
        host=host,
        ledger=WorkflowActionLedger(store=store, owner="local-os-user-v1:501:ada"),
        approvals=WorkflowApprovalStore(store=store, owner="local-os-user-v1:501:ada"),
        approval_broker=_FakeApprovalBroker(),
        reviewed_templates=templates,
        current_reviewed_template_provider=(
            (lambda capability_id: template)
            if template_provider is None
            else template_provider
        ),
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
        template_digest=_template().template_digest,
    )


def _host_result() -> ReviewedCapabilityHostResult:
    counts = {
        "source_records": 1,
        "embedding_units": 1,
        "indexed": 1,
        "skipped": 0,
        "deleted": 0,
        "errored": 0,
    }
    return ReviewedCapabilityHostResult(
        candidates=(
            ReviewedCapabilityCandidateOutput(
                "index_generation", "application/octet-stream", b"index"
            ),
            ReviewedCapabilityCandidateOutput(
                "index_manifest", "application/json", b'{"index_digest":"a"}'
            ),
            ReviewedCapabilityCandidateOutput(
                "coverage_report", "application/json", b'{"indexed":1}'
            ),
        ),
        contribution=ReviewedCapabilityHostContribution("generation-1", counts),
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


def test_host_extension_composes_the_existing_approval_executor(
    tmp_path: Path,
) -> None:
    host = _FakeExtensionHost(_job())
    store = PrivateStateStore(tmp_path / "state")
    template = _template()
    templates = ReviewedCapabilityTemplateControlPlane(
        store=store, owner="local-os-user-v1:501:ada"
    )
    templates.create(template=template)
    extension = ReviewedCapabilityHostExtension(
        template=template,
        host=host,
        dependency_binding_digest="c" * 64,
        nonce_factory=lambda: "v1.approval.nonce",
    )

    dispatched = extension.executor(
        ledger=WorkflowActionLedger(store=store, owner="local-os-user-v1:501:ada"),
        approvals=WorkflowApprovalStore(store=store, owner="local-os-user-v1:501:ada"),
        approval_broker=_FakeApprovalBroker(),
        reviewed_templates=templates,
        artifacts=SealedArtifactOutputHandleService(
            store=store, owner="local-os-user-v1:501:ada"
        ),
        store=store,
        owner="local-os-user-v1:501:ada",
    ).dispatch(_request(), now=NOW)

    assert dispatched | {"artifacts": {}} == {
        "status": "published",
        "generation_id": "generation-1",
        "published_at": "2026-09-15T00:00:00Z",
        "artifacts": {},
        "counts": {
            "source_records": 1,
            "embedding_units": 1,
            "indexed": 1,
            "skipped": 0,
            "deleted": 0,
            "errored": 0,
        },
    }
    assert set(dispatched["artifacts"]) == {
        "index_generation",
        "index_manifest",
        "coverage_report",
    }
    assert all(
        isinstance(value, str) and value for value in dispatched["artifacts"].values()
    )
    assert len(host.calls) == 1


def test_host_extension_recovers_a_pending_publication_without_rebuilding(
    tmp_path: Path,
) -> None:
    host = _FakeExtensionHost(_job())
    host.visibility_failure = True
    store = PrivateStateStore(tmp_path / "state")
    template = _template()
    templates = ReviewedCapabilityTemplateControlPlane(
        store=store, owner="local-os-user-v1:501:ada"
    )
    templates.create(template=template)
    extension = ReviewedCapabilityHostExtension(
        template=template,
        host=host,
        dependency_binding_digest="c" * 64,
        nonce_factory=lambda: "v1.approval.nonce",
    )
    executor = extension.executor(
        ledger=WorkflowActionLedger(store=store, owner="local-os-user-v1:501:ada"),
        approvals=WorkflowApprovalStore(store=store, owner="local-os-user-v1:501:ada"),
        approval_broker=_FakeApprovalBroker(),
        reviewed_templates=templates,
        artifacts=SealedArtifactOutputHandleService(
            store=store, owner="local-os-user-v1:501:ada"
        ),
        store=store,
        owner="local-os-user-v1:501:ada",
    )

    with pytest.raises(ReviewedCapabilityDispatchError, match="unavailable"):
        executor.dispatch(_request(), now=NOW)
    host.visibility_failure = False
    recovered = executor.dispatch(_request(), now=NOW)

    assert recovered["status"] == "published"
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


def test_executor_aborts_when_the_registered_template_changes_before_dispatch(
    tmp_path: Path,
) -> None:
    resolver = _FakeJobResolver(_job())
    host = _FakeHost()
    calls = 0

    def current_template(capability_id: str) -> ReviewedCapabilityTemplate:
        nonlocal calls
        assert capability_id == "vector_index.build.v1"
        calls += 1
        return _template() if calls == 1 else _template(extension_binding="changed")

    executor = _executor(tmp_path, resolver, host, current_template)

    with pytest.raises(ReviewedCapabilityDispatchError, match="unavailable"):
        executor.dispatch(_request(), now=NOW)

    assert host.calls == []


def test_executor_aborts_when_manifest_schema_changes_before_dispatch(
    tmp_path: Path,
) -> None:
    resolver = _FakeJobResolver(_job())
    host = _FakeHost()
    calls = 0

    def current_template(capability_id: str) -> ReviewedCapabilityTemplate:
        nonlocal calls
        assert capability_id == "vector_index.build.v1"
        calls += 1
        return (
            _template()
            if calls == 1
            else _template(
                canonical_manifest_schema={
                    "additionalProperties": False,
                    "properties": {
                        "index_digest": {"type": "string"},
                        "source_records": {"type": "integer"},
                    },
                    "type": "object",
                }
            )
        )

    executor = _executor(tmp_path, resolver, host, current_template)

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
