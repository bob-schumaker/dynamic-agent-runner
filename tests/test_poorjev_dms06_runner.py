"""Fake-only checks for the manually gated PoorJev DMS-06 runner."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "manual"))

from run_poorjev_dms06 import (  # noqa: E402
    EXPECTED_ARTIFACTS,
    EXPECTED_SOURCE,
    INPUTS_SHA256,
    ManualRunError,
    RUNTIME_LOCK_SHA256,
    RUNTIME_PACKAGES,
    SOURCE_REVISION,
    build_request,
    score_input_rows,
    verify_preflight,
)


def test_build_request_uses_only_input_context_and_declared_options() -> None:
    row = {
        "id": "D001",
        "kind": "decision",
        "state": {"days_elapsed": 2},
        "question": {
            "id": "period-check",
            "text": "Is this within the permitted period?",
            "options": [
                {"id": "over", "label": "Outside"},
                {"id": "within", "label": "Within"},
            ],
        },
    }

    request = build_request(row)

    assert request["questions"]["period-check"]["options"] == {
        "over": "Outside",
        "within": "Within",
    }
    assert "expected_option_id" not in str(request)
    assert "D001" not in str(request)


def test_poorjev_scoring_is_redacted_and_uses_input_only() -> None:
    row = {
        "id": "R001",
        "kind": "retention",
        "task_context": "Finish the task.",
        "eligible_messages_oldest_first": [
            {"id": "R001-M1", "age_rank": 0, "content": "Keep this secret."},
            {"id": "R001-M2", "age_rank": 1, "content": "Drop this secret."},
        ],
    }

    class Client:
        def ask(self, state, questions):
            assert "Keep this secret." in state or "Drop this secret." in state
            message_id = next(iter(questions))
            hypotheses = questions[message_id]
            keep_index = 0 if message_id.endswith("1") else 1
            return {
                message_id: SimpleNamespace(
                    value=hypotheses[keep_index],
                    probs={hypothesis: 0.8 if index == keep_index else 0.2
                           for index, hypothesis in enumerate(hypotheses)},
                    abstained=False,
                )
            }

    class Tokenizer:
        def encode(self, content, add_special_tokens=False):
            assert add_special_tokens is False
            return content.split()

    predictions, token_counts, latencies, oom = score_input_rows(
        [row],
        client=Client(),
        choice_factory=lambda options: options,
        tokenizer=Tokenizer(),
    )

    assert predictions == [{
        "id": "R001",
        "kind": "retention",
        "status": "ok",
        "score_semantics": "probability",
        "scores": {"R001-M1": 0.8, "R001-M2": 0.2},
    }]
    assert token_counts == [
        {"message_id": "R001-M1", "token_count": 3},
        {"message_id": "R001-M2", "token_count": 3},
    ]
    assert "secret" not in str(predictions + token_counts)
    assert len(latencies) == 2
    assert not oom


def test_poorjev_preflight_requires_approval_and_exact_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import run_poorjev_dms06

    monkeypatch.setattr(run_poorjev_dms06, "_repository_revision", lambda _path: SOURCE_REVISION)
    monkeypatch.setattr(run_poorjev_dms06, "_repository_clean", lambda _path: True)
    monkeypatch.setattr(
        run_poorjev_dms06, "_runtime_versions", lambda: (RUNTIME_PACKAGES, True)
    )
    original_sha256 = run_poorjev_dms06._sha256
    monkeypatch.setattr(
        run_poorjev_dms06,
        "_sha256",
        lambda path: RUNTIME_LOCK_SHA256 if path.name == "uv.lock" else original_sha256(path),
    )
    (tmp_path / "uv.lock").write_text("pinned runtime")
    root = Path(__file__).resolve().parents[1]
    runner_path = root / "tests" / "manual" / "run_poorjev_dms06.py"
    receipt = {
        "run_allowed": True,
        "candidate_run_approved": True,
        "fixture_criteria_approved": True,
        "input_sha256": INPUTS_SHA256,
        "source": EXPECTED_SOURCE,
        "artifacts": EXPECTED_ARTIFACTS,
        "expected_model_file_sha256": {
            "model.safetensors": "6e8f2af78c828dcbd5243aac40fb87430376f0b8a9c288f4993df3ea3558d557",
        },
        "runtime": {
            "python_version": sys.version.split()[0],
            "lock_sha256": RUNTIME_LOCK_SHA256,
            "packages": RUNTIME_PACKAGES,
        },
        "evaluation_harness_files": [
            {
                "id": str(path.relative_to(root)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in (root / "scripts" / "evaluate_decision_models.py", runner_path)
        ],
    }

    receipt["runtime"].update({
        "available": True,
        "executable": str(Path(sys.executable).resolve()),
    })
    verify_preflight(receipt, source_checkout=tmp_path, runtime_checkout=tmp_path)

    with pytest.raises(ManualRunError, match="candidate-specific approval"):
        verify_preflight(
            {**receipt, "candidate_run_approved": False},
            source_checkout=tmp_path,
            runtime_checkout=tmp_path,
        )
    with pytest.raises(ManualRunError, match="artifact revisions"):
        verify_preflight(
            {**receipt, "artifacts": []},
            source_checkout=tmp_path,
            runtime_checkout=tmp_path,
        )
