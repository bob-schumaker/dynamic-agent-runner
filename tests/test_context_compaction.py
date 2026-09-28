"""Tests for caller-owned provider context compaction contracts."""

from dynamic_agent_runner.decision_models import (
    DecisionExecutionLimits,
    DecisionModelBinding,
    DecisionModelIdentity,
    DecisionModelProfile,
    DecisionModelResult,
    DecisionModelResultItem,
    DecisionModelScore,
    DecisionMode,
)
from dynamic_agent_runner import (
    ProviderContextCompactionRequest,
    ProviderContextCompactionResult,
    ProviderContextCompactor,
)
from dynamic_agent_runner.context_compaction import _score_retention_turns
from dynamic_agent_runner.openai_client import OpenAIMessage
import pytest


def test_provider_context_compaction_contract_is_public() -> None:
    request = ProviderContextCompactionRequest(
        messages=(OpenAIMessage(role="user", content="hello"),),
        model="gpt-test",
        phase="pre_turn",
        provider_capability="responses_compact",
        max_replacement_messages=32,
        preserve_system_messages=True,
        tokens_before=4,
    )
    result = ProviderContextCompactionResult(messages=request.messages)

    assert ProviderContextCompactor is not None
    assert result.messages == request.messages


def _retention_binding(adapter: object) -> DecisionModelBinding:
    return DecisionModelBinding(
        profile=DecisionModelProfile(
            identity=DecisionModelIdentity(
                "local.retention.v1", "retention-test", "test-model", "rev1", "test"
            ),
            max_input_bytes=10000,
            max_input_tokens=1000,
            max_questions=2,
            max_options_per_question=2,
            max_result_bytes=10000,
            supported_modes=frozenset({DecisionMode.SCORES}),
        ),
        adapter=adapter,
        execution_limits=DecisionExecutionLimits(),
    )


def test_retention_scoring_uses_bounded_batches_stable_ids_and_atomic_turns() -> None:
    class Adapter:
        requests = []

        def decide(self, request) -> DecisionModelResult:
            self.requests.append(request)
            items = []
            for question in request.questions:
                keep = 3.0 if question.id == "turn_2" else 1.0
                items.append(
                    DecisionModelResultItem(
                        question.id,
                        scores=(
                            DecisionModelScore("keep", keep),
                            DecisionModelScore("drop", 0.0),
                        ),
                        score_semantics="ranking_score",
                    )
                )
            return DecisionModelResult(self_binding.profile.identity, tuple(items))

    adapter = Adapter()
    self_binding = _retention_binding(adapter)
    candidates = (
        ("turn_0", (("message-0000", OpenAIMessage("user", "old request")),)),
        (
            "turn_1",
            (
                ("message-0001", OpenAIMessage("user", "tool task")),
                ("message-0002", OpenAIMessage("assistant", "tool call")),
                ("message-0003", OpenAIMessage("tool", "tool result")),
            ),
        ),
        ("turn_2", (("message-0004", OpenAIMessage("user", "important request")),)),
    )

    selected = _score_retention_turns(
        task_context="finish migration",
        candidates=candidates,
        binding=self_binding,
        policy={
            "profile_id": "local.retention.v1",
            "selection": "bounded_ranking",
            "max_selected_turns": 1,
            "max_candidates": 10,
            "batch_size": 2,
            "fallback": "recency",
        },
    )

    assert tuple(turn_id for turn_id, _ in selected.turns) == ("turn_2",)
    assert selected.turns[0][1] == candidates[2][1]
    assert len(adapter.requests) == 2
    assert adapter.requests[0].questions[0].id == "turn_0"
    assert adapter.requests[0].questions[1].id == "turn_1"
    assert [
        message["id"]
        for message in adapter.requests[0].context["candidate_messages"]
    ] == ["message-0000", "message-0001", "message-0002", "message-0003"]
    assert selected.diagnostics == {"status": "scored", "scored_turns": 3, "selected_turns": 1}


def test_retention_scores_are_diagnostic_without_explicit_selection() -> None:
    class Adapter:
        def decide(self, request) -> DecisionModelResult:
            return DecisionModelResult(
                self_binding.profile.identity,
                tuple(
                    DecisionModelResultItem(
                        question.id,
                        scores=(
                            DecisionModelScore("keep", 100.0),
                            DecisionModelScore("drop", 0.0),
                        ),
                        score_semantics="ranking_score",
                    )
                    for question in request.questions
                ),
            )

    self_binding = _retention_binding(Adapter())
    result = _score_retention_turns(
        task_context="task",
        candidates=(("turn_0", (("message-0", OpenAIMessage("user", "old")),)),),
        binding=self_binding,
        policy={
            "profile_id": "local.retention.v1",
            "max_candidates": 10,
            "batch_size": 2,
            "fallback": "recency",
        },
    )

    assert result.turns == ()
    assert result.diagnostics == {"status": "diagnostic_only", "scored_turns": 1, "selected_turns": 0}


def test_retention_threshold_selection_requires_probabilities_and_keeps_only_thresholded_turns() -> None:
    class Adapter:
        def decide(self, request) -> DecisionModelResult:
            return DecisionModelResult(
                self_binding.profile.identity,
                tuple(
                    DecisionModelResultItem(
                        question.id,
                        scores=(
                            DecisionModelScore(
                                "keep", 0.8 if question.id == "turn_1" else 0.6
                            ),
                            DecisionModelScore(
                                "drop", 0.2 if question.id == "turn_1" else 0.4
                            ),
                        ),
                        score_semantics="probability",
                    )
                    for question in request.questions
                ),
            )

    self_binding = _retention_binding(Adapter())
    candidates = tuple(
        (f"turn_{index}", ((f"message-{index}", OpenAIMessage("user", f"turn {index}")),))
        for index in range(2)
    )
    result = _score_retention_turns(
        task_context="task",
        candidates=candidates,
        binding=self_binding,
        policy={
            "profile_id": "local.retention.v1",
            "selection": "threshold",
            "threshold": 0.7,
            "max_selected_turns": 2,
            "max_candidates": 10,
            "batch_size": 2,
            "fallback": "recency",
        },
    )

    assert tuple(turn_id for turn_id, _turn in result.turns) == ("turn_1",)


def test_retention_threshold_selection_rejects_ranking_scores() -> None:
    class Adapter:
        def decide(self, request) -> DecisionModelResult:
            return DecisionModelResult(
                self_binding.profile.identity,
                tuple(
                    DecisionModelResultItem(
                        question.id,
                        scores=(
                            DecisionModelScore("keep", 0.9),
                            DecisionModelScore("drop", 0.1),
                        ),
                        score_semantics="ranking_score",
                    )
                    for question in request.questions
                ),
            )

    self_binding = _retention_binding(Adapter())
    with pytest.raises(ValueError, match="probability"):
        _score_retention_turns(
            task_context="task",
            candidates=(("turn_0", (("message-0", OpenAIMessage("user", "old")),)),),
            binding=self_binding,
            policy={
                "profile_id": "local.retention.v1",
                "selection": "threshold",
                "threshold": 0.7,
                "max_selected_turns": 1,
                "max_candidates": 10,
                "batch_size": 2,
                "fallback": "recency",
            },
        )


@pytest.mark.parametrize("failure", ["missing", "invalid", "abstained", "timeout"])
def test_retention_scoring_failures_never_return_deletions(failure: str) -> None:
    class Adapter:
        def decide(self, request):
            if failure == "missing":
                return DecisionModelResult(self_binding.profile.identity, ())
            if failure == "invalid":
                return DecisionModelResult(
                    self_binding.profile.identity,
                    (DecisionModelResultItem("wrong-id", choice="keep"),),
                )
            if failure == "abstained":
                return DecisionModelResult(
                    self_binding.profile.identity,
                    (DecisionModelResultItem(request.questions[0].id, status="abstained"),),
                )
            raise TimeoutError("private timeout details")

    self_binding = _retention_binding(Adapter())
    candidates = (("turn_0", (("message-0", OpenAIMessage("user", "old")),)),)
    with pytest.raises(ValueError, match="scoring"):
        _score_retention_turns(
            task_context="task",
            candidates=candidates,
            binding=self_binding,
            policy={
                "profile_id": "local.retention.v1",
                "selection": "threshold",
                "threshold": 0.5,
                "max_selected_turns": 1,
                "max_candidates": 10,
                "batch_size": 2,
                "fallback": "recency",
            },
        )
