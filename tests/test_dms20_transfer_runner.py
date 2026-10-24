"""Fake-backed tests for the gated DMS-20 transfer runner."""

from __future__ import annotations

import hashlib
import json
import sys
from types import ModuleType
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "manual"))

from run_dms20_transfer import (
    MatrixRunError,
    _verify_artifacts,
    _lev_choice_question,
    execute_matrix,
    ordered_inputs,
    run_rows,
    verify_matrix_approval,
)


LEADS = {"julia-1", "kev-4b", "lev", "strands-decider-2b"}


def test_artifact_verification_reads_selectively_downloaded_snapshot(
    tmp_path: Path,
) -> None:
    repository = "owner/model"
    revision = "a" * 40
    relative_path = "model.safetensors"
    artifact = b"pinned weights"
    snapshot = (
        tmp_path / "models--owner--model" / "snapshots" / revision / relative_path
    )
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(artifact)
    row = {
        "model": {"id": repository, "revision": revision},
        "artifact_files": [
            {
                "repository": repository,
                "revision": revision,
                "path": relative_path,
                "size_bytes": len(artifact),
                "sha256": hashlib.sha256(artifact).hexdigest(),
            }
        ],
    }

    snapshots = _verify_artifacts(row, tmp_path)

    assert snapshots["model"] == snapshot.parent


def test_lev_choice_question_uses_the_pinned_source_public_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeChoice:
        def __init__(self, **values: object) -> None:
            self.values = values

    fake_lev = ModuleType("lev")
    fake_lev.Choice = FakeChoice  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lev", fake_lev)
    question = {
        "text": "Select the outcome.",
        "options": [
            {"id": "a", "label": "Alpha"},
            {"id": "b", "label": "Beta"},
        ],
    }

    result = _lev_choice_question(question)

    assert isinstance(result, FakeChoice)
    assert result.values == {
        "type": "choice",
        "instructions": "Select the outcome.",
        "criteria": {"a": "Alpha", "b": "Beta"},
    }


def _write_matrix(tmp_path: Path) -> tuple[Path, Path, Path]:
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(
        json.dumps(
            {
                "license_review_status": "cleared",
                "normalized_input_sha256": "ab" * 32,
                "gold_label_sha256": "cd" * 32,
            }
        ),
        encoding="utf-8",
    )
    harness_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "evaluate_decision_transfer.py"
    )
    rows = [
        {"id": "julia-1", "disposition": "selected"},
        {"id": "kev-4b", "disposition": "selected"},
        {"id": "lev", "disposition": "selected"},
        {"id": "strands-decider-2b", "disposition": "selected"},
    ]
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "rows": rows,
                "approval_scope": "one approval for the complete matrix",
                "corpus_manifest_sha256": hashlib.sha256(
                    corpus_path.read_bytes()
                ).hexdigest(),
                "normalized_input_sha256": "ab" * 32,
                "gold_label_sha256": "cd" * 32,
                "harness_files": [
                    {
                        "path": str(harness_path.relative_to(harness_path.parents[1])),
                        "sha256": hashlib.sha256(harness_path.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(
        json.dumps(
            {
                "approved": True,
                "matrix_sha256": hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
                "corpus_manifest_sha256": hashlib.sha256(
                    corpus_path.read_bytes()
                ).hexdigest(),
                "approval_scope": "one approval for the complete matrix",
                "dispositions": {row["id"]: row["disposition"] for row in rows},
                "runnable_cohort": ["julia-1", "kev-4b", "lev", "strands-decider-2b"],
            }
        ),
        encoding="utf-8",
    )
    return matrix_path, corpus_path, approval_path


def _rows() -> list[dict[str, object]]:
    return [
        {
            "id": "item-1",
            "category": "test",
            "kind": "decision",
            "state": {"content": "private fixture text"},
            "question": {
                "id": "answer",
                "text": "Choose one.",
                "options": [
                    {"id": "a", "label": "Alpha"},
                    {"id": "b", "label": "Beta"},
                ],
            },
        }
    ]


def test_runner_reverses_option_order_and_redacts_inputs() -> None:
    rows = _rows()
    reversed_rows = ordered_inputs(rows, "reversed")

    assert [option["id"] for option in reversed_rows[0]["question"]["options"]] == [
        "b",
        "a",
    ]
    predictions = run_rows(
        rows,
        lambda _row: {
            "status": "ok",
            "choice": "a",
            "score_semantics": "probability",
            "scores": {"a": 0.75, "b": 0.25},
        },
    )

    assert {row["option_order"] for row in predictions} == {"canonical", "reversed"}
    assert all("private fixture text" not in json.dumps(row) for row in predictions)
    assert all("question" not in row and "state" not in row for row in predictions)


def test_matrix_approval_binds_all_four_dispositions_and_exact_runnable_cohort(
    tmp_path: Path,
) -> None:
    matrix_path, corpus_path, approval_path = _write_matrix(tmp_path)

    matrix = verify_matrix_approval(matrix_path, corpus_path, approval_path)

    assert {row["id"] for row in matrix["rows"]} == LEADS
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["runnable_cohort"] = ["julia-1", "kev-4b"]
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(MatrixRunError, match="runnable cohort"):
        verify_matrix_approval(matrix_path, corpus_path, approval_path)


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_matrix_approval_rejects_incomplete_or_extra_lead_set(
    tmp_path: Path, change: str
) -> None:
    matrix_path, corpus_path, approval_path = _write_matrix(tmp_path)
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    if change == "missing":
        matrix["rows"].pop()
    else:
        matrix["rows"].append({"id": "other", "disposition": "deferred"})
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["matrix_sha256"] = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
    approval["dispositions"] = {row["id"]: row["disposition"] for row in matrix["rows"]}
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(MatrixRunError, match="exact four DMS-20 leads"):
        verify_matrix_approval(matrix_path, corpus_path, approval_path)


def test_matrix_approval_rejects_deferred_lead_for_all_four_run_scope(
    tmp_path: Path,
) -> None:
    matrix_path, corpus_path, approval_path = _write_matrix(tmp_path)
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    matrix["rows"][2]["disposition"] = "deferred"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["matrix_sha256"] = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
    approval["dispositions"]["lev"] = "deferred"
    approval["runnable_cohort"].remove("lev")
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(MatrixRunError, match="all four DMS-20 leads must be selected"):
        verify_matrix_approval(matrix_path, corpus_path, approval_path)


def test_matrix_execution_runs_selected_rows_only_and_requires_full_preflight(
    tmp_path: Path,
) -> None:
    matrix_path, corpus_path, approval_path = _write_matrix(tmp_path)
    matrix = verify_matrix_approval(matrix_path, corpus_path, approval_path)
    matrix["_matrix_sha256"] = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
    preflight = {
        "matrix_sha256": matrix["_matrix_sha256"],
        "corpus_manifest_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "run_allowed": True,
        "rows": {
            "julia-1": {"run_allowed": True},
            "kev-4b": {"run_allowed": True},
            "lev": {"run_allowed": True},
            "strands-decider-2b": {"run_allowed": True},
        },
    }
    called: list[str] = []

    receipt = execute_matrix(
        matrix, preflight, lambda row, _check: called.append(row["id"]) or True
    )

    assert called == ["julia-1", "kev-4b", "lev", "strands-decider-2b"]
    assert receipt["completed_rows"] == 4
    del preflight["rows"]["kev-4b"]
    with pytest.raises(MatrixRunError, match="every selected row"):
        execute_matrix(matrix, preflight, lambda _row, _check: True)


def test_matrix_rejects_changed_harness_digest(tmp_path: Path) -> None:
    matrix_path, corpus_path, approval_path = _write_matrix(tmp_path)
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    matrix["harness_files"][0]["sha256"] = "00" * 32
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

    with pytest.raises(MatrixRunError, match="harness"):
        verify_matrix_approval(matrix_path, corpus_path, approval_path)
