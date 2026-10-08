"""Fake-only tests for the manually gated Laya-MLX evaluator."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "manual"))

from run_laya_mlx_dms08 import (  # noqa: E402
    EXPECTED_ARTIFACTS,
    EXPECTED_SOURCE,
    INPUTS_SHA256,
    MAX_INPUT_TOKENS,
    MODEL_ID,
    MODEL_REVISION,
    ManualRunError,
    _ensure_context_fits,
    _load_agent,
    _validate_answer,
    build_request,
    score_input_rows,
    verify_preflight,
)


def test_laya_request_uses_only_fixture_inputs() -> None:
    row = {
        "id": "D001",
        "kind": "decision",
        "state": {"days_elapsed": 2},
        "question": {
            "id": "period-check",
            "text": "Is the elapsed period allowed?",
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
                "type": "choice",
                "instructions": "Is the elapsed period allowed?",
                "criteria": {"over": "Outside", "within": "Within"},
            }
        },
    }
    assert "expected_option_id" not in str(request)


def test_laya_retention_uses_bounded_binary_questions() -> None:
    request = build_request({
        "id": "R001",
        "kind": "retention",
        "task_context": "Complete the task.",
        "eligible_messages_oldest_first": [
            {"id": "m1", "content": "secret one"},
            {"id": "m2", "content": "secret two"},
        ],
    })

    assert list(request["questions"]) == ["m1", "m2"]
    assert request["questions"]["m1"]["type"] == "choice"
    assert set(request["questions"]["m1"]["criteria"]) == {"keep", "drop"}
    assert "secret one" in request["questions"]["m1"]["instructions"]
    assert "expected" not in str(request)


def test_laya_rejects_inputs_above_checkpoint_limit() -> None:
    question = {
        "type": "choice",
        "instructions": "Pick one.",
        "criteria": {"a": "A", "b": "B"},
    }
    row = {"id": "D001", "kind": "decision", "state": "x" * (MAX_INPUT_TOKENS + 1),
           "question": {"id": "q", "text": "Pick?", "options": [
               {"id": key, "label": value} for key, value in question["criteria"].items()
           ]}}

    def reject_oversize(_agent, _request):
        raise ManualRunError("input exceeds Laya-MLX context limit")

    predictions, *_ = score_input_rows(
        [row], agent=object(), tokenizer=lambda _text: {"input_ids": []},
        context_check=reject_oversize,
    )
    assert predictions == [{"id": "D001", "kind": "decision", "status": "oversize"}]


def test_laya_scores_map_by_option_id_and_redact_content() -> None:
    row = {
        "id": "R001", "kind": "retention", "task_context": "secret context",
        "eligible_messages_oldest_first": [
            {"id": "m1", "content": "secret keep"},
            {"id": "m2", "content": "secret drop"},
        ],
    }

    class Agent:
        def predict(self, state, questions):
            assert state == "secret context"
            assert "secret keep" in questions["m1"]["instructions"]
            assert "secret drop" in questions["m2"]["instructions"]
            assert list(questions) == ["m1", "m2"]
            return {"answers": {
                "m1": {"type": "choice", "choice": "keep", "probabilities": {"keep": .8, "drop": .2}},
                "m2": {"type": "choice", "choice": "drop", "probabilities": {"keep": .1, "drop": .9}},
            }}

    predictions, token_counts, latencies, peak_memory, oom = score_input_rows(
        [row], agent=Agent(), tokenizer=lambda text: {"input_ids": text.split()},
        context_check=lambda *_args: None,
    )

    assert predictions == [{
        "id": "R001", "kind": "retention", "status": "ok",
        "score_semantics": "probability", "scores": {"m1": .8, "m2": .1},
    }]
    assert token_counts == [
        {"message_id": "m1", "token_count": 2},
        {"message_id": "m2", "token_count": 2},
    ]
    assert "secret" not in str(predictions + token_counts)
    assert len(latencies) == 1
    assert peak_memory > 0
    assert not oom


def test_laya_decision_output_uses_option_ids() -> None:
    row = {
        "id": "D001", "kind": "decision", "state": {"days_elapsed": 2},
        "question": {
            "id": "period-check", "text": "Is it allowed?",
            "options": [{"id": "over", "label": "Outside"},
                        {"id": "within", "label": "Within"}],
        },
    }

    class Agent:
        def predict(self, _state, questions):
            assert questions["period-check"]["criteria"] == {
                "over": "Outside", "within": "Within",
            }
            return {"answers": {"period-check": {
                "type": "choice", "choice": "within",
                "probabilities": {"within": .8999, "over": .1001},
            }}}

    predictions, *_ = score_input_rows(
        [row], agent=Agent(), tokenizer=lambda _text: {"input_ids": []},
        context_check=lambda *_args: None,
    )

    assert predictions == [{
        "id": "D001", "kind": "decision", "status": "ok", "choice": "within",
        "score_semantics": "probability", "scores": {"within": .8999, "over": .1001},
    }]


def test_laya_normalizes_only_four_decimal_rounding_drift() -> None:
    values = _validate_answer({
        "type": "choice", "choice": "within",
        "probabilities": {"over": .4324, "within": .5677},
    }, {"over", "within"})

    assert sum(values.values()) == pytest.approx(1.0, abs=1e-12)
    assert values["within"] > values["over"]
    with pytest.raises(ManualRunError, match="do not sum to one"):
        _validate_answer({
            "type": "choice", "choice": "within",
            "probabilities": {"over": .4, "within": .5},
        }, {"over", "within"})


def test_laya_context_check_counts_question_prefix_and_full_state(monkeypatch) -> None:
    package = ModuleType("laya_mlx")
    common = ModuleType("laya_mlx.common")
    common.build_prefix = lambda _tok, _question, _limit: (list(range(1023)), [])
    common.serialize_state = lambda state: state
    package.common = common
    monkeypatch.setitem(sys.modules, "laya_mlx", package)
    monkeypatch.setitem(sys.modules, "laya_mlx.common", common)

    class Tokenizer:
        mask_token = "[MASK]"

        def __call__(self, _state, add_special_tokens=False):
            assert add_special_tokens is False
            return {"input_ids": [1]}

    agent = SimpleNamespace(
        cfg={"max_len": MAX_INPUT_TOKENS, "head_max_len": 256}, tok=Tokenizer(),
        _to_internal=lambda question: question,
    )

    # Special markers and one state token exceed 1024 and must not be truncated.
    with pytest.raises(ManualRunError, match="exceeds Laya-MLX context limit"):
        _ensure_context_fits(agent, {
            "state": "state", "questions": {"q": {
                "type": "choice", "instructions": "Pick.",
                "criteria": {"a": "A", "b": "B"},
            }},
        })


def test_laya_loader_pins_download_then_switches_offline(tmp_path: Path, monkeypatch) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    weight = model_dir / "model.safetensors"
    weight.touch()
    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        return model_dir

    fake_hub = ModuleType("huggingface_hub")
    fake_hub.snapshot_download = download
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
    import run_laya_mlx_dms08 as runner

    monkeypatch.setattr(runner, "_sha256", lambda _path: runner.MODEL_SHA256)
    fake_laya = ModuleType("laya_mlx")
    fake_laya.__version__ = "0.2.0"

    def load(path, *, revision, dtype):
        assert Path(path) == model_dir
        assert revision == MODEL_REVISION
        assert dtype == "float16"
        assert __import__("os").environ["HF_HUB_OFFLINE"] == "1"
        return object()

    fake_laya.load = load
    monkeypatch.setitem(sys.modules, "laya_mlx", fake_laya)

    _load_agent(tmp_path, model_dir)

    assert calls == [{"repo_id": MODEL_ID, "revision": MODEL_REVISION,
                      "local_dir": str(model_dir)}]


def test_laya_refuses_unapproved_or_blocked_preflight(tmp_path: Path) -> None:
    receipt = {
        "candidate_run_approved": True,
        "run_allowed": False,
        "fixture_criteria_approved": True,
        "input_sha256": INPUTS_SHA256,
        "source": EXPECTED_SOURCE,
        "artifacts": EXPECTED_ARTIFACTS,
    }

    with pytest.raises(ManualRunError, match="preflight did not allow"):
        verify_preflight(receipt, source_checkout=tmp_path, runtime_checkout=tmp_path)


def test_laya_refuses_mismatched_model_and_source_pins(tmp_path: Path) -> None:
    receipt = {
        "candidate_run_approved": True,
        "run_allowed": True,
        "fixture_criteria_approved": True,
        "input_sha256": INPUTS_SHA256,
        "source": {"id": EXPECTED_SOURCE["id"], "revision": "0" * 40},
        "artifacts": EXPECTED_ARTIFACTS,
    }

    with pytest.raises(ManualRunError, match="source revision differs"):
        verify_preflight(receipt, source_checkout=tmp_path, runtime_checkout=tmp_path)


def test_laya_refuses_mismatched_model_revision(tmp_path: Path) -> None:
    receipt = {
        "candidate_run_approved": True,
        "run_allowed": True,
        "fixture_criteria_approved": True,
        "input_sha256": INPUTS_SHA256,
        "source": EXPECTED_SOURCE,
        "artifacts": [{"id": MODEL_ID, "revision": "0" * 40}],
        "provenance_base": {"id": "convaiinnovations/laya-typed-decisions", "revision": "0" * 40},
        "expected_model_file_sha256": {"model.safetensors": "0" * 64},
    }

    with pytest.raises(ManualRunError, match="model revision differs"):
        verify_preflight(receipt, source_checkout=tmp_path, runtime_checkout=tmp_path)


def test_laya_accepts_only_the_exact_clean_runtime_preflight(tmp_path: Path, monkeypatch) -> None:
    import run_laya_mlx_dms08 as runner

    source = tmp_path / "source"
    runtime = tmp_path / "runtime"
    source.mkdir()
    runtime.mkdir()
    lock = runtime / "poetry.lock"
    lock.write_text("frozen isolated lock")
    lock_hash = runner._sha256(lock)
    monkeypatch.setattr(runner, "_runtime_versions", lambda: (runner.RUNTIME_PACKAGES, True))
    monkeypatch.setattr(runner, "_repository_revision", lambda _path: runner.SOURCE_REVISION)
    monkeypatch.setattr(runner, "_repository_clean", lambda _path: True)
    monkeypatch.setattr(runner, "_expected_harness_files", lambda: [{"id": "fake", "sha256": "f" * 64}])
    receipt = {
        "candidate_run_approved": True, "run_allowed": True,
        "fixture_criteria_approved": True, "input_sha256": INPUTS_SHA256,
        "source": EXPECTED_SOURCE, "artifacts": EXPECTED_ARTIFACTS,
        "provenance_base": runner.EXPECTED_BASE,
        "expected_model_file_sha256": runner.EXPECTED_MODEL_FILES,
        "runtime": {
            "available": True, "executable": str(Path(sys.executable).resolve()),
            "python_version": sys.version.split()[0], "packages": runner.RUNTIME_PACKAGES,
            "lock_sha256": lock_hash,
        },
        "evaluation_harness_files": [{"id": "fake", "sha256": "f" * 64}],
    }

    verify_preflight(receipt, source_checkout=source, runtime_checkout=runtime)

    receipt["runtime"]["packages"] = {**runner.RUNTIME_PACKAGES, "mlx": "0.31.3"}
    with pytest.raises(ManualRunError, match="exact pinned Laya-MLX runtime"):
        verify_preflight(receipt, source_checkout=source, runtime_checkout=runtime)
