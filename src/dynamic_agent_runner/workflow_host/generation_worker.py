"""Private scalar protocol for one bounded model-generation worker invocation."""

from __future__ import annotations

from dataclasses import dataclass

from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationDeadline,
    GenerationMemoryReservationRequest,
    MemoryReservationProvider,
    ReservedGenerationMemory,
    reserve_generation_memory,
)


class GenerationWorkerProtocolError(ValueError):
    """Raised without exposing worker inputs, paths, or candidate internals."""


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

    def pack(
        self, *, fragment_index: int, packed_context_tokens: int
    ) -> GenerationWorkerPackReceipt:
        if (
            self._authorization is not None
            or fragment_index != self._next_fragment_index
            or not _nonnegative_int(packed_context_tokens)
        ):
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
            self._authorization is not None
            or receipt != self._receipt
            or fragment_index != getattr(receipt, "fragment_index", None)
            or not _positive_int(remaining_generated_tokens)
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self._authorization = (receipt, remaining_generated_tokens)

    def result(
        self,
        *,
        receipt: GenerationWorkerPackReceipt,
        fragment_index: int,
        candidate: bytes,
        generated_tokens: int,
    ) -> GenerationWorkerResult:
        authorization = self._authorization
        if (
            authorization is None
            or receipt != authorization[0]
            or fragment_index != receipt.fragment_index
            or not isinstance(candidate, bytes)
            or not _nonnegative_int(generated_tokens)
            or generated_tokens > authorization[1]
            or self._total_generated_tokens + generated_tokens
            > self._max_total_generated_tokens
            or self._total_output_bytes + len(candidate) > self._max_total_output_bytes
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self._total_generated_tokens += generated_tokens
        self._total_output_bytes += len(candidate)
        self._authorization = None
        self._next_fragment_index += 1
        return GenerationWorkerResult(
            candidate,
            generated_tokens,
            self._total_generated_tokens,
            self._total_output_bytes,
        )


class GenerationWorkerLauncher:
    """Install the bootstrap envelope before allowing a child to pack input."""

    def __init__(self) -> None:
        self._packed_receipts: dict[int, GenerationWorkerPackReceipt] = {}

    def pack(
        self, *, child: object, max_memory_bytes: int, execution_device: str
    ) -> int:
        install_limit = getattr(child, "install_bootstrap_limit", None)
        pack = getattr(child, "pack", None)
        reap = getattr(child, "reap", None)
        if (
            not _positive_int(max_memory_bytes)
            or not isinstance(execution_device, str)
            or not execution_device
            or not callable(install_limit)
            or not callable(pack)
            or not callable(reap)
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        packed_successfully = False
        try:
            install_limit(max_memory_bytes, execution_device)
            packed = pack()
            packed_context_tokens = (
                packed[0] if isinstance(packed, tuple) and len(packed) == 2 else packed
            )
            model_or_accelerator_entered = (
                packed[1] if isinstance(packed, tuple) and len(packed) == 2 else None
            )
            if not _nonnegative_int(packed_context_tokens):
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                )
            if model_or_accelerator_entered is not None and (
                not isinstance(model_or_accelerator_entered, bool)
                or model_or_accelerator_entered
            ):
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                )
            packed_successfully = True
            return packed_context_tokens
        except GenerationWorkerProtocolError:
            raise
        except Exception as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error
        finally:
            if not packed_successfully:
                try:
                    reap()
                except Exception as error:
                    raise GenerationWorkerProtocolError(
                        "generation worker protocol invalid"
                    ) from error

    def abort(self, *, child: object) -> None:
        """Reap a packed child when admission cannot proceed."""

        self._packed_receipts.pop(id(child), None)
        reap = getattr(child, "reap", None)
        if not callable(reap):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        try:
            reap()
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
    ) -> GenerationWorkerPackReceipt:
        """Pack once and bind its measured context to the current receipt."""

        if not isinstance(session, GenerationWorkerSession):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        packed_context_tokens = self.pack(
            child=child,
            max_memory_bytes=max_memory_bytes,
            execution_device=execution_device,
        )
        try:
            receipt = session.pack(
                fragment_index=fragment_index,
                packed_context_tokens=packed_context_tokens,
            )
            self._packed_receipts[id(child)] = receipt
            return receipt
        except Exception as error:
            self.abort(child=child)
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
    ) -> GenerationWorkerResult:
        """Run one authorized child generation and validate its receipt-bound result."""

        generate = getattr(child, "generate", None)
        reap = getattr(child, "reap", None)
        packed_receipt = self._packed_receipts.get(id(child))
        if not callable(generate) or not callable(reap) or packed_receipt != receipt:
            if packed_receipt is not None:
                self.abort(child=child)
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self._packed_receipts.pop(id(child), None)
        reservation = self.authorize(
            session=session,
            receipt=receipt,
            remaining_generated_tokens=remaining_generated_tokens,
            provider=provider,
            request=request,
        )
        try:
            deadline.require_remaining(now)
            result = generate()
            if (
                not isinstance(result, tuple)
                or len(result) != 2
                or not isinstance(result[0], bytes)
            ):
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                )
            return session.result(
                receipt=receipt,
                fragment_index=receipt.fragment_index,
                candidate=result[0],
                generated_tokens=result[1],
            )
        except GenerationWorkerProtocolError:
            raise
        except Exception as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error
        finally:
            try:
                reap()
            except Exception as error:
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                ) from error
            finally:
                reservation.release()

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
        except Exception as error:
            raise GenerationWorkerProtocolError(
                "generation worker protocol invalid"
            ) from error


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_int(value: object) -> bool:
    return _nonnegative_int(value) and value > 0
