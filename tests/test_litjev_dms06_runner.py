"""Fake-only checks for the manually gated LitJev DMS-06 evaluator."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "manual"))

from run_litjev_dms06 import (  # noqa: E402
    EXPECTED_ARTIFACTS,
    EXPECTED_SOURCE,
    INPUTS_SHA256,
    ManualRunError,
    RUNTIME_PACKAGES,
    build_request,
    score_input_rows,
)


def test_litjev_request_keeps_gold_labels_out() -> None:
    row = {
        "id": "D001",
        "kind": "decision",
        "state": {"days_elapsed": 2},
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

    assert request["questions"]["period-check"] == {
        "text": "Is this within the permitted period?",
        "options": {"over": "Outside", "within": "Within"},
    }
    assert "expected_option_id" not in str(request)


def test_litjev_scoring_returns_redacted_probability_decisions() -> None:
    row = {
        "id": "R001",
        "kind": "retention",
        "task_context": "Finish the task.",
        "eligible_messages_oldest_first": [
            {"id": "R001-M1", "content": "Keep this secret."},
            {"id": "R001-M2", "content": "Drop this secret."},
        ],
    }

    class Engine:
        def evaluate(self, state, schema):
            assert "secret" in state
            question_id = schema.names[0]
            choice = "keep" if question_id.endswith("1") else "drop"
            return SimpleNamespace(result=SimpleNamespace(answers={
                question_id: SimpleNamespace(
                    choice=choice,
                    probabilities={"keep": 0.8 if choice == "keep" else 0.2,
                                   "drop": 0.2 if choice == "keep" else 0.8},
                )
            }))

    class Tokenizer:
        def encode(self, content, add_special_tokens=False):
            assert add_special_tokens is False
            return content.split()

    predictions, token_counts, latencies, oom = score_input_rows(
        [row],
        engine=Engine(),
        choice_factory=lambda **kwargs: kwargs,
        schema_factory=lambda questions: SimpleNamespace(
            names=tuple(questions), questions=questions
        ),
        tokenizer=Tokenizer(),
    )

    assert predictions == [{
        "id": "R001",
        "kind": "retention",
        "status": "ok",
        "score_semantics": "probability",
        "scores": {"R001-M1": 0.8, "R001-M2": 0.2},
    }]
    assert token_counts == [
        {"message_id": "R001-M1", "token_count": 3},
        {"message_id": "R001-M2", "token_count": 3},
    ]
    assert "secret" not in str(predictions + token_counts)
    assert len(latencies) == 2
    assert not oom


def test_litjev_preflight_refuses_unapproved_candidate(tmp_path: Path) -> None:
    import run_litjev_dms06

    receipt = {
        "run_allowed": False,
        "candidate_run_approved": False,
        "fixture_criteria_approved": True,
        "input_sha256": INPUTS_SHA256,
        "source": EXPECTED_SOURCE,
        "artifacts": EXPECTED_ARTIFACTS,
        "runtime": {
            "python_version": sys.version.split()[0],
            "packages": RUNTIME_PACKAGES,
        },
    }

    with pytest.raises(ManualRunError, match="candidate-specific approval"):
        run_litjev_dms06.verify_preflight(
            receipt, source_checkout=tmp_path, runtime_checkout=tmp_path
        )
