"""Caller-owned provider context-compaction contracts."""

from __future__ import annotations

import inspect
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from dynamic_agent_runner.decision_models import (
    DecisionExecutionLimits,
    DecisionModelBinding,
    DecisionModelRequest,
    DecisionModelResult,
    DecisionMode,
    DecisionOption,
    DecisionQuestion,
    DecisionScoreSemantics,
    validate_decision_request,
    validate_decision_result,
)
from dynamic_agent_runner.openai_client import OpenAIMessage

RetentionTurn = tuple[str, tuple[tuple[str, OpenAIMessage], ...]]


class DecisionContextScoringError(ValueError):
    """Raised when decision-backed context scoring cannot be trusted."""


@dataclass(frozen=True)
class ProviderContextCompactionRequest:
    """One bounded provider-compaction request prepared by DAR."""

    messages: tuple[OpenAIMessage, ...]
    model: str
    phase: Literal["pre_turn", "overflow_retry"]
    provider_capability: str
    max_replacement_messages: int
    preserve_system_messages: bool
    tokens_before: int


@dataclass(frozen=True)
class ProviderContextCompactionResult:
    """Validated-shape replacement history returned by a caller collaborator."""

    messages: tuple[OpenAIMessage, ...]
    provider_window_id: str | None = None
    token_baseline: int | None = None


class ProviderContextCompactor(Protocol):
    """Caller-owned provider compaction capability and transport boundary."""

    capabilities: Mapping[str, bool]

    def compact(
        self,
        request: ProviderContextCompactionRequest,
    ) -> ProviderContextCompactionResult:
        """Return bounded replacement history for a prepared request."""


@dataclass(frozen=True)
class DecisionRetentionSelection:
    """Older turns retained by the configured decision scoring policy."""

    turns: tuple[RetentionTurn, ...]
    diagnostics: Mapping[str, int | str]


def _score_retention_turns(
    *,
    task_context: str,
    candidates: Sequence[RetentionTurn],
    binding: DecisionModelBinding,
    policy: Mapping[str, object],
) -> DecisionRetentionSelection:
    """Score bounded, atomic older-turn batches and return explicit keep selections."""

    _validate_scoring_policy(binding, policy)
    max_candidates = int(policy["max_candidates"])
    scored_candidates = tuple(candidates[-max_candidates:])
    if not scored_candidates:
        return DecisionRetentionSelection(
            (),
            {
                "status": "scored" if policy.get("selection") else "diagnostic_only",
                "scored_turns": 0,
                "selected_turns": 0,
            },
        )
    batch_size = min(int(policy["batch_size"]), binding.profile.max_questions)
    scores: dict[str, tuple[float, float, DecisionScoreSemantics]] = {}
    for offset in range(0, len(scored_candidates), batch_size):
        batch = scored_candidates[offset : offset + batch_size]
        batch_scores = _score_retention_batch(task_context, batch, binding)
        scores.update(batch_scores)
    selected = _select_retention_turns(scored_candidates, scores, policy)
    return DecisionRetentionSelection(
        turns=selected,
        diagnostics={
            "status": "scored" if policy.get("selection") else "diagnostic_only",
            "scored_turns": len(scored_candidates),
            "selected_turns": len(selected),
        },
    )


def _validate_scoring_policy(
    binding: DecisionModelBinding,
    policy: Mapping[str, object],
) -> None:
    if policy.get("profile_id") != binding.profile.identity.profile_id:
        raise DecisionContextScoringError("decision scoring profile mismatch")
    if DecisionMode.SCORES not in binding.profile.supported_modes:
        raise DecisionContextScoringError("decision scoring profile lacks score mode")
    if policy.get("fallback") != "recency":
        raise DecisionContextScoringError("decision scoring fallback is invalid")
    if policy.get("selection") not in {None, "threshold", "bounded_ranking"}:
        raise DecisionContextScoringError("decision scoring selection is invalid")
    for field in ("batch_size", "max_candidates"):
        value = policy.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise DecisionContextScoringError("decision scoring limits are invalid")
    _validate_retention_selection(policy)


def _validate_retention_selection(policy: Mapping[str, object]) -> None:
    if policy.get("selection") is not None:
        max_selected = policy.get("max_selected_turns")
        if not isinstance(max_selected, int) or isinstance(max_selected, bool) or max_selected <= 0:
            raise DecisionContextScoringError("decision scoring limits are invalid")
    if policy.get("selection") == "threshold":
        threshold = policy.get("threshold")
        if (
            not isinstance(threshold, int | float)
            or isinstance(threshold, bool)
            or not math.isfinite(threshold)
            or threshold < 0.0
            or threshold > 1.0
        ):
            raise DecisionContextScoringError("decision scoring threshold is invalid")
    elif policy.get("selection") is None and (
        "threshold" in policy or "max_selected_turns" in policy
    ):
        raise DecisionContextScoringError("selection limits require a selection policy")


def _score_retention_batch(
    task_context: str,
    candidates: Sequence[RetentionTurn],
    binding: DecisionModelBinding,
) -> dict[str, tuple[float, float, DecisionScoreSemantics]]:
    candidate_messages = [
        {"id": message_id, "turn_id": turn_id, "role": message.role, "content": message.content}
        for turn_id, messages in candidates
        for message_id, message in messages
    ]
    questions = tuple(
        DecisionQuestion(
            id=turn_id,
            text=(
                f"Should all messages with turn_id {turn_id!r} be retained in active context "
                "to complete the current task?"
            ),
            options=(
                DecisionOption("keep", "Retain this turn."),
                DecisionOption("drop", "The active context can omit this turn."),
            ),
        )
        for turn_id, _messages in candidates
    )
    request = DecisionModelRequest(
        decision_id=f"context-retention-{candidates[0][0]}",
        context={"task_context": task_context, "candidate_messages": candidate_messages},
        questions=questions,
        mode=DecisionMode.SCORES,
        task_profile_id="context_retention_v1",
        execution_limits=_effective_scoring_limits(binding),
    )
    try:
        validate_decision_request(request, binding.profile)
        _check_scoring_lifecycle(binding)
        result = binding.adapter.decide(request)
        if inspect.isawaitable(result):
            close = getattr(result, "close", None)
            if callable(close):
                close()
            raise DecisionContextScoringError("async scoring adapters are unsupported here")
        _check_scoring_lifecycle(binding)
        if not isinstance(result, DecisionModelResult):
            raise DecisionContextScoringError("decision scoring result is invalid")
        validate_decision_result(result, request, binding.profile)
    except DecisionContextScoringError:
        raise
    except Exception as exc:  # noqa: BLE001 - failure details may contain transcript text.
        raise DecisionContextScoringError("decision scoring failed") from exc
    return _retention_batch_scores(result)


def _retention_batch_scores(
    result: DecisionModelResult,
) -> dict[str, tuple[float, float, DecisionScoreSemantics]]:
    scores: dict[str, tuple[float, float, DecisionScoreSemantics]] = {}
    for item in result.results:
        if item.status != "ok" or item.score_semantics is None:
            raise DecisionContextScoringError("decision scoring abstained")
        values = {score.option_id: score.value for score in item.scores}
        scores[item.question_id] = (values["keep"], values["drop"], item.score_semantics)
    return scores


def _select_retention_turns(
    candidates: Sequence[RetentionTurn],
    scores: Mapping[str, tuple[float, float, DecisionScoreSemantics]],
    policy: Mapping[str, object],
) -> tuple[RetentionTurn, ...]:
    if policy.get("selection") is None:
        return ()
    if policy["selection"] == "threshold":
        if any(
            semantics
            not in {
                DecisionScoreSemantics.PROBABILITY,
                DecisionScoreSemantics.CALIBRATED_PROBABILITY,
            }
            for _keep, _drop, semantics in scores.values()
        ):
            raise DecisionContextScoringError(
                "threshold selection requires probability scores"
            )
        eligible = [
            turn_id
            for turn_id, _messages in candidates
            if scores[turn_id][0] >= float(policy["threshold"])
        ]
        selected_ids = set(eligible[-int(policy["max_selected_turns"]):])
    else:
        ranking = sorted(
            enumerate(candidates),
            key=lambda pair: (
                -(scores[pair[1][0]][0] - scores[pair[1][0]][1]),
                pair[0],
            ),
        )
        positive = [
            pair
            for pair in ranking
            if scores[pair[1][0]][0] > scores[pair[1][0]][1]
        ]
        selected_ids = {
            turn_id
            for _index, (turn_id, _messages) in positive[: int(policy["max_selected_turns"])]
        }
    return tuple(
        candidate for candidate in candidates if candidate[0] in selected_ids
    )


def _effective_scoring_limits(binding: DecisionModelBinding) -> DecisionExecutionLimits:
    host = binding.execution_limits
    profile = binding.profile

    def minimum(value: int, bound: int | None) -> int:
        return min(value, bound) if bound is not None else value

    return DecisionExecutionLimits(
        max_input_bytes=minimum(profile.max_input_bytes, host.max_input_bytes),
        max_input_tokens=minimum(profile.max_input_tokens, host.max_input_tokens),
        max_questions=minimum(profile.max_questions, host.max_questions),
        max_options_per_question=minimum(
            profile.max_options_per_question, host.max_options_per_question
        ),
        max_result_bytes=minimum(profile.max_result_bytes, host.max_result_bytes),
        deadline_monotonic=host.deadline_monotonic,
        cancellation=host.cancellation,
    )


def _check_scoring_lifecycle(binding: DecisionModelBinding) -> None:
    limits = binding.execution_limits
    cancellation = limits.cancellation
    if cancellation is not None:
        raise_if_cancelled = getattr(cancellation, "raise_if_cancelled", None)
        if callable(raise_if_cancelled):
            raise_if_cancelled()
        if getattr(cancellation, "cancelled", False):
            raise DecisionContextScoringError("decision scoring cancelled")
    if limits.deadline_monotonic is not None and time.monotonic() >= limits.deadline_monotonic:
        raise DecisionContextScoringError("decision scoring deadline expired")


__all__ = [
    "DecisionContextScoringError",
    "DecisionRetentionSelection",
    "ProviderContextCompactionRequest",
    "ProviderContextCompactionResult",
    "ProviderContextCompactor",
]
