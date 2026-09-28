"""Fake-only checks for the manually gated Kev-0.6B evaluation driver."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "manual"))

from run_kev_dms01 import (  # noqa: E402
    EXPECTED_ARTIFACTS,
    HARNESS_ID,
    HARNESS_REVISION,
    INPUTS_SHA256,
    ManualRunError,
    build_request,
    verify_preflight,
)


def test_decision_request_projects_only_frozen_candidate_input() -> None:
    row = {
        "id": "D001",
        "kind": "decision",
        "state": {"days_elapsed": 2, "permitted_days": 6},
        "question": {
            "id": "period-check",
            "text": "Is this within the permitted period?",
            "options": [
                {"id": "over", "label": "Outside"},
                {"id": "within", "label": "Within"},
            ],
        },
    }

    request = build_request(row)

    assert request == {
        "state": row["state"],
        "questions": {
            "period-check": {
                "type": "choice",
                "instructions": "Is this within the permitted period?",
                "criteria": {"over": "Outside", "within": "Within"},
            }
        },
    }
    assert "labels" not in request
    assert "expected_option_id" not in request


def test_retention_request_contains_stable_candidate_ids_and_no_labels() -> None:
    row = {
        "id": "R001",
        "kind": "retention",
        "task_context": "Prepare the reminder.",
        "eligible_messages_oldest_first": [
            {"id": "R001-M1", "age_rank": 0, "content": "Keep this."},
            {"id": "R001-M2", "age_rank": 1, "content": "Drop this."},
        ],
    }

    request = build_request(row)

    assert set(request["questions"]) == {"R001-M1", "R001-M2"}
    assert request["state"]["candidate_messages"][0]["id"] == "R001-M1"
    assert request["questions"]["R001-M1"]["criteria"] == {
        "keep": "Retain this message in the active context.",
        "drop": "The active context can omit this message.",
    }
    assert "expected_retention" not in request["state"]


def test_preflight_must_be_allowed_and_match_all_pinned_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    receipt = {
        "run_allowed": True,
        "fixture_criteria_approved": True,
        "input_sha256": INPUTS_SHA256,
        "harness": {"id": HARNESS_ID, "revision": HARNESS_REVISION},
        "artifacts": EXPECTED_ARTIFACTS,
        "evaluation_harness_files": [
            {
                "id": str(path.relative_to(root)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in (
                root / "scripts" / "evaluate_decision_models.py",
                root / "tests" / "manual" / "run_kev_dms01.py",
            )
        ],
    }

    verify_preflight(receipt)

    with pytest.raises(ManualRunError, match="preflight did not allow"):
        verify_preflight({**receipt, "run_allowed": False})
    with pytest.raises(ManualRunError, match="artifact revisions differ"):
        verify_preflight({**receipt, "artifacts": []})
