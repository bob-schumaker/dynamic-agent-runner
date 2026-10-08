"""In-process adapter for the pinned Kev-0.6B Qwen3 decision checkpoint."""

from __future__ import annotations

import importlib
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
    DecisionScoreSemantics,
)

KEV_06B_MODEL_REVISION = "dece6dba8d43f0f7ded45e9f5b9df12474d90843"
KEV_06B_BASE_REVISION = "da87bfb608c14b7cf20ba1ce41287e8de496c0cd"
KEV_SOURCE_REVISION = "41c7b5a384ce93dd88ae0a28c379e947fe716a8d"
KEV_RUNTIME_LOCK_SHA256 = (
    "a9922dbb89acdef78299fd2b4a8c3f7f0fa1b2bc08b55595b6926fa785a9c466"
)
KEV_06B_DECISION_IDENTITY = DecisionModelIdentity(
    profile_id="kev.jaredpalmer.0.6b.qwen3.v1",
    adapter_id="dar.kev-0.6b",
    model_id="jaredpalmer/kev-0.6b",
    model_revision=KEV_06B_MODEL_REVISION,
    runtime_id=(
        f"jaredpalmer/kev@{KEV_SOURCE_REVISION}"
        f"#{KEV_RUNTIME_LOCK_SHA256};base=Qwen/Qwen3-0.6B-Base@{KEV_06B_BASE_REVISION}"
    ),
)


class KevDecisionAdapter:
    """Map requests to Kev's typed API over a caller-loaded model and tokenizer."""

    identity = KEV_06B_DECISION_IDENTITY
    permitted_uses = frozenset({DecisionModelUse.WORKFLOW_DECISION})

    def __init__(
        self,
        model: Any,
        *,
        tokenizer: Any,
        api: Any | None = None,
    ) -> None:
        self._model = model
        self._tokenizer = tokenizer
        self._api = api

    def decide(self, request: DecisionModelRequest) -> DecisionModelResult:
        if not isinstance(request, DecisionModelRequest):
            raise ValueError("Kev request is invalid")
        api = self._api or importlib.import_module("kev.api")
        questions, keys_by_id = _build_questions(request, api)
        system_request = api.SystemOneRequest(
            state=request.context,
            model="kev-0.6b",
            questions=questions,
        )
        record, metadata = api.to_record(system_request)
        encoded = self._model.encode(
            self._tokenizer, record, max_state=8192, max_branch=8192
        )
        raw_probabilities = self._model.probs(encoded)
        if callable(getattr(raw_probabilities, "tolist", None)):
            raw_probabilities = raw_probabilities.tolist()
        if not isinstance(raw_probabilities, list) or len(raw_probabilities) != len(
            request.questions
        ):
            raise ValueError("Kev probabilities are invalid")
        if not isinstance(metadata, list) or len(metadata) != len(request.questions):
            raise ValueError("Kev metadata is invalid")
        results = tuple(
            _map_result(request, question, meta, raw, keys_by_id[question.id])
            for question, meta, raw in zip(
                request.questions, metadata, raw_probabilities, strict=True
            )
        )
        return DecisionModelResult(KEV_06B_DECISION_IDENTITY, results)


def _build_questions(
    request: DecisionModelRequest, api: Any
) -> tuple[dict[str, object], dict[str, tuple[str, ...]]]:
    questions: dict[str, object] = {}
    keys_by_id: dict[str, tuple[str, ...]] = {}
    for question in request.questions:
        option_ids = tuple(option.id for option in question.options)
        if not 2 <= len(option_ids) <= 255:
            raise ValueError("Kev requires 2 to 255 options")
        if request.mode is DecisionMode.CHOICE:
            kind = api.Choice
            criteria: object = {
                option.id: option.label or option.id for option in question.options
            }
            keys = option_ids
        elif set(option_ids) == {"yes", "no"}:
            kind = api.Noul
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
            keys = ("false", "true")
        else:
            kind = api.Score
            criteria = [option.label or option.id for option in question.options]
            keys = tuple(str(i) for i in range(len(option_ids)))
        questions[question.id] = kind(instructions=question.text, criteria=criteria)
        keys_by_id[question.id] = keys
    return questions, keys_by_id


def _map_result(
    request: DecisionModelRequest,
    question: Any,
    meta: object,
    raw: object,
    keys: tuple[str, ...],
) -> DecisionModelResultItem:
    if not isinstance(meta, Mapping) or meta.get("id") != question.id:
        raise ValueError("Kev metadata is invalid")
    if (
        meta.get("keys") != list(keys)
        or not isinstance(raw, list)
        or len(raw) != len(keys)
    ):
        raise ValueError("Kev probabilities are invalid")
    probabilities = _probabilities(raw, keys)
    options = tuple(option.id for option in question.options)
    if request.mode is DecisionMode.CHOICE:
        choice = options[
            max(range(len(keys)), key=lambda index: probabilities[keys[index]])
        ]
        return DecisionModelResultItem(question.id, choice=choice)
    mapped = (
        {"no": probabilities["false"], "yes": probabilities["true"]}
        if set(options) == {"yes", "no"}
        else {
            option_id: probabilities[str(index)]
            for index, option_id in enumerate(options)
        }
    )
    return DecisionModelResultItem(
        question.id,
        scores=tuple(
            DecisionModelScore(option_id, mapped[option_id]) for option_id in options
        ),
        score_semantics=DecisionScoreSemantics.PROBABILITY,
    )


def _probabilities(raw: list[object], keys: tuple[str, ...]) -> dict[str, float]:
    values: dict[str, float] = {}
    for key, value in zip(keys, raw, strict=True):
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError("Kev probabilities are invalid")
        if not 0.0 <= value <= 1.0:
            raise ValueError("Kev probabilities are invalid")
        values[key] = float(value)
    total = sum(values.values())
    if not math.isclose(total, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("Kev probabilities are invalid")
    return {key: value / total for key, value in values.items()}
