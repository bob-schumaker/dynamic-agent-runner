"""In-process adapter for one host-loaded Julia 1 engine."""

from __future__ import annotations

import json
import math
from typing import Any

from dynamic_agent_runner.decision_models import (
    DecisionModelIdentity,
    DecisionModelRequest,
    DecisionModelResult,
    DecisionModelResultItem,
    DecisionModelScore,
    DecisionMode,
    DecisionModelUse,
    DecisionQuestion,
    DecisionScoreSemantics,
)

JULIA1_MODEL_REVISION = "a85b127321d580d65176c89ced8273f305745d85"
JULIA1_RUNTIME_LOCK_SHA256 = (
    "6b723941863f3c9fd72db50dc359d3e4ffa78092e1402e6e48328374766b924a"
)
JULIA1_DECISION_IDENTITY = DecisionModelIdentity(
    profile_id="julia1.supersoniclabs.v1",
    adapter_id="dar.julia1",
    model_id="SupersonicLabs/Julia-1",
    model_revision=JULIA1_MODEL_REVISION,
    runtime_id=f"supersonic-julia@{JULIA1_MODEL_REVISION}#{JULIA1_RUNTIME_LOCK_SHA256}",
)


class Julia1DecisionAdapter:
    """Map DAR typed requests to an already loaded Julia 1 engine."""

    identity = JULIA1_DECISION_IDENTITY
    permitted_uses = frozenset({DecisionModelUse.WORKFLOW_DECISION})

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def decide(self, request: DecisionModelRequest) -> DecisionModelResult:
        if not isinstance(request, DecisionModelRequest):
            raise ValueError("Julia 1 request is invalid")
        state = (
            request.context
            if isinstance(request.context, str)
            else json.dumps(
                request.context,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        questions: dict[str, dict[str, object]] = {}
        for question in request.questions:
            options = tuple(option.id for option in question.options)
            if not 2 <= len(options) <= 20:
                raise ValueError("Julia 1 requires 2 to 20 options")
            if request.mode is DecisionMode.CHOICE:
                questions[question.id] = {
                    "type": "choice",
                    "instructions": question.text,
                    "criteria": {
                        option.id: option.label or option.id
                        for option in question.options
                    },
                }
            elif options == ("yes", "no") or set(options) == {"yes", "no"}:
                questions[question.id] = {
                    "type": "noul",
                    "instructions": question.text,
                    "criteria": {
                        "false": next(
                            option.label or option.id
                            for option in question.options
                            if option.id == "no"
                        ),
                        "true": next(
                            option.label or option.id
                            for option in question.options
                            if option.id == "yes"
                        ),
                    },
                }
            else:
                questions[question.id] = {
                    "type": "score",
                    "instructions": question.text,
                    "criteria": [
                        option.label or option.id for option in question.options
                    ],
                }
        raw = self._engine.predict(state=state, questions=questions)
        answers = raw.get("answers") if isinstance(raw, dict) else None
        if not isinstance(answers, dict):
            raise ValueError("Julia 1 result is invalid")
        if set(answers) != {question.id for question in request.questions}:
            raise ValueError("Julia 1 answer IDs do not match request")
        results = tuple(
            self._map_answer(request, question, answers.get(question.id))
            for question in request.questions
        )
        return DecisionModelResult(JULIA1_DECISION_IDENTITY, results)

    def _map_answer(
        self, request: DecisionModelRequest, question: DecisionQuestion, answer: object
    ) -> DecisionModelResultItem:
        if not isinstance(answer, dict):
            raise ValueError("Julia 1 answer is invalid")
        options = tuple(option.id for option in question.options)
        noul = request.mode is DecisionMode.SCORES and set(options) == {"yes", "no"}
        expected_type = (
            "choice"
            if request.mode is DecisionMode.CHOICE
            else "noul"
            if noul
            else "score"
        )
        if answer.get("type") != expected_type:
            if answer.get("type") == "noul" and not noul:
                raise ValueError("Julia 1 noul requires exact yes and no option IDs")
            raise ValueError("Julia 1 answer type is invalid")
        if request.mode is DecisionMode.CHOICE:
            choice = answer.get("choice")
            if not isinstance(choice, str) or choice not in {
                option.id for option in question.options
            }:
                raise ValueError("Julia 1 choice is invalid")
            return DecisionModelResultItem(question.id, choice=choice)
        probabilities = answer.get("probabilities")
        if noul:
            values = _probabilities(probabilities, ("false", "true"))
            mapped = {"no": values["false"], "yes": values["true"]}
        else:
            values = _probabilities(
                probabilities, tuple(str(i) for i in range(len(options)))
            )
            mapped = {option_id: values[str(i)] for i, option_id in enumerate(options)}
        return DecisionModelResultItem(
            question.id,
            scores=tuple(
                DecisionModelScore(option_id, mapped[option_id])
                for option_id in options
            ),
            score_semantics=DecisionScoreSemantics.PROBABILITY,
        )


def _probabilities(raw: object, keys: tuple[str, ...]) -> dict[str, float]:
    if not isinstance(raw, dict) or set(raw) != set(keys):
        raise ValueError("Julia 1 probabilities are invalid")
    values: dict[str, float] = {}
    for key in keys:
        value = raw[key]
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError("Julia 1 probabilities are invalid")
        if not 0.0 <= value <= 1.0:
            raise ValueError("Julia 1 probabilities are invalid")
        values[key] = float(value)
    if not math.isclose(sum(values.values()), 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("Julia 1 probabilities are invalid")
    return values
