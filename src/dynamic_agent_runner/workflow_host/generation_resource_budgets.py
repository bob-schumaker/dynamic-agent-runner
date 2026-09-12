"""Canonical, host-resolved resource budgets for one model generation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
import math
from typing import Protocol

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptor,
)


class GenerationResourceBudgetError(ValueError):
    """Raised with a redacted generation-budget admission classification."""


@dataclass(frozen=True)
class GenerationDeadline:
    """One monotonic invocation deadline checked before every backend entry."""

    expires_at: float

    @classmethod
    def start(
        cls, now: float, *, max_runtime_milliseconds: int
    ) -> "GenerationDeadline":
        if (
            not isinstance(now, float)
            or not math.isfinite(now)
            or not _positive_int(max_runtime_milliseconds)
        ):
            raise GenerationResourceBudgetError("generation deadline is invalid")
        return cls(now + max_runtime_milliseconds / 1_000)

    def remaining_seconds(self, now: float) -> float:
        if not isinstance(now, float) or not math.isfinite(now):
            raise GenerationResourceBudgetError("generation deadline is invalid")
        return self.expires_at - now

    def require_remaining(self, now: float) -> None:
        if self.remaining_seconds(now) <= 0:
            raise GenerationResourceBudgetError("generation deadline exceeded")


class MemoryReservation(Protocol):
    """One opaque receiver-owned reservation released after request cleanup."""

    def release(self) -> None:
        """Release this reservation exactly once."""


class MemoryReservationProvider(Protocol):
    """Receiver-owned admission control for model-execution memory."""

    def reserve(
        self, request: "GenerationMemoryReservationRequest"
    ) -> MemoryReservation | None:
        """Reserve bounded memory or return no reservation."""


@dataclass(frozen=True)
class GenerationExecutionHostPolicy:
    """Receiver-private generation ceiling, device choice, and admission provider."""

    ceiling: "GenerationResourceBudget"
    execution_device: str
    memory_reservation_provider: MemoryReservationProvider | None

    def __post_init__(self) -> None:
        if not isinstance(self.ceiling, GenerationResourceBudget) or (
            not isinstance(self.execution_device, str) or not self.execution_device
        ):
            raise GenerationResourceBudgetError("generation budget is invalid")
        if not callable(getattr(self.memory_reservation_provider, "reserve", None)):
            raise GenerationResourceBudgetError("generation budget is unavailable")


@dataclass(frozen=True)
class GenerationMemoryReservationRequest:
    """The only data a memory admission provider receives from an invocation."""

    material_lock_digest: str
    runner_identity: str
    execution_device: str
    packed_context_tokens: int
    requested_new_tokens: int
    max_memory_bytes: int
    deadline_monotonic: float

    def __post_init__(self) -> None:
        if (
            len(self.material_lock_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.material_lock_digest
            )
            or not isinstance(self.runner_identity, str)
            or not self.runner_identity
            or not isinstance(self.execution_device, str)
            or not self.execution_device
            or not _nonnegative_int(self.packed_context_tokens)
            or not _positive_int(self.requested_new_tokens)
            or not _positive_int(self.max_memory_bytes)
            or not isinstance(self.deadline_monotonic, float)
            or not math.isfinite(self.deadline_monotonic)
        ):
            raise GenerationResourceBudgetError("generation memory budget is invalid")


class ReservedGenerationMemory:
    """Idempotently release one opaque reservation after request cleanup."""

    def __init__(self, reservation: MemoryReservation) -> None:
        self._reservation: MemoryReservation | None = reservation

    def release(self) -> None:
        reservation = self._reservation
        if reservation is None:
            return
        self._reservation = None
        reservation.release()


@dataclass(frozen=True)
class GenerationResourceBudget:
    """The immutable seven-dimensional budget for one model invocation."""

    max_new_tokens_per_fragment: int
    max_continuations: int
    max_total_generated_tokens: int
    max_total_output_bytes: int
    max_effective_context_tokens: int
    max_runtime_milliseconds: int
    max_memory_bytes: int

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            minimum = 0 if field.name == "max_continuations" else 1
            if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                raise GenerationResourceBudgetError("generation budget is invalid")


_FIELD_NAMES = frozenset(field.name for field in fields(GenerationResourceBudget))


def parse_generation_resource_budget(value: object) -> GenerationResourceBudget:
    """Parse the strict sealed ``generation_budget`` declaration."""

    if not isinstance(value, Mapping) or set(value) != _FIELD_NAMES:
        raise GenerationResourceBudgetError("generation budget is invalid")
    try:
        return GenerationResourceBudget(**dict(value))
    except (TypeError, GenerationResourceBudgetError) as error:
        raise GenerationResourceBudgetError("generation budget is invalid") from error


def validate_generation_budget_field(
    descriptor: ExecutionDescriptor,
) -> GenerationResourceBudget:
    """Validate the sealed field that an exact execution ABI chooses to expose."""

    if not isinstance(descriptor, ExecutionDescriptor):
        raise GenerationResourceBudgetError("generation budget is invalid")
    try:
        return parse_generation_resource_budget(
            descriptor.abi_fields["generation_budget"]
        )
    except KeyError as error:
        raise GenerationResourceBudgetError("generation budget is invalid") from error


def reserve_generation_memory(
    provider: MemoryReservationProvider | None,
    request: GenerationMemoryReservationRequest,
) -> ReservedGenerationMemory:
    """Obtain an enforceable receiver reservation before backend entry."""

    if not isinstance(request, GenerationMemoryReservationRequest):
        raise GenerationResourceBudgetError("generation memory budget is invalid")
    reserve = getattr(provider, "reserve", None)
    if not callable(reserve):
        raise GenerationResourceBudgetError("generation memory budget is unavailable")
    try:
        reservation = reserve(request)
    except Exception as error:  # noqa: BLE001 - receiver admission stays private.
        raise GenerationResourceBudgetError(
            "generation memory budget is unavailable"
        ) from error
    if not callable(getattr(reservation, "release", None)):
        raise GenerationResourceBudgetError("generation memory budget is unavailable")
    return ReservedGenerationMemory(reservation)


def resolve_generation_resource_budget(
    *,
    declared: GenerationResourceBudget,
    material_profile: GenerationResourceBudget | None = None,
    runner: GenerationResourceBudget | None = None,
    host: GenerationResourceBudget | None = None,
    sealed_artifact: GenerationResourceBudget | None = None,
    max_tokens: object | None = None,
    max_continuations: object | None = None,
) -> GenerationResourceBudget:
    """Resolve the strict fieldwise minimum and reducing legacy aliases."""

    sources = (declared, material_profile, runner, host, sealed_artifact)
    if any(
        source is not None and not isinstance(source, GenerationResourceBudget)
        for source in sources
    ):
        raise GenerationResourceBudgetError("generation budget is unavailable")
    resolved = {
        field: min(getattr(source, field) for source in sources if source is not None)
        for field in _FIELD_NAMES
    }
    _reduce_legacy_limit(
        resolved,
        field="max_new_tokens_per_fragment",
        value=max_tokens,
        minimum=1,
    )
    _reduce_legacy_limit(
        resolved,
        field="max_continuations",
        value=max_continuations,
        minimum=0,
    )
    return GenerationResourceBudget(**resolved)


def _reduce_legacy_limit(
    resolved: dict[str, int],
    *,
    field: str,
    value: object | None,
    minimum: int,
) -> None:
    if value is None:
        return
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > resolved[field]
    ):
        raise GenerationResourceBudgetError("generation budget is invalid")
    resolved[field] = value


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
