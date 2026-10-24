"""Fake-backed checks for the pinned mlx-decision DMS-20 adapter."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "manual"))

from run_dms20_mlx_decision import (  # noqa: E402
    _choice_question,
    _map_choice_answer,
    run_rows,
)


def test_choice_question_preserves_ids_descriptions_and_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeChoice:
        def __init__(self, **values: object) -> None:
            self.values = values

    class FakeMlxDecision:
        Choice = FakeChoice

    monkeypatch.setitem(sys.modules, "mlx_decision", FakeMlxDecision)
    question = {
        "text": "Choose one.",
        "options": [
            {"id": "b", "label": "Beta"},
            {"id": "a", "label": "Alpha"},
        ],
    }

    result = _choice_question(question)

    assert isinstance(result, FakeChoice)
    assert result.values == {
        "instructions": "Choose one.",
        "criteria": {"b": "Beta", "a": "Alpha"},
    }


def test_answer_requires_exact_finite_probability_distribution() -> None:
    answer = {"choice": "a", "probabilities": {"a": 0.75, "b": 0.25}}

    assert _map_choice_answer(answer, ["a", "b"]) == {
        "choice": "a",
        "scores": {"a": 0.75, "b": 0.25},
    }
    with pytest.raises(ValueError, match="probabilities"):
        _map_choice_answer({"a": 0.5, "b": 0.4}, ["a", "b"])


def test_runner_marks_truncated_results_as_oversize_without_using_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeChoice:
        def __init__(self, **values: object) -> None:
            self.values = values

    class FakeMlxDecision:
        Choice = FakeChoice

    monkeypatch.setitem(sys.modules, "mlx_decision", FakeMlxDecision)

    class FakeAnswer:
        choice = "a"
        probabilities = {"a": 1.0, "b": 0.0}

    class FakeResult:
        answers = {"decision": FakeAnswer()}
        truncated = True

    class FakeModel:
        def decide(self, state: object, questions: object) -> FakeResult:
            return FakeResult()

    predictions = run_rows(
        [
            {
                "id": "sample",
                "kind": "decision",
                "state": {"text": "private state"},
                "question": {
                    "text": "Choose.",
                    "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                },
            }
        ],
        FakeModel(),
    )

    assert len(predictions) == 2
    assert all(item["status"] == "oversize" for item in predictions)
    assert all("choice" not in item for item in predictions)
