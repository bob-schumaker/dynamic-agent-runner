"""Private scalar protocol for one bounded model-generation worker invocation."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from typing import Mapping, NoReturn

from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationDeadline,
    GenerationMemoryReservationRequest,
    MemoryReservationProvider,
    ReservedGenerationMemory,
    GenerationRunnerCapability,
    GenerationResourceBudget,
    GenerationResourceBudgetError,
    parse_generation_resource_budget,
    reserve_generation_memory,
)


class GenerationWorkerProtocolError(ValueError):
    """Raised without exposing worker inputs, paths, or candidate internals."""


class GenerationWorkerDeadlineExceeded(GenerationWorkerProtocolError):
    """Raised after a deadline path has discarded late worker output."""


class GenerationWorkerExecutionFailed(GenerationWorkerProtocolError):
    """Raised for a redacted terminal failure inside an otherwise valid worker."""


class GenerationWorkerOutputLimitExceeded(GenerationWorkerProtocolError):
    """Raised after a worker discards a candidate that cannot fit its output frame."""


@dataclass(frozen=True)
class GenerationWorkerLaunchDescriptor:
    """Bounded non-executable launch data for the fixed worker entry point."""

    protocol_version: str
    invocation_digest: str
    fragment_index: int
    runner_id: str
    capability_contract_digest: str
    converter_id: str
    converter_asset_digest: str
    material_lock_digest: str
    execution_descriptor_digest: str
    execution_device: str
    budget: GenerationResourceBudget
    asset_handles: tuple[str, ...]

    def __post_init__(self) -> None:
        identifiers = (
            self.protocol_version,
            self.runner_id,
            self.converter_id,
            self.execution_device,
        )
        digests = (
            self.invocation_digest,
            self.capability_contract_digest,
            self.converter_asset_digest,
            self.material_lock_digest,
            self.execution_descriptor_digest,
        )
        if (
            self.protocol_version != "generation-worker-v1"
            or any(not isinstance(value, str) or not value for value in identifiers)
            or any(not _digest(value) for value in digests)
            or not _nonnegative_int(self.fragment_index)
            or not isinstance(self.budget, GenerationResourceBudget)
            or not isinstance(self.asset_handles, tuple)
            or not self.asset_handles
            or len(self.asset_handles) > 16
            or any(not _opaque_handle(handle) for handle in self.asset_handles)
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        if len(self._encoded()) > 8_192:
            raise GenerationWorkerProtocolError("generation worker protocol invalid")

    def to_wire(self) -> dict[str, object]:
        """Return the exact, versioned mapping accepted by the worker entry point."""

        return {
            "protocol_version": self.protocol_version,
            "invocation_digest": self.invocation_digest,
            "fragment_index": self.fragment_index,
            "runner_id": self.runner_id,
            "capability_contract_digest": self.capability_contract_digest,
            "converter_id": self.converter_id,
            "converter_asset_digest": self.converter_asset_digest,
            "material_lock_digest": self.material_lock_digest,
            "execution_descriptor_digest": self.execution_descriptor_digest,
            "execution_device": self.execution_device,
            "budget": asdict(self.budget),
            "asset_handles": self.asset_handles,
        }

    @classmethod
    def from_wire(cls, value: object) -> "GenerationWorkerLaunchDescriptor":
        """Reject every field outside the fixed host-private descriptor mapping."""

        if not isinstance(value, Mapping) or set(value) != _LAUNCH_DESCRIPTOR_FIELDS:
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        asset_handles = value["asset_handles"]
        if not isinstance(asset_handles, (tuple, list)):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        try:
            return cls(
                protocol_version=value["protocol_version"],
                invocation_digest=value["invocation_digest"],
                fragment_index=value["fragment_index"],
                runner_id=value["runner_id"],
                capability_contract_digest=value["capability_contract_digest"],
                converter_id=value["converter_id"],
                converter_asset_digest=value["converter_asset_digest"],
                material_lock_digest=value["material_lock_digest"],
                execution_descriptor_digest=value["execution_descriptor_digest"],
                execution_device=value["execution_device"],
                budget=parse_generation_resource_budget(value["budget"]),
                asset_handles=tuple(asset_handles),
            )
        except (
            GenerationResourceBudgetError,
            KeyError,
            TypeError,
            GenerationWorkerProtocolError,
        ) as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error

    def _encoded(self) -> bytes:
        return json.dumps(self.to_wire(), sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )


_LAUNCH_DESCRIPTOR_FIELDS = frozenset(
    {
        "protocol_version",
        "invocation_digest",
        "fragment_index",
        "runner_id",
        "capability_contract_digest",
        "converter_id",
        "converter_asset_digest",
        "material_lock_digest",
        "execution_descriptor_digest",
        "execution_device",
        "budget",
        "asset_handles",
    }
)


@dataclass(frozen=True)
class GenerationWorkerPackReceipt:
    """Identity-bound scalar receipt returned by the worker packing phase."""

    invocation_id: str
    invocation_digest: str
    converter_digest: str
    material_lock_digest: str
    execution_device: str
    fragment_index: int
    packed_context_tokens: int


@dataclass(frozen=True)
class GenerationWorkerResult:
    """One authorized candidate and its compatible-runner token attestation."""

    candidate: bytes
    generated_tokens: int
    aggregate_generated_tokens: int
    aggregate_output_bytes: int
    exhausted: bool = False
    packed_context_tokens: int | None = None


class GenerationWorkerSession:
    """Enforce pack, authorization, and one result for one private invocation."""

    def __init__(
        self,
        *,
        invocation_id: str,
        invocation_digest: str,
        converter_digest: str,
        material_lock_digest: str,
        execution_device: str,
        max_total_generated_tokens: int,
        max_total_output_bytes: int,
    ) -> None:
        values = (
            invocation_id,
            invocation_digest,
            converter_digest,
            material_lock_digest,
            execution_device,
        )
        if (
            any(not isinstance(value, str) or not value for value in values)
            or any(len(value) != 64 for value in values[1:4])
            or not _positive_int(max_total_generated_tokens)
            or not _positive_int(max_total_output_bytes)
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self._identity = values
        self._receipt: GenerationWorkerPackReceipt | None = None
        self._authorization: tuple[GenerationWorkerPackReceipt, int] | None = None
        self._next_fragment_index = 0
        self._total_generated_tokens = 0
        self._total_output_bytes = 0
        self._max_total_generated_tokens = max_total_generated_tokens
        self._max_total_output_bytes = max_total_output_bytes
        self._failed = False

    def pack(
        self, *, fragment_index: int, packed_context_tokens: int
    ) -> GenerationWorkerPackReceipt:
        if (
            self._failed
            or self._receipt is not None
            or self._authorization is not None
            or fragment_index != self._next_fragment_index
            or not _nonnegative_int(packed_context_tokens)
        ):
            self._failed = True
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        receipt = GenerationWorkerPackReceipt(
            *self._identity,
            fragment_index=fragment_index,
            packed_context_tokens=packed_context_tokens,
        )
        self._receipt = receipt
        return receipt

    def authorize(
        self,
        *,
        receipt: GenerationWorkerPackReceipt,
        fragment_index: int,
        remaining_generated_tokens: int,
    ) -> None:
        if (
            self._failed
            or self._authorization is not None
            or receipt != self._receipt
            or fragment_index != getattr(receipt, "fragment_index", None)
            or not _positive_int(remaining_generated_tokens)
        ):
            self._failed = True
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self._authorization = (receipt, remaining_generated_tokens)

    def result(
        self,
        *,
        receipt: GenerationWorkerPackReceipt,
        fragment_index: int,
        candidate: bytes,
        generated_tokens: int,
        reported_aggregate_generated_tokens: int | None = None,
        reported_aggregate_output_bytes: int | None = None,
        exhausted: bool = False,
    ) -> GenerationWorkerResult:
        authorization = self._authorization
        if (
            self._failed
            or authorization is None
            or receipt != authorization[0]
            or fragment_index != receipt.fragment_index
            or not isinstance(candidate, bytes)
            or not _nonnegative_int(generated_tokens)
            or not isinstance(exhausted, bool)
        ):
            self._failed = True
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        aggregate_generated_tokens = self._total_generated_tokens + generated_tokens
        aggregate_output_bytes = self._total_output_bytes + len(candidate)
        if (
            generated_tokens > authorization[1]
            or aggregate_generated_tokens > self._max_total_generated_tokens
            or aggregate_output_bytes > self._max_total_output_bytes
            or (
                reported_aggregate_generated_tokens is not None
                and (
                    not _nonnegative_int(reported_aggregate_generated_tokens)
                    or reported_aggregate_generated_tokens != aggregate_generated_tokens
                )
            )
            or (
                reported_aggregate_output_bytes is not None
                and (
                    not _nonnegative_int(reported_aggregate_output_bytes)
                    or reported_aggregate_output_bytes != aggregate_output_bytes
                )
            )
        ):
            self._failed = True
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self._total_generated_tokens = aggregate_generated_tokens
        self._total_output_bytes = aggregate_output_bytes
        self._receipt = None
        self._authorization = None
        self._next_fragment_index += 1
        return GenerationWorkerResult(
            candidate,
            generated_tokens,
            self._total_generated_tokens,
            self._total_output_bytes,
            exhausted,
            receipt.packed_context_tokens,
        )


class GenerationWorkerLauncher:
    """Install the bootstrap envelope before allowing a child to pack input."""

    def __init__(self) -> None:
        self._packed_receipts: dict[int, GenerationWorkerPackReceipt] = {}

    def launch(
        self,
        *,
        factory: object,
        controller: object,
        deadline: GenerationDeadline,
        clock: Callable[[], float] = time.monotonic,
    ) -> object:
        """Create and revalidate one typed descriptor before child launch."""

        create_descriptor = getattr(factory, "create_launch_descriptor", None)
        launch = getattr(controller, "launch", None)
        wait_ready = getattr(controller, "wait_ready", None)
        if (
            not isinstance(deadline, GenerationDeadline)
            or not callable(create_descriptor)
            or not callable(launch)
            or not callable(wait_ready)
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        try:
            deadline.require_remaining(clock())
            descriptor = create_descriptor()
            if not isinstance(descriptor, GenerationWorkerLaunchDescriptor):
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                )
            if not _has_matching_worker_bindings(
                factory=factory,
                controller=controller,
                descriptor=descriptor,
            ):
                raise GenerationResourceBudgetError(
                    "generation memory budget is unavailable"
                )
            child = launch(fixed_generation_worker_entry_point(descriptor.to_wire()))
            if wait_ready(child, deadline.remaining_seconds(clock())) is not True:
                self._close_with_controller(
                    child=child,
                    controller=controller,
                    deadline=deadline,
                    clock=clock,
                )
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                )
            try:
                deadline.require_remaining(clock())
            except GenerationResourceBudgetError:
                self._close_with_controller(
                    child=child,
                    controller=controller,
                    deadline=deadline,
                    clock=clock,
                )
                raise
            return child
        except GenerationWorkerProtocolError:
            raise
        except GenerationResourceBudgetError as error:
            _raise_worker_budget_error(error)
        except Exception as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error

    def pack(
        self,
        *,
        child: object,
        max_memory_bytes: int,
        execution_device: str,
        deadline: GenerationDeadline | None = None,
        clock: Callable[[], float] = time.monotonic,
        controller: object | None = None,
    ) -> int:
        install_limit = getattr(child, "install_bootstrap_limit", None)
        pack = getattr(child, "pack", None)
        reap = getattr(child, "reap", None)
        if not _valid_pack_request(
            max_memory_bytes=max_memory_bytes,
            execution_device=execution_device,
            install_limit=install_limit,
            pack=pack,
            reap=reap,
            deadline=deadline,
            controller=controller,
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        if controller is not None and not isinstance(deadline, GenerationDeadline):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        packed_successfully = False
        try:
            packed_context_tokens = self._pack_with_envelope(
                install_limit=install_limit,
                pack=pack,
                max_memory_bytes=max_memory_bytes,
                execution_device=execution_device,
                deadline=deadline,
                clock=clock,
            )
            packed_successfully = True
            return packed_context_tokens
        except GenerationWorkerProtocolError:
            raise
        except GenerationResourceBudgetError as error:
            _raise_worker_budget_error(error)
        except Exception as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error
        finally:
            if not packed_successfully:
                try:
                    if controller is None:
                        reap()
                    else:
                        self._close_with_controller(
                            child=child,
                            controller=controller,
                            deadline=deadline,
                            clock=clock,
                        )
                except Exception as error:
                    raise GenerationWorkerProtocolError(
                        "generation worker protocol invalid"
                    ) from error

    def _pack_with_envelope(
        self,
        *,
        install_limit: Callable[[int, str], object],
        pack: Callable[[], object],
        max_memory_bytes: int,
        execution_device: str,
        deadline: GenerationDeadline | None,
        clock: Callable[[], float],
    ) -> int:
        if deadline is not None:
            deadline.require_remaining(clock())
        install_limit(max_memory_bytes, execution_device)
        packed = pack()
        packed_context_tokens = (
            packed[0] if isinstance(packed, tuple) and len(packed) == 2 else packed
        )
        model_or_accelerator_entered = (
            packed[1] if isinstance(packed, tuple) and len(packed) == 2 else None
        )
        if not _nonnegative_int(packed_context_tokens) or (
            model_or_accelerator_entered is not None
            and (
                not isinstance(model_or_accelerator_entered, bool)
                or model_or_accelerator_entered
            )
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        if deadline is not None:
            deadline.require_remaining(clock())
        return packed_context_tokens

    def abort(
        self,
        *,
        child: object,
        controller: object | None = None,
        deadline: GenerationDeadline | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Reap a packed child when admission cannot proceed."""

        self._packed_receipts.pop(id(child), None)
        if controller is not None and not isinstance(deadline, GenerationDeadline):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        try:
            if controller is None:
                reap = getattr(child, "reap", None)
                if not callable(reap):
                    raise GenerationWorkerProtocolError(
                        "generation worker protocol invalid"
                    )
                reap()
            else:
                self._close_with_controller(
                    child=child,
                    controller=controller,
                    deadline=deadline,
                    clock=clock,
                )
        except Exception as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error

    def pack_receipt(
        self,
        *,
        child: object,
        session: GenerationWorkerSession,
        fragment_index: int,
        max_memory_bytes: int,
        execution_device: str,
        deadline: GenerationDeadline | None = None,
        clock: Callable[[], float] = time.monotonic,
        controller: object | None = None,
    ) -> GenerationWorkerPackReceipt:
        """Pack once and bind its measured context to the current receipt."""

        if not isinstance(session, GenerationWorkerSession):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        packed_context_tokens = self.pack(
            child=child,
            max_memory_bytes=max_memory_bytes,
            execution_device=execution_device,
            deadline=deadline,
            clock=clock,
            controller=controller,
        )
        try:
            receipt = session.pack(
                fragment_index=fragment_index,
                packed_context_tokens=packed_context_tokens,
            )
            self._packed_receipts[id(child)] = receipt
            return receipt
        except Exception as error:
            self.abort(
                child=child,
                controller=controller,
                deadline=deadline,
                clock=clock,
            )
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error

    def generate(
        self,
        *,
        child: object,
        session: GenerationWorkerSession,
        receipt: GenerationWorkerPackReceipt,
        remaining_generated_tokens: int,
        provider: MemoryReservationProvider,
        request: GenerationMemoryReservationRequest,
        deadline: GenerationDeadline,
        now: float,
        clock: Callable[[], float] = time.monotonic,
        controller: object | None = None,
    ) -> GenerationWorkerResult:
        """Run one authorized child generation and validate its receipt-bound result."""

        generate = getattr(child, "generate", None)
        reap = getattr(child, "reap", None)
        packed_receipt = self._packed_receipts.get(id(child))
        if (
            not callable(generate)
            or (not callable(reap) and controller is None)
            or packed_receipt != receipt
        ):
            if packed_receipt is not None:
                self.abort(
                    child=child,
                    controller=controller,
                    deadline=deadline,
                    clock=clock,
                )
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self._packed_receipts.pop(id(child), None)
        reservation: ReservedGenerationMemory | None = None
        try:
            reservation = self.authorize(
                session=session,
                receipt=receipt,
                remaining_generated_tokens=remaining_generated_tokens,
                provider=provider,
                request=request,
            )
            _authorize_child_if_supported(child, receipt, remaining_generated_tokens)
            deadline.require_remaining(now)
            _configure_child_deadline(child=child, deadline=deadline, clock=clock)
            return self._validated_generation_result(
                generate=generate,
                deadline=deadline,
                clock=clock,
                receipt=receipt,
                session=session,
            )
        except GenerationWorkerProtocolError:
            raise
        except GenerationResourceBudgetError as error:
            _raise_worker_budget_error(error)
        except Exception as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error
        finally:
            try:
                if controller is None:
                    reap()
                else:
                    self._close_with_controller(
                        child=child,
                        controller=controller,
                        deadline=deadline,
                        clock=clock,
                    )
            except Exception as error:
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                ) from error
            else:
                if reservation is not None:
                    reservation.release()

    def _validated_generation_result(
        self,
        *,
        generate: Callable[[], object],
        deadline: GenerationDeadline,
        clock: Callable[[], float],
        receipt: GenerationWorkerPackReceipt,
        session: GenerationWorkerSession,
    ) -> GenerationWorkerResult:
        result = generate()
        if (
            not isinstance(result, tuple)
            or len(result) not in (2, 3, 4, 5)
            or not isinstance(result[0], bytes)
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        deadline.require_remaining(clock())
        reported_generated_tokens = result[2] if len(result) in (4, 5) else None
        reported_output_bytes = result[3] if len(result) in (4, 5) else None
        exhausted = result[-1] if len(result) in (3, 5) else False
        return session.result(
            receipt=receipt,
            fragment_index=receipt.fragment_index,
            candidate=result[0],
            generated_tokens=result[1],
            reported_aggregate_generated_tokens=reported_generated_tokens,
            reported_aggregate_output_bytes=reported_output_bytes,
            exhausted=exhausted,
        )

    def _close_with_controller(
        self,
        *,
        child: object,
        controller: object,
        deadline: GenerationDeadline,
        clock: Callable[[], float],
    ) -> None:
        """Confirm worker cleanup, escalating an expired deadline through kill."""

        terminate = getattr(controller, "terminate", None)
        kill = getattr(controller, "kill", None)
        reap = getattr(controller, "reap", None)
        if not all(callable(operation) for operation in (terminate, kill, reap)):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        expired = deadline.remaining_seconds(clock()) <= 0
        if expired:
            terminate(child)
        try:
            confirmed = reap(child, max(deadline.remaining_seconds(clock()), 0.0))
            if confirmed is not True:
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                )
        except Exception as error:
            kill(child)
            confirmed = reap(child, 0.0)
            if confirmed is not True:
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                ) from error

    def authorize(
        self,
        *,
        session: GenerationWorkerSession,
        receipt: GenerationWorkerPackReceipt,
        remaining_generated_tokens: int,
        provider: MemoryReservationProvider,
        request: GenerationMemoryReservationRequest,
    ) -> ReservedGenerationMemory:
        """Reserve first, then grant the one receipt-bound generation permit."""

        if (
            not isinstance(session, GenerationWorkerSession)
            or not isinstance(receipt, GenerationWorkerPackReceipt)
            or not _positive_int(remaining_generated_tokens)
            or not isinstance(request, GenerationMemoryReservationRequest)
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        try:
            reservation = reserve_generation_memory(provider, request)
            try:
                session.authorize(
                    receipt=receipt,
                    fragment_index=receipt.fragment_index,
                    remaining_generated_tokens=remaining_generated_tokens,
                )
            except Exception:
                reservation.release()
                raise
            return reservation
        except GenerationResourceBudgetError:
            raise
        except Exception as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error


def _authorize_child_if_supported(
    child: object,
    receipt: GenerationWorkerPackReceipt,
    remaining_generated_tokens: int,
) -> None:
    authorize = getattr(child, "authorize", None)
    if callable(authorize):
        authorize(receipt, remaining_generated_tokens)


def _configure_child_deadline(
    *,
    child: object,
    deadline: GenerationDeadline,
    clock: Callable[[], float],
) -> None:
    """Pass the remaining deadline only to children that support timed result waits."""

    set_deadline_timeout = getattr(child, "set_deadline_timeout", None)
    if callable(set_deadline_timeout):
        deadline.require_remaining(clock())
        set_deadline_timeout(deadline.remaining_seconds(clock()))


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_int(value: object) -> bool:
    return _nonnegative_int(value) and value > 0


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _opaque_handle(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 256
        and "/" not in value
        and "\\" not in value
        and all(
            character.isprintable() and not character.isspace() for character in value
        )
    )


def _memory_budget_unavailable(error: GenerationResourceBudgetError) -> bool:
    return str(error) == "generation memory budget is unavailable"


def _valid_pack_request(
    *,
    max_memory_bytes: object,
    execution_device: object,
    install_limit: object,
    pack: object,
    reap: object,
    deadline: object,
    controller: object | None,
) -> bool:
    return (
        _positive_int(max_memory_bytes)
        and isinstance(execution_device, str)
        and bool(execution_device)
        and callable(install_limit)
        and callable(pack)
        and (callable(reap) or controller is not None)
        and (deadline is None or isinstance(deadline, GenerationDeadline))
    )


def _raise_worker_budget_error(error: GenerationResourceBudgetError) -> NoReturn:
    if str(error) == "generation deadline exceeded":
        raise GenerationWorkerDeadlineExceeded(
            "generation deadline exceeded"
        ) from error
    if _memory_budget_unavailable(error):
        raise error
    raise GenerationWorkerProtocolError("generation worker protocol invalid") from error


def _has_matching_worker_bindings(
    *,
    factory: object,
    controller: object,
    descriptor: GenerationWorkerLaunchDescriptor,
) -> bool:
    """Reject a mismatched runner/device controller before child launch."""

    supported_devices = getattr(controller, "supported_execution_devices", None)
    capability = getattr(factory, "capability", None)
    return (
        getattr(factory, "runner_id", None) == descriptor.runner_id
        and isinstance(capability, GenerationRunnerCapability)
        and capability.runner_id == descriptor.runner_id
        and capability.worker_protocol == descriptor.protocol_version
        and capability.contract_digest == descriptor.capability_contract_digest
        and getattr(controller, "runner_id", None) == descriptor.runner_id
        and isinstance(supported_devices, frozenset)
        and descriptor.execution_device in supported_devices
    )


def fixed_generation_worker_entry_point(
    wire_descriptor: object,
    *,
    asset_handles: object | None = None,
    now: datetime | None = None,
) -> GenerationWorkerLaunchDescriptor:
    """Validate fixed worker input before any child asset resolution can begin."""

    descriptor = GenerationWorkerLaunchDescriptor.from_wire(wire_descriptor)
    if asset_handles is not None:
        resolve = getattr(asset_handles, "resolve", None)
        if not callable(resolve) or not isinstance(now, datetime):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        try:
            for handle in descriptor.asset_handles:
                resolve(handle=handle, descriptor=descriptor, now=now)
        except Exception as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error
    return descriptor
