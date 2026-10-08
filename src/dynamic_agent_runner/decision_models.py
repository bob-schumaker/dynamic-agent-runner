"""Typed, runtime-neutral contracts for bounded decision models."""

from __future__ import annotations

import json
import math
from collections.abc import Awaitable, Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class DecisionModelContractError(ValueError):
    """Raised when a decision request, profile, or adapter result is invalid."""


class DecisionMode(str, Enum):
    """Supported bounded decision output modes."""

    CHOICE = "choice"
    SCORES = "scores"


class DecisionModelUse(str, Enum):
    """Host-declared purpose for which a decision binding may be invoked."""

    WORKFLOW_DECISION = "workflow_decision"
    CONTEXT_RETENTION = "context_retention"


class DecisionScoreSemantics(str, Enum):
    """Meaning assigned to option scores by the adapter."""

    RANKING_SCORE = "ranking_score"
    PROBABILITY = "probability"
    CALIBRATED_PROBABILITY = "calibrated_probability"


@dataclass(frozen=True)
class DecisionModelIdentity:
    """Exact profile, adapter, model, revision, and runtime binding identity."""

    profile_id: str
    adapter_id: str
    model_id: str
    model_revision: str
    runtime_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "profile_id",
            "adapter_id",
            "model_id",
            "model_revision",
            "runtime_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip() or "\x00" in value:
                raise DecisionModelContractError(
                    f"{field_name.replace('_', ' ')} is invalid"
                )


@dataclass(frozen=True)
class DecisionExecutionLimits:
    """Host-supplied stricter bounds and lifecycle context for one request."""

    max_input_bytes: int | None = None
    max_input_tokens: int | None = None
    max_questions: int | None = None
    max_options_per_question: int | None = None
    max_result_bytes: int | None = None
    deadline_monotonic: float | None = None
    cancellation: object | None = None

    def __post_init__(self) -> None:
        for name in (
            "max_input_bytes",
            "max_input_tokens",
            "max_questions",
            "max_options_per_question",
            "max_result_bytes",
        ):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value <= 0
            ):
                raise DecisionModelContractError(
                    f"{name.replace('_', ' ')} limit is invalid"
                )
        if self.deadline_monotonic is not None and (
            not isinstance(self.deadline_monotonic, (int, float))
            or not math.isfinite(self.deadline_monotonic)
        ):
            raise DecisionModelContractError("deadline is invalid")


@dataclass(frozen=True)
class DecisionOption:
    """One stable option ID and its adapter-facing description."""

    id: str
    label: str = ""

    def __post_init__(self) -> None:
        _validate_id(self.id, "option id")
        if not isinstance(self.label, str):
            raise DecisionModelContractError("option label is invalid")


@dataclass(frozen=True)
class DecisionQuestion:
    """One ordered question with a finite set of unique options."""

    id: str
    options: tuple[DecisionOption, ...]
    text: str

    def __post_init__(self) -> None:
        _validate_id(self.id, "question id")
        if not isinstance(self.text, str) or not self.text.strip():
            raise DecisionModelContractError("question text is invalid")
        if not isinstance(self.options, tuple) or not self.options:
            raise DecisionModelContractError("question options must be non-empty")
        if not all(isinstance(option, DecisionOption) for option in self.options):
            raise DecisionModelContractError("question options are invalid")
        _unique((option.id for option in self.options), "option ids")


@dataclass(frozen=True)
class DecisionModelRequest:
    """One bounded batch of questions over a JSON-compatible context value."""

    decision_id: str
    context: Any
    questions: tuple[DecisionQuestion, ...]
    mode: DecisionMode = DecisionMode.CHOICE
    task_profile_id: str | None = None
    input_tokens: int | None = None
    execution_limits: DecisionExecutionLimits | None = None

    def __post_init__(self) -> None:
        _validate_id(self.decision_id, "decision id")
        try:
            mode = DecisionMode(self.mode)
        except (TypeError, ValueError) as exc:
            raise DecisionModelContractError("request mode is unsupported") from exc
        object.__setattr__(self, "mode", mode)
        if not isinstance(self.questions, tuple) or not self.questions:
            raise DecisionModelContractError("request questions must be non-empty")
        if not all(
            isinstance(question, DecisionQuestion) for question in self.questions
        ):
            raise DecisionModelContractError("request questions are invalid")
        _unique((question.id for question in self.questions), "question ids")
        if self.task_profile_id is not None:
            _validate_id(self.task_profile_id, "task profile id")
        if self.input_tokens is not None and (
            not isinstance(self.input_tokens, int)
            or isinstance(self.input_tokens, bool)
            or self.input_tokens < 0
        ):
            raise DecisionModelContractError("input token count is invalid")
        if self.execution_limits is not None and not isinstance(
            self.execution_limits, DecisionExecutionLimits
        ):
            raise DecisionModelContractError("execution limits are invalid")
        _canonical_json(self.context, "request context")


@dataclass(frozen=True)
class DecisionModelProfile:
    """Immutable model capability limits and supported output modes."""

    identity: DecisionModelIdentity
    max_input_bytes: int
    max_input_tokens: int
    max_questions: int
    max_options_per_question: int
    max_result_bytes: int
    supported_modes: frozenset[DecisionMode]
    calibration_evidence_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DecisionModelIdentity):
            raise DecisionModelContractError("profile identity is invalid")
        for name in (
            "max_input_bytes",
            "max_input_tokens",
            "max_questions",
            "max_options_per_question",
            "max_result_bytes",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise DecisionModelContractError(
                    f"profile {name.replace('_', ' ')} limit is invalid"
                )
        try:
            modes = frozenset(DecisionMode(mode) for mode in self.supported_modes)
        except (TypeError, ValueError) as exc:
            raise DecisionModelContractError(
                "profile supported modes are invalid"
            ) from exc
        if not modes:
            raise DecisionModelContractError("profile supported modes are empty")
        object.__setattr__(self, "supported_modes", modes)
        if self.calibration_evidence_id is not None:
            _validate_id(self.calibration_evidence_id, "calibration evidence id")


@dataclass(frozen=True)
class DecisionModelScore:
    """One finite score for one declared option."""

    option_id: str
    value: float

    def __post_init__(self) -> None:
        _validate_id(self.option_id, "score option id")
        if (
            not isinstance(self.value, (int, float))
            or isinstance(self.value, bool)
            or not math.isfinite(self.value)
        ):
            raise DecisionModelContractError("score must be finite")
        object.__setattr__(self, "value", float(self.value))


@dataclass(frozen=True)
class DecisionModelResultItem:
    """One choice, score vector, or explicit abstention for a question."""

    question_id: str
    status: str = "ok"
    choice: str | None = None
    scores: tuple[DecisionModelScore, ...] = ()
    score_semantics: DecisionScoreSemantics | str | None = None
    calibration_evidence: str | None = None

    def __post_init__(self) -> None:
        _validate_id(self.question_id, "result question id")
        if self.status not in {"ok", "abstained"}:
            raise DecisionModelContractError("result status is invalid")
        if self.choice is not None:
            _validate_id(self.choice, "result choice")
        if not isinstance(self.scores, tuple) or not all(
            isinstance(score, DecisionModelScore) for score in self.scores
        ):
            raise DecisionModelContractError("result scores are invalid")
        if self.score_semantics is not None:
            try:
                semantics = DecisionScoreSemantics(self.score_semantics)
            except (TypeError, ValueError) as exc:
                raise DecisionModelContractError(
                    "score semantics is unsupported"
                ) from exc
            object.__setattr__(self, "score_semantics", semantics)
        if self.calibration_evidence is not None and (
            not isinstance(self.calibration_evidence, str)
            or not self.calibration_evidence.strip()
        ):
            raise DecisionModelContractError("calibration evidence is invalid")


@dataclass(frozen=True)
class DecisionModelResult:
    """Adapter output bound to the exact identity selected by the caller."""

    identity: DecisionModelIdentity
    results: tuple[DecisionModelResultItem, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DecisionModelIdentity):
            raise DecisionModelContractError("result identity is invalid")
        if not isinstance(self.results, tuple) or not all(
            isinstance(result, DecisionModelResultItem) for result in self.results
        ):
            raise DecisionModelContractError("result items are invalid")


class DecisionModelAdapter(Protocol):
    """Caller-provided adapter for one typed decision-model profile."""

    def decide(
        self, request: DecisionModelRequest
    ) -> DecisionModelResult | Awaitable[DecisionModelResult]:
        """Return bounded decisions for the supplied request."""


@dataclass(frozen=True)
class DecisionModelBinding:
    """Caller-created binding of one exact profile to its adapter and limits."""

    profile: DecisionModelProfile
    adapter: DecisionModelAdapter
    execution_limits: DecisionExecutionLimits = DecisionExecutionLimits()
    permitted_uses: frozenset[DecisionModelUse] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.profile, DecisionModelProfile):
            raise DecisionModelContractError("decision binding profile is invalid")
        if not callable(getattr(self.adapter, "decide", None)):
            raise DecisionModelContractError("decision binding adapter is invalid")
        adapter_identity = getattr(self.adapter, "identity", None)
        if adapter_identity is not None and adapter_identity != self.profile.identity:
            raise DecisionModelContractError(
                "decision binding adapter identity does not match profile"
            )
        if not isinstance(self.execution_limits, DecisionExecutionLimits):
            raise DecisionModelContractError("decision binding limits are invalid")
        try:
            uses = frozenset(DecisionModelUse(use) for use in self.permitted_uses)
        except (TypeError, ValueError) as exc:
            raise DecisionModelContractError(
                "decision binding permitted uses are invalid"
            ) from exc
        if not uses:
            raise DecisionModelContractError(
                "decision binding permitted uses are empty"
            )
        adapter_uses = getattr(self.adapter, "permitted_uses", None)
        if adapter_uses is not None:
            try:
                supported_uses = frozenset(
                    DecisionModelUse(use) for use in adapter_uses
                )
            except (TypeError, ValueError) as exc:
                raise DecisionModelContractError(
                    "decision adapter permitted uses are invalid"
                ) from exc
            if not uses <= supported_uses:
                raise DecisionModelContractError(
                    "decision binding permits an unsupported use"
                )
        object.__setattr__(self, "permitted_uses", uses)


def validate_decision_request(
    request: DecisionModelRequest,
    profile: DecisionModelProfile,
) -> None:
    """Validate request modes, serialized size, and item/token limits."""

    if not isinstance(request, DecisionModelRequest) or not isinstance(
        profile, DecisionModelProfile
    ):
        raise DecisionModelContractError("request or profile is invalid")
    if request.mode not in profile.supported_modes:
        raise DecisionModelContractError("request mode is not supported by profile")
    limits = request.execution_limits
    _enforce_limit(
        len(_canonical_json(_request_mapping(request), "request")),
        profile.max_input_bytes,
        limits.max_input_bytes if limits else None,
        "input bytes",
    )
    if request.input_tokens is not None:
        _enforce_limit(
            request.input_tokens,
            profile.max_input_tokens,
            limits.max_input_tokens if limits else None,
            "input token count",
        )
    _enforce_limit(
        len(request.questions),
        profile.max_questions,
        limits.max_questions if limits else None,
        "question count",
    )
    for question in request.questions:
        _enforce_limit(
            len(question.options),
            profile.max_options_per_question,
            limits.max_options_per_question if limits else None,
            "option count",
        )


def validate_decision_result(
    result: DecisionModelResult,
    request: DecisionModelRequest,
    profile: DecisionModelProfile,
) -> None:
    """Validate exact identity, request order, semantics, and result byte limits."""

    validate_decision_request(request, profile)
    if (
        not isinstance(result, DecisionModelResult)
        or result.identity != profile.identity
    ):
        raise DecisionModelContractError(
            "adapter identity does not match selected profile"
        )
    if tuple(item.question_id for item in result.results) != tuple(
        question.id for question in request.questions
    ):
        raise DecisionModelContractError(
            "result question order or cardinality does not match request"
        )
    for item, question in zip(result.results, request.questions, strict=True):
        _validate_result_item(item, question.options, request.mode, profile)
    encoded = _canonical_json(_result_mapping(result), "result")
    limit = _effective_limit(
        profile.max_result_bytes,
        request.execution_limits.max_result_bytes if request.execution_limits else None,
    )
    if len(encoded) > limit:
        raise DecisionModelContractError("result exceeds byte limit")


def _validate_id(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 128
        or "\x00" in value
    ):
        raise DecisionModelContractError(f"{label} is invalid")


def _unique(values: Iterable[str], label: str) -> None:
    items = tuple(values)
    if len(set(items)) != len(items):
        raise DecisionModelContractError(f"duplicate {label}")


def _canonical_json(value: Any, label: str) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise DecisionModelContractError(f"{label} is not JSON-compatible") from exc


def _effective_limit(profile_limit: int, host_limit: int | None) -> int:
    return min(profile_limit, host_limit) if host_limit is not None else profile_limit


def _enforce_limit(
    value: int, profile_limit: int, host_limit: int | None, label: str
) -> None:
    if value > _effective_limit(profile_limit, host_limit):
        raise DecisionModelContractError(f"{label} exceeds limit")


def _validate_result_item(
    item: DecisionModelResultItem,
    options: tuple[DecisionOption, ...],
    mode: DecisionMode,
    profile: DecisionModelProfile,
) -> None:
    if item.status == "abstained":
        if item.choice is not None or item.scores or item.score_semantics is not None:
            raise DecisionModelContractError(
                "abstention must not contain a decision payload"
            )
        return
    if mode is DecisionMode.CHOICE:
        if item.choice is None or item.scores or item.score_semantics is not None:
            raise DecisionModelContractError(
                "choice result must contain exactly one choice"
            )
        if item.choice not in {option.id for option in options}:
            raise DecisionModelContractError("choice is not a declared option")
        return
    _validate_score_item(item, options, profile)


def _validate_score_item(
    item: DecisionModelResultItem,
    options: tuple[DecisionOption, ...],
    profile: DecisionModelProfile,
) -> None:
    if item.choice is not None or item.score_semantics is None:
        raise DecisionModelContractError(
            "score result must contain scores and score semantics"
        )
    if tuple(score.option_id for score in item.scores) != tuple(
        option.id for option in options
    ):
        raise DecisionModelContractError(
            "result scores must match option order exactly"
        )
    values = tuple(score.value for score in item.scores)
    if item.score_semantics in {
        DecisionScoreSemantics.PROBABILITY,
        DecisionScoreSemantics.CALIBRATED_PROBABILITY,
    }:
        if any(value < 0.0 or value > 1.0 for value in values):
            raise DecisionModelContractError(
                "probability scores must be in range [0, 1]"
            )
        if not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise DecisionModelContractError("probability scores must sum to one")
    calibrated = item.score_semantics is DecisionScoreSemantics.CALIBRATED_PROBABILITY
    if calibrated and item.calibration_evidence is None:
        raise DecisionModelContractError(
            "calibrated probability requires calibration evidence"
        )
    if calibrated and item.calibration_evidence != profile.calibration_evidence_id:
        raise DecisionModelContractError(
            "calibration evidence does not match profile binding"
        )
    if not calibrated and item.calibration_evidence is not None:
        raise DecisionModelContractError(
            "calibration evidence requires calibrated probability"
        )


def _result_mapping(result: DecisionModelResult) -> dict[str, Any]:
    return {
        "identity": result.identity.__dict__,
        "results": [
            {
                "question_id": item.question_id,
                "status": item.status,
                "choice": item.choice,
                "scores": [score.__dict__ for score in item.scores],
                "score_semantics": item.score_semantics.value
                if isinstance(item.score_semantics, Enum)
                else item.score_semantics,
                "calibration_evidence": item.calibration_evidence,
            }
            for item in result.results
        ],
    }


def _request_mapping(request: DecisionModelRequest) -> dict[str, Any]:
    return {
        "decision_id": request.decision_id,
        "context": request.context,
        "questions": [
            {
                "id": question.id,
                "text": question.text,
                "options": [
                    {"id": option.id, "label": option.label}
                    for option in question.options
                ],
            }
            for question in request.questions
        ],
        "mode": request.mode.value,
        "task_profile_id": request.task_profile_id,
    }


__all__ = [
    "DecisionExecutionLimits",
    "DecisionModelAdapter",
    "DecisionModelBinding",
    "DecisionModelContractError",
    "DecisionModelIdentity",
    "DecisionModelProfile",
    "DecisionModelRequest",
    "DecisionModelResult",
    "DecisionModelResultItem",
    "DecisionModelScore",
    "DecisionMode",
    "DecisionOption",
    "DecisionQuestion",
    "DecisionScoreSemantics",
    "validate_decision_request",
    "validate_decision_result",
]
