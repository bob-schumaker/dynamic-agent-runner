"""In-process adapter for pinned Von 1.2.0 option-marker models."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from typing import Any

from dynamic_agent_runner.decision_models import (
    DecisionModelIdentity,
    DecisionModelRequest,
    DecisionModelResult,
    DecisionModelResultItem,
    DecisionModelScore,
    DecisionMode,
    DecisionModelUse,
    DecisionScoreSemantics,
)

VON_MODEL_REVISION = "5df8185a4f2327ad0a7cd117cc4f701ac557b9ae"
VON_SOURCE_REVISION = "fb6e7a937e4fc6b6e72b2ce5035edd56bc370e54"
VON_RUNTIME_LOCK_SHA256 = (
    "6b723941863f3c9fd72db50dc359d3e4ffa78092e1402e6e48328374766b924a"
)
VON_DECISION_IDENTITY = DecisionModelIdentity(
    profile_id="von.wfzyx.v1",
    adapter_id="dar.von-1.2.0",
    model_id="wfzyx/von",
    model_revision=VON_MODEL_REVISION,
    runtime_id=f"wfzyx/von@{VON_SOURCE_REVISION}#{VON_RUNTIME_LOCK_SHA256}",
)


class VonDecisionAdapter:
    """Translate bounded DAR questions to a caller-loaded Von backend."""

    identity = VON_DECISION_IDENTITY
    permitted_uses = frozenset({DecisionModelUse.WORKFLOW_DECISION})

    def __init__(self, backend: Any, choice_factory: Callable[..., object]) -> None:
        self._backend = backend
        self._choice_factory = choice_factory

    def decide(self, request: DecisionModelRequest) -> DecisionModelResult:
        if not isinstance(request, DecisionModelRequest):
            raise ValueError("Von request is invalid")
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
        results: list[DecisionModelResultItem] = []
        for question in request.questions:
            options = tuple(option.id for option in question.options)
            if not 2 <= len(options) <= 20:
                raise ValueError("Von requires 2 to 20 options")
            choice = self._choice_factory(
                instructions=question.text,
                criteria={
                    option.id: option.label or option.id for option in question.options
                },
            )
            answer = self._backend.evaluate_choice(question.id, state, choice)
            probabilities = _probabilities(
                getattr(answer, "probabilities", None), options
            )
            selected = getattr(answer, "choice", None)
            if not isinstance(selected, str) or selected not in probabilities:
                raise ValueError("Von choice is invalid")
            if probabilities[selected] + 0.00011 < max(probabilities.values()):
                raise ValueError("Von choice does not match its probabilities")
            if request.mode is DecisionMode.CHOICE:
                results.append(DecisionModelResultItem(question.id, choice=selected))
            else:
                results.append(
                    DecisionModelResultItem(
                        question.id,
                        scores=tuple(
                            DecisionModelScore(option_id, probabilities[option_id])
                            for option_id in options
                        ),
                        score_semantics=DecisionScoreSemantics.PROBABILITY,
                    )
                )
        return DecisionModelResult(VON_DECISION_IDENTITY, tuple(results))


def _probabilities(raw: object, option_ids: tuple[str, ...]) -> dict[str, float]:
    if not isinstance(raw, Mapping) or set(raw) != set(option_ids):
        raise ValueError("Von probabilities are incomplete")
    values: dict[str, float] = {}
    for key in option_ids:
        value = raw[key]
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError("Von probabilities are invalid")
        if not 0.0 <= value <= 1.0:
            raise ValueError("Von probabilities are invalid")
        values[key] = float(value)
    total = sum(values.values())
    if not math.isclose(total, 1.0, abs_tol=0.00005 * len(values) + 1e-6):
        raise ValueError("Von probabilities do not sum to one")
    return {key: value / total for key, value in values.items()}
