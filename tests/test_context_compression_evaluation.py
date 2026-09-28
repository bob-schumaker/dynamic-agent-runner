from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluate_context_compression import (
    ContextEvaluationError,
    aggregate_results,
    build_answer_prompt_messages,
    build_history_messages,
    build_redacted_receipt,
    count_answer_prompt_tokens,
    count_history_tokens,
    load_dataset,
    paired_accuracy_bootstrap_interval,
    recency_baseline,
    run_evaluation,
    write_redacted_predictions,
)


def _item() -> dict[str, object]:
    return {
        "question_id": "item-1",
        "question_type": "multi-session",
        "question": "SECRET QUESTION",
        "answer": "SECRET ANSWER",
        "question_date": "2025/01/01",
        "haystack_session_ids": ["s1", "s2"],
        "haystack_dates": ["2024/01/01", "2024/01/02"],
        "haystack_sessions": [
            [
                {"role": "user", "content": "old user", "has_answer": True},
                {"role": "assistant", "content": "old answer"},
            ],
            [
                {"role": "user", "content": "recent user"},
                {"role": "assistant", "content": "recent answer"},
            ],
        ],
        "answer_session_ids": ["s1"],
    }


def test_load_dataset_checks_digest_and_unique_ids(tmp_path) -> None:
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps([_item()]), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    items = load_dataset(path, expected_sha256=digest)

    assert len(items) == 1
    assert items[0]["question_id"] == "item-1"
    with pytest.raises(ContextEvaluationError, match="digest"):
        load_dataset(path, expected_sha256="0" * 64)
    path.write_text(json.dumps([_item(), _item()]), encoding="utf-8")
    duplicate_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ContextEvaluationError, match="identity"):
        load_dataset(path, expected_sha256=duplicate_digest)


def test_history_view_removes_question_gold_and_evidence_labels() -> None:
    messages = build_history_messages(_item())

    assert [message["content"] for message in messages] == [
        "old user",
        "old answer",
        "recent user",
        "recent answer",
    ]
    serialized = json.dumps(messages)
    assert "SECRET QUESTION" not in serialized
    assert "SECRET ANSWER" not in serialized
    assert "has_answer" not in serialized
    assert [message["id"] for message in messages] == [
        "item-1:s1:0",
        "item-1:s1:1",
        "item-1:s2:0",
        "item-1:s2:1",
    ]


def test_answer_prompt_preserves_timestamps_and_uses_answer_tokenizer() -> None:
    history = build_history_messages(_item())

    class Tokenizer:
        def encode(self, text, *, add_special_tokens):
            assert add_special_tokens is False
            return text.split()

        def apply_chat_template(self, messages, **kwargs):
            assert kwargs == {
                "tokenize": True,
                "add_generation_prompt": True,
                "enable_thinking": False,
            }
            prompt = " ".join(message["content"] for message in messages)
            return {"input_ids": [[0] * len(prompt.split())]}

    prompts = build_answer_prompt_messages(history, "SECRET QUESTION")

    assert "2024/01/01" in prompts[1]["content"]
    assert "2024/01/02" in prompts[1]["content"]
    assert count_history_tokens(history, Tokenizer()) > 0
    assert count_answer_prompt_tokens(history, "SECRET QUESTION", Tokenizer()) > 0
def test_recency_baseline_keeps_whole_user_assistant_turns_within_budget() -> None:
    messages = build_history_messages(_item())

    def count_tokens(value):
        return sum(len(message["content"]) for message in value)

    kept = recency_baseline(messages, token_counter=count_tokens, budget=24)

    assert [message["content"] for message in kept] == ["recent user", "recent answer"]
    assert count_tokens(kept) <= 24


def test_aggregate_results_reports_accuracy_evidence_recall_and_token_ratio() -> None:
    item = _item()
    messages = build_history_messages(item)
    predictions = [
        {
            "question_id": "item-1",
            "question_type": "multi-session",
            "condition": "model_guided",
            "budget": 10,
            "correct": True,
            "retained_message_ids": [messages[0]["id"], messages[2]["id"]],
            "input_tokens": 20,
            "retained_tokens": 10,
        }
    ]

    metrics = aggregate_results([item], predictions)

    row = metrics["model_guided"][10]
    assert row["answer_accuracy"] == 1.0
    assert row["evidence_turn_recall"] == 1.0
    assert row["retained_token_ratio"] == 0.5
    assert row["by_question_type"]["multi-session"]["count"] == 1


def test_paired_bootstrap_accuracy_interval_is_deterministic_and_paired() -> None:
    items = [_item() | {"question_id": f"item-{index}"} for index in range(4)]
    recency = [
        {
            "question_id": item["question_id"],
            "question_type": item["question_type"],
            "correct": index != 0,
        }
        for index, item in enumerate(items)
    ]
    model = [dict(row) | {"correct": True} for row in recency]

    interval = paired_accuracy_bootstrap_interval(
        model, recency, resamples=1000, seed=13
    )

    assert interval == (0.0, 0.75)


def test_redacted_receipt_contains_only_aggregate_evidence() -> None:
    receipt = build_redacted_receipt(
        corpus_revision="revision",
        corpus_sha256="a" * 64,
        answer_model="answer-model@revision",
        scorer="scorer@revision",
        metrics={"full_history": {4096: {"answer_accuracy": 0.5}}},
        item_count=1,
    )

    serialized = json.dumps(receipt)
    assert "SECRET QUESTION" not in serialized
    assert "SECRET ANSWER" not in serialized
    assert "hypothesis" not in serialized
    assert receipt["item_count"] == 1


def test_prediction_writer_omits_unapproved_free_text(tmp_path) -> None:
    path = tmp_path / "predictions.jsonl"
    row = {
        "question_id": "item-1",
        "question_type": "multi-session",
        "is_abstention": False,
        "condition": "model_guided",
        "budget": 4096,
        "correct": True,
        "retained_message_ids": ["item-1:s1:0"],
        "input_tokens": 20,
        "retained_tokens": 10,
        "prompt_tokens": 100,
        "compaction_latency_ms": 1.0,
        "answer_latency_ms": 2.0,
        "scorer_latency_ms": 3.0,
        "question": "SECRET QUESTION",
        "gold_answer": "SECRET ANSWER",
        "hypothesis": "SECRET HYPOTHESIS",
    }

    write_redacted_predictions(path, [row])

    serialized = path.read_text(encoding="utf-8")
    assert "SECRET" not in serialized
    assert "hypothesis" not in serialized
    assert json.loads(serialized)["question_id"] == "item-1"


def test_run_evaluation_keeps_compactor_question_blind_and_budgets_matched() -> None:
    item = _item()
    seen_compactor_inputs = []
    seen_answers = []
    seen_judgments = []

    def token_counter(messages):
        return sum(len(message["content"]) for message in messages)

    def prompt_token_counter(messages, question):
        return 100 + token_counter(messages) + len(question)

    def compact(compactor_input, budget):
        seen_compactor_inputs.append(compactor_input)
        candidates = compactor_input["candidate_messages"]
        return [message["id"] for message in candidates[-2:]]

    def answer(messages, question):
        seen_answers.append((messages, question))
        return "answer text is not persisted"

    def judge(question_id, question, gold, hypothesis, question_type):
        seen_judgments.append((question_id, question, gold, hypothesis, question_type))
        return True

    rows = run_evaluation(
        [item],
        budgets=[24],
        max_context_tokens=300,
        reserved_generation_tokens=16,
        token_counter=token_counter,
        prompt_token_counter=prompt_token_counter,
        answer=answer,
        judge=judge,
        compact=compact,
    )

    assert {row["condition"] for row in rows} == {
        "full_history",
        "recency",
        "model_guided",
    }
    assert rows[1]["retained_tokens"] == rows[2]["retained_tokens"] == 24
    assert len(seen_answers) == len(seen_judgments) == 3
    assert seen_answers[0][1] == "SECRET QUESTION"
    assert seen_judgments[0][1:3] == ("SECRET QUESTION", "SECRET ANSWER")
    compactor_payload = json.dumps(seen_compactor_inputs)
    assert "SECRET QUESTION" not in compactor_payload
    assert "SECRET ANSWER" not in compactor_payload
    assert "has_answer" not in compactor_payload
    assert all("answer text" not in json.dumps(row) for row in rows)


def test_run_evaluation_skips_answer_and_judge_when_prompt_overflows() -> None:
    item = _item()
    calls = {"answer": 0, "judge": 0}

    def token_counter(messages):
        return sum(len(message["content"]) for message in messages)

    def compact(compactor_input, budget):
        return [message["id"] for message in compactor_input["candidate_messages"][-2:]]

    def answer(messages, question):
        calls["answer"] += 1
        return "answer"

    def judge(question_id, question, gold, hypothesis, question_type):
        calls["judge"] += 1
        return True

    rows = run_evaluation(
        [item],
        budgets=[24],
        max_context_tokens=16,
        reserved_generation_tokens=4,
        token_counter=token_counter,
        prompt_token_counter=lambda messages, question: 20,
        answer=answer,
        judge=judge,
        compact=compact,
    )

    assert len(rows) == 3
    assert all(row["correct"] is None for row in rows)
    assert calls == {"answer": 0, "judge": 0}
