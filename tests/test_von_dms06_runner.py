"""Fake-only checks for the manually gated Von DMS-06 evaluation driver."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent / "manual"))

from run_von_dms06 import (  # noqa: E402
    EXPECTED_ARTIFACTS,
    EXPECTED_SOURCE,
    INPUTS_SHA256,
    ManualRunError,
    RUNTIME_PACKAGES,
    SOURCE_REVISION,
    build_request,
    score_input_rows,
    verify_preflight,
)


def test_builds_von_questions_only_from_frozen_decision_input() -> None:
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

    assert request == {
        "state": {"days_elapsed": 2},
        "questions": {
            "period-check": {
                "text": "Is this within the permitted period?",
                "options": {"over": "Outside", "within": "Within"},
            }
        },
    }
    assert "expected_option_id" not in str(request)


def test_von_scoring_emits_probabilities_and_token_counts_without_content() -> None:
    row = {
        "id": "R001",
        "kind": "retention",
        "task_context": "Finish the task.",
        "eligible_messages_oldest_first": [
            {"id": "R001-M1", "age_rank": 0, "content": "Keep this."},
            {"id": "R001-M2", "age_rank": 1, "content": "Drop this."},
        ],
    }

    class Backend:
        def evaluate_choice(self, question_id, _state_text, question):
            option_ids = list(question.criteria)
            choice = "keep" if question_id.endswith("1") else "drop"
            return SimpleNamespace(
                choice=choice,
                probabilities={option_id: 0.8 if option_id == choice else 0.2 for option_id in option_ids},
            )

    class Tokenizer:
        def encode(self, content: str, add_special_tokens: bool) -> list[int]:
            assert add_special_tokens is False
            return content.split()

    def make_choice(*, instructions, criteria):
        return SimpleNamespace(instructions=instructions, criteria=criteria)

    predictions, token_counts, latencies, oom = score_input_rows(
        [row],
        backend=Backend(),
        choice_factory=make_choice,
        tokenizer=Tokenizer(),
        digit_split=False,
    )

    assert predictions == [
        {
            "id": "R001",
            "kind": "retention",
            "status": "ok",
            "score_semantics": "probability",
            "scores": {"R001-M1": 0.8, "R001-M2": 0.2},
        }
    ]
    assert token_counts == [
        {"message_id": "R001-M1", "token_count": 2},
        {"message_id": "R001-M2", "token_count": 2},
    ]
    assert "Keep this." not in str(predictions + token_counts)
    assert len(latencies) == 2
    assert not oom


def test_von_preflight_requires_separate_candidate_approval_and_exact_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import run_von_dms06

    monkeypatch.setattr(run_von_dms06, "_repository_revision", lambda _path: SOURCE_REVISION)
    root = Path(__file__).resolve().parents[1]
    runner_path = root / "tests" / "manual" / "run_von_dms06.py"
    receipt = {
        "run_allowed": True,
        "candidate_run_approved": True,
        "fixture_criteria_approved": True,
        "input_sha256": INPUTS_SHA256,
        "source": EXPECTED_SOURCE,
        "artifacts": EXPECTED_ARTIFACTS,
        "runtime": {
            "available": True,
            "executable": str(Path(sys.executable).resolve()),
            "python_version": sys.version.split()[0],
            "lock_sha256": "acaaa8abfcd3bc18eff1557fe2c73be73c00899eed5b1145de1b30518acf1f41",
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

    verify_preflight(receipt, source_checkout=tmp_path)

    with pytest.raises(ManualRunError, match="candidate-specific approval"):
        verify_preflight(
            {**receipt, "candidate_run_approved": False}, source_checkout=tmp_path
        )
    with pytest.raises(ManualRunError, match="artifact revisions"):
        verify_preflight({**receipt, "artifacts": []}, source_checkout=tmp_path)


@pytest.mark.parametrize(
    "failure, expected_status, expected_oom",
    [
        ("raise", "error", False),
        ("timeout", "timeout", False),
        ("invalid", "invalid", False),
        ("oom", "error", True),
    ],
)
def test_von_scoring_counts_failures_without_emitting_input_or_error_text(
    failure: str, expected_status: str, expected_oom: bool
) -> None:
    row = {
        "id": "D001",
        "kind": "decision",
        "state": {"private": "synthetic private text"},
        "question": {
            "id": "question",
            "text": "Choose.",
            "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        },
    }

    class Backend:
        def evaluate_choice(self, *_args):
            if failure == "raise":
                raise RuntimeError("synthetic private text in exception")
            if failure == "timeout":
                raise TimeoutError("synthetic private timeout")
            if failure == "oom":
                raise RuntimeError("MPS backend out of memory")
            return SimpleNamespace(choice="a", probabilities={"a": 2.0, "b": -1.0})

    predictions, _token_counts, _latencies, oom = score_input_rows(
        [row],
        backend=Backend(),
        choice_factory=lambda **kwargs: SimpleNamespace(**kwargs),
        tokenizer=SimpleNamespace(encode=lambda *_args, **_kwargs: [1]),
        digit_split=False,
    )

    assert predictions == [{"id": "D001", "kind": "decision", "status": expected_status}]
    assert "synthetic private text" not in str(predictions)
    assert oom is expected_oom
