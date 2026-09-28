#!/usr/bin/env python3
"""Normalize and score a frozen DMS-14 typed-decision corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


class TransferEvaluationError(ValueError):
    """Raised when corpus rows or candidate outputs violate the DMS-14 protocol."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return _sha256(path)


def _unique_index(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = row.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in indexed:
            raise TransferEvaluationError(f"{field} contains a missing or duplicate id")
        indexed[item_id] = row
    return indexed


def normalize_corpus(
    source_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert Kev typed questions to choice inputs and a separate gold file."""

    inputs: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in source_rows:
        meta = row.get("_meta")
        questions = row.get("questions")
        if not isinstance(meta, dict) or not isinstance(questions, dict) or len(questions) != 1:
            raise TransferEvaluationError("each corpus row must have one question and source metadata")
        item_id = meta.get("id")
        category = meta.get("source")
        if not isinstance(item_id, str) or not item_id or item_id in seen:
            raise TransferEvaluationError("corpus contains a missing or duplicate item id")
        if not isinstance(category, str) or not category:
            raise TransferEvaluationError("corpus item has no source category")
        seen.add(item_id)
        question_id, question = next(iter(questions.items()))
        if not isinstance(question_id, str) or not isinstance(question, dict):
            raise TransferEvaluationError("corpus question is malformed")
        prompt, task_type, options, expected = _normalize_question(question)
        inputs.append(
            {
                "id": item_id,
                "category": category,
                "kind": "decision",
                "state": row.get("state"),
                "question": {
                    "id": question_id,
                    "text": prompt,
                    "options": options,
                },
            }
        )
        labels.append(
            {
                "id": item_id,
                "category": category,
                "expected_choice": expected,
                "source_type": task_type,
            }
        )
    if not inputs:
        raise TransferEvaluationError("corpus split is empty")
    return inputs, labels


def _normalize_question(
    question: dict[str, Any],
) -> tuple[str, str, list[dict[str, str]], str]:
    prompt = question.get("instructions")
    task_type = question.get("type")
    criteria = question.get("criteria")
    label = question.get("label")
    if not isinstance(prompt, str) or not prompt.strip():
        raise TransferEvaluationError("corpus question has no instructions")
    if task_type in {"choice", "noul"} and isinstance(criteria, dict):
        if any(value is not None and not isinstance(value, str) for value in criteria.values()):
            raise TransferEvaluationError("corpus option description has an unsupported type")
        options = [
            {"id": key, "label": value if value is not None else key}
            for key, value in criteria.items()
        ]
        expected = str(label).lower() if task_type == "noul" else label
    elif task_type == "noul" and criteria is None:
        options = [{"id": "true", "label": "Yes"}, {"id": "false", "label": "No"}]
        expected = str(label).lower()
    elif task_type == "score" and isinstance(criteria, list):
        options = [{"id": str(index), "label": value} for index, value in enumerate(criteria)]
        expected = str(label)
    else:
        raise TransferEvaluationError("corpus task type cannot map to the choice contract")
    option_ids = {option["id"] for option in options}
    if (
        len(options) < 2
        or any(not isinstance(option["id"], str) or not option["id"] for option in options)
        or any(not isinstance(option["label"], str) or not option["label"] for option in options)
        or len(option_ids) != len(options)
        or expected not in option_ids
    ):
        raise TransferEvaluationError("corpus options or gold label are invalid")
    return prompt, task_type, options, expected


def prepare_corpus(
    source_path: Path,
    upstream_manifest_path: Path,
    corpus_manifest_path: Path,
    inputs_path: Path,
    labels_path: Path,
) -> dict[str, Any]:
    """Verify the pinned development split and emit label-separated JSONL."""

    manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    upstream_digest = _sha256(upstream_manifest_path)
    raw_digest = _sha256(source_path)
    if upstream_digest != manifest.get("upstream_manifest_sha256"):
        raise TransferEvaluationError("upstream corpus manifest digest differs")
    if raw_digest != manifest.get("raw_split_sha256"):
        raise TransferEvaluationError("raw development split digest differs")
    upstream_manifest = json.loads(upstream_manifest_path.read_text(encoding="utf-8"))
    if upstream_manifest.get("files", {}).get(source_path.name, {}).get("sha256") != raw_digest:
        raise TransferEvaluationError("upstream manifest does not verify the development split")
    rows = _read_jsonl(source_path)
    excluded_categories = manifest.get("excluded_categories", {})
    if not isinstance(excluded_categories, dict) or any(
        not isinstance(category, str)
        or not category
        or not isinstance(reason, str)
        or not reason
        for category, reason in excluded_categories.items()
    ):
        raise TransferEvaluationError("excluded categories need explicit reasons")
    excluded_rows = [
        row for row in rows
        if isinstance(row.get("_meta"), dict)
        and row["_meta"].get("source") in excluded_categories
    ]
    observed_excluded_counts = dict(
        sorted(Counter(row["_meta"]["source"] for row in excluded_rows).items())
    )
    expected_excluded_counts = manifest.get("excluded_category_counts", {})
    if observed_excluded_counts != expected_excluded_counts:
        raise TransferEvaluationError("excluded source category counts differ")
    excluded_id_digests = {
        category: hashlib.sha256(
            "\n".join(
                sorted(
                    row["_meta"]["id"]
                    for row in excluded_rows
                    if row["_meta"].get("source") == category
                )
            ).encode("utf-8")
        ).hexdigest()
        for category in sorted(excluded_categories)
    }
    if excluded_id_digests != manifest.get("excluded_id_sha256", {}):
        raise TransferEvaluationError("excluded source item identity differs")
    included_rows = [row for row in rows if row not in excluded_rows]
    inputs, labels = normalize_corpus(included_rows)
    expected_counts = manifest.get("category_counts")
    actual_counts = dict(sorted(Counter(row["category"] for row in inputs).items()))
    if len(inputs) != manifest.get("item_count") or actual_counts != expected_counts:
        raise TransferEvaluationError("development split item count or task categories differ")
    input_digest = _write_jsonl(inputs_path, inputs)
    labels_digest = _write_jsonl(labels_path, labels)
    if manifest.get("normalized_input_sha256") not in {None, input_digest}:
        raise TransferEvaluationError("normalized input digest differs from the corpus manifest")
    if manifest.get("gold_label_sha256") not in {None, labels_digest}:
        raise TransferEvaluationError("gold label digest differs from the corpus manifest")
    return {
        "corpus_id": manifest["corpus_id"],
        "upstream_revision": manifest["upstream_revision"],
        "split": manifest["split"],
        "raw_split_sha256": raw_digest,
        "normalized_input_sha256": input_digest,
        "gold_label_sha256": labels_digest,
        "item_count": len(inputs),
        "category_counts": actual_counts,
        "excluded_category_counts": observed_excluded_counts,
        "excluded_id_sha256": excluded_id_digests,
        "inputs_path": str(inputs_path),
        "labels_path": str(labels_path),
        "license_review_status": manifest.get("license_review_status", "unreviewed"),
    }


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _valid_scores(prediction: dict[str, Any], option_ids: set[str]) -> dict[str, float] | None:
    if prediction.get("score_semantics") not in {"probability", "calibrated_probability"}:
        return None
    scores = prediction.get("scores")
    if not isinstance(scores, dict) or set(scores) != option_ids:
        return None
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or value > 1
        for value in scores.values()
    ):
        return None
    if not math.isclose(sum(scores.values()), 1.0, abs_tol=1e-4):
        return None
    return {key: float(value) for key, value in scores.items()}


def _calibration(
    inputs: dict[str, dict[str, Any]],
    labels: dict[str, dict[str, Any]],
    indexed_predictions: dict[tuple[str, str], dict[str, Any]],
    common_probability_ids: set[str],
) -> dict[str, Any]:
    brier_by_category: dict[str, list[float]] = defaultdict(list)
    confidence: list[tuple[float, bool]] = []
    for item_id in sorted(common_probability_ids):
        input_row = inputs[item_id]
        prediction = indexed_predictions.get((item_id, "canonical"))
        if not prediction or prediction.get("status") != "ok":
            continue
        option_ids = {option["id"] for option in input_row["question"]["options"]}
        scores = _valid_scores(prediction, option_ids)
        if scores is None or prediction.get("choice") not in option_ids:
            continue
        expected = labels[item_id]["expected_choice"]
        brier_by_category[input_row["category"]].append(
            sum((value - float(option_id == expected)) ** 2 for option_id, value in scores.items())
        )
        top = max(scores, key=scores.get)
        confidence.append((scores[top], prediction["choice"] == expected))
    count = len(confidence)
    if not count:
        return {"status": "unavailable; no common comparable probability outputs", "n": 0}
    bins = [[] for _ in range(10)]
    for value in confidence:
        bins[min(int(value[0] * 10), 9)].append(value)
    ece = sum(
        len(bucket)
        / count
        * abs(
            sum(correct for _, correct in bucket) / len(bucket)
            - sum(score for score, _ in bucket) / len(bucket)
        )
        for bucket in bins
        if bucket
    )
    return {
        "status": "available; raw outputs only, calibration not fitted",
        "n": count,
        "macro_multiclass_brier": sum(
            sum(values) / len(values) for values in brier_by_category.values()
        )
        / len(brier_by_category),
        "top_label_ece_10_bins": ece,
    }


def _common_probability_ids(
    inputs: dict[str, dict[str, Any]],
    matrix: dict[str, dict[tuple[str, str], dict[str, Any]]],
) -> set[str]:
    common = set()
    for item_id, input_row in inputs.items():
        option_ids = {option["id"] for option in input_row["question"]["options"]}
        semantics = set()
        for indexed in matrix.values():
            prediction = indexed.get((item_id, "canonical"))
            if (
                prediction is None
                or prediction.get("status") != "ok"
                or prediction.get("choice") not in option_ids
                or prediction.get("score_semantics") not in {"probability", "calibrated_probability"}
                or _valid_scores(prediction, option_ids) is None
            ):
                break
            scores = _valid_scores(prediction, option_ids)
            if max(scores, key=scores.get) != prediction.get("choice"):
                break
            semantics.add(prediction["score_semantics"])
        else:
            if len(semantics) == 1:
                common.add(item_id)
    return common


def _index_predictions(
    inputs: dict[str, dict[str, Any]],
    candidate_predictions: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[tuple[str, str], dict[str, Any]]]:
    matrix = {}
    for candidate, predictions in candidate_predictions.items():
        if not candidate.strip():
            raise TransferEvaluationError("candidate key is empty")
        indexed = {}
        for prediction in predictions:
            key = (prediction.get("id"), prediction.get("option_order"))
            if key[0] not in inputs or key[1] not in {"canonical", "reversed"}:
                raise TransferEvaluationError("prediction references an unknown item or option order")
            if key in indexed:
                raise TransferEvaluationError("predictions contain a duplicate item/order pair")
            indexed[key] = prediction
        matrix[candidate] = indexed
    return matrix


def _score_order(
    *,
    item_ids: dict[str, list[str]],
    indexed: dict[tuple[str, str], dict[str, Any]],
    option_ids: dict[str, set[str]],
    expected_by_id: dict[str, str],
    order: str,
    correctness: dict[tuple[str, str], int],
) -> dict[str, Any]:
    task_report = {}
    status_counts: Counter[str] = Counter()
    successes = count = 0
    for category, ids in item_ids.items():
        right = 0
        for item_id in ids:
            prediction = indexed.get((item_id, order))
            status = "missing" if prediction is None else prediction.get("status", "invalid")
            choice = prediction.get("choice") if prediction else None
            if status == "ok" and choice not in option_ids[item_id]:
                status = "invalid"
            if (
                status == "ok"
                and prediction is not None
                and prediction.get("score_semantics") in {"probability", "calibrated_probability"}
                and _valid_scores(prediction, option_ids[item_id]) is None
            ):
                status = "invalid"
            if (
                status == "ok"
                and prediction is not None
                and prediction.get("score_semantics") in {"probability", "calibrated_probability"}
                and prediction.get("choice")
                != max(prediction["scores"], key=prediction["scores"].get)
            ):
                status = "invalid"
            correct = int(status == "ok" and choice == expected_by_id[item_id])
            status_counts[status] += 1
            correctness[(item_id, order)] = correct
            right += correct
        task_report[category] = {"correct": right, "total": len(ids), "accuracy": right / len(ids)}
        successes += right
        count += len(ids)
    return {
        "correct": successes,
        "total": count,
        "accuracy": successes / count,
        "macro_accuracy": sum(row["accuracy"] for row in task_report.values()) / len(task_report),
        "by_category": task_report,
        "status_counts": dict(sorted(status_counts.items())),
    }


def _option_order_report(
    indexed: dict[tuple[str, str], dict[str, Any]], input_ids: set[str]
) -> dict[str, Any]:
    paired = [
        item_id
        for item_id in input_ids
        if indexed.get((item_id, "canonical"), {}).get("status") == "ok"
        and indexed.get((item_id, "reversed"), {}).get("status") == "ok"
    ]
    flips = sum(
        indexed[(item_id, "canonical")].get("choice")
        != indexed[(item_id, "reversed")].get("choice")
        for item_id in paired
    )
    return {
        "paired_valid_items": len(paired),
        "choice_flips": flips,
        "flip_rate": flips / len(paired) if paired else None,
    }


def _bootstrap_results(
    matrix: dict[str, dict[tuple[str, str], dict[str, Any]]],
    correctness: dict[str, dict[tuple[str, str], int]],
    task_ids: dict[str, list[str]],
    *,
    resamples: int,
    seed: int,
) -> tuple[str, dict[str, float], dict[str, list[float]]]:
    point_scores = {
        candidate: sum(
            sum(correctness[candidate][(item_id, "canonical")] for item_id in ids) / len(ids)
            for ids in task_ids.values()
        )
        / len(task_ids)
        for candidate in matrix
    }
    leader = max(point_scores, key=point_scores.get)
    rng = random.Random(seed)
    accuracy_draws = {candidate: [] for candidate in matrix}
    for _ in range(resamples):
        samples = {
            category: [rng.choice(ids) for _ in ids] for category, ids in task_ids.items()
        }
        scores = {
            candidate: sum(
                sum(correctness[candidate][(item_id, "canonical")] for item_id in sample)
                / len(sample)
                for sample in samples.values()
            )
            / len(task_ids)
            for candidate in matrix
        }
        for candidate, score in scores.items():
            accuracy_draws[candidate].append(score)
    return leader, point_scores, accuracy_draws


def evaluate_matrix(
    input_rows: list[dict[str, Any]],
    label_rows: list[dict[str, Any]],
    candidate_predictions: dict[str, list[dict[str, Any]]],
    *,
    bootstrap_resamples: int = 10_000,
    bootstrap_seed: int = 14,
) -> dict[str, Any]:
    """Score canonical/reversed predictions and paired task-stratified intervals."""
    if bootstrap_resamples < 1 or not candidate_predictions:
        raise TransferEvaluationError("bootstrap count and candidate matrix must be non-empty")
    inputs = _unique_index(input_rows, "inputs")
    labels = _unique_index(label_rows, "labels")
    if inputs.keys() != labels.keys():
        raise TransferEvaluationError("input and label item IDs differ")
    if any(labels[item_id].get("category") != inputs[item_id].get("category") for item_id in inputs):
        raise TransferEvaluationError("input and label categories differ")
    categories = sorted({row["category"] for row in input_rows})
    option_ids = {
        item_id: {item["id"] for item in row["question"]["options"]}
        for item_id, row in inputs.items()
    }
    matrix = _index_predictions(inputs, candidate_predictions)
    common_probability_ids = _common_probability_ids(inputs, matrix)
    expected_by_id = {item_id: labels[item_id]["expected_choice"] for item_id in inputs}
    task_ids = {
        category: [item_id for item_id, row in inputs.items() if row["category"] == category]
        for category in categories
    }
    candidate_reports = {}
    correctness = {}
    for candidate, indexed in matrix.items():
        correctness[candidate] = {}
        section = {
            order: _score_order(
                item_ids=task_ids,
                indexed=indexed,
                option_ids=option_ids,
                expected_by_id=expected_by_id,
                order=order,
                correctness=correctness[candidate],
            )
            for order in ("canonical", "reversed")
        }
        section["option_order"] = _option_order_report(indexed, set(inputs))
        section["calibration"] = _calibration(
            inputs, labels, indexed, common_probability_ids
        )
        candidate_reports[candidate] = section

    top_candidate, point_scores, accuracy_draws = _bootstrap_results(
        matrix,
        correctness,
        task_ids,
        resamples=bootstrap_resamples,
        seed=bootstrap_seed,
    )
    paired = {}
    for candidate in matrix:
        for comparison in matrix:
            if candidate == comparison:
                continue
            deltas = [
                candidate_score - comparison_score
                for candidate_score, comparison_score in zip(
                    accuracy_draws[candidate], accuracy_draws[comparison], strict=True
                )
            ]
            paired[f"{candidate}_vs_{comparison}"] = {
                "macro_accuracy_difference": point_scores[candidate]
                - point_scores[comparison],
                "bootstrap_95": {
                    "lower": _percentile(deltas, 0.025),
                    "upper": _percentile(deltas, 0.975),
                },
            }
    for candidate in matrix:
        candidate_reports[candidate]["canonical"]["macro_accuracy_bootstrap_95"] = {
            "lower": _percentile(accuracy_draws[candidate], 0.025),
            "upper": _percentile(accuracy_draws[candidate], 0.975),
        }
    result = {
        "candidates": candidate_reports,
        "paired_bootstrap": paired,
        "protocol": {
        "task_categories": categories,
        "item_count": len(inputs),
        "option_orders": ["canonical", "reversed"],
        "primary_metric": "equally weighted macro accuracy on canonical option order",
        "invalid_missing_and_abstaining_are_incorrect": True,
        "bootstrap_resamples": bootstrap_resamples,
        "bootstrap_seed": bootstrap_seed,
            "bootstrap_stratification": "item IDs sampled with replacement within task; shared samples across candidates",
            "common_probability_item_count": len(common_probability_ids),
        "point_leader": top_candidate,
        },
    }
    result["ranking"] = [
        {"rank": rank, "candidate": name, "macro_accuracy": point_scores[name]}
        for rank, name in enumerate(
            sorted(point_scores, key=point_scores.get, reverse=True), start=1
        )
    ]
    return result


def write_redacted_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TransferEvaluationError(f"invalid JSONL at {path.name}:{line_number}") from exc
        if not isinstance(row, dict):
            raise TransferEvaluationError(f"expected an object at {path.name}:{line_number}")
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--upstream-manifest", type=Path, required=True)
    prepare.add_argument("--corpus-manifest", type=Path, required=True)
    prepare.add_argument("--inputs", type=Path, required=True)
    prepare.add_argument("--labels", type=Path, required=True)
    prepare.add_argument("--receipt", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--inputs", type=Path, required=True)
    evaluate.add_argument("--labels", type=Path, required=True)
    evaluate.add_argument("--predictions", action="append", required=True, metavar="ID=JSONL")
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--bootstrap-seed", type=int, required=True)
    evaluate.add_argument("--bootstrap-resamples", type=int, default=10_000)
    arguments = parser.parse_args()
    try:
        if arguments.command == "prepare":
            receipt = prepare_corpus(
                arguments.source,
                arguments.upstream_manifest,
                arguments.corpus_manifest,
                arguments.inputs,
                arguments.labels,
            )
            arguments.receipt.parent.mkdir(parents=True, exist_ok=True)
            arguments.receipt.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        else:
            predictions = {}
            for item in arguments.predictions:
                candidate, separator, path = item.partition("=")
                if not separator or candidate in predictions:
                    raise TransferEvaluationError("candidate predictions must use unique ID=JSONL values")
                predictions[candidate] = _read_jsonl(Path(path))
            report = evaluate_matrix(
                _read_jsonl(arguments.inputs),
                _read_jsonl(arguments.labels),
                predictions,
                bootstrap_resamples=arguments.bootstrap_resamples,
                bootstrap_seed=arguments.bootstrap_seed,
            )
            write_redacted_report(report, arguments.output)
    except (OSError, TransferEvaluationError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
