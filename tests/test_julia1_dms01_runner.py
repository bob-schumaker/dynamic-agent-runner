"""Fake-only checks for the Julia 1 DMS-01 runner."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "manual"))

from run_julia1_dms01 import build_request, _predict  # noqa: E402


def test_decision_request_contains_only_candidate_input() -> None:
    row = {
        "id": "D001",
        "kind": "decision",
        "state": {"elapsed": 3},
        "question": {
            "id": "period",
            "text": "Within the limit?",
            "options": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}],
        },
    }

    state, questions = build_request(row)

    assert state == '{"elapsed":3}'
    assert questions["period"]["criteria"] == {"yes": "Yes", "no": "No"}
    assert "expected_option_id" not in state


def test_retention_prediction_uses_julia_keep_probability() -> None:
    row = {
        "id": "R001",
        "kind": "retention",
        "task_context": "Complete the task.",
        "eligible_messages_oldest_first": [
            {"id": "R001-M1", "content": "Keep me."},
            {"id": "R001-M2", "content": "Maybe."},
        ],
    }

    class FakeEngine:
        def predict(self, *, state: str, questions: dict[str, object]) -> dict[str, object]:
            assert "expected_retention" not in state
            assert set(questions) == {"R001-M1", "R001-M2"}
            return {
                "answers": {
                    "R001-M1": {"probabilities": {"keep": 0.8, "drop": 0.2}},
                    "R001-M2": {"probabilities": {"keep": 0.3, "drop": 0.7}},
                }
            }

    prediction, elapsed = _predict(FakeEngine(), row)

    assert elapsed >= 0
    assert prediction["kind"] == "retention"
    assert prediction["score_semantics"] == "probability"
    assert prediction["scores"] == {"R001-M1": 0.8, "R001-M2": 0.3}
