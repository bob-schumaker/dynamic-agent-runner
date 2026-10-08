"""Fake-backend tests for the gated DMS-14 in-process runner."""

from __future__ import annotations

import json
import hashlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "manual"))

from run_dms14_transfer import (
    MatrixRunError,
    _configure_offline_model_access,
    _verify_candidate_artifacts,
    execute_matrix,
    ordered_inputs,
    run_rows,
    verify_matrix_approval,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_matrix(path: Path, corpus: Path) -> None:
    harness = ROOT / "scripts" / "evaluate_decision_transfer.py"
    path.write_text(
        json.dumps(
            {
                "rows": [{"id": "a"}],
                "approval_scope": "one approval for the complete matrix",
                "corpus_manifest_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(),
                "normalized_input_sha256": "ab" * 32,
                "gold_label_sha256": "cd" * 32,
                "harness_files": [
                    {
                        "path": str(harness.relative_to(ROOT)),
                        "sha256": hashlib.sha256(harness.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _rows() -> list[dict[str, object]]:
    return [
        {
            "id": "item-1",
            "category": "test",
            "kind": "decision",
            "state": {"content": "hidden corpus text"},
            "question": {
                "id": "answer",
                "text": "Choose one.",
                "options": [{"id": "a", "label": "Alpha"}, {"id": "b", "label": "Beta"}],
            },
        }
    ]


def test_option_permutation_changes_order_only_and_keeps_item_inputs_intact() -> None:
    rows = _rows()
    reversed_rows = ordered_inputs(rows, "reversed")

    assert [option["id"] for option in reversed_rows[0]["question"]["options"]] == ["b", "a"]
    assert [option["id"] for option in rows[0]["question"]["options"]] == ["a", "b"]
    assert reversed_rows[0]["state"] == rows[0]["state"]


def test_runner_records_predictions_for_both_orders_without_input_text() -> None:
    calls = []

    def fake_infer(row: dict[str, object]) -> dict[str, object]:
        calls.append(row["question"]["options"])
        return {
            "status": "ok",
            "choice": "a",
            "score_semantics": "probability",
            "scores": {"a": 0.7, "b": 0.3},
        }

    output = run_rows(_rows(), fake_infer)

    assert len(calls) == 2
    assert {row["option_order"] for row in output} == {"canonical", "reversed"}
    assert all("hidden corpus text" not in json.dumps(row) for row in output)
    assert all("question" not in row and "state" not in row for row in output)


def test_runner_redacts_backend_exceptions_and_keeps_going() -> None:
    def failing_infer(_row: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("failure includes hidden corpus text")

    output = run_rows(_rows(), failing_infer)

    assert len(output) == 2
    assert all(row["status"] == "error" for row in output)
    assert "hidden corpus text" not in json.dumps(output)


def test_candidate_model_access_is_offline_and_uses_pinned_cache_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = {"id": "kev-0.6b-cpu"}

    _configure_offline_model_access(candidate, tmp_path / "cache")

    assert os.environ["HF_HOME"] == str(tmp_path / "cache")
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    _configure_offline_model_access({"id": "von-cpu"}, tmp_path / "von-cache")
    assert os.environ["HF_HOME"] == str(tmp_path / "von-cache" / "hf-home")
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_candidate_artifacts_are_checked_against_matrix_digests(tmp_path: Path) -> None:
    artifact = tmp_path / "weights.bin"
    artifact.write_bytes(b"pinned weights")
    candidate = {
        "id": "test-cpu",
        "artifact_files": [
            {
                "repository": "test/model",
                "revision": "a" * 40,
                "path": "weights.bin",
                "size_bytes": artifact.stat().st_size,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            }
        ],
    }

    _verify_candidate_artifacts(candidate, tmp_path)

    artifact.write_bytes(b"different weights")
    with pytest.raises(MatrixRunError, match="artifact digest"):
        _verify_candidate_artifacts(candidate, tmp_path)


def test_runner_rejects_choices_or_scores_outside_the_supplied_options() -> None:
    output = run_rows(
        _rows(),
        lambda _row: {"status": "ok", "choice": "hidden corpus text"},
    )

    assert all(row["status"] == "invalid" for row in output)
    assert "hidden corpus text" not in json.dumps(output)


def test_matrix_approval_covers_exact_matrix_and_corpus(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"
    corpus = tmp_path / "corpus.json"
    approval = tmp_path / "approval.json"
    corpus.write_text(
        json.dumps(
            {
                "license_review_status": "cleared",
                "normalized_input_sha256": "ab" * 32,
                "gold_label_sha256": "cd" * 32,
            }
        ),
        encoding="utf-8",
    )
    _write_matrix(matrix, corpus)
    approval.write_text(
        json.dumps(
            {
                "approved": True,
                "matrix_sha256": "6f" * 32,
                "corpus_manifest_sha256": "00" * 32,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MatrixRunError, match="matrix hash"):
        verify_matrix_approval(matrix, corpus, approval)


def test_one_approval_receipt_authorizes_the_whole_matrix(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"
    corpus = tmp_path / "corpus.json"
    approval = tmp_path / "approval.json"
    corpus.write_text(
        json.dumps(
            {
                "license_review_status": "cleared",
                "normalized_input_sha256": "ab" * 32,
                "gold_label_sha256": "cd" * 32,
            }
        ),
        encoding="utf-8",
    )
    _write_matrix(matrix, corpus)
    matrix_value = json.loads(matrix.read_text())
    approval.write_text(
        json.dumps(
            {
                "approved": True,
                "matrix_sha256": hashlib.sha256(matrix.read_bytes()).hexdigest(),
                "corpus_manifest_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(),
                "approval_scope": matrix_value["approval_scope"],
            }
        ),
        encoding="utf-8",
    )

    assert verify_matrix_approval(matrix, corpus, approval) == matrix_value


def test_matrix_run_is_blocked_when_source_terms_are_unresolved(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"
    corpus = tmp_path / "corpus.json"
    approval = tmp_path / "approval.json"
    corpus.write_text(
        json.dumps(
            {
                "license_review_status": "blocked-unresolved",
                "normalized_input_sha256": "ab" * 32,
                "gold_label_sha256": "cd" * 32,
            }
        ),
        encoding="utf-8",
    )
    _write_matrix(matrix, corpus)
    approval.write_text("{}", encoding="utf-8")

    with pytest.raises(MatrixRunError, match="license review"):
        verify_matrix_approval(matrix, corpus, approval)


def test_full_matrix_uses_one_approval_and_runs_each_row_without_prompting() -> None:
    matrix = {
        "_matrix_sha256": "a" * 64,
        "rows": [{"id": "first"}, {"id": "second"}, {"id": "third"}],
    }
    preflight = {
        "matrix_sha256": "a" * 64,
        "corpus_manifest_sha256": "b" * 64,
        "run_allowed": True,
        "rows": {
            row["id"]: {
                "run_allowed": True,
                "runtime_executable": "/python",
                "source_checkout": "/source",
                "runtime_lock": "/lock",
                "model_directory": "/model",
            }
            for row in matrix["rows"]
        },
    }
    called: list[str] = []

    def run_row(row: dict[str, object], _preflight: dict[str, object]) -> bool:
        called.append(str(row["id"]))
        return True

    receipt = execute_matrix(matrix, preflight, run_row)

    assert called == ["first", "second", "third"]
    assert receipt["approval_scope"] == "one approval for the complete matrix"
    assert receipt["completed_rows"] == 3
    assert receipt["failed_rows"] == 0


def test_full_matrix_refuses_to_start_if_any_row_lacks_preflight() -> None:
    matrix = {"_matrix_sha256": "a" * 64, "rows": [{"id": "first"}, {"id": "second"}]}
    preflight = {
        "matrix_sha256": "a" * 64,
        "run_allowed": True,
        "rows": {
            "first": {"run_allowed": True},
            "second": {"run_allowed": False},
        },
    }
    called: list[str] = []

    with pytest.raises(MatrixRunError, match="failed preflight"):
        execute_matrix(matrix, preflight, lambda row, _: called.append(row["id"]) or True)

    assert called == []


def test_full_matrix_validates_every_row_command_before_starting_any() -> None:
    matrix = {"_matrix_sha256": "a" * 64, "rows": [{"id": "first"}, {"id": "second"}]}
    preflight = {
        "matrix_sha256": "a" * 64,
        "run_allowed": True,
        "rows": {
            "first": {
                "run_allowed": True,
                "runtime_executable": "/python",
                "source_checkout": "/source",
                "runtime_lock": "/lock",
                "model_directory": "/model",
            },
            "second": {"run_allowed": True},
        },
    }
    called: list[str] = []

    with pytest.raises(MatrixRunError, match="command inputs"):
        execute_matrix(matrix, preflight, lambda row, _: called.append(row["id"]) or True)

    assert called == []
