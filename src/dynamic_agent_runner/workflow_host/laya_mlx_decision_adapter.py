"""In-process adapter for one pinned Laya-MLX checkpoint and runtime."""

from __future__ import annotations

import math
from collections.abc import Mapping
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

LAYA_MLX_SOURCE_REVISION = "0a859518634112655cb97c745dbf04f5191aaf13"
LAYA_MLX_MODEL_REVISION = "28416e78cb26a239a4eabaa2e084904ec5e6cacb"
LAYA_MLX_RUNTIME_LOCK_SHA256 = (
    "6b723941863f3c9fd72db50dc359d3e4ffa78092e1402e6e48328374766b924a"
)
LAYA_MLX_DECISION_IDENTITY = DecisionModelIdentity(
    profile_id="laya-mlx.aac6fef.typed-decisions.v1",
    adapter_id="dar.laya-mlx-0.2.0",
    model_id="aac6fef/laya-typed-decisions-mlx",
    model_revision=LAYA_MLX_MODEL_REVISION,
    runtime_id=(
        f"mizorewww/laya-mlx@{LAYA_MLX_SOURCE_REVISION}#{LAYA_MLX_RUNTIME_LOCK_SHA256}"
    ),
)


class LayaMLXDecisionAdapter:
    """Map DAR typed questions to a caller-loaded Laya-MLX agent."""

    identity = LAYA_MLX_DECISION_IDENTITY
    permitted_uses = frozenset({DecisionModelUse.WORKFLOW_DECISION})

    def __init__(self, agent: Any) -> None:
        self._agent = agent

    def decide(self, request: DecisionModelRequest) -> DecisionModelResult:
        if not isinstance(request, DecisionModelRequest):
            raise ValueError("Laya-MLX request is invalid")
        questions: dict[str, dict[str, object]] = {}
        kinds: dict[str, str] = {}
        for question in request.questions:
            options = tuple(option.id for option in question.options)
            if not 2 <= len(options) <= 20:
                raise ValueError("Laya-MLX requires 2 to 20 options")
            if request.mode is DecisionMode.CHOICE:
                kind = "choice"
                criteria: object = {
                    option.id: option.label or option.id for option in question.options
                }
            elif set(options) == {"yes", "no"}:
                kind = "noul"
                criteria = {
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
                }
            else:
                kind = "score"
                criteria = [option.label or option.id for option in question.options]
            questions[question.id] = {
                "type": kind,
                "instructions": question.text,
                "criteria": criteria,
            }
            kinds[question.id] = kind
        raw = self._agent.predict(request.context, questions)
        answers = raw.get("answers") if isinstance(raw, dict) else None
        if not isinstance(answers, dict) or set(answers) != set(kinds):
            raise ValueError("Laya-MLX answers are incomplete")
        results = tuple(
            self._map_answer(question, kinds[question.id], answers[question.id])
            for question in request.questions
        )
        return DecisionModelResult(LAYA_MLX_DECISION_IDENTITY, results)

    @staticmethod
    def _map_answer(
        question: DecisionQuestion, kind: str, answer: object
    ) -> DecisionModelResultItem:
        if isinstance(answer, dict) and answer.get("type") == "noul" and kind != "noul":
            raise ValueError("Laya-MLX noul requires exact yes and no option IDs")
        if not isinstance(answer, dict) or answer.get("type") != kind:
            raise ValueError("Laya-MLX answer type is invalid")
        option_ids = tuple(option.id for option in question.options)
        if kind == "choice":
            choice = answer.get("choice")
            if not isinstance(choice, str) or choice not in option_ids:
                raise ValueError("Laya-MLX choice is not a declared option")
            values = _probabilities(answer.get("probabilities"), option_ids)
            if values[choice] + 0.00011 < max(values.values()):
                raise ValueError("Laya-MLX choice does not match its probabilities")
            return DecisionModelResultItem(question.id, choice=choice)
        if kind == "noul":
            p_true = answer.get("noul")
            if (
                not isinstance(p_true, int | float)
                or isinstance(p_true, bool)
                or not math.isfinite(p_true)
                or not 0.0 <= p_true <= 1.0
            ):
                raise ValueError("Laya-MLX noul probability is invalid")
            values = {"no": 1.0 - float(p_true), "yes": float(p_true)}
        else:
            raw = answer.get("probabilities")
            values = _probabilities(raw, tuple(str(i) for i in range(len(option_ids))))
            values = {
                option_id: values[str(i)] for i, option_id in enumerate(option_ids)
            }
        return DecisionModelResultItem(
            question.id,
            scores=tuple(
                DecisionModelScore(option_id, values[option_id])
                for option_id in option_ids
            ),
            score_semantics=DecisionScoreSemantics.PROBABILITY,
        )


def _probabilities(raw: object, keys: tuple[str, ...]) -> dict[str, float]:
    if not isinstance(raw, Mapping) or set(raw) != set(keys):
        raise ValueError("Laya-MLX probabilities are incomplete")
    values: dict[str, float] = {}
    for key in keys:
        value = raw[key]
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError("Laya-MLX probabilities are invalid")
        if not 0.0 <= value <= 1.0:
            raise ValueError("Laya-MLX probabilities are invalid")
        values[key] = float(value)
    total = sum(values.values())
    if not math.isclose(total, 1.0, abs_tol=0.00005 * len(values) + 1e-6):
        raise ValueError("Laya-MLX probabilities do not sum to one")
    return {key: value / total for key, value in values.items()}
