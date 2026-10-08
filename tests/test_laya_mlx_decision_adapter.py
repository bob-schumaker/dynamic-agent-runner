from __future__ import annotations

import pytest

from dynamic_agent_runner.decision_models import (
    DecisionMode,
    DecisionModelRequest,
    DecisionOption,
    DecisionQuestion,
    DecisionScoreSemantics,
    DecisionModelUse,
    validate_decision_result,
)
from dynamic_agent_runner.workflow_host.laya_mlx_decision_adapter import (
    LAYA_MLX_DECISION_IDENTITY,
    LayaMLXDecisionAdapter,
)


class FakeAgent:
    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers
        self.call = None

    def predict(self, state: object, questions: dict[str, object]) -> dict[str, object]:
        self.call = (state, questions)
        return {"answers": self.answers}


def _request(mode: DecisionMode, ids: tuple[str, ...]) -> DecisionModelRequest:
    return DecisionModelRequest(
        "d1",
        {"ticket": "duplicate charge"},
        (
            DecisionQuestion(
                "answer",
                tuple(
                    DecisionOption(option_id, option_id.title()) for option_id in ids
                ),
                "Choose based on the ticket.",
            ),
        ),
        mode=mode,
    )


def test_choice_preserves_option_ids_and_validates_result() -> None:
    agent = FakeAgent(
        {
            "answer": {
                "type": "choice",
                "choice": "billing",
                "probabilities": {"billing": 0.8, "sales": 0.2},
            }
        }
    )
    adapter = LayaMLXDecisionAdapter(agent)
    request = _request(DecisionMode.CHOICE, ("billing", "sales"))

    result = adapter.decide(request)

    validate_decision_result(result, request, _profile())
    assert result.identity == LAYA_MLX_DECISION_IDENTITY
    assert result.results[0].choice == "billing"
    assert agent.call[1]["answer"]["criteria"] == {
        "billing": "Billing",
        "sales": "Sales",
    }


def test_laya_adapter_is_workflow_decision_only() -> None:
    assert LayaMLXDecisionAdapter.identity == LAYA_MLX_DECISION_IDENTITY
    assert LayaMLXDecisionAdapter.permitted_uses == frozenset(
        {DecisionModelUse.WORKFLOW_DECISION}
    )


def test_ordered_score_probabilities_map_back_to_declared_option_ids() -> None:
    agent = FakeAgent(
        {"answer": {"type": "score", "probabilities": {"0": 0.2, "1": 0.8}}}
    )
    adapter = LayaMLXDecisionAdapter(agent)
    request = _request(DecisionMode.SCORES, ("low", "high"))

    result = adapter.decide(request)

    validate_decision_result(result, request, _profile())
    assert result.results[0].score_semantics is DecisionScoreSemantics.PROBABILITY
    assert [score.option_id for score in result.results[0].scores] == ["low", "high"]
    assert agent.call[1]["answer"]["criteria"] == ["Low", "High"]


@pytest.mark.parametrize(
    ("ids", "noul", "expected"),
    [(("yes", "no"), 0.8, (0.8, 0.2)), (("no", "yes"), 0.8, (0.2, 0.8))],
)
def test_noul_maps_probability_to_yes_no_in_request_order(
    ids: tuple[str, str], noul: float, expected: tuple[float, float]
) -> None:
    agent = FakeAgent({"answer": {"type": "noul", "noul": noul}})
    adapter = LayaMLXDecisionAdapter(agent)
    request = _request(DecisionMode.SCORES, ids)

    result = adapter.decide(request)

    validate_decision_result(result, request, _profile())
    assert tuple(score.value for score in result.results[0].scores) == pytest.approx(
        expected
    )
    assert agent.call[1]["answer"]["criteria"] == {"false": "No", "true": "Yes"}


@pytest.mark.parametrize(
    "answer",
    [
        {"type": "noul", "noul": float("nan")},
        {"type": "noul", "noul": 1.01},
        {"type": "noul", "noul": True},
    ],
)
def test_noul_rejects_malformed_probability(answer: dict[str, object]) -> None:
    adapter = LayaMLXDecisionAdapter(FakeAgent({"answer": answer}))

    with pytest.raises(ValueError, match="noul probability"):
        adapter.decide(_request(DecisionMode.SCORES, ("yes", "no")))


def test_laya_rejects_missing_answers_and_noul_for_other_option_ids() -> None:
    with pytest.raises(ValueError, match="answers"):
        LayaMLXDecisionAdapter(FakeAgent({})).decide(
            _request(DecisionMode.CHOICE, ("a", "b"))
        )
    with pytest.raises(ValueError, match="yes and no"):
        LayaMLXDecisionAdapter(
            FakeAgent({"answer": {"type": "noul", "noul": 0.5}})
        ).decide(_request(DecisionMode.SCORES, ("approve", "reject")))


@pytest.mark.parametrize(
    "answers",
    [
        {
            "other": {
                "type": "choice",
                "choice": "billing",
                "probabilities": {"billing": 1.0},
            }
        },
        {
            "answer": {
                "type": "choice",
                "choice": "billing",
                "probabilities": {"billing": 0.8, "sales": 0.2},
            },
            "other": {
                "type": "choice",
                "choice": "billing",
                "probabilities": {"billing": 1.0},
            },
        },
    ],
)
def test_laya_rejects_missing_or_unrequested_answer_ids(
    answers: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="answers are incomplete"):
        LayaMLXDecisionAdapter(FakeAgent(answers)).decide(
            _request(DecisionMode.CHOICE, ("billing", "sales"))
        )


def test_laya_rejects_wrong_answer_type_and_declared_choice_mismatch() -> None:
    with pytest.raises(ValueError, match="answer type"):
        LayaMLXDecisionAdapter(
            FakeAgent(
                {"answer": {"type": "score", "probabilities": {"0": 0.5, "1": 0.5}}}
            )
        ).decide(_request(DecisionMode.CHOICE, ("billing", "sales")))
    with pytest.raises(ValueError, match="declared option"):
        LayaMLXDecisionAdapter(
            FakeAgent(
                {
                    "answer": {
                        "type": "choice",
                        "choice": "other",
                        "probabilities": {"billing": 0.8, "sales": 0.2},
                    }
                }
            )
        ).decide(_request(DecisionMode.CHOICE, ("billing", "sales")))


def _profile():
    from dynamic_agent_runner.decision_models import DecisionModelProfile

    return DecisionModelProfile(
        LAYA_MLX_DECISION_IDENTITY,
        10000,
        1024,
        16,
        20,
        10000,
        frozenset({DecisionMode.CHOICE, DecisionMode.SCORES}),
    )
