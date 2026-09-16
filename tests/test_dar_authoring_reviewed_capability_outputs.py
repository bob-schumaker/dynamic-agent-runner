"""Tests for private reviewed-capability candidate output validation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from dynamic_agent_runner.workflow_host.capabilities import (
    ReviewedCapabilityTemplateOutput,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_outputs import (
    ReviewedCapabilityCandidateOutput,
    ReviewedCapabilityCandidateOutputError,
    ReviewedCapabilityHostContribution,
    stage_reviewed_capability_candidates,
    validate_reviewed_capability_candidates,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactOutputHandleService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


NOW = datetime(2026, 9, 15, tzinfo=UTC)


def _outputs() -> tuple[ReviewedCapabilityTemplateOutput, ...]:
    return (
        ReviewedCapabilityTemplateOutput(
            "index_generation", "application/octet-stream", 16, 60
        ),
        ReviewedCapabilityTemplateOutput("index_manifest", "application/json", 128, 60),
        ReviewedCapabilityTemplateOutput(
            "coverage_report", "application/json", 128, 60
        ),
    )


def _candidates() -> tuple[ReviewedCapabilityCandidateOutput, ...]:
    return (
        ReviewedCapabilityCandidateOutput(
            "index_generation", "application/octet-stream", b"index"
        ),
        ReviewedCapabilityCandidateOutput(
            "index_manifest",
            "application/json",
            json.dumps({"digests": {"snapshot": "a" * 64}, "counts": {}}).encode(),
        ),
        ReviewedCapabilityCandidateOutput(
            "coverage_report",
            "application/json",
            json.dumps({"source_records": 1, "indexed": 1}).encode(),
        ),
    )


def _contribution() -> ReviewedCapabilityHostContribution:
    return ReviewedCapabilityHostContribution(
        generation_id="generation-1",
        counts={
            "source_records": 1,
            "embedding_units": 1,
            "indexed": 1,
            "skipped": 0,
            "deleted": 0,
            "errored": 0,
        },
    )


def test_candidate_validation_accepts_the_exact_private_output_triple() -> None:
    accepted = validate_reviewed_capability_candidates(
        outputs=_outputs(),
        candidates=_candidates(),
        contribution=_contribution(),
        count_ceiling=8,
    )

    assert accepted == _candidates()


def test_validated_reviewed_candidates_stage_as_a_private_output_set(tmp_path) -> None:
    store = PrivateStateStore(tmp_path / "state")
    artifacts = SealedArtifactOutputHandleService(store=store, owner="host")

    staged = stage_reviewed_capability_candidates(
        artifacts=artifacts,
        template_digest="a" * 64,
        outputs=_outputs(),
        candidates=_candidates(),
        contribution=_contribution(),
        count_ceiling=8,
        receiver_id="principal",
        revision_digest="b" * 64,
        invocation_id="run",
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )

    assert staged.contribution == _contribution()
    assert "index" not in repr(staged.private)
    handles = artifacts.promote(staged.private, now=NOW)
    assert [handle.role for handle in handles] == [
        "index_generation",
        "index_manifest",
        "coverage_report",
    ]


def test_candidate_staging_rejects_a_caller_selected_expiry_beyond_the_template(
    tmp_path,
) -> None:
    store = PrivateStateStore(tmp_path / "state")
    artifacts = SealedArtifactOutputHandleService(store=store, owner="host")

    with pytest.raises(ReviewedCapabilityCandidateOutputError, match="candidate"):
        stage_reviewed_capability_candidates(
            artifacts=artifacts,
            template_digest="a" * 64,
            outputs=_outputs(),
            candidates=_candidates(),
            contribution=_contribution(),
            count_ceiling=8,
            receiver_id="principal",
            revision_digest="b" * 64,
            invocation_id="run",
            expires_at=NOW + timedelta(seconds=61),
            now=NOW,
        )

    assert (
        store.active_records(
            kind="sealed_artifact_private_output_set", owner="host", now=NOW
        )
        == ()
    )


def test_unsafe_reviewed_candidates_create_no_private_output_set(tmp_path) -> None:
    store = PrivateStateStore(tmp_path / "state")
    artifacts = SealedArtifactOutputHandleService(store=store, owner="host")
    unsafe = (
        _candidates()[0],
        ReviewedCapabilityCandidateOutput(
            "index_manifest", "application/json", b'{"source_path":"secret"}'
        ),
        _candidates()[2],
    )

    with pytest.raises(ReviewedCapabilityCandidateOutputError, match="candidate"):
        stage_reviewed_capability_candidates(
            artifacts=artifacts,
            template_digest="a" * 64,
            outputs=_outputs(),
            candidates=unsafe,
            contribution=_contribution(),
            count_ceiling=8,
            receiver_id="principal",
            revision_digest="b" * 64,
            invocation_id="run",
            expires_at=NOW + timedelta(minutes=1),
            now=NOW,
        )

    assert (
        store.active_records(
            kind="sealed_artifact_private_output_set", owner="host", now=NOW
        )
        == ()
    )


@pytest.mark.parametrize(
    "candidates",
    (
        lambda: _candidates()[:-1],
        lambda: (
            ReviewedCapabilityCandidateOutput(
                "index_generation", "text/plain", b"index"
            ),
            *_candidates()[1:],
        ),
        lambda: (
            _candidates()[0],
            ReviewedCapabilityCandidateOutput(
                "index_manifest", "application/json", b'{"source_path":"secret"}'
            ),
            _candidates()[2],
        ),
    ),
)
def test_candidate_validation_rejects_before_any_publication(candidates) -> None:
    with pytest.raises(ReviewedCapabilityCandidateOutputError, match="candidate"):
        validate_reviewed_capability_candidates(
            outputs=_outputs(),
            candidates=candidates(),
            contribution=_contribution(),
            count_ceiling=8,
        )
