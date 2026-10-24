"""Fake-backed tests for the gated DMS-20 MLX extension runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "manual"))

from run_dms20_mlx_extension import (  # noqa: E402
    _choice_request,
    _map_choice_answer,
    _prediction_jsonl,
)


def test_choice_request_preserves_option_ids_order_and_descriptions() -> None:
    question = {
        "text": "Choose one.",
        "options": [
            {"id": "second", "label": "Second choice"},
            {"id": "first", "label": "First choice"},
        ],
    }

    request = _choice_request("state text", question)

    assert request["state"] == "state text"
    assert request["questions"]["decision"] == {
        "type": "choice",
        "instructions": "Choose one.",
        "criteria": {"second": "Second choice", "first": "First choice"},
    }


def test_choice_answer_requires_exact_option_probabilities() -> None:
    answer = {
        "choice": "first",
        "probabilities": {"first": 0.8, "second": 0.2},
    }

    result = _map_choice_answer(answer, ["first", "second"])

    assert result == {"choice": "first", "scores": {"first": 0.8, "second": 0.2}}

    with pytest.raises(ValueError, match="option IDs"):
        _map_choice_answer(
            {"choice": "first", "probabilities": {"first": 1.0, "unexpected": 0.0}},
            ["first", "second"],
        )


def test_choice_answer_uses_highest_probability_when_backend_returns_distribution_only() -> (
    None
):
    answer = {"probabilities": {"first": 0.8, "second": 0.2}}

    result = _map_choice_answer(answer, ["first", "second"])

    assert result == {"choice": "first", "scores": {"first": 0.8, "second": 0.2}}


def test_choice_answer_accepts_optiq_probability_map() -> None:
    answer = {"second": 0.2, "first": 0.8}

    result = _map_choice_answer(answer, ["first", "second"])

    assert result == {"choice": "first", "scores": {"first": 0.8, "second": 0.2}}


def test_choice_answer_preserves_a_backend_selected_top_probability_tie() -> None:
    answer = {
        "choice": "second",
        "probabilities": {"first": 0.5, "second": 0.5},
    }

    result = _map_choice_answer(answer, ["first", "second"])

    assert result == {"choice": "second", "scores": {"second": 0.5, "first": 0.5}}


def test_prediction_serialization_preserves_probability_option_order() -> None:
    prediction = {
        "id": "item",
        "option_order": "canonical",
        "status": "ok",
        "choice": "second",
        "score_semantics": "probability",
        "scores": {"second": 0.5, "first": 0.5},
    }

    serialized = _prediction_jsonl([prediction])

    assert list(json.loads(serialized)["scores"]) == ["second", "first"]
