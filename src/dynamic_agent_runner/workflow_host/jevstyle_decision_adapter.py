"""Machine-selected adapter for the pinned Jev-Style v3 local profiles."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from dynamic_agent_runner.decision_models import (
    DecisionMode,
    DecisionModelBinding,
    DecisionModelIdentity,
    DecisionModelProfile,
    DecisionModelRequest,
    DecisionModelResult,
    DecisionModelResultItem,
    DecisionModelScore,
    DecisionModelUse,
    DecisionQuestion,
    DecisionScoreSemantics,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
)

JEVSTYLE_V3_MLX_MODEL_REVISION = "1235ccd1c95d5228a07616cd7e323c9e0532c1dc"
JEVSTYLE_V3_TORCH_MODEL_REVISION = "b023d1f9c7858fbf01504577a3bfc349ea5c7385"
JEVSTYLE_V3_GGUF_MODEL_REVISION = "edf37c26a1098f83cf4264b8adbe0dca2d2ebb0c"

JEVSTYLE_V3_MLX_DECISION_IDENTITY = DecisionModelIdentity(
    profile_id="jevstyle-v3.mlx-metal.v1",
    adapter_id="dar.jevstyle-v3-auto",
    model_id="chaoliangUNSW/Jev-Style-0.8B-Decision-v3-MLX",
    model_revision=JEVSTYLE_V3_MLX_MODEL_REVISION,
    runtime_id=(
        "mlx-runtime@8e50ab3a48cc4b0b6896cf8241b111d1619d50af41982257970dfb7689d4078d"
        ";weights=36890afff7a9da5b7228d81cd79434088267bd250c9eafab14539e6a5161a5fe"
        ";source=e3ba700043d764f0fe50931cc3524d8329552bf4f4187f411671fd323e363acf"
    ),
)
JEVSTYLE_V3_TORCH_DECISION_IDENTITY = DecisionModelIdentity(
    profile_id="jevstyle-v3.torch-cpu.v1",
    adapter_id="dar.jevstyle-v3-auto",
    model_id="chaoliangUNSW/Jev-Style-0.8B-Decision-v3",
    model_revision=JEVSTYLE_V3_TORCH_MODEL_REVISION,
    runtime_id=(
        "torch-runtime@82e6a2853231188d2fed184459aede8c9f72090e083da8d7053d6bc4166a0a5b"
        ";weights=0f8c861605dcdfb356a63e056baa2106e81042e8981e8d0d26fe50b34599541e"
        ";source=b93c2345732be8ef5ec4274b77ded564e421ccb91967a207de4f18254438ce42"
    ),
)
JEVSTYLE_V3_GGUF_DECISION_IDENTITY = DecisionModelIdentity(
    profile_id="jevstyle-v3.gguf-f16-cpu.v1",
    adapter_id="dar.jevstyle-v3-auto",
    model_id="chaoliangUNSW/Jev-Style-0.8B-Decision-v3-GGUF",
    model_revision=JEVSTYLE_V3_GGUF_MODEL_REVISION,
    runtime_id=(
        "gguf-runtime@e0273c1d05185421eff953f538a59de7213b6b1731993831878943215568f975"
        ";weights=a33f709e10009c3fe182b51e4945d440288b137a35ad5d481e4ac1f2800b1a27"
        ";source=e6b028f043d943b5e33d63368070405c5f038b6ee6f71a11b44e93caa562f5ed"
        ";llama-cpp=441df11f65ea0b6d0c72965aaf70c8241070ddcb"
        ";build=5789a1585c51fbc4a03b423099a451e05cb66b9db49bc6c9361f326aca170fda"
    ),
)


def _profile(identity: DecisionModelIdentity) -> DecisionModelProfile:
    return DecisionModelProfile(
        identity=identity,
        max_input_bytes=1_000_000,
        max_input_tokens=25_600,
        max_questions=64,
        max_options_per_question=10,
        max_result_bytes=64_000,
        supported_modes=frozenset({DecisionMode.CHOICE, DecisionMode.SCORES}),
    )


JEVSTYLE_V3_MLX_PROFILE = _profile(JEVSTYLE_V3_MLX_DECISION_IDENTITY)
JEVSTYLE_V3_TORCH_PROFILE = _profile(JEVSTYLE_V3_TORCH_DECISION_IDENTITY)
JEVSTYLE_V3_GGUF_PROFILE = _profile(JEVSTYLE_V3_GGUF_DECISION_IDENTITY)


class JevStyleAdapterError(ValueError):
    """Raised with a redacted Jev-Style profile or result classification."""


class JevStyleBackend(StrEnum):
    MLX = "mlx-metal"
    GGUF = "gguf-f16-cpu"
    TORCH = "torch-bf16-cpu"


_EXPECTED_PROFILES = {
    JevStyleBackend.MLX: JEVSTYLE_V3_MLX_PROFILE,
    JevStyleBackend.GGUF: JEVSTYLE_V3_GGUF_PROFILE,
    JevStyleBackend.TORCH: JEVSTYLE_V3_TORCH_PROFILE,
}


@dataclass(frozen=True)
class JevStyleMachineConfiguration:
    """Host-reported platform/device facts used before loading any model."""

    platform: str
    architecture: str
    metal_available: bool

    def __post_init__(self) -> None:
        if (
            self.platform not in {"darwin", "linux", "win32"}
            or self.architecture not in {"arm64", "aarch64", "x86_64", "amd64"}
            or not isinstance(self.metal_available, bool)
        ):
            raise JevStyleAdapterError("host machine configuration is invalid")


@dataclass(frozen=True)
class JevStyleModelCandidate:
    """One exact, already admitted model/material/runtime and its local loader."""

    backend: JevStyleBackend
    profile: DecisionModelProfile
    execution_binding: ModelExecutionBinding
    materials_admitted: bool
    resource_admitted: bool
    load_engine: Callable[[ModelExecutionBinding], Any]

    def __post_init__(self) -> None:
        try:
            backend = JevStyleBackend(self.backend)
        except (TypeError, ValueError) as error:
            raise JevStyleAdapterError("Jev-Style backend is invalid") from error
        if (
            self.profile != _EXPECTED_PROFILES[backend]
            or not isinstance(self.execution_binding, ModelExecutionBinding)
            or self.execution_binding.logical_model_id != self.profile.identity.model_id
            or not _valid_digest(self.execution_binding.material_lock_digest)
            or not isinstance(self.materials_admitted, bool)
            or not isinstance(self.resource_admitted, bool)
            or not callable(self.load_engine)
        ):
            raise JevStyleAdapterError("Jev-Style candidate binding is invalid")
        object.__setattr__(self, "backend", backend)

    @property
    def admitted(self) -> bool:
        return self.materials_admitted and self.resource_admitted


def select_jevstyle_candidate(
    machine: JevStyleMachineConfiguration,
    candidates: Sequence[JevStyleModelCandidate],
) -> JevStyleModelCandidate:
    """Select the best pre-admitted exact profile without loading it."""

    if not isinstance(machine, JevStyleMachineConfiguration):
        raise JevStyleAdapterError("host machine configuration is invalid")
    by_backend: dict[JevStyleBackend, JevStyleModelCandidate] = {}
    for candidate in candidates:
        if not isinstance(candidate, JevStyleModelCandidate):
            raise JevStyleAdapterError("Jev-Style candidate list is invalid")
        if candidate.backend in by_backend:
            raise JevStyleAdapterError("Jev-Style candidate list is invalid")
        by_backend[candidate.backend] = candidate

    order = (
        (JevStyleBackend.MLX, JevStyleBackend.GGUF, JevStyleBackend.TORCH)
        if (
            machine.platform == "darwin"
            and machine.architecture in {"arm64", "aarch64"}
            and machine.metal_available
        )
        else (JevStyleBackend.GGUF, JevStyleBackend.TORCH)
    )
    for backend in order:
        candidate = by_backend.get(backend)
        if candidate is not None and candidate.admitted:
            return candidate
    raise JevStyleAdapterError("no admitted Jev-Style profile is available")


def load_jevstyle_v3_binding(
    machine: JevStyleMachineConfiguration,
    candidates: Sequence[JevStyleModelCandidate],
) -> DecisionModelBinding:
    """Load only the selected backend and return its exact decision binding."""

    candidate = select_jevstyle_candidate(machine, candidates)
    try:
        engine = candidate.load_engine(candidate.execution_binding)
    except Exception as error:  # noqa: BLE001 - preserve cause, redact boundary.
        raise JevStyleAdapterError(
            "selected Jev-Style backend failed to load"
        ) from error
    adapter = JevStyleV3DecisionAdapter(
        engine,
        candidate.profile,
        material_lock_digest=candidate.execution_binding.material_lock_digest,
    )
    return DecisionModelBinding(
        profile=candidate.profile,
        adapter=adapter,
        permitted_uses=frozenset({DecisionModelUse.WORKFLOW_DECISION}),
    )


class JevStyleV3DecisionAdapter:
    """Translate bounded DAR decisions through one already loaded v3 engine."""

    permitted_uses = frozenset({DecisionModelUse.WORKFLOW_DECISION})

    def __init__(
        self,
        engine: Any,
        profile: DecisionModelProfile,
        *,
        material_lock_digest: str = "0" * 64,
    ) -> None:
        if (
            profile not in _EXPECTED_PROFILES.values()
            or not (
                callable(getattr(engine, "decide", None))
                or callable(getattr(engine, "decide_many", None))
            )
            or not _valid_digest(material_lock_digest)
        ):
            raise JevStyleAdapterError("Jev-Style adapter binding is invalid")
        self.identity = profile.identity
        self.profile = profile
        self.material_lock_digest = material_lock_digest
        self._engine = engine

    def decide(self, request: DecisionModelRequest) -> DecisionModelResult:
        if not isinstance(request, DecisionModelRequest):
            raise JevStyleAdapterError("Jev-Style request is invalid")
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
        results = tuple(
            self._decide_one(state, request.mode, question)
            for question in request.questions
        )
        return DecisionModelResult(self.identity, results)

    def _decide_one(
        self, state: object, mode: DecisionMode, question: DecisionQuestion
    ) -> DecisionModelResultItem:
        options = tuple(question.options)
        option_ids = tuple(option.id for option in options)
        if not 2 <= len(options) <= self.profile.max_options_per_question:
            raise JevStyleAdapterError("Jev-Style option count is unsupported")

        if mode is DecisionMode.CHOICE:
            kind = "choice"
            criteria: object = {
                option.id: option.label or option.id for option in options
            }
            names = option_ids
        elif set(option_ids) == {"yes", "no"}:
            kind = "noul"
            criteria = {
                "false": next(
                    option.label or option.id for option in options if option.id == "no"
                ),
                "true": next(
                    option.label or option.id
                    for option in options
                    if option.id == "yes"
                ),
            }
            names = ("false", "true")
        else:
            kind = "score"
            criteria = [option.label or option.id for option in options]
            names = tuple(str(index) for index in range(len(options)))

        answer = self._run_engine(
            state,
            {"t": kind, "ins": question.text, "crit": criteria},
        )
        if not isinstance(answer, Mapping):
            raise JevStyleAdapterError("Jev-Style answer is invalid")
        probabilities = _probabilities(answer.get("probabilities"), names)
        selected = answer.get("answer")
        if not isinstance(selected, str) or selected not in probabilities:
            raise JevStyleAdapterError("Jev-Style selected option is invalid")
        if probabilities[selected] + 0.002 < max(probabilities.values()):
            raise JevStyleAdapterError("Jev-Style selected option is inconsistent")

        if mode is DecisionMode.CHOICE:
            if selected not in option_ids:
                raise JevStyleAdapterError("Jev-Style choice is not a declared option")
            return DecisionModelResultItem(question.id, choice=selected)

        mapped = (
            {"no": probabilities["false"], "yes": probabilities["true"]}
            if kind == "noul"
            else {
                option.id: probabilities[str(index)]
                for index, option in enumerate(options)
            }
        )
        return DecisionModelResultItem(
            question.id,
            scores=tuple(
                DecisionModelScore(option.id, mapped[option.id]) for option in options
            ),
            score_semantics=DecisionScoreSemantics.PROBABILITY,
        )

    def _run_engine(self, state: object, question: dict[str, object]) -> object:
        try:
            decide = getattr(self._engine, "decide", None)
            if callable(decide):
                return decide(state, question)
            answers = self._engine.decide_many(state, [question])
            if not isinstance(answers, list) or len(answers) != 1:
                raise JevStyleAdapterError("Jev-Style answer cardinality is invalid")
            return answers[0]
        except JevStyleAdapterError:
            raise
        except Exception as error:  # noqa: BLE001 - model errors stay redacted.
            raise JevStyleAdapterError("Jev-Style inference failed") from error


def _probabilities(raw: object, names: tuple[str, ...]) -> dict[str, float]:
    if not isinstance(raw, Mapping) or set(raw) != set(names):
        raise JevStyleAdapterError("Jev-Style probabilities are incomplete")
    values: dict[str, float] = {}
    for name in names:
        value = raw[name]
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0.0
            or value > 1.0
        ):
            raise JevStyleAdapterError("Jev-Style probabilities are invalid")
        values[name] = float(value)
    total = sum(values.values())
    if total <= 0 or not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=0.002):
        raise JevStyleAdapterError("Jev-Style probabilities are invalid")
    return {name: value / total for name, value in values.items()}


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "JEVSTYLE_V3_GGUF_PROFILE",
    "JEVSTYLE_V3_MLX_PROFILE",
    "JEVSTYLE_V3_TORCH_PROFILE",
    "JevStyleAdapterError",
    "JevStyleBackend",
    "JevStyleMachineConfiguration",
    "JevStyleModelCandidate",
    "JevStyleV3DecisionAdapter",
    "load_jevstyle_v3_binding",
    "select_jevstyle_candidate",
]
