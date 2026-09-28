from __future__ import annotations

import argparse
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


def test_dms13_judge_adapter_uses_dar_default_openai_auth(monkeypatch) -> None:
    from dynamic_agent_runner import openai_client

    expected_adapter = object()
    provider = object()
    provider_calls = []
    adapter_calls = []

    def create_provider(config=None):
        provider_calls.append(config)
        return provider

    def create_adapter(*, provider):
        adapter_calls.append(provider)
        return expected_adapter

    monkeypatch.setattr(openai_client, "create_default_openai_provider", create_provider)
    monkeypatch.setattr(openai_client, "create_openai_adapter", create_adapter)

    from run_context_compression_dms13 import _create_judge_adapter

    assert _create_judge_adapter() is expected_adapter
    assert provider_calls == [None]
    assert adapter_calls == [provider]


def test_dms13_judge_uses_selected_responses_model() -> None:
    from run_context_compression_dms13 import SCORER_MODEL, _score_with_adapter

    class FakeAdapter:
        def __init__(self):
            self.requests = []

        def create_response(self, request):
            self.requests.append(request)
            return type("Response", (), {"content": "Yes"})()

    adapter = FakeAdapter()

    assert _score_with_adapter(adapter, "safe synthetic prompt") == "Yes"
    request = adapter.requests[0]
    assert request.model == SCORER_MODEL == "gpt-6-luna"
    assert request.messages == ({"role": "user", "content": "safe synthetic prompt"},)
    assert request.extra == {"max_output_tokens": 64, "temperature": 0}


def test_run_approval_must_bind_all_pinned_run_artifacts() -> None:
    expected = {
        "manifest_sha256": "a" * 64,
        "preflight_sha256": "b" * 64,
        "harness_sha256": "c" * 64,
        "runtime_lock_sha256": "d" * 64,
        "scorer_model": "gpt-6-luna",
        "expected_external_requests": 4500,
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
        / "preflight-dms13-2026-09-27.json",
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
