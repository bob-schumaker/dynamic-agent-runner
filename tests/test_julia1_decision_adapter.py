from __future__ import annotations

import pytest

from dynamic_agent_runner.decision_models import (
    DecisionModelRequest,
    DecisionMode,
    DecisionOption,
    DecisionQuestion,
    DecisionScoreSemantics,
    DecisionModelUse,
    validate_decision_result,
)
from dynamic_agent_runner.workflow_host.julia1_decision_adapter import (
    JULIA1_DECISION_IDENTITY,
    Julia1DecisionAdapter,
)


class FakeEngine:
    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers
        self.call = None

    def predict(self, *, state: str, questions: dict[str, object]) -> dict[str, object]:
        self.call = (state, questions)
        return {"answers": self.answers}


def test_choice_maps_named_julia_answer_to_declared_option() -> None:
    engine = FakeEngine({"route": {"type": "choice", "choice": "billing"}})
    adapter = Julia1DecisionAdapter(engine)
    request = DecisionModelRequest(
        "d1",
        {"ticket": "duplicate charge"},
        (
            DecisionQuestion(
                "route",
                (
                    DecisionOption("billing", "Payments"),
                    DecisionOption("access", "Login"),
                ),
                "Where?",
            ),
        ),
    )

    result = adapter.decide(request)

    validate_decision_result(
        result,
        request,
        _profile(),
    )
    assert result.results[0].choice == "billing"
    assert engine.call[1]["route"]["criteria"] == {
        "billing": "Payments",
        "access": "Login",
    }


@pytest.mark.parametrize("choice", ["other", ""])
def test_choice_rejects_answers_outside_the_declared_options(choice: str) -> None:
    adapter = Julia1DecisionAdapter(
        FakeEngine({"route": {"type": "choice", "choice": choice}})
    )
    request = DecisionModelRequest(
        "d1",
        "state",
        (
            DecisionQuestion(
                "route", (DecisionOption("billing"), DecisionOption("access")), "Where?"
            ),
        ),
    )

    with pytest.raises(ValueError, match="choice is invalid"):
        adapter.decide(request)


def test_rejects_unrequested_answer_ids() -> None:
    adapter = Julia1DecisionAdapter(
        FakeEngine(
            {
                "route": {"type": "choice", "choice": "billing"},
                "unrequested": {"type": "choice", "choice": "billing"},
            }
        )
    )
    request = DecisionModelRequest(
        "d1",
        "state",
        (
            DecisionQuestion(
                "route", (DecisionOption("billing"), DecisionOption("access")), "Where?"
            ),
        ),
    )

    with pytest.raises(ValueError, match="answer IDs"):
        adapter.decide(request)


def test_rejects_missing_answers_and_answer_type_mismatch() -> None:
    request = DecisionModelRequest(
        "d1",
        "state",
        (
            DecisionQuestion(
                "route", (DecisionOption("billing"), DecisionOption("access")), "Where?"
            ),
        ),
    )
    with pytest.raises(ValueError, match="answer IDs"):
        Julia1DecisionAdapter(FakeEngine({})).decide(request)
    with pytest.raises(ValueError, match="answer type"):
        Julia1DecisionAdapter(
            FakeEngine(
                {"route": {"type": "score", "probabilities": {"0": 0.5, "1": 0.5}}}
            )
        ).decide(request)


def test_julia_adapter_is_workflow_decision_only() -> None:
    assert Julia1DecisionAdapter.identity == JULIA1_DECISION_IDENTITY
    assert Julia1DecisionAdapter.permitted_uses == frozenset(
        {DecisionModelUse.WORKFLOW_DECISION}
    )


def test_score_maps_probabilities_to_option_ids_in_request_order() -> None:
    engine = FakeEngine(
        {"priority": {"type": "score", "probabilities": {"0": 0.2, "1": 0.8}}}
    )
    adapter = Julia1DecisionAdapter(engine)
    request = DecisionModelRequest(
        "d1",
        "state",
        (
            DecisionQuestion(
                "priority",
                (DecisionOption("low", "Low"), DecisionOption("high", "High")),
                "Rank.",
            ),
        ),
        mode=DecisionMode.SCORES,
    )

    result = adapter.decide(request)

    validate_decision_result(result, request, _profile())
    assert result.results[0].scores[0].option_id == "low"
    assert result.results[0].scores[1].option_id == "high"
    assert result.results[0].score_semantics is DecisionScoreSemantics.PROBABILITY
    assert engine.call[1]["priority"]["criteria"] == ["Low", "High"]


@pytest.mark.parametrize(
    ("option_order", "probabilities", "expected"),
    [
        (("yes", "no"), {"false": 0.25, "true": 0.75}, (0.75, 0.25)),
        (("no", "yes"), {"false": 0.25, "true": 0.75}, (0.25, 0.75)),
    ],
)
def test_noul_maps_boolean_probability_by_ids_and_order(
    option_order: tuple[str, str],
    probabilities: dict[str, float],
    expected: tuple[float, float],
) -> None:
    engine = FakeEngine({"answer": {"type": "noul", "probabilities": probabilities}})
    adapter = Julia1DecisionAdapter(engine)
    request = DecisionModelRequest(
        "d1",
        "state",
        (
            DecisionQuestion(
                "answer",
                tuple(DecisionOption(i, i.title()) for i in option_order),
                "True?",
            ),
        ),
        mode=DecisionMode.SCORES,
    )

    result = adapter.decide(request)

    validate_decision_result(result, request, _profile())
    assert tuple(score.value for score in result.results[0].scores) == expected
    assert engine.call[1]["answer"]["criteria"] == {"false": "No", "true": "Yes"}


@pytest.mark.parametrize(
    "answer",
    [
        {"type": "noul", "probabilities": {"false": 0.2}},
        {"type": "noul", "probabilities": {"false": 0.2, "true": 0.7}},
        {"type": "noul", "probabilities": {"false": float("nan"), "true": 0.0}},
    ],
)
def test_noul_rejects_malformed_probabilities(answer: dict[str, object]) -> None:
    adapter = Julia1DecisionAdapter(FakeEngine({"answer": answer}))
    request = DecisionModelRequest(
        "d1",
        "state",
        (
            DecisionQuestion(
                "answer", (DecisionOption("yes"), DecisionOption("no")), "True?"
            ),
        ),
        mode=DecisionMode.SCORES,
    )

    with pytest.raises(ValueError):
        adapter.decide(request)


@pytest.mark.parametrize(
    "probabilities",
    [
        {"0": -0.1, "1": 1.1},
        {"0": 0.5, "1": 0.4},
        {"0": True, "1": 0.0},
        {"0": 0.5, "1": 0.5, "2": 0.0},
        {"0": 0.5},
    ],
)
def test_score_rejects_out_of_range_or_malformed_probabilities(
    probabilities: dict[str, object],
) -> None:
    adapter = Julia1DecisionAdapter(
        FakeEngine({"priority": {"type": "score", "probabilities": probabilities}})
    )
    request = DecisionModelRequest(
        "d1",
        "state",
        (
            DecisionQuestion(
                "priority", (DecisionOption("low"), DecisionOption("high")), "Rank."
            ),
        ),
        mode=DecisionMode.SCORES,
    )

    with pytest.raises(ValueError, match="probabilities are invalid"):
        adapter.decide(request)


def test_score_rejects_choice_shaped_answer() -> None:
    adapter = Julia1DecisionAdapter(
        FakeEngine({"priority": {"type": "choice", "choice": "low"}})
    )
    request = DecisionModelRequest(
        "d1",
        "state",
        (
            DecisionQuestion(
                "priority", (DecisionOption("low"), DecisionOption("high")), "Rank."
            ),
        ),
        mode=DecisionMode.SCORES,
    )

    with pytest.raises(ValueError, match="answer type"):
        adapter.decide(request)


def test_noul_requires_exact_yes_no_option_ids() -> None:
    adapter = Julia1DecisionAdapter(
        FakeEngine(
            {"answer": {"type": "noul", "probabilities": {"false": 0.5, "true": 0.5}}}
        )
    )
    request = DecisionModelRequest(
        "d1",
        "state",
        (
            DecisionQuestion(
                "answer", (DecisionOption("approve"), DecisionOption("deny")), "True?"
            ),
        ),
        mode=DecisionMode.SCORES,
    )

    with pytest.raises(ValueError, match="yes and no"):
        adapter.decide(request)


def _profile():
    from dynamic_agent_runner.decision_models import DecisionModelProfile

    return DecisionModelProfile(
        JULIA1_DECISION_IDENTITY,
        10000,
        8192,
        8,
        20,
        10000,
        frozenset({DecisionMode.CHOICE, DecisionMode.SCORES}),
    )
