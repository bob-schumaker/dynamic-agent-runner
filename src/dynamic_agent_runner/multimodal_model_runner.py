"""Value contracts for the sealed multimodal model-runner protocol."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field as dataclass_field
from types import MappingProxyType
from typing import Any, Protocol


PROTOCOL_ID = "dar.multimodal-runner.v1"
PROTOCOL_VERSION = "1.0"
WORKER_PROTOCOL = "generation-worker-v1"
TERMINAL_STATUSES = frozenset(
    {
        "rejected",
        "completed",
        "budget_exhausted",
        "cancelled",
        "deadline_exceeded",
        "runner_failed",
        "cleanup_failed",
    }
)
TERMINAL_ERRORS = frozenset(
    {
        "admission_rejected",
        "budget_exhausted",
        "cancelled",
        "deadline_exceeded",
        "runner_failed",
        "cleanup_failed",
    }
)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_ROLE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_BUDGET_FIELDS = (
    "max_new_tokens_per_fragment",
    "max_continuations",
    "max_total_generated_tokens",
    "max_total_output_bytes",
    "max_effective_context_tokens",
    "max_runtime_milliseconds",
    "max_memory_bytes",
)


class MultimodalRunnerProtocolError(ValueError):
    """Raised when untrusted protocol data violates the v1 contract."""


class MultimodalRunnerAdmissionError(MultimodalRunnerProtocolError):
    """Raised when a receiver-installed runner cannot be admitted."""


class DARMultimodalModelRunnerProtocol(Protocol):
    """One receiver-installed provider translation boundary."""

    runner_id: str
    protocol_id: str
    protocol_version: str

    def describe(self) -> "MultimodalRunnerDescriptor":
        """Return the immutable descriptor without loading model materials."""

    def health(self) -> "MultimodalRunnerHealth":
        """Return bounded, redacted runner readiness."""

    def run(
        self,
        request: "SealedMultimodalRequest",
        *,
        context: "DARGenerationRequestContext",
    ) -> "MultimodalRunnerResult":
        """Translate one admitted sealed request to the provider call."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise MultimodalRunnerProtocolError(f"{field} is invalid")
    return value


def _identifier(value: object, field: str) -> str:
    value = _text(value, field)
    if not _IDENTIFIER.fullmatch(value):
        raise MultimodalRunnerProtocolError(f"{field} is invalid")
    return value


def _role(value: object, field: str = "role") -> str:
    value = _text(value, field)
    if not _ROLE.fullmatch(value):
        raise MultimodalRunnerProtocolError(f"{field} is invalid")
    return value


def _digest_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise MultimodalRunnerProtocolError(f"{field} is invalid")
    return value


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MultimodalRunnerProtocolError(f"{field} is invalid")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MultimodalRunnerProtocolError(f"{field} is invalid")
    return value


def _validate_result_handles(
    handles: tuple[SealedMultimodalHandle, ...],
    *,
    package_id: str,
    package_revision_digest: str,
    material_lock_digest: str,
    converter_digest: str,
) -> None:
    if any(not isinstance(item, SealedMultimodalHandle) for item in handles):
        raise MultimodalRunnerProtocolError("result handles are invalid")
    for item in handles:
        if (
            item.package_id != package_id
            or item.package_revision_digest != package_revision_digest
            or item.material_lock_digest != material_lock_digest
            or item.converter_digest != converter_digest
        ):
            raise MultimodalRunnerProtocolError("result handle binding is invalid")


def _validate_coverage(value: Mapping[str, int]) -> Mapping[str, int]:
    coverage = dict(value)
    if any(not isinstance(key, str) or not key for key in coverage):
        raise MultimodalRunnerProtocolError("coverage is invalid")
    for key, count in coverage.items():
        _nonnegative_int(count, f"coverage.{key}")
    return MappingProxyType(coverage)


def _validate_bound_result(
    result: "MultimodalRunnerResult",
    *,
    request: "SealedMultimodalRequest",
    descriptor: "MultimodalRunnerDescriptor",
    context: "DARGenerationRequestContext",
) -> None:
    if (
        result.contract_digest != descriptor.contract_digest
        or result.package_id != request.package_id
        or result.package_revision_digest != request.package_revision_digest
        or result.material_lock_digest != descriptor.material_lock_digest
        or result.converter_digest != descriptor.converter_digest
    ):
        raise MultimodalRunnerProtocolError("runner result identity is invalid")
    if result.output_bytes > descriptor.resource_limits.max_output_bytes:
        raise MultimodalRunnerProtocolError("runner result exceeds output limit")
    if len(result.output_handles) > 16:
        raise MultimodalRunnerProtocolError("runner result exceeds handle limit")
    if any(
        handle.role not in descriptor.output_modalities
        for handle in result.output_handles
    ):
        raise MultimodalRunnerProtocolError("runner result modality is invalid")
    if any(key not in descriptor.input_modalities for key in result.coverage):
        raise MultimodalRunnerProtocolError("runner result coverage is invalid")
    budget = context.generation_budget
    if (
        result.generated_tokens > budget["max_total_generated_tokens"]
        or result.output_bytes > budget["max_total_output_bytes"]
    ):
        raise MultimodalRunnerProtocolError("runner result exceeds generation budget")


def _modalities(value: Sequence[object], field: str) -> tuple[str, ...]:
    result = tuple(_role(item, field) for item in value)
    if not result or result != tuple(sorted(result)) or len(set(result)) != len(result):
        raise MultimodalRunnerProtocolError(f"{field} are invalid")
    return result


@dataclass(frozen=True)
class MultimodalRunnerLimits:
    """Closed receiver-selected resource limits for one runner descriptor."""

    max_input_bytes: int
    max_output_bytes: int
    max_runtime_milliseconds: int
    max_memory_bytes: int

    def __post_init__(self) -> None:
        for field in (
            "max_input_bytes",
            "max_output_bytes",
            "max_runtime_milliseconds",
            "max_memory_bytes",
        ):
            _positive_int(getattr(self, field), field)

    @classmethod
    def from_mapping(cls, value: object) -> "MultimodalRunnerLimits":
        if not isinstance(value, Mapping) or set(value) != {
            "max_input_bytes",
            "max_output_bytes",
            "max_runtime_milliseconds",
            "max_memory_bytes",
        }:
            raise MultimodalRunnerProtocolError("resource limits are invalid")
        return cls(**value)

    def to_mapping(self) -> dict[str, int]:
        return {
            "max_input_bytes": self.max_input_bytes,
            "max_output_bytes": self.max_output_bytes,
            "max_runtime_milliseconds": self.max_runtime_milliseconds,
            "max_memory_bytes": self.max_memory_bytes,
        }


@dataclass(frozen=True)
class MultimodalRunnerDescriptor:
    """Immutable identity and capability contract for one admitted runner."""

    runner_id: str
    provider_runtime_id: str
    material_lock_digest: str
    execution_abi_digest: str
    input_modalities: tuple[str, ...]
    output_modalities: tuple[str, ...]
    converter_digest: str
    output_contract_digest: str
    resource_limits: MultimodalRunnerLimits
    protocol_id: str = PROTOCOL_ID
    protocol_version: str = PROTOCOL_VERSION
    contract_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "runner_id", _identifier(self.runner_id, "runner_id"))
        object.__setattr__(
            self,
            "provider_runtime_id",
            _identifier(self.provider_runtime_id, "provider_runtime_id"),
        )
        if self.protocol_id != PROTOCOL_ID or self.protocol_version != PROTOCOL_VERSION:
            raise MultimodalRunnerProtocolError("protocol identity is invalid")
        for field in (
            "material_lock_digest",
            "execution_abi_digest",
            "converter_digest",
            "output_contract_digest",
        ):
            _digest_text(getattr(self, field), field)
        object.__setattr__(
            self,
            "input_modalities",
            _modalities(self.input_modalities, "input_modalities"),
        )
        object.__setattr__(
            self,
            "output_modalities",
            _modalities(self.output_modalities, "output_modalities"),
        )
        limits = self.resource_limits
        if isinstance(limits, Mapping):
            limits = MultimodalRunnerLimits.from_mapping(limits)
        if not isinstance(limits, MultimodalRunnerLimits):
            raise MultimodalRunnerProtocolError("resource limits are invalid")
        object.__setattr__(self, "resource_limits", limits)
        computed = self.digest
        if self.contract_digest:
            if self.contract_digest != computed:
                raise MultimodalRunnerProtocolError("contract digest does not match")
        else:
            object.__setattr__(self, "contract_digest", computed)

    def _payload(self) -> dict[str, Any]:
        return {
            "execution_abi_digest": self.execution_abi_digest,
            "input_modalities": list(self.input_modalities),
            "material_lock_digest": self.material_lock_digest,
            "output_contract_digest": self.output_contract_digest,
            "output_modalities": list(self.output_modalities),
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "provider_runtime_id": self.provider_runtime_id,
            "resource_limits": self.resource_limits.to_mapping(),
            "runner_id": self.runner_id,
            "converter_digest": self.converter_digest,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json(self._payload())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    def to_mapping(self) -> dict[str, Any]:
        return {**self._payload(), "contract_digest": self.contract_digest}


@dataclass(frozen=True)
class MultimodalRunnerHealth:
    """Bounded, redacted readiness information."""

    status: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ready", "unavailable", "degraded"}:
            raise MultimodalRunnerProtocolError("health status is invalid")
        if self.reason is not None:
            _role(self.reason, "health reason")

    def to_mapping(self) -> dict[str, str | None]:
        return {"status": self.status, "reason": self.reason}


@dataclass(frozen=True)
class SealedMultimodalHandle:
    """One receiver-created opaque input or output handle."""

    value: str
    role: str
    package_id: str
    package_revision_digest: str
    invocation_id: str
    material_lock_digest: str
    converter_digest: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not self.value.startswith("sealed:")
            or "/" in self.value
            or "\\" in self.value
        ):
            raise MultimodalRunnerProtocolError("sealed handle is invalid")
        object.__setattr__(self, "role", _role(self.role))
        object.__setattr__(
            self, "package_id", _identifier(self.package_id, "package_id")
        )
        _digest_text(self.package_revision_digest, "package_revision_digest")
        _identifier(self.invocation_id, "invocation_id")
        _digest_text(self.material_lock_digest, "material_lock_digest")
        _digest_text(self.converter_digest, "converter_digest")

    def to_mapping(self) -> dict[str, str]:
        return {
            "value": self.value,
            "role": self.role,
            "package_id": self.package_id,
            "package_revision_digest": self.package_revision_digest,
            "invocation_id": self.invocation_id,
            "material_lock_digest": self.material_lock_digest,
            "converter_digest": self.converter_digest,
        }


@dataclass(frozen=True)
class SealedMultimodalRequest:
    """Receiver-created sealed inputs bound to one exact workflow invocation."""

    package_id: str
    package_revision_digest: str
    invocation_id: str
    descriptor: MultimodalRunnerDescriptor
    handles: tuple[SealedMultimodalHandle, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "package_id", _identifier(self.package_id, "package_id")
        )
        _digest_text(self.package_revision_digest, "package_revision_digest")
        _identifier(self.invocation_id, "invocation_id")
        if not isinstance(self.descriptor, MultimodalRunnerDescriptor):
            raise MultimodalRunnerProtocolError("descriptor is invalid")
        handles = tuple(self.handles)
        if not handles or any(
            not isinstance(item, SealedMultimodalHandle) for item in handles
        ):
            raise MultimodalRunnerProtocolError("sealed handles are invalid")
        if len({item.role for item in handles}) != len(handles):
            raise MultimodalRunnerProtocolError("sealed handle roles are invalid")
        for item in handles:
            if (
                item.package_id != self.package_id
                or item.package_revision_digest != self.package_revision_digest
                or item.invocation_id != self.invocation_id
                or item.material_lock_digest != self.descriptor.material_lock_digest
                or item.converter_digest != self.descriptor.converter_digest
            ):
                raise MultimodalRunnerProtocolError("sealed handle binding is invalid")
        object.__setattr__(self, "handles", handles)

    @property
    def identity_tuple(self) -> tuple[str, ...]:
        return (
            self.descriptor.protocol_id,
            self.descriptor.protocol_version,
            self.descriptor.runner_id,
            self.descriptor.contract_digest,
            self.descriptor.material_lock_digest,
            self.descriptor.execution_abi_digest,
            self.descriptor.converter_digest,
            self.descriptor.output_contract_digest,
            self.package_id,
            self.package_revision_digest,
            self.invocation_id,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "package_revision_digest": self.package_revision_digest,
            "invocation_id": self.invocation_id,
            "descriptor": self.descriptor.to_mapping(),
            "handles": [item.to_mapping() for item in self.handles],
        }


@dataclass(frozen=True)
class DARGenerationRequestContext:
    """Effective bounded generation context passed to one runner invocation."""

    invocation_id: str
    invocation_digest: str
    execution_device: str
    generation_budget: Mapping[str, int]
    cancellation_supported: bool
    worker_protocol: str

    def __post_init__(self) -> None:
        _identifier(self.invocation_id, "invocation_id")
        _digest_text(self.invocation_digest, "invocation_digest")
        _identifier(self.execution_device, "execution_device")
        if set(self.generation_budget) != set(_BUDGET_FIELDS):
            raise MultimodalRunnerProtocolError("generation budget is invalid")
        budget = dict(self.generation_budget)
        for field in _BUDGET_FIELDS:
            checker = (
                _nonnegative_int if field == "max_continuations" else _positive_int
            )
            checker(budget[field], field)
        if not isinstance(
            self.cancellation_supported, bool
        ) or self.worker_protocol not in {
            WORKER_PROTOCOL,
            "cancellation-v1",
        }:
            raise MultimodalRunnerProtocolError("lifecycle context is invalid")
        object.__setattr__(self, "generation_budget", MappingProxyType(budget))

    def to_mapping(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "invocation_digest": self.invocation_digest,
            "execution_device": self.execution_device,
            "generation_budget": dict(self.generation_budget),
            "cancellation_supported": self.cancellation_supported,
            "worker_protocol": self.worker_protocol,
        }


@dataclass(frozen=True)
class MultimodalRunnerResult:
    """Normalized, identity-bound result returned by one runner invocation."""

    status: str
    text: str | None
    output_handles: tuple[SealedMultimodalHandle, ...]
    generated_tokens: int
    output_bytes: int
    coverage: Mapping[str, int]
    worker_reaped: bool
    package_id: str
    package_revision_digest: str
    material_lock_digest: str
    converter_digest: str
    contract_digest: str

    def __post_init__(self) -> None:
        if self.status not in TERMINAL_STATUSES:
            raise MultimodalRunnerProtocolError("result status is invalid")
        if self.text is not None and not isinstance(self.text, str):
            raise MultimodalRunnerProtocolError("result text is invalid")
        handles = tuple(self.output_handles)
        if self.status == "completed" and not self.text and not handles:
            raise MultimodalRunnerProtocolError("completed result is empty")
        if self.status != "completed" and (self.text or handles):
            raise MultimodalRunnerProtocolError("failed result contains output")
        _nonnegative_int(self.generated_tokens, "generated_tokens")
        _nonnegative_int(self.output_bytes, "output_bytes")
        if self.text is not None and self.output_bytes != len(
            self.text.encode("utf-8")
        ):
            raise MultimodalRunnerProtocolError("result byte accounting is invalid")
        if not isinstance(self.worker_reaped, bool) or not self.worker_reaped:
            raise MultimodalRunnerProtocolError("worker reap attestation is invalid")
        _identifier(self.package_id, "package_id")
        _digest_text(self.package_revision_digest, "package_revision_digest")
        _digest_text(self.material_lock_digest, "material_lock_digest")
        _digest_text(self.converter_digest, "converter_digest")
        _digest_text(self.contract_digest, "contract_digest")
        _validate_result_handles(
            handles,
            package_id=self.package_id,
            package_revision_digest=self.package_revision_digest,
            material_lock_digest=self.material_lock_digest,
            converter_digest=self.converter_digest,
        )
        object.__setattr__(self, "output_handles", handles)
        object.__setattr__(self, "coverage", _validate_coverage(self.coverage))

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "text": self.text,
            "output_handles": [item.to_mapping() for item in self.output_handles],
            "generated_tokens": self.generated_tokens,
            "output_bytes": self.output_bytes,
            "coverage": dict(self.coverage),
            "worker_reaped": self.worker_reaped,
            "package_id": self.package_id,
            "package_revision_digest": self.package_revision_digest,
            "material_lock_digest": self.material_lock_digest,
            "converter_digest": self.converter_digest,
            "contract_digest": self.contract_digest,
        }

    def to_redacted_mapping(self) -> dict[str, Any]:
        """Return only normalized, identity-bound receipt fields."""

        return self.to_mapping()


def _terminal_result(
    *,
    request: SealedMultimodalRequest,
    descriptor: MultimodalRunnerDescriptor,
    status: str,
) -> MultimodalRunnerResult:
    return MultimodalRunnerResult(
        status=status,
        text=None,
        output_handles=(),
        generated_tokens=0,
        output_bytes=0,
        coverage={},
        worker_reaped=True,
        package_id=request.package_id,
        package_revision_digest=request.package_revision_digest,
        material_lock_digest=descriptor.material_lock_digest,
        converter_digest=descriptor.converter_digest,
        contract_digest=descriptor.contract_digest,
    )


@dataclass(frozen=True)
class MultimodalRunnerBinding:
    """One exact, receiver-admitted runner binding."""

    runner: DARMultimodalModelRunnerProtocol
    descriptor: MultimodalRunnerDescriptor
    _consumed_invocations: set[str] = dataclass_field(
        default_factory=set, init=False, repr=False, compare=False
    )

    def health(self) -> MultimodalRunnerHealth:
        try:
            health = self.runner.health()
        except Exception as error:  # noqa: BLE001 - receiver boundary is redacted.
            raise MultimodalRunnerAdmissionError(
                "multimodal runner is unavailable"
            ) from error
        if not isinstance(health, MultimodalRunnerHealth):
            raise MultimodalRunnerAdmissionError("multimodal runner health is invalid")
        return health

    def run(
        self,
        request: SealedMultimodalRequest,
        *,
        context: DARGenerationRequestContext,
    ) -> MultimodalRunnerResult:
        self._claim(request, context)
        return self._invoke(request, context=context)

    def _invoke(
        self,
        request: SealedMultimodalRequest,
        *,
        context: DARGenerationRequestContext,
    ) -> MultimodalRunnerResult:
        try:
            result = self.runner.run(request, context=context)
        except MultimodalRunnerProtocolError:
            raise
        except Exception as error:  # noqa: BLE001 - provider boundary is redacted.
            raise MultimodalRunnerProtocolError("runner_failed") from error
        if not isinstance(result, MultimodalRunnerResult):
            raise MultimodalRunnerProtocolError("runner result is invalid")
        _validate_bound_result(
            result, request=request, descriptor=self.descriptor, context=context
        )
        return result

    def dispatch(  # noqa: C901 - ordered lifecycle gate
        self,
        request: SealedMultimodalRequest,
        *,
        context: DARGenerationRequestContext,
        clear_inputs: Callable[[], object],
        release_reservation: Callable[[], object],
        reap_worker: Callable[[], object],
        should_cancel: Callable[[], bool] | None = None,
        deadline_expired: Callable[[], bool] | None = None,
    ) -> MultimodalRunnerResult:
        """Run once, then complete host cleanup before exposing the result."""

        callbacks = (clear_inputs, release_reservation, reap_worker)
        if any(not callable(callback) for callback in callbacks):
            raise MultimodalRunnerProtocolError("cleanup_failed")
        self._claim(request, context)
        cancelled = should_cancel is not None and should_cancel()
        expired = deadline_expired is not None and deadline_expired()
        if cancelled or expired:
            cleanup_error: Exception | None = None
            for callback in callbacks:
                try:
                    callback()
                except Exception as error:  # noqa: BLE001 - cleanup is redacted.
                    cleanup_error = cleanup_error or error
            if cleanup_error is not None:
                raise MultimodalRunnerProtocolError("cleanup_failed") from cleanup_error
            return _terminal_result(
                request=request,
                descriptor=self.descriptor,
                status="cancelled" if cancelled else "deadline_exceeded",
            )
        result: MultimodalRunnerResult | None = None
        run_error: Exception | None = None
        try:
            result = self._invoke(request, context=context)
        except Exception as error:  # noqa: BLE001 - terminal mapping is redacted.
            run_error = error
        cleanup_error: Exception | None = None
        for callback in callbacks:
            try:
                callback()
            except Exception as error:  # noqa: BLE001 - cleanup is redacted.
                cleanup_error = cleanup_error or error
        if cleanup_error is not None:
            raise MultimodalRunnerProtocolError("cleanup_failed") from cleanup_error
        if run_error is not None:
            if isinstance(run_error, MultimodalRunnerProtocolError):
                raise run_error
            raise MultimodalRunnerProtocolError("runner_failed") from run_error
        assert result is not None
        return result

    def dispatch_with_worker_cleanup(
        self,
        request: SealedMultimodalRequest,
        *,
        context: DARGenerationRequestContext,
        clear_inputs: Callable[[], object],
        release_reservation: Callable[[], object],
        launcher: object,
        child: object,
        controller: object,
        deadline: object,
        clock: Callable[[], float],
        should_cancel: Callable[[], bool] | None = None,
        deadline_expired: Callable[[], bool] | None = None,
    ) -> MultimodalRunnerResult:
        """Use the existing generation-worker launcher for confirmed reap."""

        cleanup = getattr(launcher, "cleanup", None)
        if not callable(cleanup):
            raise MultimodalRunnerProtocolError("cleanup_failed")
        return self.dispatch(
            request,
            context=context,
            clear_inputs=clear_inputs,
            release_reservation=release_reservation,
            reap_worker=lambda: cleanup(
                child=child,
                controller=controller,
                deadline=deadline,
                clock=clock,
            ),
            should_cancel=should_cancel,
            deadline_expired=deadline_expired,
        )

    def _claim(
        self, request: SealedMultimodalRequest, context: DARGenerationRequestContext
    ) -> None:
        if request.descriptor != self.descriptor:
            raise MultimodalRunnerAdmissionError("multimodal runner binding drifted")
        if context.invocation_id != request.invocation_id:
            raise MultimodalRunnerAdmissionError("multimodal runner invocation drifted")
        if request.invocation_id in self._consumed_invocations:
            raise MultimodalRunnerAdmissionError(
                "multimodal runner invocation replayed"
            )
        self._consumed_invocations.add(request.invocation_id)


def admit_multimodal_runner(
    runner: DARMultimodalModelRunnerProtocol,
    *,
    expected_descriptor: MultimodalRunnerDescriptor,
) -> MultimodalRunnerBinding:
    """Admit one exact runner without creating a registry or dispatching work."""

    if not isinstance(expected_descriptor, MultimodalRunnerDescriptor):
        raise MultimodalRunnerAdmissionError("multimodal runner descriptor is invalid")
    if any(
        not callable(getattr(runner, operation, None))
        for operation in ("describe", "health", "run")
    ):
        raise MultimodalRunnerAdmissionError("multimodal runner is unavailable")
    try:
        descriptor = runner.describe()
    except Exception as error:  # noqa: BLE001 - receiver boundary is redacted.
        raise MultimodalRunnerAdmissionError(
            "multimodal runner is unavailable"
        ) from error
    if not isinstance(descriptor, MultimodalRunnerDescriptor):
        raise MultimodalRunnerAdmissionError("multimodal runner descriptor is invalid")
    if descriptor != expected_descriptor:
        raise MultimodalRunnerAdmissionError("multimodal runner descriptor mismatch")
    binding = MultimodalRunnerBinding(runner=runner, descriptor=descriptor)
    health = binding.health()
    if health.status == "unavailable":
        raise MultimodalRunnerAdmissionError("multimodal runner is unavailable")
    return binding
