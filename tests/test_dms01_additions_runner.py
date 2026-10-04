"""Fake-only checks for the added DMS-01 candidate runners."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "manual"))

import run_dms01_additions as runner  # noqa: E402
from run_dms01_additions import Candidate, build_questions, prediction_from_answers  # noqa: E402


def test_decision_question_uses_only_candidate_input() -> None:
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

    state, questions = build_questions(row)

    assert state == {"elapsed": 3}
    assert list(questions) == ["period"]
    assert questions["period"]["options"] == {"yes": "Yes", "no": "No"}
    assert "expected_option_id" not in str((state, questions))


def test_retention_questions_bind_each_message_to_keep_drop() -> None:
    row = {
        "id": "R001",
        "kind": "retention",
        "task_context": "Complete the task.",
        "eligible_messages_oldest_first": [
            {"id": "R001-M1", "content": "Keep me."},
            {"id": "R001-M2", "content": "Maybe."},
        ],
    }

    state, questions = build_questions(row)

    assert state == "Complete the task."
    assert list(questions) == ["R001-M1", "R001-M2"]
    assert "Keep me." in questions["R001-M1"]["text"]
    assert questions["R001-M1"]["options"] == {
        "keep": "Retain this message in active context.",
        "drop": "The active context can omit this message.",
    }
    assert "expected_retention" not in str((state, questions))


def test_prediction_maps_probabilities_without_reordering_ids() -> None:
    row = {
        "id": "D001",
        "kind": "decision",
        "state": "state",
        "question": {
            "id": "period",
            "text": "Within the limit?",
            "options": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}],
        },
    }

    prediction = prediction_from_answers(
        row,
        {"period": {"choice": "yes", "probabilities": {"yes": 0.8, "no": 0.2}}},
    )

    assert prediction == {
        "id": "D001",
        "kind": "decision",
        "status": "ok",
        "choice": "yes",
        "score_semantics": "probability",
        "scores": {"yes": 0.8, "no": 0.2},
    }


def test_prediction_rejects_missing_probability_options() -> None:
    row = {
        "id": "D001",
        "kind": "decision",
        "state": "state",
        "question": {
            "id": "period",
            "text": "Within the limit?",
            "options": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}],
        },
    }

    try:
        prediction_from_answers(
            row, {"period": {"choice": "yes", "probabilities": {"yes": 1.0}}}
        )
    except ValueError as exc:
        assert "probability" in str(exc)
    else:
        raise AssertionError("incomplete probability distribution was accepted")


def test_jevstyle_adapter_uses_upstream_question_and_answer_contract() -> None:
    class Engine:
        def decide(self, state, question, options=None):
            assert state == "state"
            assert question == {"t": "choice", "ins": "Choose", "crit": {"a": "A", "b": "B"}}
            assert options is None
            return {"answer": "b", "probabilities": {"a": 0.1, "b": 0.9}}

    candidate = Candidate.__new__(Candidate)
    candidate.engine = Engine()

    answer = candidate._infer_jevstyle("state", {"text": "Choose", "options": {"a": "A", "b": "B"}})

    assert answer == {"choice": "b", "probabilities": {"a": 0.1, "b": 0.9}}


def test_gguf_rss_includes_scorer_child(monkeypatch) -> None:
    values = {runner.resource.RUSAGE_SELF: 100, runner.resource.RUSAGE_CHILDREN: 250}
    monkeypatch.setattr(runner.resource, "getrusage", lambda who: type("Usage", (), {"ru_maxrss": values[who]})())
    monkeypatch.setattr(runner.sys, "platform", "darwin")

    assert runner._rss_peak_bytes(include_child=True) == 350
