from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "manual"))

from run_context_compression_dms13 import ManualRunError, VonTurnScorer, verify_run_approval, get_official_judge_prompt


class _Tokenizer:
    def __init__(self, count: int = 12) -> None:
        self.count = count
        self.inputs: list[str] = []

    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
        assert add_special_tokens is False
        self.inputs.append(text)
        return list(range(self.count))


class _Backend:
    def __init__(self) -> None:
        self.calls = []

    def evaluate_choice(self, question_id, state_text, choice):
        self.calls.append((question_id, state_text, choice))
        return type("Answer", (), {"choice": "keep", "probabilities": {"keep": 0.8, "drop": 0.2}})()


def _choice_factory(*, instructions, criteria):
    return {"instructions": instructions, "criteria": criteria}


def test_von_turn_scorer_uses_only_turn_content_and_returns_keep_drop_margin() -> None:
    backend = _Backend()
    tokenizer = _Tokenizer()
    scorer = VonTurnScorer(
        backend=backend,
        choice_factory=_choice_factory,
        tokenizer=tokenizer,
    )
    turn = [
        {
            "id": "q:0:s:0",
            "role": "user",
            "content": "Remember I prefer tea.",
            "session_id": "s",
            "session_date": "2024/01/01",
        },
        {
            "id": "q:0:s:1",
            "role": "assistant",
            "content": "I will remember.",
            "session_id": "s",
            "session_date": "2024/01/01",
        },
    ]

    margin = scorer(turn)

    assert margin == pytest.approx(0.6)
    assert backend.calls[0][2]["criteria"] == {
        "keep": "Retain this turn in active context.",
        "drop": "The active context can omit this turn.",
    }
    serialized = backend.calls[0][1]
    assert "Remember I prefer tea." in serialized
    assert "SECRET QUESTION" not in serialized
    assert "SECRET ANSWER" not in serialized


def test_von_turn_scorer_rejects_input_over_candidate_limit_before_inference() -> None:
    backend = _Backend()
    scorer = VonTurnScorer(
        backend=backend,
        choice_factory=_choice_factory,
        tokenizer=_Tokenizer(count=8193),
    )

    with pytest.raises(ManualRunError, match="input limit"):
        scorer([{"id": "q:0:s:0", "role": "user", "content": "large"}])

    assert backend.calls == []


def test_official_judge_prompt_uses_pinned_type_and_abstention_rules() -> None:
    prompts = []

    def builder(question_type, question, gold, response, abstention=False):
        prompts.append((question_type, question, gold, response, abstention))
        return f"{question_type}:{abstention}:{question}:{gold}:{response}"

    regular = get_official_judge_prompt(
        builder, "temporal-reasoning", "SECRET QUESTION", "18 days", "19 days", False
    )
    abstention = get_official_judge_prompt(
        builder, "multi-session", "SECRET QUESTION", "unknown", "cannot answer", True
    )

    assert regular == "temporal-reasoning:False:SECRET QUESTION:18 days:19 days"
    assert abstention.endswith(":True:SECRET QUESTION:unknown:cannot answer")
    assert prompts[0][0] == "temporal-reasoning"
    assert prompts[0][4] is False
    assert prompts[1][4] is True


def test_run_approval_must_bind_all_pinned_run_artifacts() -> None:
    expected = {
        "manifest_sha256": "a" * 64,
        "preflight_sha256": "b" * 64,
        "harness_sha256": "c" * 64,
        "runtime_lock_sha256": "d" * 64,
        "scorer_model": "gpt-4o-2024-08-06",
        "expected_external_requests": 4500,
    }

    verify_run_approval({"approved": True} | expected, expected=expected)

    with pytest.raises(ManualRunError, match="approval"):
        verify_run_approval({"approved": True} | (expected | {"harness_sha256": "0" * 64}), expected=expected)
