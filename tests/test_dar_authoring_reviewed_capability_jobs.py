"""Tests for sealed reviewed-capability job transport."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from dynamic_agent_runner.workflow_host.reviewed_capability_jobs import (
    ReviewedCapabilityJobError,
    SealedReviewedCapabilityJob,
    resolve_sealed_reviewed_capability_job,
)


NOW = datetime(2026, 9, 15, tzinfo=UTC)


class _FakeJobResolver:
    def __init__(self, job: SealedReviewedCapabilityJob) -> None:
        self.job = job
        self.resolved: list[tuple[str, str]] = []

    def resolve(self, *, job_handle: str, principal: str, now: datetime):
        del now
        self.resolved.append((job_handle, principal))
        return self.job


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


def test_resolve_sealed_job_accepts_only_canonical_handle_and_exact_bindings() -> None:
    resolver = _FakeJobResolver(_job())

    job = resolve_sealed_reviewed_capability_job(
        arguments={"job_handle": "sealed:vector-index-job:job-1"},
        resolver=resolver,
        principal="local-os-user-v1:501:ada",
        template_capability_id="vector_index.build.v1",
        template_contract_version="1",
        template_digest="b" * 64,
        extension_binding="host-vector-index-v1",
        dependency_binding_digest="c" * 64,
        now=NOW,
    )

    assert job == _job()
    assert resolver.resolved == [
        ("sealed:vector-index-job:job-1", "local-os-user-v1:501:ada")
    ]


@pytest.mark.parametrize(
    "arguments",
    (
        {},
        {"job_handle": "sealed:vector-index-job:job-1", "profile": "other"},
        {"job_handle": "foreign:job-1"},
    ),
)
def test_resolve_sealed_job_rejects_noncanonical_public_input(
    arguments: dict[str, str],
) -> None:
    resolver = _FakeJobResolver(_job())

    with pytest.raises(ReviewedCapabilityJobError, match="job"):
        resolve_sealed_reviewed_capability_job(
            arguments=arguments,
            resolver=resolver,
            principal="local-os-user-v1:501:ada",
            template_capability_id="vector_index.build.v1",
            template_contract_version="1",
            template_digest="b" * 64,
            extension_binding="host-vector-index-v1",
            dependency_binding_digest="c" * 64,
            now=NOW,
        )

    assert resolver.resolved == []


@pytest.mark.parametrize(
    "changed_job",
    (
        lambda job: replace(job, principal="other-principal"),
        lambda job: replace(job, expires_at=NOW),
        lambda job: replace(job, template_digest="e" * 64),
        lambda job: replace(job, extension_binding="host-vector-index-v2"),
        lambda job: replace(job, dependency_binding_digest="f" * 64),
    ),
)
def test_resolve_sealed_job_rejects_foreign_expired_or_changed_bindings(
    changed_job,
) -> None:
    resolver = _FakeJobResolver(changed_job(_job()))

    with pytest.raises(ReviewedCapabilityJobError, match="job"):
        resolve_sealed_reviewed_capability_job(
            arguments={"job_handle": "sealed:vector-index-job:job-1"},
            resolver=resolver,
            principal="local-os-user-v1:501:ada",
            template_capability_id="vector_index.build.v1",
            template_contract_version="1",
            template_digest="b" * 64,
            extension_binding="host-vector-index-v1",
            dependency_binding_digest="c" * 64,
            now=NOW,
        )
