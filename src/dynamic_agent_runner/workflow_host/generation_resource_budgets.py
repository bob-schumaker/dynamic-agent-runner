"""Canonical, host-resolved resource budgets for one model generation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from hashlib import sha256
import json
import math
import threading
from typing import Protocol

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptor,
    ExecutionDescriptorAbi,
    ExecutionDescriptorError,
)


class GenerationResourceBudgetError(ValueError):
    """Raised with a redacted generation-budget admission classification."""


@dataclass(frozen=True)
class GenerationBudgetDescriptorValidator:
    """Validate the canonical budget field for one exact execution ABI."""

    identity: ExecutionDescriptorAbi

    def validate(self, descriptor: ExecutionDescriptor) -> None:
        if (
            not isinstance(descriptor, ExecutionDescriptor)
            or descriptor.architecture_abi != self.identity
        ):
            raise ExecutionDescriptorError("execution descriptor ABI is invalid")
        try:
            validate_generation_budget_field(descriptor)
        except GenerationResourceBudgetError as error:
            raise ExecutionDescriptorError(
                "execution descriptor generation budget is invalid"
            ) from error


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


class CapacityMemoryReservationProvider:
    """Atomic receiver-owned admission against one device memory capacity."""

    def __init__(self, *, capacity_bytes: int) -> None:
        if not _positive_int(capacity_bytes):
            raise GenerationResourceBudgetError("generation memory budget is invalid")
        self._capacity_bytes = capacity_bytes
        self._reserved_bytes = 0
        self._lock = threading.Lock()

    def reserve(
        self, request: "GenerationMemoryReservationRequest"
    ) -> MemoryReservation | None:
        if not isinstance(request, GenerationMemoryReservationRequest):
            return None
        with self._lock:
            if request.max_memory_bytes > self._capacity_bytes - self._reserved_bytes:
                return None
            self._reserved_bytes += request.max_memory_bytes
        return _CapacityMemoryReservation(self, request.max_memory_bytes)

    def _release(self, bytes_to_release: int) -> None:
        with self._lock:
            self._reserved_bytes -= bytes_to_release


class _CapacityMemoryReservation:
    def __init__(
        self, provider: CapacityMemoryReservationProvider, bytes_: int
    ) -> None:
        self._provider = provider
        self._bytes = bytes_
        self._released = False

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._provider._release(self._bytes)


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
            not isinstance(self.material_lock_digest, str)
            or len(self.material_lock_digest) != 64
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
        try:
            reservation.release()
        except Exception as error:  # noqa: BLE001 - receiver cleanup stays private.
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            ) from error


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
_OUTER_CAP_FIELDS = frozenset({"max_runtime_milliseconds", "max_memory_bytes"})
_MEMORY_ADMISSION_METHODS = frozenset(
    {
        "conservative_reservation",
        "process_hard_limit",
        "runtime_allocation_limit",
    }
)
_PRE_PACKING_CONTAINMENT_METHODS = frozenset(
    {"process_hard_limit", "runtime_allocation_limit"}
)
_HARD_LIMIT_METHODS = _PRE_PACKING_CONTAINMENT_METHODS


@dataclass(frozen=True)
class GenerationResourceBudgetCap:
    """A strict partial cap record from selected materials or an outer artifact."""

    max_new_tokens_per_fragment: int | None = None
    max_continuations: int | None = None
    max_total_generated_tokens: int | None = None
    max_total_output_bytes: int | None = None
    max_effective_context_tokens: int | None = None
    max_runtime_milliseconds: int | None = None
    max_memory_bytes: int | None = None

    def __post_init__(self) -> None:
        if not any(getattr(self, field) is not None for field in _FIELD_NAMES):
            raise GenerationResourceBudgetError("generation budget is invalid")
        for field in _FIELD_NAMES:
            value = getattr(self, field)
            if value is None:
                continue
            minimum = 0 if field == "max_continuations" else 1
            if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                raise GenerationResourceBudgetError("generation budget is invalid")


@dataclass(frozen=True)
class GenerationRunnerCapability:
    """Reviewed runner facts needed before a bounded generation starts."""

    runner_id: str
    max_effective_context_tokens: int
    memory_admission_method: str
    pre_packing_containment_method: str
    supported_execution_devices: frozenset[str]
    cancellation_phases: frozenset[str] = frozenset()
    worker_protocol: str | None = None
    bootstrap_hard_limit_method: str | None = None
    generation_hard_limit_method: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.runner_id, str)
            or not self.runner_id
            or not _positive_int(self.max_effective_context_tokens)
            or self.memory_admission_method not in _MEMORY_ADMISSION_METHODS
            or self.pre_packing_containment_method
            not in _PRE_PACKING_CONTAINMENT_METHODS
            or not isinstance(self.supported_execution_devices, frozenset)
            or not self.supported_execution_devices
            or any(
                not isinstance(device, str) or not device
                for device in self.supported_execution_devices
            )
            or not isinstance(self.cancellation_phases, frozenset)
        ):
            raise GenerationResourceBudgetError("generation budget is invalid")
        cancellation = self.cancellation_phases == frozenset({"load", "generate"})
        worker = (
            self.worker_protocol == "generation-worker-v1"
            and self.bootstrap_hard_limit_method in _HARD_LIMIT_METHODS
            and self.generation_hard_limit_method in _HARD_LIMIT_METHODS
        )
        worker_fields_present = any(
            value is not None
            for value in (
                self.worker_protocol,
                self.bootstrap_hard_limit_method,
                self.generation_hard_limit_method,
            )
        )
        if (cancellation and not worker_fields_present) or (
            worker and not self.cancellation_phases
        ):
            return
        raise GenerationResourceBudgetError("generation budget is invalid")

    @property
    def contract_digest(self) -> str:
        """Return the stable identity bound into a worker launch descriptor."""

        payload = {
            "runner_id": self.runner_id,
            "max_effective_context_tokens": self.max_effective_context_tokens,
            "memory_admission_method": self.memory_admission_method,
            "pre_packing_containment_method": self.pre_packing_containment_method,
            "supported_execution_devices": sorted(self.supported_execution_devices),
            "cancellation_phases": sorted(self.cancellation_phases),
            "worker_protocol": self.worker_protocol,
            "bootstrap_hard_limit_method": self.bootstrap_hard_limit_method,
            "generation_hard_limit_method": self.generation_hard_limit_method,
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def parse_generation_resource_budget(value: object) -> GenerationResourceBudget:
    """Parse the strict sealed ``generation_budget`` declaration."""

    if not isinstance(value, Mapping) or set(value) != _FIELD_NAMES:
        raise GenerationResourceBudgetError("generation budget is invalid")
    try:
        return GenerationResourceBudget(**dict(value))
    except (TypeError, GenerationResourceBudgetError) as error:
        raise GenerationResourceBudgetError("generation budget is invalid") from error


def parse_generation_resource_budget_cap(value: object) -> GenerationResourceBudgetCap:
    """Parse one strict partial material/profile generation cap record."""

    if not isinstance(value, Mapping) or not value or not set(value) <= _FIELD_NAMES:
        raise GenerationResourceBudgetError("generation budget is invalid")
    try:
        return GenerationResourceBudgetCap(**dict(value))
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
    material_profile: GenerationResourceBudgetCap | None = None,
    runner_capability: GenerationRunnerCapability | None = None,
    host: GenerationResourceBudget | None = None,
    sealed_artifact_cap: GenerationResourceBudgetCap | None = None,
    execution_device: str | None = None,
) -> GenerationResourceBudget:
    """Resolve declared limits against their typed, applicable caps."""

    if (
        not isinstance(declared, GenerationResourceBudget)
        or not isinstance(runner_capability, GenerationRunnerCapability)
        or not isinstance(host, GenerationResourceBudget)
        or not isinstance(execution_device, str)
        or not execution_device
        or execution_device not in runner_capability.supported_execution_devices
        or (
            material_profile is not None
            and not isinstance(material_profile, GenerationResourceBudgetCap)
        )
        or (
            sealed_artifact_cap is not None
            and not isinstance(sealed_artifact_cap, GenerationResourceBudgetCap)
        )
        or (
            sealed_artifact_cap is not None
            and any(
                getattr(sealed_artifact_cap, field) is not None
                for field in _FIELD_NAMES - _OUTER_CAP_FIELDS
            )
        )
    ):
        raise GenerationResourceBudgetError("generation budget is unavailable")
    resolved: dict[str, int] = {}
    for field in _FIELD_NAMES:
        limits = [getattr(declared, field), getattr(host, field)]
        if material_profile is not None:
            cap = getattr(material_profile, field)
            if cap is not None:
                limits.append(cap)
        if sealed_artifact_cap is not None:
            cap = getattr(sealed_artifact_cap, field)
            if cap is not None:
                limits.append(cap)
        if field == "max_effective_context_tokens":
            limits.append(runner_capability.max_effective_context_tokens)
        resolved[field] = min(limits)
    return GenerationResourceBudget(**resolved)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
