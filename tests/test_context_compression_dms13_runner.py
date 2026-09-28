from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "manual"))

from run_context_compression_dms13 import ManualRunError, VonTurnScorer, get_official_judge_prompt, run, verify_preflight, verify_run_approval


class _Tokenizer:
    def __init__(self, count: int = 12) -> None:
        self.count = count
        self.inputs: list[str] = []

    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
        assert add_special_tokens is False
        self.inputs.append(text)
        return list(range(self.count))


class _Backend:
    def __init__(self) -> None:
        self.calls = []

    def evaluate_choice(self, question_id, state_text, choice):
        self.calls.append((question_id, state_text, choice))
        return type("Answer", (), {"choice": "keep", "probabilities": {"keep": 0.8, "drop": 0.2}})()


def _choice_factory(*, instructions, criteria):
    return {"instructions": instructions, "criteria": criteria}


def test_von_turn_scorer_uses_only_turn_content_and_returns_keep_drop_margin() -> None:
    backend = _Backend()
    tokenizer = _Tokenizer()
    scorer = VonTurnScorer(
        backend=backend,
        choice_factory=_choice_factory,
        tokenizer=tokenizer,
    )
    turn = [
        {
            "id": "q:0:s:0",
            "role": "user",
            "content": "Remember I prefer tea.",
            "session_id": "s",
            "session_date": "2024/01/01",
        },
        {
            "id": "q:0:s:1",
            "role": "assistant",
            "content": "I will remember.",
            "session_id": "s",
            "session_date": "2024/01/01",
        },
    ]

    margin = scorer(turn)

    assert margin == pytest.approx(0.6)
    assert backend.calls[0][2]["criteria"] == {
        "keep": "Retain this turn in active context.",
        "drop": "The active context can omit this turn.",
    }
    serialized = backend.calls[0][1]
    assert "Remember I prefer tea." in serialized
    assert "SECRET QUESTION" not in serialized
    assert "SECRET ANSWER" not in serialized


def test_von_turn_scorer_rejects_input_over_candidate_limit_before_inference() -> None:
    backend = _Backend()
    scorer = VonTurnScorer(
        backend=backend,
        choice_factory=_choice_factory,
        tokenizer=_Tokenizer(count=8193),
    )

    with pytest.raises(ManualRunError, match="input limit"):
        scorer([{"id": "q:0:s:0", "role": "user", "content": "large"}])

    assert backend.calls == []


def test_von_turn_scorer_checks_the_packed_prompt_length() -> None:
    backend = _Backend()
    tokenizer = _Tokenizer(count=8193)
    scorer = VonTurnScorer(
        backend=backend,
        choice_factory=_choice_factory,
        tokenizer=tokenizer,
        pack_sequence=lambda state, question, options: f"{question} {state} {' '.join(options)}",
    )

    with pytest.raises(ManualRunError, match="input limit"):
        scorer([{"id": "q:0:s:0", "role": "user", "content": "short"}])

    assert backend.calls == []


def test_official_judge_prompt_uses_pinned_type_and_abstention_rules() -> None:
    prompts = []

    def builder(question_type, question, gold, response, abstention=False):
        prompts.append((question_type, question, gold, response, abstention))
        return f"{question_type}:{abstention}:{question}:{gold}:{response}"

    regular = get_official_judge_prompt(
        builder, "temporal-reasoning", "SECRET QUESTION", "18 days", "19 days", False
    )
    abstention = get_official_judge_prompt(
        builder, "multi-session", "SECRET QUESTION", "unknown", "cannot answer", True
    )

    assert regular == "temporal-reasoning:False:SECRET QUESTION:18 days:19 days"
    assert abstention.endswith(":True:SECRET QUESTION:unknown:cannot answer")
    assert prompts[0][0] == "temporal-reasoning"
    assert prompts[0][4] is False
    assert prompts[1][4] is True


def test_dms13_judge_uses_local_mlx_in_process() -> None:
    from run_context_compression_dms13 import (
        SCORER_MODEL,
        _score_with_local_model,
    )

    class FakeTokenizer:
        def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
            assert messages == [{"role": "user", "content": "safe synthetic prompt"}]
            assert tokenize is False
            assert add_generation_prompt is True
            return "<|user|>safe synthetic prompt<|assistant|>"

    calls = []

    def fake_generate(model, tokenizer, prompt, **kwargs):
        calls.append((model, tokenizer, prompt, kwargs))
        return "Yes"

    model = object()
    tokenizer = FakeTokenizer()

    assert SCORER_MODEL == (
        "mlx-community/Llama-3.1-8B-Instruct-4bit"
        "@90215b22ec18e72f623dde2ea7af4097025160e2"
    )
    assert _score_with_local_model(
        fake_generate, model, tokenizer, "safe synthetic prompt"
    ) == "Yes"
    assert calls == [
        (
            model,
            tokenizer,
            "<|user|>safe synthetic prompt<|assistant|>",
            {"temp": 0, "max_tokens": 10, "verbose": False},
        )
    ]


def test_dms13_judge_snapshot_must_match_pinned_file_digest(tmp_path, monkeypatch) -> None:
    import run_context_compression_dms13 as runner

    content = b"pinned local model file"
    (tmp_path / "config.json").write_bytes(content)
    monkeypatch.setattr(
        runner,
        "SCORER_MODEL_FILES",
        {"config.json": hashlib.sha256(content).hexdigest()},
    )

    runner._verify_judge_snapshot(tmp_path)

    (tmp_path / "config.json").write_bytes(b"changed model file")
    with pytest.raises(ManualRunError, match="judge snapshot"):
        runner._verify_judge_snapshot(tmp_path)


def test_sha256_reads_snapshot_in_bounded_chunks() -> None:
    import run_context_compression_dms13 as runner

    class ChunkReader:
        def __init__(self):
            self.chunks = iter((b"pinned ", b"model", b""))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            assert size == 1024 * 1024
            return next(self.chunks)

    class SnapshotFile:
        def open(self, mode):
            assert mode == "rb"
            return ChunkReader()

    assert runner._sha256(SnapshotFile()) == hashlib.sha256(b"pinned model").hexdigest()


def test_run_approval_must_bind_all_pinned_run_artifacts() -> None:
    expected = {
        "manifest_sha256": "a" * 64,
        "preflight_sha256": "b" * 64,
        "harness_sha256": "c" * 64,
        "runtime_lock_sha256": "d" * 64,
        "scorer_model": "mlx-community/Llama-3.1-8B-Instruct-4bit@90215b22ec18e72f623dde2ea7af4097025160e2",
        "expected_remote_judge_calls": 0,
        "expected_local_judge_calls": 4500,
        "expected_von_turn_scores": 122462,
    }

    verify_run_approval({"approved": True} | expected, expected=expected)

    with pytest.raises(ManualRunError, match="approval"):
        verify_run_approval({"approved": True} | (expected | {"harness_sha256": "0" * 64}), expected=expected)


def test_manual_run_refuses_missing_approval_before_creating_model_cache(tmp_path) -> None:
    model_cache = tmp_path / "models"
    arguments = argparse.Namespace(
        preflight=Path(__file__).resolve().parents[1]
        / "specs"
        / "decision-model-support"
        / "evaluation"
        / "preflight-dms13-run-2026-09-28.json",
        approval=tmp_path / "missing-approval.json",
        model_cache=model_cache,
        source_checkout=tmp_path / "not-used-source",
        longmemeval_source=tmp_path / "not-used-benchmark",
        dataset=tmp_path / "not-used-dataset.json",
        output_dir=tmp_path / "not-used-output",
    )

    with pytest.raises(ManualRunError, match="approval"):
        run(arguments)

    assert not model_cache.exists()


def test_run_preflight_binds_current_manifest_harness_and_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    preflight_path = (
        root
        / "specs"
        / "decision-model-support"
        / "evaluation"
        / "preflight-dms13-run-2026-09-28.json"
    )
    receipt = json.loads(preflight_path.read_text(encoding="utf-8"))
    runtime_lock = (
        root
        / "specs"
        / "decision-model-support"
        / "evaluation"
        / "dms13-runtime"
        / "poetry.lock"
    )

    verify_preflight(receipt, runtime_lock_path=runtime_lock, root=root)

    altered = dict(receipt)
    altered["manifest_sha256"] = "0" * 64
    with pytest.raises(ManualRunError, match="manifest digest"):
        verify_preflight(altered, runtime_lock_path=runtime_lock, root=root)

    altered = dict(receipt)
    altered["scorer_model_snapshot_path"] = "/missing/local-judge-snapshot"
    with pytest.raises(ManualRunError, match="judge snapshot"):
        verify_preflight(altered, runtime_lock_path=runtime_lock, root=root)
