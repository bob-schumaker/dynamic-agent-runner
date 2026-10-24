"""Fake-backed tests for the gated DMS-20 extension runner."""

from __future__ import annotations

import hashlib
import json
import sys
from types import ModuleType
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "manual"))

from run_dms20_extension import (  # noqa: E402
    ExtensionRunError,
    _load_tev,
    _nimble_schema,
    _tev_messages,
    _verify_artifacts,
    run_predictions,
    verify_extension_approval,
)


EXPECTED = {"tev1-4b", "tev1-0.8b", "nimble-9b"}


def test_merged_checkpoint_does_not_require_a_pinned_base_revision(
    tmp_path: Path,
) -> None:
    model_file = (
        tmp_path / "models--org--model" / "snapshots" / "model-rev" / "weights.bin"
    )
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"merged checkpoint")
    row = {
        "artifact_files": [
            {
                "repository": "org/model",
                "revision": "model-rev",
                "path": "weights.bin",
                "sha256": hashlib.sha256(model_file.read_bytes()).hexdigest(),
            }
        ],
        "model": {"id": "org/model", "revision": "model-rev"},
        "base_model": {"id": "org/base", "training_revision": None},
    }

    snapshots = _verify_artifacts(row, tmp_path)

    assert snapshots["model"] == model_file.parent
    assert snapshots["base"] is None


def test_tev_text_only_loader_uses_tokenizer_without_image_processor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class Tokenizer:
        @classmethod
        def from_pretrained(cls, path: str, **kwargs: object) -> Tokenizer:
            calls.append((path, kwargs))
            return cls()

    class Model:
        @classmethod
        def from_pretrained(cls, *_args: object, **_kwargs: object) -> Model:
            return cls()

        def to(self, _device: str) -> Model:
            return self

        def eval(self) -> Model:
            return self

    torch = ModuleType("torch")
    torch.bfloat16 = object()  # type: ignore[attr-defined]
    transformers = ModuleType("transformers")
    transformers.AutoTokenizer = Tokenizer  # type: ignore[attr-defined]
    transformers.Qwen3_5ForConditionalGeneration = Model  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)

    _infer, tokenizer = _load_tev({}, tmp_path)

    assert isinstance(tokenizer, Tokenizer)
    assert calls == [(str(tmp_path), {"local_files_only": True})]


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
    inputs_path = tmp_path / "inputs.jsonl"
    inputs_path.write_text("input\n", encoding="utf-8")
    labels_path = tmp_path / "labels.jsonl"
    labels_path.write_text("labels\n", encoding="utf-8")
    harness = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "manual"
        / "run_dms20_extension.py"
    )
    original_matrix = (
        Path(__file__).resolve().parents[1]
        / "specs"
        / "decision-model-support"
        / "evaluation"
        / "dms20-matrix.json"
    )
    rows = [{"id": item, "disposition": "selected"} for item in sorted(EXPECTED)]
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "approval_scope": "all three extension candidates",
                "corpus_manifest_sha256": hashlib.sha256(
                    corpus_path.read_bytes()
                ).hexdigest(),
                "normalized_input_sha256": "ab" * 32,
                "gold_label_sha256": "cd" * 32,
                "original_matrix_sha256": hashlib.sha256(
                    original_matrix.read_bytes()
                ).hexdigest(),
                "input_files": {
                    "normalized_inputs": {
                        "path": str(inputs_path),
                        "sha256": hashlib.sha256(inputs_path.read_bytes()).hexdigest(),
                    },
                    "gold_labels": {
                        "path": str(labels_path),
                        "sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
                    },
                },
                "protocol": {"model_prompt_token_limit": 4096},
                "rows": rows,
                "runnable_cohort": sorted(EXPECTED),
                "harness_files": [
                    {
                        "path": str(harness.relative_to(harness.parents[2])),
                        "sha256": hashlib.sha256(harness.read_bytes()).hexdigest(),
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
                "approval_scope": "all three extension candidates",
                "matrix_sha256": hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
                "corpus_manifest_sha256": hashlib.sha256(
                    corpus_path.read_bytes()
                ).hexdigest(),
                "dispositions": {row["id"]: row["disposition"] for row in rows},
                "runnable_cohort": sorted(EXPECTED),
            }
        ),
        encoding="utf-8",
    )
    return matrix_path, corpus_path, approval_path


def test_extension_approval_binds_exact_three_candidate_cohort(tmp_path: Path) -> None:
    matrix_path, corpus_path, approval_path = _write_matrix(tmp_path)

    matrix = verify_extension_approval(matrix_path, corpus_path, approval_path)

    assert {row["id"] for row in matrix["rows"]} == EXPECTED
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["runnable_cohort"] = ["tev1-4b"]
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(ExtensionRunError, match="runnable cohort"):
        verify_extension_approval(matrix_path, corpus_path, approval_path)


def test_tev_prompt_preserves_option_ids_and_non_thinking_contract() -> None:
    row = {
        "state": {"source": "fixture"},
        "question": {
            "text": "Choose one.",
            "options": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}],
        },
    }

    messages = _tev_messages(row)

    assert messages[0]["content"].endswith(
        "Return only its letter, with no explanation."
    )
    request = json.loads(messages[1]["content"])
    assert [option["key"] for option in request["options"]] == ["yes", "no"]
    assert [option["label"] for option in request["options"]] == ["A", "B"]


def test_tev_rejects_option_count_outside_published_contract() -> None:
    row = {
        "state": {"source": "fixture"},
        "question": {
            "text": "Choose one.",
            "options": [{"id": str(index), "label": str(index)} for index in range(25)],
        },
    }

    with pytest.raises(ValueError, match="between 2 and 24"):
        _tev_messages(row)


def test_nimble_schema_uses_current_order_and_maps_labels() -> None:
    row = {
        "question": {
            "text": "Choose one.",
            "options": [{"id": "b", "label": "Beta"}, {"id": "a", "label": "Alpha"}],
        },
    }

    schema = _nimble_schema(row)

    assert schema["decision"]["choices"] == ["b", "a"]
    assert schema["decision"]["choice_descriptions"] == {"b": "Beta", "a": "Alpha"}


def test_predictions_redact_input_and_report_progress(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rows = [
        {
            "id": "item-1",
            "state": {"private": "fixture text"},
            "kind": "decision",
            "question": {
                "text": "Choose one.",
                "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            },
        }
    ]

    predictions, latency_ms = run_predictions(
        rows, lambda _row: {"choice": "a", "scores": {"a": 0.75, "b": 0.25}}
    )

    assert len(predictions) == 2
    assert len(latency_ms) == 2
    assert all(item["status"] == "ok" for item in predictions)
    assert "fixture text" not in json.dumps(predictions)
    assert "1/2" in capsys.readouterr().err
