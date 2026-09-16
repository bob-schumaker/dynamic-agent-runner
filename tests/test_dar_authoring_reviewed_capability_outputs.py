"""Tests for private reviewed-capability candidate output validation."""

from __future__ import annotations

import json

import pytest

from dynamic_agent_runner.workflow_host.capabilities import (
    ReviewedCapabilityTemplateOutput,
)
from dynamic_agent_runner.workflow_host.reviewed_capability_outputs import (
    ReviewedCapabilityCandidateOutput,
    ReviewedCapabilityCandidateOutputError,
    ReviewedCapabilityHostContribution,
    validate_reviewed_capability_candidates,
)


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
