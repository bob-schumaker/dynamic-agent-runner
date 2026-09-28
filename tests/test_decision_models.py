from __future__ import annotations

import math

import pytest

from dynamic_agent_runner.decision_models import (
    DecisionExecutionLimits,
    DecisionModelIdentity,
    DecisionModelProfile,
    DecisionModelRequest,
    DecisionModelResult,
    DecisionModelResultItem,
    DecisionModelScore,
    DecisionModelContractError,
    DecisionMode,
    DecisionQuestion,
    DecisionOption,
    validate_decision_request,
    validate_decision_result,
)


IDENTITY = DecisionModelIdentity(
    profile_id="local.test.v1",
    adapter_id="test-adapter",
    model_id="test-model",
    model_revision="revision-1",
    runtime_id="test-runtime",
)


def profile(**overrides: object) -> DecisionModelProfile:
    values: dict[str, object] = {
        "identity": IDENTITY,
        "max_input_bytes": 1024,
        "max_input_tokens": 100,
        "max_questions": 4,
        "max_options_per_question": 4,
        "max_result_bytes": 1024,
        "supported_modes": frozenset({DecisionMode.CHOICE, DecisionMode.SCORES}),
    }
    values.update(overrides)
    return DecisionModelProfile(**values)  # type: ignore[arg-type]


def request(
    *,
    mode: DecisionMode = DecisionMode.CHOICE,
    questions: tuple[DecisionQuestion, ...] | None = None,
    context: object = None,
    input_tokens: int = 1,
) -> DecisionModelRequest:
    return DecisionModelRequest(
        decision_id="decision-1",
        context={"value": "test"} if context is None else context,
        questions=questions
        or (
            DecisionQuestion(
                id="question-1",
                options=(DecisionOption("yes"), DecisionOption("no")),
                text="Answer the question.",
            ),
        ),
        mode=mode,
        task_profile_id="task.test.v1",
        input_tokens=input_tokens,
    )


def test_valid_choice_and_score_requests_are_accepted() -> None:
    validate_decision_request(request(), profile())
    validate_decision_request(request(mode=DecisionMode.SCORES), profile())
    assert request().questions[0].text == "Answer the question."


def test_invalid_mode_duplicate_ids_missing_questions_and_empty_options_rejected() -> None:
    with pytest.raises(DecisionModelContractError, match="mode"):
        DecisionModelRequest("d", {}, (), "other", None)  # type: ignore[arg-type]
    with pytest.raises(DecisionModelContractError, match="decision id"):
        DecisionModelRequest(
            "",
            {},
            (DecisionQuestion("q", (DecisionOption("a"),), "Choose."),),
            DecisionMode.CHOICE,
        )
    with pytest.raises(DecisionModelContractError, match="question"):
        DecisionModelRequest("d", {}, ())
    with pytest.raises(DecisionModelContractError, match="duplicate"):
        DecisionModelRequest(
            "d",
            {},
            (DecisionQuestion("q", (DecisionOption("a"),), "Choose."),) * 2,
        )
    with pytest.raises(DecisionModelContractError, match="option"):
        DecisionQuestion("q", (), "Choose.")


def test_duplicate_option_ids_and_invalid_profile_limits_are_rejected() -> None:
    with pytest.raises(DecisionModelContractError, match="duplicate"):
        DecisionQuestion("q", (DecisionOption("a"), DecisionOption("a")), "Choose.")
    with pytest.raises(DecisionModelContractError, match="limit"):
        profile(max_questions=0)


def test_unknown_choice_and_missing_or_duplicate_results_are_rejected() -> None:
    source = request()
    with pytest.raises(DecisionModelContractError, match="option"):
        validate_decision_result(
            DecisionModelResult(IDENTITY, (DecisionModelResultItem("question-1", choice="maybe"),)),
            source,
            profile(),
        )
    with pytest.raises(DecisionModelContractError, match="cardinality"):
        validate_decision_result(DecisionModelResult(IDENTITY, ()), source, profile())
    duplicate = DecisionModelResult(
        IDENTITY,
        (
            DecisionModelResultItem("question-1", choice="yes"),
            DecisionModelResultItem("question-1", choice="no"),
        ),
    )
    with pytest.raises(DecisionModelContractError, match="order"):
        validate_decision_result(duplicate, source, profile())


def test_result_question_order_must_match_request_order() -> None:
    source = request(
        questions=(
            DecisionQuestion("first", (DecisionOption("a"), DecisionOption("b")), "First?"),
            DecisionQuestion("second", (DecisionOption("a"), DecisionOption("b")), "Second?"),
        )
    )
    result = DecisionModelResult(
        IDENTITY,
        (
            DecisionModelResultItem("second", choice="a"),
            DecisionModelResultItem("first", choice="b"),
        ),
    )
    with pytest.raises(DecisionModelContractError, match="order"):
        validate_decision_result(result, source, profile())


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf])
def test_non_finite_scores_are_rejected(score: float) -> None:
    with pytest.raises(DecisionModelContractError, match="finite"):
        DecisionModelScore("yes", score)


@pytest.mark.parametrize(
    "scores",
    [
        (DecisionModelScore("yes", 1.1), DecisionModelScore("no", -0.1)),
        (DecisionModelScore("yes", 0.4), DecisionModelScore("no", 0.4)),
    ],
)
def test_probability_range_and_sum_are_enforced(scores: tuple[DecisionModelScore, ...]) -> None:
    source = request(mode=DecisionMode.SCORES)
    result = DecisionModelResult(
        IDENTITY,
        (DecisionModelResultItem("question-1", scores=scores, score_semantics="probability"),),
    )
    with pytest.raises(DecisionModelContractError, match="probabilit"):
        validate_decision_result(result, source, profile())


def test_ranking_scores_are_not_constrained_as_probabilities() -> None:
    source = request(mode=DecisionMode.SCORES)
    result = DecisionModelResult(
        IDENTITY,
        (
            DecisionModelResultItem(
                "question-1",
                scores=(DecisionModelScore("yes", 7.0), DecisionModelScore("no", -3.0)),
                score_semantics="ranking_score",
            ),
        ),
    )
    validate_decision_result(result, source, profile())


def test_duplicate_or_reordered_scores_are_rejected() -> None:
    source = request(mode=DecisionMode.SCORES)
    for scores in (
        (DecisionModelScore("yes", 0.6), DecisionModelScore("yes", 0.4)),
        (DecisionModelScore("no", 0.4), DecisionModelScore("yes", 0.6)),
    ):
        result = DecisionModelResult(
            IDENTITY,
            (
                DecisionModelResultItem(
                    "question-1",
                    scores=scores,
                    score_semantics="ranking_score",
                ),
            ),
        )
        with pytest.raises(DecisionModelContractError, match="option order"):
            validate_decision_result(result, source, profile())


def test_calibrated_probability_requires_evidence_and_choice_mode_requires_choice() -> None:
    source = request(mode=DecisionMode.SCORES)
    calibrated = DecisionModelResult(
        IDENTITY,
        (
            DecisionModelResultItem(
                "question-1",
                scores=(DecisionModelScore("yes", 0.7), DecisionModelScore("no", 0.3)),
                score_semantics="calibrated_probability",
            ),
        ),
    )
    with pytest.raises(DecisionModelContractError, match="calibration evidence"):
        validate_decision_result(calibrated, source, profile())

    choice_source = request()
    scores_only = DecisionModelResult(
        IDENTITY,
        (
            DecisionModelResultItem(
                "question-1",
                scores=(DecisionModelScore("yes", 0.7), DecisionModelScore("no", 0.3)),
                score_semantics="probability",
            ),
        ),
    )
    with pytest.raises(DecisionModelContractError, match="choice"):
        validate_decision_result(scores_only, choice_source, profile())


def test_abstention_is_explicit_and_contains_no_decision_payload() -> None:
    source = request()
    abstention = DecisionModelResult(
        IDENTITY,
        (DecisionModelResultItem("question-1", status="abstained"),),
    )
    validate_decision_result(abstention, source, profile())
    invalid = DecisionModelResult(
        IDENTITY,
        (DecisionModelResultItem("question-1", status="abstained", choice="yes"),),
    )
    with pytest.raises(DecisionModelContractError, match="abstention"):
        validate_decision_result(invalid, source, profile())


def test_request_and_result_limits_are_enforced() -> None:
    with pytest.raises(DecisionModelContractError, match="input"):
        validate_decision_request(request(context={"large": "x" * 300}), profile(max_input_bytes=32))
    with pytest.raises(DecisionModelContractError, match="input"):
        validate_decision_request(
            DecisionModelRequest(
                "decision-1",
                {"value": "test"},
                request().questions,
                execution_limits=DecisionExecutionLimits(max_input_bytes=2),
            ),
            profile(),
        )
    with pytest.raises(DecisionModelContractError, match="token"):
        validate_decision_request(request(input_tokens=101), profile())
    with pytest.raises(DecisionModelContractError, match="question"):
        validate_decision_request(
            request(questions=tuple(DecisionQuestion(str(i), (DecisionOption("a"),), "Choose.") for i in range(5))),
            profile(),
        )
    with pytest.raises(DecisionModelContractError, match="option"):
        validate_decision_request(
            request(questions=(DecisionQuestion("q", tuple(DecisionOption(str(i)) for i in range(5)), "Choose."),)),
            profile(),
        )
    scores_request = request(mode=DecisionMode.SCORES)
    result = DecisionModelResult(
        IDENTITY,
        (
            DecisionModelResultItem(
                "question-1",
                scores=(DecisionModelScore("yes", 0.5), DecisionModelScore("no", 0.5)),
                score_semantics="probability",
            ),
        ),
    )
    with pytest.raises(DecisionModelContractError, match="result"):
        validate_decision_result(result, scores_request, profile(max_result_bytes=1))


def test_profile_mode_and_exact_adapter_identity_are_enforced() -> None:
    with pytest.raises(DecisionModelContractError, match="mode"):
        validate_decision_request(request(mode=DecisionMode.SCORES), profile(supported_modes=frozenset({DecisionMode.CHOICE})))
    result = DecisionModelResult(
        DecisionModelIdentity("local.test.v1", "other-adapter", "test-model", "revision-1", "test-runtime"),
        (DecisionModelResultItem("question-1", choice="yes"),),
    )
    with pytest.raises(DecisionModelContractError, match="identity"):
        validate_decision_result(result, request(), profile())


def test_public_package_exports_only_the_contract_types() -> None:
    import dynamic_agent_runner as dar

    assert dar.DecisionModelRequest is DecisionModelRequest
    assert dar.DecisionModelResult is DecisionModelResult
    assert dar.DecisionModelProfile is DecisionModelProfile
