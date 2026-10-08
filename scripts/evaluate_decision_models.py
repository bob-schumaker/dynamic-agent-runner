#!/usr/bin/env python3
"""Evaluate externally produced DMS-01 outputs without invoking a model."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = ROOT / "specs" / "decision-model-support" / "evaluation"
DMS01_INPUTS_SHA256 = "6d0230190f455d3f488881ef0f709881fba783f33bab4d5a6a93db576cf5c73f"
DMS01_LABELS_SHA256 = "a87f79b376b7e0c790df78cdd6a623d06450364d6d7c708974c8a953d7b7c7a5"
DECISION_ACCURACY_MIN = 0.80
DECISION_CATEGORY_ACCURACY_MIN = 0.70
RETENTION_F1_MIN = 0.80
RETENTION_KEEP_RECALL_MIN = 0.90
RETENTION_UTILITY_GAIN_MIN = 0.05
PROBABILITY_ECE_MAX = 0.10
PEAK_MEMORY_MAX_BYTES = 24 * 1024**3
_STATUSES = {"ok", "invalid", "missing", "timeout", "oversize", "abstained", "error"}


class EvaluationError(ValueError):
    """Raised when frozen inputs or evaluation evidence are inconsistent."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_fixture_hashes(inputs_path: Path, labels_path: Path) -> None:
    """Require the exact pre-registered synthetic DMS-01 fixtures."""

    if _sha256(inputs_path) != DMS01_INPUTS_SHA256:
        raise EvaluationError("input fixture hash does not match the frozen DMS-01 set")
    if _sha256(labels_path) != DMS01_LABELS_SHA256:
        raise EvaluationError("label fixture hash does not match the frozen DMS-01 set")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationError(f"invalid JSONL at {path.name}:{line_number}") from exc
        if not isinstance(row, dict):
            raise EvaluationError(f"expected JSON object at {path.name}:{line_number}")
        rows.append(row)
    return rows


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"invalid JSON object in {path.name}") from exc
    if not isinstance(value, dict):
        raise EvaluationError(f"expected JSON object in {path.name}")
    return value


def prepare_candidate_inputs(inputs_path: Path, destination: Path) -> str:
    """Copy only the frozen input fixture to a candidate-runner handoff file."""

    if _sha256(inputs_path) != DMS01_INPUTS_SHA256:
        raise EvaluationError("input fixture hash does not match the frozen DMS-01 set")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(inputs_path.read_bytes())
    return DMS01_INPUTS_SHA256


def _memory_available_bytes() -> int | None:
    if sys.platform == "darwin":
        result = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, check=False, timeout=5
        )
        if result.returncode == 0:
            first_line, *lines = result.stdout.splitlines()
            marker = "page size of "
            if marker in first_line:
                try:
                    page_size = int(first_line.split(marker, 1)[1].split(" bytes", 1)[0])
                    pages = 0
                    for line in lines:
                        if any(
                            name in line
                            for name in ("Pages free", "Pages inactive", "Pages speculative")
                        ):
                            pages += int(line.split(":", 1)[1].strip().rstrip("."))
                    return pages * page_size
                except (IndexError, ValueError):
                    return None
    try:
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(available_pages * page_size)
    except (AttributeError, OSError, ValueError):
        return None


def create_preflight_receipt(
    *,
    artifacts: list[dict[str, str]],
    harness_id: str,
    harness_revision: str,
    runtime_id: str,
    runtime_executable: Path,
    runtime_python_version: str,
    runtime_packages: dict[str, str],
    runtime_lock_sha256: str,
    accelerator_status: str,
    execution_mode: str,
    storage_path: Path,
    required_free_bytes: int,
    fixture_criteria_approved: bool,
    dar_profile_id: str | None = None,
    runner_harness: Path | None = None,
) -> dict[str, Any]:
    """Record whether the exact local evaluation setup is ready to run."""

    inputs_path = EVALUATION_DIR / "dms01-inputs.jsonl"
    labels_path = EVALUATION_DIR / "dms01-labels.jsonl"
    hashes_valid = True
    try:
        verify_fixture_hashes(inputs_path, labels_path)
    except (EvaluationError, OSError):
        hashes_valid = False
    total_memory = None
    try:
        total_memory = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        pass
    free_storage = shutil.disk_usage(storage_path).free if storage_path.exists() else 0
    runtime_available = runtime_executable.is_file() and os.access(runtime_executable, os.X_OK)
    evaluation_harnesses = [
        ROOT / "scripts" / "evaluate_decision_models.py",
        ROOT / (runner_harness or Path("tests/manual/run_kev_dms01.py")),
    ]
    harness_files_valid = all(path.is_file() for path in evaluation_harnesses)
    harness_files = [
        {"id": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
        for path in evaluation_harnesses
        if path.is_file()
    ]
    artifacts_valid = bool(artifacts) and all(
        isinstance(item.get("id"), str)
        and bool(item["id"].strip())
        and len(item.get("revision", "")) == 40
        and all(character in "0123456789abcdef" for character in item["revision"].lower())
        for item in artifacts
    )
    harness_valid = bool(harness_id.strip()) and len(harness_revision) == 40 and all(
        character in "0123456789abcdef" for character in harness_revision.lower()
    )
    checks = (
        (not fixture_criteria_approved, "fixture and criteria approval is absent"),
        (not hashes_valid, "frozen fixture hashes do not match"),
        (not artifacts_valid, "exact artifact IDs and immutable revisions are required"),
        (not harness_valid, "exact evaluation harness revision is required"),
        (not runtime_available, "the selected runtime executable is unavailable"),
        (not runtime_python_version or not runtime_packages, "exact runtime versions are required"),
        (
            len(runtime_lock_sha256) != 64
            or any(character not in "0123456789abcdef" for character in runtime_lock_sha256.lower()),
            "a pinned runtime lock hash is required",
        ),
        (not harness_files_valid, "evaluation harness files are missing"),
        (
            execution_mode not in {"external_research_harness", "dar_admitted_runner"},
            "execution mode is not recognized",
        ),
        (
            execution_mode == "dar_admitted_runner" and not dar_profile_id,
            "an exact admitted DAR profile is required for DAR execution",
        ),
        (
            required_free_bytes <= 0 or free_storage < required_free_bytes,
            "available storage is below the declared requirement",
        ),
        (
            total_memory is None or total_memory < 24 * 1024**3,
            "host does not meet the 24 GiB evaluation memory ceiling",
        ),
    )
    blockers = [message for blocked, message in checks if blocked]
    return {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "fixture_criteria_approved": fixture_criteria_approved,
        "fixture_hashes_valid": hashes_valid,
        "input_sha256": DMS01_INPUTS_SHA256,
        "labels_sha256": DMS01_LABELS_SHA256,
        "artifacts": artifacts,
        "harness": {"id": harness_id, "revision": harness_revision},
        "evaluation_harness_files": harness_files,
        "runtime": {
            "id": runtime_id,
            "executable": str(runtime_executable),
            "available": runtime_available,
            "python_version": runtime_python_version,
            "packages": runtime_packages,
            "lock_sha256": runtime_lock_sha256,
        },
        "accelerator_status": accelerator_status,
        "execution_mode": execution_mode,
        "dar_profile_id": dar_profile_id,
        "host": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "total_memory_bytes": total_memory,
            "available_memory_estimate_bytes": _memory_available_bytes(),
            "storage_path": str(storage_path),
            "free_storage_bytes": free_storage,
            "required_free_storage_bytes": required_free_bytes,
        },
        "remote_code_allowed": False,
        "blockers": blockers,
        "run_allowed": not blockers,
    }


def write_preflight_receipt(receipt: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _unique_index(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = row.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in result:
            raise EvaluationError(f"{label} contains a missing or duplicate id")
        result[item_id] = row
    return result


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _wilson(successes: int, total: int) -> dict[str, float]:
    if total == 0:
        return {"lower": 0.0, "upper": 0.0}
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return {"lower": max(0.0, center - margin), "upper": min(1.0, center + margin)}


def _evaluate_decision_prediction(
    prediction: dict[str, Any] | None,
    option_ids: list[str],
    expected: str,
) -> tuple[str, bool, tuple[list[str], str, bool, dict[str, float]] | None]:
    status = prediction.get("status") if prediction else "missing"
    if status not in _STATUSES:
        return "invalid", False, None
    if status != "ok":
        return status, False, None
    if prediction is None or prediction.get("kind") != "decision":
        return "invalid", False, None
    choice = prediction.get("choice")
    raw_scores = prediction.get("scores")
    semantics = prediction.get("score_semantics")
    if choice not in option_ids or not isinstance(raw_scores, dict) or set(raw_scores) != set(option_ids):
        return "invalid", False, None
    if not all(_finite_number(value) for value in raw_scores.values()):
        return "invalid", False, None
    scores = {key: float(value) for key, value in raw_scores.items()}
    if max(scores, key=scores.get) != choice:
        return "invalid", False, None
    if semantics == "probability":
        if any(value < 0 or value > 1 for value in scores.values()) or not math.isclose(
            sum(scores.values()), 1.0, abs_tol=1e-6
        ):
            return "invalid", False, None
        return "ok", choice == expected, (option_ids, expected, choice == expected, scores)
    if semantics != "ranking_score":
        return "invalid", False, None
    return "ok", choice == expected, None


def _decision_metrics(
    inputs: dict[str, dict[str, Any]],
    labels: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[tuple[list[str], str, bool, dict[str, float]]]]:
    by_category: dict[str, list[bool]] = defaultdict(list)
    failure_counts: Counter[str] = Counter()
    probability_rows: list[tuple[list[str], str, bool, dict[str, float]]] = []
    for item_id, item in inputs.items():
        if item.get("kind") != "decision":
            continue
        label = labels[item_id]
        prediction = predictions.get(item_id)
        options = item["question"]["options"]
        option_ids = [option["id"] for option in options]
        expected = label.get("expected_option_id")
        category = str(label.get("category", "unknown"))
        status, correct, probability_row = _evaluate_decision_prediction(
            prediction, option_ids, expected
        )
        if probability_row is not None:
            probability_rows.append(probability_row)
        by_category[category].append(correct)
        if status != "ok":
            failure_counts[status] += 1

    decisions = [result for values in by_category.values() for result in values]
    total = len(decisions)
    successes = sum(decisions)
    failure_rates = {
        status: failure_counts[status] / total if total else 0.0
        for status in ("invalid", "missing", "timeout", "oversize", "abstained", "error")
    }
    metrics = {
        "count": total,
        "accuracy": successes / total if total else 0.0,
        "wilson_95": _wilson(successes, total),
        "by_category": {
            category: {
                "count": len(values),
                "accuracy": sum(values) / len(values) if values else 0.0,
                "wilson_95": _wilson(sum(values), len(values)),
            }
            for category, values in sorted(by_category.items())
        },
        "failure_rates": failure_rates,
        "passes_thresholds": (successes / total if total else 0.0) >= DECISION_ACCURACY_MIN
        and all(
            values and sum(values) / len(values) >= DECISION_CATEGORY_ACCURACY_MIN
            for values in by_category.values()
        ),
    }
    return metrics, probability_rows


def _retained_with_budget(
    candidates: list[tuple[str, float, int]], budget: int
) -> set[str]:
    retained: set[str] = set()
    used = 0
    for message_id, _score, token_count in sorted(candidates, key=lambda item: (-item[1], item[0])):
        if used + token_count <= budget:
            retained.add(message_id)
            used += token_count
    return retained


def _classification_metrics(
    expected: dict[str, str], retained: set[str], token_counts: dict[str, int]
) -> dict[str, float | int]:
    tp = sum(value == "keep" and message_id in retained for message_id, value in expected.items())
    fp = sum(value == "drop" and message_id in retained for message_id, value in expected.items())
    fn = sum(value == "keep" and message_id not in retained for message_id, value in expected.items())
    tn = sum(value == "drop" and message_id not in retained for message_id, value in expected.items())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "true_keep": tp,
        "false_keep": fp,
        "missed_keep": fn,
        "true_drop": tn,
        "keep_precision": precision,
        "keep_recall": recall,
        "keep_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "token_weighted_keep_recall": (
            sum(token_counts[mid] for mid, value in expected.items() if value == "keep" and mid in retained)
            / sum(token_counts[mid] for mid, value in expected.items() if value == "keep")
            if any(value == "keep" for value in expected.values())
            else 0.0
        ),
    }


def _retention_prediction(
    prediction: dict[str, Any] | None, expected: dict[str, str], ids: set[str]
) -> tuple[dict[str, float], str, list[tuple[bool, float]]]:
    status = prediction.get("status") if prediction else "missing"
    if status != "ok" or prediction is None:
        return {}, status if status in _STATUSES else "invalid", []
    raw_scores = prediction.get("scores")
    if (
        prediction.get("kind") != "retention"
        or not isinstance(raw_scores, dict)
        or set(raw_scores) != ids
        or not all(_finite_number(value) for value in raw_scores.values())
    ):
        return {}, "invalid", []
    scores = {key: float(value) for key, value in raw_scores.items()}
    semantics = prediction.get("score_semantics")
    if semantics == "probability":
        if any(value < 0 or value > 1 for value in scores.values()):
            return {}, "invalid", []
        calibration_rows = [
            (expected[message_id] == "keep", score)
            for message_id, score in scores.items()
        ]
        return scores, "ok", calibration_rows
    if semantics == "ranking_score":
        return scores, "ok", []
    return {}, "invalid", []


def _retention_metrics(
    inputs: dict[str, dict[str, Any]],
    labels: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    token_counts: dict[str, int],
) -> tuple[dict[str, Any], list[tuple[bool, float]]]:
    per_category: dict[str, dict[str, list[Any]]] = defaultdict(lambda: {"model": [], "baseline": [], "utility": []})
    all_model_expected: dict[str, str] = {}
    all_model_retained: set[str] = set()
    all_model_tokens: dict[str, int] = {}
    all_base_retained: set[str] = set()
    all_base_expected: dict[str, str] = {}
    failure_counts: Counter[str] = Counter()
    retention_count = 0
    probability_rows: list[tuple[bool, float]] = []

    for item_id, item in inputs.items():
        if item.get("kind") != "retention":
            continue
        retention_count += 1
        label = labels[item_id]
        expected = label.get("expected_retention")
        messages = item["eligible_messages_oldest_first"]
        ids = {message["id"] for message in messages}
        if not isinstance(expected, dict) or set(expected) != ids or any(
            value not in {"keep", "drop"} for value in expected.values()
        ):
            raise EvaluationError("retention labels do not match the frozen message ids")
        if any(message_id not in token_counts or token_counts[message_id] <= 0 for message_id in ids):
            raise EvaluationError("token counts are missing or non-positive for a retention message")
        budget = sum(token_counts[message_id] for message_id in ids) // 2
        scores, status, calibration_rows = _retention_prediction(
            predictions.get(item_id), expected, ids
        )
        if status != "ok":
            failure_counts[status] += 1
        probability_rows.extend(calibration_rows)
        if not scores:
            scores = {message_id: float("-inf") for message_id in ids}
        model_candidates = [
            (message["id"], scores[message["id"]], token_counts[message["id"]])
            for message in messages
        ]
        model_retained = _retained_with_budget(model_candidates, budget)
        recent_candidates = [
            (message["id"], float(message["age_rank"]), token_counts[message["id"]])
            for message in messages
        ]
        baseline_retained = _retained_with_budget(recent_candidates, budget)
        category = str(label.get("category", "unknown"))
        model_stats = _classification_metrics(expected, model_retained, token_counts)
        baseline_stats = _classification_metrics(expected, baseline_retained, token_counts)
        utility = float(model_stats["token_weighted_keep_recall"])
        baseline_utility = float(baseline_stats["token_weighted_keep_recall"])
        per_category[category]["model"].append(model_stats)
        per_category[category]["baseline"].append(baseline_stats)
        per_category[category]["utility"].append((utility, baseline_utility))
        all_model_expected.update(expected)
        all_model_retained.update(model_retained)
        all_model_tokens.update({message_id: token_counts[message_id] for message_id in ids})
        all_base_expected.update(expected)
        all_base_retained.update(baseline_retained)

    model_overall = _classification_metrics(all_model_expected, all_model_retained, all_model_tokens)
    baseline_overall = _classification_metrics(all_base_expected, all_base_retained, all_model_tokens)
    by_category: dict[str, Any] = {}
    model_utilities: list[float] = []
    baseline_utilities: list[float] = []
    for category, groups in sorted(per_category.items()):
        model_util = statistics.mean(item[0] for item in groups["utility"])
        baseline_util = statistics.mean(item[1] for item in groups["utility"])
        model_utilities.append(model_util)
        baseline_utilities.append(baseline_util)
        by_category[category] = {
            "model": _mean_stats(groups["model"]),
            "baseline": _mean_stats(groups["baseline"]),
            "model_utility": model_util,
            "baseline_utility": baseline_util,
        }
    model_utility = statistics.mean(model_utilities) if model_utilities else 0.0
    baseline_utility = statistics.mean(baseline_utilities) if baseline_utilities else 0.0
    gain = model_utility - baseline_utility
    result = {
        "budget_fraction": 0.5,
        "model": model_overall,
        "baseline": baseline_overall,
        "utility_definition": "category-macro token-weighted gold-keep recall",
        "model_utility": model_utility,
        "baseline_utility": baseline_utility,
        "utility_improvement": gain,
        "by_category": by_category,
        "failure_rates": {
            status: failure_counts[status] / retention_count if retention_count else 0.0
            for status in ("invalid", "missing", "timeout", "oversize", "abstained", "error")
        },
        "passes_thresholds": model_overall["keep_f1"] >= RETENTION_F1_MIN
        and model_overall["keep_recall"] >= RETENTION_KEEP_RECALL_MIN
        and gain >= RETENTION_UTILITY_GAIN_MIN,
    }
    return result, probability_rows


def _mean_stats(rows: list[dict[str, float | int]]) -> dict[str, float]:
    keys = ("keep_precision", "keep_recall", "keep_f1", "token_weighted_keep_recall")
    return {key: statistics.mean(float(row[key]) for row in rows) for key in keys}


def _calibration_metrics(
    labels: dict[str, dict[str, Any]],
    rows: list[tuple[list[str], str, bool, dict[str, float]]],
) -> dict[str, Any]:
    if not rows:
        return {"status": "not-claimed", "count": 0}
    brier_values: list[float] = []
    confidence_correct: list[tuple[float, float]] = []
    for option_ids, expected, correct, scores in rows:
        brier_values.append(
            sum((scores[option_id] - (1.0 if option_id == expected else 0.0)) ** 2 for option_id in option_ids)
        )
        confidence_correct.append((max(scores.values()), float(correct)))
    ece = 0.0
    for bucket in range(10):
        members = [
            pair
            for pair in confidence_correct
            if min(int(pair[0] * 10), 9) == bucket
        ]
        if members:
            mean_confidence = statistics.mean(pair[0] for pair in members)
            mean_accuracy = statistics.mean(pair[1] for pair in members)
            ece += len(members) / len(rows) * abs(mean_confidence - mean_accuracy)
    classes = Counter(row.get("expected_option_id") for row in labels.values() if row.get("kind") == "decision")
    total = sum(classes.values())
    prevalence_scores = {key: count / total for key, count in classes.items()}
    baseline_brier = statistics.mean(
        sum(
            (prevalence_scores.get(option_id, 0.0) - (1.0 if option_id == expected else 0.0)) ** 2
            for option_id in option_ids
        )
        for option_ids, expected, _correct, _scores in rows
    )
    brier = statistics.mean(brier_values)
    calibrated = ece <= PROBABILITY_ECE_MAX and brier < baseline_brier
    return {
        "status": "calibrated" if calibrated else "uncalibrated",
        "count": len(rows),
        "brier_score": brier,
        "ece_10_bins": ece,
        "prevalence_baseline_brier_score": baseline_brier,
        "passes_thresholds": calibrated,
    }


def _retention_calibration_metrics(
    labels: dict[str, dict[str, Any]], rows: list[tuple[bool, float]]
) -> dict[str, Any]:
    if not rows:
        return {"status": "not-claimed", "count": 0}
    brier = statistics.mean((probability - float(expected)) ** 2 for expected, probability in rows)
    confidences = [(max(probability, 1 - probability), (probability >= 0.5) == expected) for expected, probability in rows]
    ece = 0.0
    for bucket in range(10):
        members = [
            (confidence, correct)
            for confidence, correct in confidences
            if min(int(confidence * 10), 9) == bucket
        ]
        if members:
            ece += len(members) / len(rows) * abs(
                statistics.mean(confidence for confidence, _ in members)
                - statistics.mean(float(correct) for _, correct in members)
            )
    values = [
        row["expected_retention"].values()
        for row in labels.values()
        if row.get("kind") == "retention"
    ]
    targets = [value == "keep" for group in values for value in group]
    prevalence = sum(targets) / len(targets) if targets else 0.0
    baseline_brier = statistics.mean((prevalence - float(expected)) ** 2 for expected, _ in rows)
    calibrated = ece <= PROBABILITY_ECE_MAX and brier < baseline_brier
    return {
        "status": "calibrated" if calibrated else "uncalibrated",
        "count": len(rows),
        "brier_score": brier,
        "ece_10_bins": ece,
        "prevalence_baseline_brier_score": baseline_brier,
        "passes_thresholds": calibrated,
    }


def _combined_calibration(
    decision: dict[str, Any], retention: dict[str, Any]
) -> dict[str, Any]:
    claimed = [
        result["status"]
        for result in (decision, retention)
        if result["status"] != "not-claimed"
    ]
    status = (
        "not-claimed"
        if not claimed
        else "calibrated"
        if all(item == "calibrated" for item in claimed)
        else "uncalibrated"
    )
    return {
        "status": status,
        "passes_thresholds": bool(claimed) and status == "calibrated",
        "decision": decision,
        "retention": retention,
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _read_token_counts(
    inputs: dict[str, dict[str, Any]], token_counts_path: Path, measurements: dict[str, Any]
) -> dict[str, int]:
    rows = _read_jsonl(token_counts_path)
    if any(
        not isinstance(row.get("token_count"), int)
        or isinstance(row.get("token_count"), bool)
        for row in rows
    ):
        raise EvaluationError("token counts must be integers emitted by the candidate tokenizer")
    indexed = _unique_index(
        [{"id": row.get("message_id"), "token_count": row.get("token_count")} for row in rows],
        "token counts",
    )
    token_counts = {message_id: row["token_count"] for message_id, row in indexed.items()}
    expected_ids = {
        message["id"]
        for row in inputs.values()
        if row.get("kind") == "retention"
        for message in row["eligible_messages_oldest_first"]
    }
    if set(token_counts) != expected_ids:
        raise EvaluationError("token counts do not exactly match the frozen retention message IDs")
    revision = measurements.get("tokenizer_revision")
    if (
        not isinstance(measurements.get("tokenizer_id"), str)
        or not measurements["tokenizer_id"]
        or not isinstance(revision, str)
        or len(revision) != 40
    ):
        raise EvaluationError("exact tokenizer ID and immutable revision are required")
    return token_counts


def _operation_metrics(measurements: dict[str, Any]) -> dict[str, Any]:
    warm = measurements.get("warm_latency_ms", [])
    if not isinstance(warm, list) or not warm or not all(
        _finite_number(value) and value >= 0 for value in warm
    ):
        raise EvaluationError("warm latency measurements must be a non-empty list")
    cold = measurements.get("cold_latency_ms")
    if not _finite_number(cold) or cold < 0:
        raise EvaluationError("cold_latency_ms must be a non-negative measurement")
    peak_rss = measurements.get("peak_rss_bytes")
    if not isinstance(peak_rss, int) or isinstance(peak_rss, bool) or peak_rss < 0:
        raise EvaluationError("peak_rss_bytes must be a non-negative integer")
    if not isinstance(measurements.get("oom"), bool):
        raise EvaluationError("oom must be a boolean measurement")
    return {
        "cold_latency_ms": cold,
        "warm_latency_ms": {"p50": _percentile(warm, 0.50), "p95": _percentile(warm, 0.95)},
        "peak_rss_bytes": peak_rss,
        "oom": measurements["oom"],
        "passes_thresholds": not measurements["oom"] and peak_rss <= PEAK_MEMORY_MAX_BYTES,
    }


def evaluate_candidate(
    *,
    inputs_path: Path,
    labels_path: Path,
    predictions_path: Path,
    token_counts_path: Path,
    measurements: dict[str, Any],
) -> dict[str, Any]:
    """Score externally generated outputs against the frozen synthetic set."""

    verify_fixture_hashes(inputs_path, labels_path)
    inputs = _unique_index(_read_jsonl(inputs_path), "inputs")
    labels = _unique_index(_read_jsonl(labels_path), "labels")
    predictions = _unique_index(_read_jsonl(predictions_path), "predictions")
    if set(inputs) != set(labels):
        raise EvaluationError("input and label ids do not match")
    if set(predictions) - set(inputs):
        raise EvaluationError("predictions contain IDs outside the frozen input set")
    token_counts = _read_token_counts(inputs, token_counts_path, measurements)
    decisions, probability_rows = _decision_metrics(inputs, labels, predictions)
    retention, retention_probability_rows = _retention_metrics(
        inputs, labels, predictions, token_counts
    )
    calibration = _combined_calibration(
        _calibration_metrics(labels, probability_rows),
        _retention_calibration_metrics(labels, retention_probability_rows),
    )
    operations = _operation_metrics(measurements)
    return {
        "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "input_sha256": DMS01_INPUTS_SHA256,
        "labels_sha256": DMS01_LABELS_SHA256,
        "candidate": {
            key: measurements.get(key)
            for key in (
                "model_id",
                "artifact_revision",
                "base_model_id",
                "base_revision",
                "harness_id",
                "harness_revision",
                "runtime",
                "runtime_lock_sha256",
                "device",
                "precision",
                "tokenizer_id",
                "tokenizer_revision",
                "model_server",
            )
        },
        "decision": decisions,
        "retention": retention,
        "calibration": calibration,
        "operations": operations,
    }


def write_redacted_receipt(report: dict[str, Any], destination: Path) -> None:
    """Write aggregate-only evidence; source rows and raw scores are omitted."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare-inputs")
    prepare.add_argument("--output", type=Path, required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--output", type=Path, required=True)
    preflight.add_argument("--artifact", action="append", required=True, metavar="ID@REVISION")
    preflight.add_argument("--harness-id", required=True)
    preflight.add_argument("--harness-revision", required=True)
    preflight.add_argument("--runtime-id", required=True)
    preflight.add_argument("--runtime-executable", type=Path, required=True)
    preflight.add_argument("--runtime-python-version", required=True)
    preflight.add_argument("--runtime-package", action="append", required=True, metavar="NAME=VERSION")
    preflight.add_argument("--runtime-lock-sha256", required=True)
    preflight.add_argument("--accelerator-status", required=True)
    preflight.add_argument(
        "--execution-mode",
        choices=("external_research_harness", "dar_admitted_runner"),
        required=True,
    )
    preflight.add_argument("--dar-profile-id")
    preflight.add_argument("--storage-path", type=Path, required=True)
    preflight.add_argument("--required-free-bytes", type=int, required=True)
    preflight.add_argument("--fixture-criteria-approved", action="store_true")
    preflight.add_argument("--runner-harness", type=Path)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--predictions", type=Path, required=True)
    evaluate.add_argument("--token-counts", type=Path, required=True)
    evaluate.add_argument("--measurements", type=Path, required=True)
    evaluate.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "prepare-inputs":
            digest = prepare_candidate_inputs(EVALUATION_DIR / "dms01-inputs.jsonl", arguments.output)
            print(json.dumps({"input_sha256": digest, "output": str(arguments.output)}))
            return 0
        if arguments.command == "preflight":
            artifacts = []
            for specification in arguments.artifact:
                artifact_id, separator, revision = specification.rpartition("@")
                if not separator:
                    raise EvaluationError("artifact must use ID@REVISION")
                artifacts.append({"id": artifact_id, "revision": revision})
            packages = {}
            for specification in arguments.runtime_package:
                name, separator, version = specification.partition("=")
                if not separator:
                    raise EvaluationError("runtime package must use NAME=VERSION")
                packages[name] = version
            receipt = create_preflight_receipt(
                artifacts=artifacts,
                harness_id=arguments.harness_id,
                harness_revision=arguments.harness_revision,
                runtime_id=arguments.runtime_id,
                runtime_executable=arguments.runtime_executable,
                runtime_python_version=arguments.runtime_python_version,
                runtime_packages=packages,
                runtime_lock_sha256=arguments.runtime_lock_sha256,
                accelerator_status=arguments.accelerator_status,
                execution_mode=arguments.execution_mode,
                storage_path=arguments.storage_path,
                required_free_bytes=arguments.required_free_bytes,
                fixture_criteria_approved=arguments.fixture_criteria_approved,
                dar_profile_id=arguments.dar_profile_id,
                runner_harness=arguments.runner_harness,
            )
            write_preflight_receipt(receipt, arguments.output)
            print(json.dumps({"receipt": str(arguments.output), "run_allowed": receipt["run_allowed"]}))
            return 0 if receipt["run_allowed"] else 2
        report = evaluate_candidate(
            inputs_path=EVALUATION_DIR / "dms01-inputs.jsonl",
            labels_path=EVALUATION_DIR / "dms01-labels.jsonl",
            predictions_path=arguments.predictions,
            token_counts_path=arguments.token_counts,
            measurements=_read_json_object(arguments.measurements),
        )
        write_redacted_receipt(report, arguments.receipt)
        print(json.dumps({"receipt": str(arguments.receipt), "report": report}, sort_keys=True))
        return 0
    except (EvaluationError, OSError, ValueError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
