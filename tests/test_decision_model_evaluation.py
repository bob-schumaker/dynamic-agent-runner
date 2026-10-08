"""Fake-output tests for the gated DMS-01 evaluation harness."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluate_decision_models import (
    DMS01_INPUTS_SHA256,
    DMS01_LABELS_SHA256,
    EvaluationError,
    evaluate_candidate,
    create_preflight_receipt,
    prepare_candidate_inputs,
    verify_fixture_hashes,
    write_redacted_receipt,
)


EVALUATION_DIR = Path("specs/decision-model-support/evaluation")
INPUTS = EVALUATION_DIR / "dms01-inputs.jsonl"
LABELS = EVALUATION_DIR / "dms01-labels.jsonl"


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _fake_run_files(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    input_rows = [json.loads(line) for line in INPUTS.read_text().splitlines()]
    label_rows = [json.loads(line) for line in LABELS.read_text().splitlines()]
    labels_by_id = {row["id"]: row for row in label_rows}
    predictions: list[dict[str, object]] = []
    token_counts: list[dict[str, object]] = []

    for row in input_rows:
        label = labels_by_id[row["id"]]
        if row["kind"] == "decision":
            expected = label["expected_option_id"]
            option_ids = [option["id"] for option in row["question"]["options"]]
            predictions.append(
                {
                    "id": row["id"],
                    "kind": "decision",
                    "status": "ok",
                    "choice": expected,
                    "score_semantics": "probability",
                    "scores": {
                        option_id: 1.0 if option_id == expected else 0.0
                        for option_id in option_ids
                    },
                }
            )
        else:
            expected = label["expected_retention"]
            predictions.append(
                {
                    "id": row["id"],
                    "kind": "retention",
                    "status": "ok",
                    "score_semantics": "probability",
                    "scores": {
                        message["id"]: 1.0
                        if expected[message["id"]] == "keep"
                        else 0.0
                        for message in row["eligible_messages_oldest_first"]
                    },
                }
            )
            token_counts.extend(
                {"message_id": message["id"], "token_count": 10}
                for message in row["eligible_messages_oldest_first"]
            )

    predictions_path = tmp_path / "predictions.jsonl"
    counts_path = tmp_path / "token-counts.jsonl"
    _write_jsonl(predictions_path, predictions)
    _write_jsonl(counts_path, token_counts)
    measurements: dict[str, object] = {
        "model_id": "test/fake-model",
        "artifact_revision": "fake-revision",
        "runtime": "fake-test-runtime",
        "precision": "not-applicable",
        "tokenizer_id": "Qwen/Qwen3-0.6B-Base",
        "tokenizer_revision": "b" * 40,
        "cold_latency_ms": 100.0,
        "warm_latency_ms": [20.0, 30.0, 40.0],
        "peak_rss_bytes": 1024,
        "oom": False,
    }
    return predictions_path, counts_path, INPUTS, measurements


def test_frozen_fixture_digests_match_the_pre_registered_values() -> None:
    assert DMS01_INPUTS_SHA256 == hashlib.sha256(INPUTS.read_bytes()).hexdigest()
    assert DMS01_LABELS_SHA256 == hashlib.sha256(LABELS.read_bytes()).hexdigest()
    verify_fixture_hashes(INPUTS, LABELS)


def test_fixture_hash_verification_rejects_modified_inputs(tmp_path: Path) -> None:
    changed_inputs = tmp_path / "inputs.jsonl"
    changed_inputs.write_bytes(INPUTS.read_bytes() + b"{}\n")

    with pytest.raises(EvaluationError, match="input fixture hash"):
        verify_fixture_hashes(changed_inputs, LABELS)


def test_candidate_input_export_never_receives_or_contains_labels(
    tmp_path: Path,
) -> None:
    candidate_inputs = tmp_path / "candidate-inputs.jsonl"

    digest = prepare_candidate_inputs(INPUTS, candidate_inputs)

    assert digest == DMS01_INPUTS_SHA256
    assert candidate_inputs.read_bytes() == INPUTS.read_bytes()
    assert "expected_option_id" not in candidate_inputs.read_text()
    assert "expected_retention" not in candidate_inputs.read_text()


def test_evaluation_reports_decision_and_matched_token_retention_metrics(
    tmp_path: Path,
) -> None:
    predictions, token_counts, _, measurements = _fake_run_files(tmp_path)

    report = evaluate_candidate(
        inputs_path=INPUTS,
        labels_path=LABELS,
        predictions_path=predictions,
        token_counts_path=token_counts,
        measurements=measurements,
    )

    assert report["decision"]["accuracy"] == 1.0
    assert report["decision"]["wilson_95"]["lower"] < 1.0
    assert report["decision"]["wilson_95"]["upper"] == 1.0
    assert report["decision"]["by_category"]
    assert report["retention"]["model"]["keep_f1"] == 1.0
    assert report["retention"]["model"]["keep_recall"] == 1.0
    assert report["retention"]["baseline"]["keep_f1"] < 1.0
    assert report["calibration"]["status"] == "calibrated"
    assert report["calibration"]["decision"]["status"] == "calibrated"
    assert report["calibration"]["retention"]["status"] == "calibrated"
    assert report["operations"]["cold_latency_ms"] == 100.0
    assert report["operations"]["warm_latency_ms"]["p50"] == 30.0
    assert report["operations"]["peak_rss_bytes"] == 1024


def test_invalid_and_missing_predictions_count_as_incorrect(tmp_path: Path) -> None:
    predictions, token_counts, _, measurements = _fake_run_files(tmp_path)
    rows = [json.loads(line) for line in predictions.read_text().splitlines()]
    rows[0] = {"id": rows[0]["id"], "kind": "decision", "status": "timeout"}
    predictions.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows[:1] + rows[2:]),
        encoding="utf-8",
    )

    report = evaluate_candidate(
        inputs_path=INPUTS,
        labels_path=LABELS,
        predictions_path=predictions,
        token_counts_path=token_counts,
        measurements=measurements,
    )

    assert report["decision"]["accuracy"] < 1.0
    assert report["decision"]["failure_rates"]["timeout"] > 0.0
    assert report["decision"]["failure_rates"]["missing"] > 0.0


def test_probability_scores_report_brier_ece_and_calibration_gate(
    tmp_path: Path,
) -> None:
    predictions, token_counts, _, measurements = _fake_run_files(tmp_path)
    rows = [json.loads(line) for line in predictions.read_text().splitlines()]
    decision = next(row for row in rows if row["kind"] == "decision")
    option_ids = list(decision["scores"])
    decision["scores"] = {
        option_id: 0.55 if option_id == decision["choice"] else 0.45
        for option_id in option_ids
    }
    predictions.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    report = evaluate_candidate(
        inputs_path=INPUTS,
        labels_path=LABELS,
        predictions_path=predictions,
        token_counts_path=token_counts,
        measurements=measurements,
    )

    assert 0.0 < report["calibration"]["decision"]["brier_score"] < 1.0
    assert 0.0 <= report["calibration"]["decision"]["ece_10_bins"] <= 1.0
    assert report["calibration"]["decision"]["status"] in {
        "calibrated",
        "uncalibrated",
    }


def test_receipt_contains_aggregates_but_no_transcript_or_prediction_payload(
    tmp_path: Path,
) -> None:
    predictions, token_counts, _, measurements = _fake_run_files(tmp_path)
    report = evaluate_candidate(
        inputs_path=INPUTS,
        labels_path=LABELS,
        predictions_path=predictions,
        token_counts_path=token_counts,
        measurements=measurements,
    )
    receipt = tmp_path / "receipt.json"

    write_redacted_receipt(report, receipt)

    encoded = receipt.read_text()
    assert report["decision"]["accuracy"] is not None
    assert "The renewal fee" not in encoded
    assert "expected_option_id" not in encoded
    assert "scores" not in encoded
    assert json.loads(encoded)["input_sha256"] == DMS01_INPUTS_SHA256


def test_preflight_records_exact_runtime_and_blocks_unapproved_or_missing_runtime(
    tmp_path: Path,
) -> None:
    arguments = {
        "artifacts": [
            {"id": "jaredpalmer/kev-0.6b", "revision": "a" * 40},
            {"id": "Qwen/Qwen3-0.6B-Base", "revision": "b" * 40},
            {"id": "Qwen/Qwen3-0.6B-Base-tokenizer", "revision": "c" * 40},
        ],
        "harness_id": "kev-evaluation-harness",
        "harness_revision": "d" * 40,
        "runtime_id": "python-transformers-peft-mps",
        "accelerator_status": "CPU",
        "runtime_executable": Path(sys.executable),
        "runtime_python_version": "3.13.15",
        "runtime_packages": {"torch": "2.8.0"},
        "runtime_lock_sha256": "e" * 64,
        "execution_mode": "external_research_harness",
        "storage_path": tmp_path,
        "required_free_bytes": 1,
        "fixture_criteria_approved": True,
    }

    ready = create_preflight_receipt(**arguments)
    unapproved = create_preflight_receipt(
        **{**arguments, "fixture_criteria_approved": False}
    )
    missing_runtime = create_preflight_receipt(
        **{**arguments, "runtime_executable": tmp_path / "missing-python"}
    )

    assert ready["run_allowed"] is True
    assert ready["artifacts"] == arguments["artifacts"]
    assert ready["accelerator_status"] == "CPU"
    assert ready["host"]["free_storage_bytes"] >= 1
    assert unapproved["run_allowed"] is False
    assert missing_runtime["run_allowed"] is False


def test_preflight_binds_candidate_specific_runner_when_requested(tmp_path: Path) -> None:
    runner = Path("tests/manual/run_kev08_dms01.py")
    arguments = {
        "artifacts": [
            {"id": "jaredpalmer/kev-0.8b", "revision": "a" * 40},
            {"id": "Qwen/Qwen3.5-0.8B-Base", "revision": "b" * 40},
        ],
        "harness_id": "jaredpalmer/kev",
        "harness_revision": "c" * 40,
        "runtime_id": "kev-source-locked",
        "runtime_executable": Path(sys.executable),
        "runtime_python_version": "3.13.15",
        "runtime_packages": {"torch": "2.8.0"},
        "runtime_lock_sha256": "d" * 64,
        "accelerator_status": "CPU",
        "execution_mode": "external_research_harness",
        "storage_path": tmp_path,
        "required_free_bytes": 1,
        "fixture_criteria_approved": True,
        "runner_harness": runner,
    }

    receipt = create_preflight_receipt(**arguments)

    assert receipt["evaluation_harness_files"][-1]["id"] == str(runner)
    assert receipt["evaluation_harness_files"][-1]["sha256"] == hashlib.sha256(
        runner.read_bytes()
    ).hexdigest()
