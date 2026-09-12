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
            return packed_context_tokens
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
    ) -> bytes:
        """Run one authorized child generation and release its reservation."""

        generate = getattr(child, "generate", None)
        if not callable(generate):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        reservation = self.authorize(
            session=session,
            receipt=receipt,
            remaining_generated_tokens=remaining_generated_tokens,
            provider=provider,
            request=request,
        )
        try:
            deadline.require_remaining(now)
            candidate = generate()
            if not isinstance(candidate, bytes):
                raise GenerationWorkerProtocolError(
                    "generation worker protocol invalid"
                )
            return candidate
        except GenerationWorkerProtocolError:
            raise
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
