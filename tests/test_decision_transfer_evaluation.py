"""Fake-corpus tests for the DMS-14 transfer evaluator."""

from __future__ import annotations

import json
import hashlib
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluate_decision_transfer import (
    TransferEvaluationError,
    evaluate_matrix,
    normalize_corpus,
    prepare_corpus,
    write_redacted_report,
)


def _corpus_rows() -> list[dict[str, object]]:
    return [
        {
            "state": {"case": "alpha"},
            "questions": {
                "answer": {
                    "type": "choice",
                    "instructions": "Select one.",
                    "criteria": {"a": "A", "b": "B"},
                    "label": "a",
                }
            },
            "_meta": {"id": "choice/1", "source": "choice-family"},
        },
        {
            "state": "binary example",
            "questions": {
                "answer": {
                    "type": "noul",
                    "instructions": "Is it true?",
                    "criteria": {"true": "Yes", "false": "No"},
                    "label": True,
                }
            },
            "_meta": {"id": "binary/1", "source": "binary-family"},
        },
        {
            "state": {"case": "ordinal"},
            "questions": {
                "answer": {
                    "type": "score",
                    "instructions": "Choose a level.",
                    "criteria": ["low", "medium", "high"],
                    "label": 2,
                }
            },
            "_meta": {"id": "ordinal/1", "source": "ordinal-family"},
        },
    ]


def _predictions(
    inputs: list[dict[str, object]], *, reverse: bool = False
) -> list[dict[str, object]]:
    result = []
    expected_by_id = {"choice/1": "a", "binary/1": "true", "ordinal/1": "2"}
    for row in inputs:
        question = row["question"]
        options = question["options"]
        expected = expected_by_id[row["id"]]
        if reverse:
            expected = next(option["id"] for option in options if option["id"] != expected)
        result.append(
            {
                "id": row["id"],
                "option_order": "reversed" if reverse else "canonical",
                "status": "ok",
                "choice": expected,
                "score_semantics": "probability",
                "scores": {option["id"]: 1.0 if option["id"] == expected else 0.0 for option in options},
            }
        )
    return result


def test_normalization_separates_gold_labels_and_maps_all_task_types() -> None:
    inputs, labels = normalize_corpus(_corpus_rows())

    assert [row["category"] for row in inputs] == [
        "choice-family",
        "binary-family",
        "ordinal-family",
    ]
    assert [row["expected_choice"] for row in labels] == ["a", "true", "2"]
    assert inputs[1]["question"]["options"] == [
        {"id": "true", "label": "Yes"},
        {"id": "false", "label": "No"},
    ]
    assert inputs[2]["question"]["options"][-1] == {"id": "2", "label": "high"}
    serialized_inputs = json.dumps(inputs)
    assert "label\": \"a\"" not in serialized_inputs
    assert "expected_choice" not in serialized_inputs
    assert "_meta" not in serialized_inputs


def test_normalization_rejects_unknown_or_malformed_task_mappings() -> None:
    rows = _corpus_rows()
    rows[0]["questions"]["answer"]["label"] = "missing"

    with pytest.raises(TransferEvaluationError, match="label"):
        normalize_corpus(rows)


def test_prepare_verifies_both_source_hashes_and_writes_separate_labels(
    tmp_path: Path,
) -> None:
    source = tmp_path / "development.jsonl"
    upstream = tmp_path / "upstream-manifest.json"
    corpus_manifest = tmp_path / "dms14-manifest.json"
    inputs_path = tmp_path / "inputs.jsonl"
    labels_path = tmp_path / "labels.jsonl"
    source.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in _corpus_rows()),
        encoding="utf-8",
    )
    raw_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    upstream.write_text(
        json.dumps({"files": {source.name: {"sha256": raw_hash}}}),
        encoding="utf-8",
    )
    upstream_hash = hashlib.sha256(upstream.read_bytes()).hexdigest()
    corpus_manifest.write_text(
        json.dumps(
            {
                "corpus_id": "fake/transfer",
                "upstream_revision": "a" * 40,
                "split": "development",
                "raw_split_sha256": raw_hash,
                "upstream_manifest_sha256": upstream_hash,
                "item_count": 3,
                "category_counts": {
                    "binary-family": 1,
                    "choice-family": 1,
                    "ordinal-family": 1,
                },
                "license_review_status": "test-fixture",
            }
        ),
        encoding="utf-8",
    )

    receipt = prepare_corpus(source, upstream, corpus_manifest, inputs_path, labels_path)

    assert receipt["item_count"] == 3
    assert receipt["raw_split_sha256"] == raw_hash
    assert "expected_choice" not in inputs_path.read_text()
    assert "binary example" not in labels_path.read_text()


def test_prepare_rejects_raw_split_that_differs_from_pinned_digest(tmp_path: Path) -> None:
    source = tmp_path / "development.jsonl"
    upstream = tmp_path / "upstream-manifest.json"
    corpus_manifest = tmp_path / "dms14-manifest.json"
    source.write_text("{}\n", encoding="utf-8")
    upstream.write_text(json.dumps({"files": {"development": {"sha256": "0" * 64}}}))
    corpus_manifest.write_text(
        json.dumps(
            {
                "corpus_id": "fake/transfer",
                "upstream_revision": "a" * 40,
                "split": "development",
                "raw_split_sha256": "0" * 64,
                "upstream_manifest_sha256": hashlib.sha256(upstream.read_bytes()).hexdigest(),
                "item_count": 0,
                "category_counts": {},
            }
        )
    )

    with pytest.raises(TransferEvaluationError, match="raw development split digest"):
        prepare_corpus(
            source,
            upstream,
            corpus_manifest,
            tmp_path / "inputs.jsonl",
            tmp_path / "labels.jsonl",
        )


def test_prepare_excludes_manifest_categories_before_normalizing(tmp_path: Path) -> None:
    source = tmp_path / "development.jsonl"
    upstream = tmp_path / "upstream-manifest.json"
    corpus_manifest = tmp_path / "dms14-manifest.json"
    rows = _corpus_rows()
    rows.append(
        {
            "_meta": {"id": "excluded-item", "source": "tweet_offensive"},
            "state": "private tweet text must not be normalized",
            "questions": {
                "answer": {
                    "instructions": "Is it offensive?",
                    "type": "noul",
                    "criteria": None,
                    "label": True,
                }
            },
        }
    )
    source.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    raw_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    upstream.write_text(
        json.dumps({"files": {source.name: {"sha256": raw_hash}}}), encoding="utf-8"
    )
    upstream_hash = hashlib.sha256(upstream.read_bytes()).hexdigest()
    selected_inputs, _ = normalize_corpus(rows[:-1])
    corpus_manifest.write_text(
        json.dumps(
            {
                "corpus_id": "fake/transfer",
                "upstream_revision": "a" * 40,
                "split": "development",
                "raw_split_sha256": raw_hash,
                "upstream_manifest_sha256": upstream_hash,
                "item_count": len(selected_inputs),
                "category_counts": dict(
                    sorted(Counter(row["category"] for row in selected_inputs).items())
                ),
                "normalized_input_sha256": None,
                "gold_label_sha256": None,
                "excluded_categories": {"tweet_offensive": "explicit source exclusion"},
                "excluded_category_counts": {"tweet_offensive": 1},
                "excluded_id_sha256": {
                    "tweet_offensive": hashlib.sha256(b"excluded-item").hexdigest()
                },
                "license_review_status": "test-fixture",
            }
        ),
        encoding="utf-8",
    )

    receipt = prepare_corpus(
        source, upstream, corpus_manifest,
        tmp_path / "inputs.jsonl", tmp_path / "labels.jsonl"
    )

    assert receipt["item_count"] == len(selected_inputs)
    assert "tweet_offensive" not in receipt["category_counts"]
    assert "excluded-item" not in (tmp_path / "inputs.jsonl").read_text()
    assert "private tweet text" not in (tmp_path / "inputs.jsonl").read_text()


def test_matrix_scores_macro_accuracy_order_effect_and_paired_intervals() -> None:
    inputs, labels = normalize_corpus(_corpus_rows())
    predictions = _predictions(inputs)
    candidate_predictions = {
        "candidate-a": predictions + _predictions(inputs, reverse=True),
        "candidate-b": [
            *predictions[1:],
            *[dict(row, option_order="reversed") for row in _predictions(inputs, reverse=True)[1:]],
        ],
    }

    report = evaluate_matrix(
        inputs,
        labels,
        candidate_predictions,
        bootstrap_resamples=100,
        bootstrap_seed=19,
    )

    assert report["protocol"]["bootstrap_resamples"] == 100
    assert report["candidates"]["candidate-a"]["canonical"]["macro_accuracy"] == 1.0
    assert report["candidates"]["candidate-a"]["option_order"]["flip_rate"] == 1.0
    assert report["candidates"]["candidate-b"]["canonical"]["status_counts"]["missing"] == 1
    assert report["candidates"]["candidate-b"]["canonical"]["macro_accuracy"] < 1.0
    assert report["paired_bootstrap"]["candidate-b_vs_candidate-a"]["macro_accuracy_difference"]
    assert report["paired_bootstrap"]["candidate-a_vs_candidate-b"]["macro_accuracy_difference"]
    assert report["candidates"]["candidate-a"]["calibration"]["n"] == 2
    assert report["candidates"]["candidate-b"]["calibration"]["n"] == 2


def test_evaluation_receipt_is_aggregate_only(tmp_path: Path) -> None:
    inputs, labels = normalize_corpus(_corpus_rows())
    report = evaluate_matrix(
        inputs,
        labels,
        {"candidate-a": _predictions(inputs) + _predictions(inputs, reverse=True)},
        bootstrap_resamples=20,
        bootstrap_seed=1,
    )
    path = tmp_path / "report.json"

    write_redacted_report(report, path)

    serialized = path.read_text()
    assert "alpha" not in serialized
    assert "binary example" not in serialized
    assert "Select one." not in serialized
    assert report["candidates"]["candidate-a"]["calibration"]["status"].startswith("available")


def test_calibration_uses_only_common_items_with_matching_probability_semantics() -> None:
    inputs, labels = normalize_corpus(_corpus_rows())
    probabilities = _predictions(inputs)
    calibrated = [dict(row, score_semantics="calibrated_probability") for row in probabilities]

    report = evaluate_matrix(
        inputs,
        labels,
        {
            "candidate-a": probabilities + _predictions(inputs, reverse=True),
            "candidate-b": calibrated
            + [dict(row, option_order="reversed", score_semantics="calibrated_probability")
               for row in _predictions(inputs, reverse=True)],
        },
        bootstrap_resamples=10,
        bootstrap_seed=2,
    )

    assert report["protocol"]["common_probability_item_count"] == 0
    assert report["candidates"]["candidate-a"]["calibration"]["n"] == 0
    assert report["candidates"]["candidate-b"]["calibration"]["n"] == 0


def test_probability_result_with_non_argmax_choice_is_invalid() -> None:
    inputs, labels = normalize_corpus(_corpus_rows())
    predictions = _predictions(inputs)
    predictions[0]["scores"] = {"a": 0.1, "b": 0.9}

    report = evaluate_matrix(
        inputs,
        labels,
        {"candidate-a": predictions + _predictions(inputs, reverse=True)},
        bootstrap_resamples=10,
        bootstrap_seed=2,
    )

    assert report["candidates"]["candidate-a"]["canonical"]["status_counts"]["invalid"] == 1


def test_prediction_pairing_rejects_duplicate_ids() -> None:
    inputs, labels = normalize_corpus(_corpus_rows())
    predictions = _predictions(inputs)
    predictions.append(predictions[0])

    with pytest.raises(TransferEvaluationError, match="duplicate"):
        evaluate_matrix(
            inputs,
            labels,
            {"candidate-a": predictions},
            bootstrap_resamples=10,
            bootstrap_seed=1,
        )
