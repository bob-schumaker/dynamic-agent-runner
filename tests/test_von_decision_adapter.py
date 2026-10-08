from __future__ import annotations

from types import SimpleNamespace

import pytest

from dynamic_agent_runner.decision_models import (
    DecisionMode,
    DecisionModelRequest,
    DecisionModelResult,
    DecisionOption,
    DecisionQuestion,
    DecisionScoreSemantics,
    DecisionModelUse,
    validate_decision_result,
)
from dynamic_agent_runner.workflow_host.von_decision_adapter import (
    VON_DECISION_IDENTITY,
    VonDecisionAdapter,
)


class FakeBackend:
    def __init__(self, answer: object) -> None:
        self.answer = answer
        self.calls = []

    def evaluate_choice(self, question_id: str, state: str, choice: object) -> object:
        self.calls.append((question_id, state, choice))
        return self.answer


class FakeChoice:
    def __init__(self, *, instructions: str, criteria: dict[str, str]) -> None:
        self.instructions = instructions
        self.criteria = criteria


def _request(mode: DecisionMode = DecisionMode.CHOICE) -> DecisionModelRequest:
    return DecisionModelRequest(
        "d1",
        {"ticket": "duplicate charge"},
        (
            DecisionQuestion(
                "route",
                (
                    DecisionOption("billing", "Payments"),
                    DecisionOption("access", "Login"),
                ),
                "Where should it go?",
            ),
        ),
        mode=mode,
    )


def test_von_choice_maps_bounded_request_and_exact_choice() -> None:
    backend = FakeBackend(
        SimpleNamespace(choice="billing", probabilities={"billing": 0.8, "access": 0.2})
    )
    adapter = VonDecisionAdapter(backend, FakeChoice)

    result = adapter.decide(_request())

    assert isinstance(result, DecisionModelResult)
    assert result.identity == VON_DECISION_IDENTITY
    assert result.results[0].choice == "billing"
    question_id, state, choice = backend.calls[0]
    assert question_id == "route"
    assert '"ticket":"duplicate charge"' in state
    assert choice.criteria == {"billing": "Payments", "access": "Login"}


def test_von_adapter_is_workflow_decision_only() -> None:
    assert VonDecisionAdapter.identity == VON_DECISION_IDENTITY
    assert VonDecisionAdapter.permitted_uses == frozenset(
        {DecisionModelUse.WORKFLOW_DECISION}
    )


def test_von_scores_are_returned_in_option_order_as_probabilities() -> None:
    backend = FakeBackend(
        SimpleNamespace(
            choice="access", probabilities={"access": 0.6, "billing": 0.3999}
        )
    )
    adapter = VonDecisionAdapter(backend, FakeChoice)
    request = _request(DecisionMode.SCORES)

    result = adapter.decide(request)

    validate_decision_result(result, request, _profile())
    assert [score.option_id for score in result.results[0].scores] == [
        "billing",
        "access",
    ]
    assert [score.value for score in result.results[0].scores] == pytest.approx(
        [0.3999 / 0.9999, 0.6 / 0.9999]
    )
    assert result.results[0].score_semantics is DecisionScoreSemantics.PROBABILITY


def test_von_rejects_choice_that_disagrees_with_probabilities() -> None:
    backend = FakeBackend(
        SimpleNamespace(choice="billing", probabilities={"billing": 0.2, "access": 0.8})
    )

    with pytest.raises(ValueError, match="does not match"):
        VonDecisionAdapter(backend, FakeChoice).decide(_request())


@pytest.mark.parametrize(
    "probabilities",
    [
        {"billing": 1.0},
        {"billing": 0.2, "access": 0.2},
        {"billing": float("nan"), "access": 0.1},
    ],
)
def test_von_rejects_incomplete_or_invalid_probability_vectors(
    probabilities: dict[str, float],
) -> None:
    adapter = VonDecisionAdapter(
        FakeBackend(SimpleNamespace(choice="billing", probabilities=probabilities)),
        FakeChoice,
    )

    with pytest.raises(ValueError, match="probabilities"):
        adapter.decide(_request(DecisionMode.SCORES))


def _profile():
    from dynamic_agent_runner.decision_models import DecisionModelProfile

    return DecisionModelProfile(
        VON_DECISION_IDENTITY,
        10000,
        8192,
        8,
        20,
        10000,
        frozenset({DecisionMode.CHOICE, DecisionMode.SCORES}),
    )
