"""Benchmark-specific helpers for the gated DMS-13 evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


class ContextEvaluationError(ValueError):
    """Raised when LongMemEval-S inputs or evaluation outputs are invalid."""


QUESTION_TYPES = frozenset(
    {
        "single-session-user",
        "single-session-assistant",
        "single-session-preference",
        "temporal-reasoning",
        "knowledge-update",
        "multi-session",
    }
)
CONDITIONS = frozenset({"full_history", "recency", "model_guided"})
COMPACTION_TASK_CONTEXT = (
    "Preserve useful information from this conversation for future requests."
)


def load_dataset(path: Path, *, expected_sha256: str) -> tuple[dict[str, Any], ...]:
    """Load a pinned LongMemEval-S JSON file and validate its public schema."""

    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ContextEvaluationError("dataset cannot be read") from exc
    actual_digest = hashlib.sha256(payload).hexdigest()
    if actual_digest != expected_sha256:
        raise ContextEvaluationError("dataset digest does not match the approved revision")
    try:
        rows = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContextEvaluationError("dataset JSON is invalid") from exc
    if not isinstance(rows, list) or not rows:
        raise ContextEvaluationError("dataset must be a non-empty JSON array")

    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        question_id = _validate_dataset_item(row, seen_ids)
        seen_ids.add(question_id)
        result.append(row)
    return tuple(result)


def _validate_dataset_item(row: Any, seen_ids: set[str]) -> str:
    if not isinstance(row, dict):
        raise ContextEvaluationError("dataset item is invalid")
    question_id = row.get("question_id")
    question_type = row.get("question_type")
    if (
        not isinstance(question_id, str)
        or not question_id
        or question_id in seen_ids
        or not isinstance(question_type, str)
        or question_type not in QUESTION_TYPES
        or not isinstance(row.get("question"), str)
        or "answer" not in row
    ):
        raise ContextEvaluationError("dataset item identity or question fields are invalid")
    sessions = row.get("haystack_sessions")
    session_ids = row.get("haystack_session_ids")
    dates = row.get("haystack_dates")
    if (
        not isinstance(sessions, list)
        or not isinstance(session_ids, list)
        or not isinstance(dates, list)
        or not (len(sessions) == len(session_ids) == len(dates))
        or not all(isinstance(value, str) and value for value in session_ids)
        or not all(isinstance(value, str) for value in dates)
    ):
        raise ContextEvaluationError("dataset session structure is invalid")
    _validate_dataset_turns(sessions)
    return question_id


def _validate_dataset_turns(sessions: Sequence[Any]) -> None:
    for session in sessions:
        if not isinstance(session, list):
            raise ContextEvaluationError("dataset session turns are invalid")
        for turn in session:
            if (
                not isinstance(turn, dict)
                or turn.get("role") not in {"user", "assistant"}
                or not isinstance(turn.get("content"), str)
                or ("has_answer" in turn and not isinstance(turn["has_answer"], bool))
            ):
                raise ContextEvaluationError("dataset turn is invalid")


def build_history_messages(item: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return timestamped history turns without questions, gold, or evidence."""

    question_id = str(item["question_id"])
    sessions = item["haystack_sessions"]
    session_ids = item["haystack_session_ids"]
    dates = item["haystack_dates"]
    if not (len(sessions) == len(session_ids) == len(dates)):
        raise ContextEvaluationError("dataset session structure is invalid")
    messages: list[dict[str, str]] = []
    for session_id, session_date, session in zip(session_ids, dates, sessions, strict=True):
        if not isinstance(session, Sequence) or isinstance(session, (str, bytes, bytearray)):
            raise ContextEvaluationError("dataset session turns are invalid")
        for turn_index, turn in enumerate(session):
            if (
                not isinstance(turn, Mapping)
                or turn.get("role") not in {"user", "assistant"}
                or not isinstance(turn.get("content"), str)
            ):
                raise ContextEvaluationError("dataset turn is invalid")
            messages.append(
                {
                    "id": f"{question_id}:{session_id}:{turn_index}",
                    "role": str(turn["role"]),
                    "content": turn["content"],
                    "session_id": str(session_id),
                    "session_date": str(session_date),
                }
            )
    return messages


def build_compactor_input(item: Mapping[str, Any]) -> dict[str, Any]:
    """Build question-blind compactor input from sanitized conversation history."""

    return {
        "task_context": COMPACTION_TASK_CONTEXT,
        "candidate_messages": build_history_messages(item),
    }


def build_answer_prompt_messages(
    history: Sequence[Mapping[str, Any]], question: str
) -> list[dict[str, str]]:
    """Format the same timestamped history and question for the fixed answer model."""

    lines = [
        f"[{message['session_date']}] session {message['session_id']} "
        f"{message['role']}: {message['content']}"
        for message in history
    ]
    return [
        {
            "role": "system",
            "content": (
                "Answer the question using the conversation history. "
                "If the history does not contain the answer, say that it is unavailable."
            ),
        },
        {
            "role": "user",
            "content": "Conversation history:\n"
            + "\n".join(lines)
            + "\n\nQuestion: "
            + question,
        },
    ]


def count_history_tokens(
    history: Sequence[Mapping[str, Any]], tokenizer: Any
) -> int:
    """Count serialized history with the exact downstream answer tokenizer."""

    text = "\n".join(
        f"[{message['session_date']}] session {message['session_id']} "
        f"{message['role']}: {message['content']}"
        for message in history
    )
    return len(tokenizer.encode(text, add_special_tokens=False))


def count_answer_prompt_tokens(
    history: Sequence[Mapping[str, Any]], question: str, tokenizer: Any
) -> int:
    """Count the complete model input, including system prompt and question."""

    encoded = tokenizer.apply_chat_template(
        build_answer_prompt_messages(history, question),
        tokenize=True,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    input_ids = encoded["input_ids"] if isinstance(encoded, Mapping) else encoded
    if input_ids and isinstance(input_ids[0], list | tuple):
        if len(input_ids) != 1:
            raise ContextEvaluationError("answer tokenizer returned an invalid batch")
        input_ids = input_ids[0]
    if not isinstance(input_ids, Sequence) or isinstance(
        input_ids, (str, bytes, bytearray)
    ):
        raise ContextEvaluationError("answer tokenizer returned invalid input IDs")
    return len(input_ids)


def _conversation_turns(
    messages: Sequence[Mapping[str, Any]],
) -> list[list[Mapping[str, Any]]]:
    turns: list[list[Mapping[str, Any]]] = []
    current: list[Mapping[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "user" and current:
            turns.append(current)
            current = []
        current.append(message)
    if current:
        turns.append(current)
    return turns


def recency_baseline(
    messages: Sequence[Mapping[str, Any]],
    *,
    token_counter: Callable[[Sequence[Mapping[str, Any]]], int],
    budget: int,
) -> list[Mapping[str, Any]]:
    """Keep the newest complete conversation turns that fit the token budget."""

    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        raise ContextEvaluationError("history token budget is invalid")
    kept_turns: list[list[Mapping[str, Any]]] = []
    for turn in reversed(_conversation_turns(messages)):
        candidate_turns = [turn, *kept_turns]
        candidate = [message for selected in candidate_turns for message in selected]
        count = token_counter(candidate)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ContextEvaluationError("token counter returned an invalid count")
        if count > budget:
            break
        kept_turns = candidate_turns
    return [message for turn in kept_turns for message in turn]


def run_evaluation(
    items: Sequence[Mapping[str, Any]],
    *,
    budgets: Sequence[int],
    max_context_tokens: int,
    reserved_generation_tokens: int,
    token_counter: Callable[[Sequence[Mapping[str, Any]]], int],
    prompt_token_counter: Callable[[Sequence[Mapping[str, Any]], str], int],
    answer: Callable[[Sequence[Mapping[str, Any]], str], str],
    judge: Callable[[str, str, Any, str, str], bool],
    compact: Callable[[Mapping[str, Any], int], Sequence[str]],
) -> list[dict[str, Any]]:
    """Run full-history, recency, and question-blind model compaction conditions."""

    _validate_run_configuration(
        budgets, max_context_tokens, reserved_generation_tokens
    )
    predictions: list[dict[str, Any]] = []
    for item in items:
        messages = build_history_messages(item)
        input_tokens = _checked_token_count(token_counter(messages))
        question = str(item["question"])
        question_id = str(item["question_id"])
        question_type = str(item["question_type"])
        conditions: list[tuple[str, int, list[Mapping[str, Any]], float]] = [
            ("full_history", max_context_tokens, list(messages), 0.0)
        ]
        for budget in budgets:
            started = time.perf_counter()
            recent = recency_baseline(messages, token_counter=token_counter, budget=budget)
            conditions.append(
                ("recency", budget, recent, (time.perf_counter() - started) * 1000)
            )
            started = time.perf_counter()
            selected = _model_guided_history(
                item, messages, budget, compact=compact, token_counter=token_counter
            )
            conditions.append(
                ("model_guided", budget, selected, (time.perf_counter() - started) * 1000)
            )
        for condition, budget, history, compaction_latency_ms in conditions:
            predictions.append(
                _evaluate_condition(
                    item,
                    question,
                    history,
                    condition=condition,
                    budget=budget,
                    input_tokens=input_tokens,
                    compaction_latency_ms=compaction_latency_ms,
                    max_context_tokens=max_context_tokens,
                    reserved_generation_tokens=reserved_generation_tokens,
                    token_counter=token_counter,
                    prompt_token_counter=prompt_token_counter,
                    answer=answer,
                    judge=judge,
                    question_id=question_id,
                    question_type=question_type,
                )
            )
    return predictions


def _validate_run_configuration(
    budgets: Sequence[int], max_context_tokens: int, reserved_generation_tokens: int
) -> None:
    if (
        not budgets
        or any(not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0 for budget in budgets)
        or len(set(budgets)) != len(budgets)
        or not isinstance(max_context_tokens, int)
        or isinstance(max_context_tokens, bool)
        or max_context_tokens <= 0
        or not isinstance(reserved_generation_tokens, int)
        or isinstance(reserved_generation_tokens, bool)
        or reserved_generation_tokens <= 0
        or reserved_generation_tokens >= max_context_tokens
    ):
        raise ContextEvaluationError("benchmark context budgets are invalid")


def _checked_token_count(count: Any) -> int:
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ContextEvaluationError("token counter returned an invalid count")
    return count


def _model_guided_history(
    item: Mapping[str, Any],
    messages: Sequence[Mapping[str, Any]],
    budget: int,
    *,
    compact: Callable[[Mapping[str, Any], int], Sequence[str]],
    token_counter: Callable[[Sequence[Mapping[str, Any]]], int],
) -> list[Mapping[str, Any]]:
    result = compact(build_compactor_input(item), budget)
    if not isinstance(result, Sequence) or isinstance(result, (str, bytes, bytearray)):
        raise ContextEvaluationError("model compactor returned invalid message selection")
    selected_ids = list(result)
    if not all(isinstance(message_id, str) for message_id in selected_ids):
        raise ContextEvaluationError("model compactor returned invalid message selection")
    valid_ids = [message["id"] for message in messages]
    selected_id_set = set(selected_ids)
    if (
        len(selected_ids) != len(selected_id_set)
        or not selected_id_set <= set(valid_ids)
        or selected_ids != [message_id for message_id in valid_ids if message_id in selected_id_set]
    ):
        raise ContextEvaluationError("model compactor returned invalid message selection")
    selected = [message for message in messages if message["id"] in selected_id_set]
    if _checked_token_count(token_counter(selected)) > budget:
        raise ContextEvaluationError("model compactor exceeded its matched history budget")
    return selected


def _evaluate_condition(
    item: Mapping[str, Any],
    question: str,
    history: Sequence[Mapping[str, Any]],
    *,
    condition: str,
    budget: int,
    input_tokens: int,
    compaction_latency_ms: float,
    max_context_tokens: int,
    reserved_generation_tokens: int,
    token_counter: Callable[[Sequence[Mapping[str, Any]]], int],
    prompt_token_counter: Callable[[Sequence[Mapping[str, Any]], str], int],
    answer: Callable[[Sequence[Mapping[str, Any]], str], str],
    judge: Callable[[str, str, Any, str, str], bool],
    question_id: str,
    question_type: str,
) -> dict[str, Any]:
    history_tokens = _checked_token_count(token_counter(history))
    prompt_tokens = _checked_token_count(prompt_token_counter(history, question))
    correct: bool | None = None
    answer_latency_ms = 0.0
    scorer_latency_ms = 0.0
    if prompt_tokens + reserved_generation_tokens <= max_context_tokens:
        answer_started = time.perf_counter()
        hypothesis = answer(history, question)
        answer_latency_ms = (time.perf_counter() - answer_started) * 1000
        if not isinstance(hypothesis, str):
            raise ContextEvaluationError("answer model output is invalid")
        judge_started = time.perf_counter()
        correct = judge(question_id, question, item["answer"], hypothesis, question_type)
        scorer_latency_ms = (time.perf_counter() - judge_started) * 1000
        if not isinstance(correct, bool):
            raise ContextEvaluationError("answer judgment is invalid")
    return {
        "question_id": question_id,
        "question_type": question_type,
        "is_abstention": question_id.endswith("_abs"),
        "condition": condition,
        "budget": budget,
        "correct": correct,
        "retained_message_ids": [message["id"] for message in history],
        "input_tokens": input_tokens,
        "retained_tokens": history_tokens,
        "prompt_tokens": prompt_tokens,
        "compaction_latency_ms": compaction_latency_ms,
        "answer_latency_ms": answer_latency_ms,
        "scorer_latency_ms": scorer_latency_ms,
    }


def _evidence_ids(item: Mapping[str, Any]) -> set[str]:
    evidence: set[str] = set()
    question_id = str(item["question_id"])
    for session_id, session in zip(
        item["haystack_session_ids"], item["haystack_sessions"], strict=True
    ):
        for turn_index, turn in enumerate(session):
            if turn.get("has_answer") is True:
                evidence.add(f"{question_id}:{session_id}:{turn_index}")
    return evidence


def _group_metrics(
    rows: Sequence[Mapping[str, Any]],
    items_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    answer_values = [row["correct"] for row in rows if row["correct"] is not None]
    evidence_retained = 0
    evidence_total = 0
    token_ratios: list[float] = []
    for row in rows:
        retained = set(row["retained_message_ids"])
        evidence = _evidence_ids(items_by_id[row["question_id"]])
        evidence_retained += len(retained & evidence)
        evidence_total += len(evidence)
        if row["input_tokens"] > 0:
            token_ratios.append(row["retained_tokens"] / row["input_tokens"])
    metrics: dict[str, Any] = {
        "count": len(rows),
        "answer_count": len(answer_values),
        "context_overflow_count": sum(row["correct"] is None for row in rows),
        "answer_accuracy": (
            sum(answer_values) / len(answer_values) if answer_values else None
        ),
        "evidence_turn_recall": (
            evidence_retained / evidence_total if evidence_total else None
        ),
        "evidence_turns_retained": evidence_retained,
        "evidence_turns_total": evidence_total,
        "retained_token_ratio": (
            sum(token_ratios) / len(token_ratios) if token_ratios else None
        ),
    }
    for field in (
        "compaction_latency_ms",
        "answer_latency_ms",
        "scorer_latency_ms",
    ):
        values = [row[field] for row in rows if field in row]
        if values:
            if any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
                for value in values
            ):
                raise ContextEvaluationError("evaluation latency is invalid")
            metrics[field] = sum(values) / len(values)
    return metrics


def aggregate_results(
    items: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]]
) -> dict[str, dict[int, dict[str, Any]]]:
    """Aggregate redacted answer judgments, evidence recall, and token ratios."""

    items_by_id = {str(item["question_id"]): item for item in items}
    if not items_by_id or len(items_by_id) != len(items):
        raise ContextEvaluationError("benchmark item identities are invalid")
    grouped: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str, int]] = set()
    for row in predictions:
        question_id = row.get("question_id")
        condition = row.get("condition")
        budget = row.get("budget")
        if (
            question_id not in items_by_id
            or condition not in CONDITIONS
            or not isinstance(budget, int)
            or isinstance(budget, bool)
            or budget <= 0
        ):
            raise ContextEvaluationError("evaluation result identity is invalid")
        key = (question_id, condition, budget)
        if key in seen:
            raise ContextEvaluationError("duplicate evaluation result")
        item = items_by_id[question_id]
        if row.get("question_type") != item["question_type"]:
            raise ContextEvaluationError("evaluation question type does not match corpus")
        if row.get("is_abstention", str(question_id).endswith("_abs")) is not str(
            question_id
        ).endswith("_abs"):
            raise ContextEvaluationError("evaluation answerability does not match corpus")
        correct = row.get("correct")
        if correct is not None and not isinstance(correct, bool):
            raise ContextEvaluationError("answer judgment is invalid")
        retained_ids = row.get("retained_message_ids")
        input_tokens = row.get("input_tokens")
        retained_tokens = row.get("retained_tokens")
        valid_ids = {message["id"] for message in build_history_messages(item)}
        if (
            "correct" not in row
            or not isinstance(retained_ids, list)
            or not all(isinstance(value, str) for value in retained_ids)
            or len(retained_ids) != len(set(retained_ids))
            or not set(retained_ids) <= valid_ids
            or not isinstance(input_tokens, int)
            or isinstance(input_tokens, bool)
            or input_tokens < 0
            or not isinstance(retained_tokens, int)
            or isinstance(retained_tokens, bool)
            or retained_tokens < 0
            or retained_tokens > input_tokens
        ):
            raise ContextEvaluationError("retained history measurements are invalid")
        seen.add(key)
        grouped[(condition, budget)].append(row)

    results: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for (condition, budget), rows in grouped.items():
        metrics = _group_metrics(rows, items_by_id)
        categories = sorted({str(row["question_type"]) for row in rows})
        metrics["by_question_type"] = {
            category: _group_metrics(
                [row for row in rows if row["question_type"] == category], items_by_id
            )
            for category in categories
        }
        categories_metrics = list(metrics["by_question_type"].values())
        category_accuracies = [
            category["answer_accuracy"]
            for category in categories_metrics
            if category["answer_accuracy"] is not None
        ]
        metrics["macro_answer_accuracy"] = (
            sum(category_accuracies) / len(category_accuracies)
            if category_accuracies
            else None
        )
        metrics["by_answerability"] = {
            label: _group_metrics(
                [row for row in rows if bool(row.get("is_abstention")) is abstention],
                items_by_id,
            )
            for label, abstention in (("answerable", False), ("abstention", True))
            if any(bool(row.get("is_abstention")) is abstention for row in rows)
        }
        results[condition][budget] = metrics
    return dict(results)


def paired_accuracy_bootstrap_interval(
    model_rows: Sequence[Mapping[str, Any]],
    baseline_rows: Sequence[Mapping[str, Any]],
    *,
    resamples: int = 10_000,
    seed: int = 13,
) -> tuple[float, float]:
    """Return a percentile CI for paired, question-type-stratified accuracy."""

    def indexed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
        result: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            question_id = row.get("question_id")
            if (
                not isinstance(question_id, str)
                or question_id in result
                or not isinstance(row.get("question_type"), str)
                or not isinstance(row.get("correct"), bool)
            ):
                raise ContextEvaluationError("bootstrap result rows are invalid")
            result[question_id] = row
        return result

    model = indexed(model_rows)
    baseline = indexed(baseline_rows)
    if (
        not model
        or model.keys() != baseline.keys()
        or not isinstance(resamples, int)
        or isinstance(resamples, bool)
        or resamples < 100
        or not isinstance(seed, int)
        or isinstance(seed, bool)
    ):
        raise ContextEvaluationError("paired bootstrap configuration is invalid")
    categories: dict[str, list[str]] = defaultdict(list)
    for question_id, row in model.items():
        if row["question_type"] != baseline[question_id]["question_type"]:
            raise ContextEvaluationError("paired result question types do not match")
        categories[row["question_type"]].append(question_id)

    rng = random.Random(seed)
    differences: list[float] = []
    for _ in range(resamples):
        paired = [
            question_id
            for ids in categories.values()
            for question_id in (rng.choice(ids) for _ in range(len(ids)))
        ]
        differences.append(
            sum(model[item_id]["correct"] for item_id in paired) / len(paired)
            - sum(baseline[item_id]["correct"] for item_id in paired) / len(paired)
        )
    differences.sort()
    return (
        differences[int(0.025 * resamples)],
        differences[min(resamples - 1, int(0.975 * resamples))],
    )


def build_redacted_receipt(
    *,
    corpus_revision: str,
    corpus_sha256: str,
    answer_model: str,
    scorer: str,
    metrics: Mapping[str, Any],
    item_count: int,
) -> dict[str, Any]:
    """Create the aggregate-only result receipt; never persist prompts or answers."""

    if not corpus_revision or len(corpus_sha256) != 64:
        raise ContextEvaluationError("corpus identity is invalid")
    if not answer_model or not scorer:
        raise ContextEvaluationError("answer model or scorer identity is missing")
    if not isinstance(item_count, int) or isinstance(item_count, bool) or item_count <= 0:
        raise ContextEvaluationError("item count is invalid")
    return {
        "corpus_revision": corpus_revision,
        "corpus_sha256": corpus_sha256,
        "answer_model": answer_model,
        "scorer": scorer,
        "item_count": item_count,
        "metrics": metrics,
    }


def write_redacted_predictions(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Persist only fixed per-item metadata, never prompts or generated text."""

    allowed_fields = (
        "question_id",
        "question_type",
        "is_abstention",
        "condition",
        "budget",
        "correct",
        "retained_message_ids",
        "input_tokens",
        "retained_tokens",
        "prompt_tokens",
        "compaction_latency_ms",
        "answer_latency_ms",
        "scorer_latency_ms",
    )
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            if any(field not in row for field in allowed_fields):
                raise ContextEvaluationError("redacted prediction fields are incomplete")
            stream.write(
                json.dumps({field: row[field] for field in allowed_fields}, sort_keys=True)
                + "\n"
            )
