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
from dynamic_agent_runner.workflow_host.kev_decision_adapter import (
    KEV_06B_DECISION_IDENTITY,
    KevDecisionAdapter,
)


class FakeAPI:
    class Choice:
        def __init__(self, **data):
            self.data = data

    class Score:
        def __init__(self, **data):
            self.data = data

    class Noul:
        def __init__(self, **data):
            self.data = data

    class SystemOneRequest:
        def __init__(self, **data):
            self.data = data

    @staticmethod
    def to_record(request):
        metadata = []
        for question_id, question in request.data["questions"].items():
            kind = question.__class__.__name__.lower()
            criteria = question.data.get("criteria")
            keys = (
                list(criteria)
                if kind == "choice"
                else ["false", "true"]
                if kind == "noul"
                else [str(i) for i in range(len(criteria))]
            )
            metadata.append({"id": question_id, "keys": keys})
        return request.data, metadata


class FakeModel:
    def __init__(self, values: list[list[float]]) -> None:
        self.values = values
        self.encoded = None

    def encode(self, tokenizer, record, *, max_state: int, max_branch: int):
        self.encoded = (tokenizer, record, max_state, max_branch)
        return object()

    def probs(self, _encoded):
        return self.values


def _request(mode: DecisionMode, ids: tuple[str, ...]) -> DecisionModelRequest:
    return DecisionModelRequest(
        "d1",
        {"ticket": "payment issue"},
        (
            DecisionQuestion(
                "answer",
                tuple(
                    DecisionOption(option_id, option_id.title()) for option_id in ids
                ),
                "Where should this go?",
            ),
        ),
        mode=mode,
    )


def test_kev_choice_maps_named_options_and_uses_pinned_serving_limits() -> None:
    model = FakeModel([[0.75, 0.25]])
    adapter = KevDecisionAdapter(model, tokenizer="tok", api=FakeAPI)
    request = _request(DecisionMode.CHOICE, ("billing", "access"))

    result = adapter.decide(request)

    assert result.identity == KEV_06B_DECISION_IDENTITY
    assert result.results[0].choice == "billing"
    assert model.encoded[2:] == (8192, 8192)


def test_kev_adapter_is_workflow_decision_only() -> None:
    assert KevDecisionAdapter.identity == KEV_06B_DECISION_IDENTITY
    assert KevDecisionAdapter.permitted_uses == frozenset(
        {DecisionModelUse.WORKFLOW_DECISION}
    )


def test_kev_score_returns_probabilities_in_request_order() -> None:
    model = FakeModel([[0.2, 0.8]])
    adapter = KevDecisionAdapter(model, tokenizer="tok", api=FakeAPI)
    request = _request(DecisionMode.SCORES, ("low", "high"))

    result = adapter.decide(request)

    validate_decision_result(result, request, _profile())
    assert result.results[0].score_semantics is DecisionScoreSemantics.PROBABILITY
    assert [score.option_id for score in result.results[0].scores] == ["low", "high"]


@pytest.mark.parametrize(
    ("ids", "probabilities", "expected"),
    [(("yes", "no"), [0.3, 0.7], (0.7, 0.3)), (("no", "yes"), [0.3, 0.7], (0.3, 0.7))],
)
def test_kev_noul_maps_false_true_probabilities_by_option_id_and_order(
    ids: tuple[str, str], probabilities: list[float], expected: tuple[float, float]
) -> None:
    adapter = KevDecisionAdapter(
        FakeModel([probabilities]), tokenizer="tok", api=FakeAPI
    )
    result = adapter.decide(_request(DecisionMode.SCORES, ids))

    assert tuple(score.value for score in result.results[0].scores) == expected


@pytest.mark.parametrize(
    "probabilities", [[[0.5]], [[0.5, 0.3]], [[float("nan"), 0.5]]]
)
def test_kev_rejects_malformed_probabilities(probabilities: list[list[float]]) -> None:
    adapter = KevDecisionAdapter(FakeModel(probabilities), tokenizer="tok", api=FakeAPI)

    with pytest.raises(ValueError, match="probabilities"):
        adapter.decide(_request(DecisionMode.SCORES, ("low", "high")))


def test_kev_imports_its_optional_api_only_when_decide_is_selected(monkeypatch) -> None:
    calls = []

    def import_module(name: str):
        calls.append(name)
        return FakeAPI

    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.kev_decision_adapter.importlib.import_module",
        import_module,
    )
    adapter = KevDecisionAdapter(FakeModel([[0.6, 0.4]]), tokenizer="tok")
    assert calls == []

    adapter.decide(_request(DecisionMode.CHOICE, ("a", "b")))

    assert calls == ["kev.api"]


def _profile():
    from dynamic_agent_runner.decision_models import DecisionModelProfile

    return DecisionModelProfile(
        KEV_06B_DECISION_IDENTITY,
        10000,
        8192,
        16,
        255,
        10000,
        frozenset({DecisionMode.CHOICE, DecisionMode.SCORES}),
    )
