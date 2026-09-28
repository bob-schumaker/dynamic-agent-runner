"""Fake-only tests for the manually gated Jev-Style DMS-12 evaluator."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "manual"))

from run_jevstyle_dms12 import (  # noqa: E402
    EXPECTED_ARTIFACTS,
    EXPECTED_MODEL_FILES,
    INPUTS_SHA256,
    MODEL_ID,
    MODEL_REVISION,
    ManualRunError,
    _active_virtualenv,
    _load_agent,
    _validate_answer,
    build_request,
    score_input_rows,
    verify_preflight,
)


def test_decision_request_uses_only_fixture_inputs() -> None:
    row = {
        "id": "D001", "kind": "decision", "state": "known state",
        "question": {
            "id": "decision", "text": "Choose the valid option.",
            "options": [{"id": "bad", "label": "Invalid"}, {"id": "good", "label": "Valid"}],
        },
        "expected_option_id": "good",
    }

    state, questions = build_request(row)

    assert state == "known state"
    assert questions == [{
        "t": "choice", "ins": "Choose the valid option.",
        "crit": {"bad": "Invalid", "good": "Valid"},
    }]
    assert "expected_option_id" not in str((state, questions))


def test_retention_questions_are_batched_and_keep_labels_out() -> None:
    row = {
        "id": "R001", "kind": "retention", "task_context": "Finish the task.",
        "eligible_messages_oldest_first": [
            {"id": "m1", "content": "keep this"}, {"id": "m2", "content": "drop this"},
        ],
        "gold_keep_ids": ["m1"],
    }

    state, questions = build_request(row)

    assert state == "Finish the task."
    assert len(questions) == 2
    assert all(question["t"] == "choice" for question in questions)
    assert all(list(question["crit"]) == ["keep", "drop"] for question in questions)
    assert "keep this" in questions[0]["ins"]
    assert "gold_keep_ids" not in str((state, questions))


def test_rejects_invalid_jevstyle_probabilities() -> None:
    with pytest.raises(ManualRunError, match="do not sum to one"):
        _validate_answer({"answer": "good", "probabilities": {"good": .7, "bad": .2}}, {"good", "bad"})
    with pytest.raises(ManualRunError, match="invalid probabilities"):
        _validate_answer({"answer": "good", "probabilities": {"good": float("nan"), "bad": 0}},
                         {"good", "bad"})


def test_records_oversize_without_truncation() -> None:
    class Agent:
        def decide_many(self, *_args):
            raise ManualRunError("input exceeds token budget; nothing was truncated")

    row = {
        "id": "D001", "kind": "decision", "state": "too long",
        "question": {"id": "q", "text": "Select.", "options": [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
        ]},
    }

    predictions, *_ = score_input_rows([row], agent=Agent())

    assert predictions == [{"id": "D001", "kind": "decision", "status": "oversize"}]


def test_scores_batched_results_by_option_id_and_redacts_content() -> None:
    class Agent:
        def encode(self, text):
            return text.split()

        def decide_many(self, state, questions):
            assert state == "Complete the task."
            assert "private content" in questions[0]["ins"]
            return [
                {"answer": "keep", "probabilities": {"keep": .8, "drop": .2}},
                {"answer": "drop", "probabilities": {"keep": .1, "drop": .9}},
            ]

    row = {
        "id": "R001", "kind": "retention", "task_context": "Complete the task.",
        "eligible_messages_oldest_first": [
            {"id": "m1", "content": "private content keep"},
            {"id": "m2", "content": "private content drop"},
        ],
    }

    predictions, token_counts, latencies, peak_memory, oom = score_input_rows([row], agent=Agent())

    assert predictions == [{
        "id": "R001", "kind": "retention", "status": "ok", "score_semantics": "probability",
        "scores": {"m1": .8, "m2": .1},
    }]
    assert token_counts == [
        {"message_id": "m1", "token_count": 3}, {"message_id": "m2", "token_count": 3},
    ]
    assert "private" not in str(predictions + token_counts)
    assert len(latencies) == 1 and peak_memory > 0 and not oom


def test_loader_pins_and_verifies_local_runtime_before_model_load(tmp_path: Path, monkeypatch) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    for name in EXPECTED_MODEL_FILES:
        path = model_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (model_dir / "jev_style_decision_mlx.py").write_text(
        "class JevStyleDecisionMLX:\n"
        " def __init__(self, path, **kwargs):\n"
        "  assert path.name == 'model' and kwargs == {'precision': '8bit', 'verify': True, 'cache_limit_gib': 2.0}\n"
        "  assert __import__('os').environ['HF_HUB_OFFLINE'] == '1'\n"
    )
    calls = []
    fake_hub = ModuleType("huggingface_hub")
    fake_hub.snapshot_download = lambda **kwargs: calls.append(kwargs) or model_dir
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
    import run_jevstyle_dms12 as runner

    monkeypatch.setattr(runner, "_sha256", lambda path: EXPECTED_MODEL_FILES[path.relative_to(model_dir).as_posix()])

    _load_agent(model_dir)

    assert calls == [{
        "repo_id": MODEL_ID, "revision": MODEL_REVISION, "local_dir": str(model_dir),
        "allow_patterns": ["manifest.json", "jev_style_decision_mlx.py", "readout_config.json",
                           "release_config.json", "requirements.txt", "LICENSE", "8bit/*"],
    }]


def test_refuses_unapproved_preflight(tmp_path: Path) -> None:
    receipt = {
        "candidate_run_approved": False,
        "source": {"id": MODEL_ID, "revision": MODEL_REVISION},
        "artifacts": EXPECTED_ARTIFACTS,
    }

    with pytest.raises(ManualRunError, match="run approval is absent"):
        verify_preflight(receipt, runtime_checkout=tmp_path)


def test_active_virtualenv_must_contain_the_running_interpreter(tmp_path: Path, monkeypatch) -> None:
    environment = tmp_path / "venv"
    executable = environment / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setenv("VIRTUAL_ENV", str(environment))
    monkeypatch.setattr(sys, "executable", str(executable))

    assert _active_virtualenv() == str(environment)

    monkeypatch.setattr(sys, "executable", str(tmp_path / "system-python"))
    assert _active_virtualenv() is None


def test_refuses_model_revision_mismatch(tmp_path: Path) -> None:
    receipt = {
        "candidate_run_approved": True,
        "run_allowed": True,
        "fixture_criteria_approved": True,
        "input_sha256": INPUTS_SHA256,
        "source": {"id": MODEL_ID, "revision": MODEL_REVISION},
        "artifacts": [{"id": MODEL_ID, "revision": "0" * 40}],
    }

    with pytest.raises(ManualRunError, match="model revision differs"):
        verify_preflight(receipt, runtime_checkout=tmp_path)
