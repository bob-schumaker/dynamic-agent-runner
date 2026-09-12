"""Private scalar protocol for one bounded model-generation worker invocation."""

from __future__ import annotations

from dataclasses import dataclass


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
            or not _positive_int(max_total_output_bytes)
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self._identity = values
        self._receipt: GenerationWorkerPackReceipt | None = None
        self._authorization: tuple[GenerationWorkerPackReceipt, int] | None = None
        self._max_total_output_bytes = max_total_output_bytes
        self._resulted = False

    def pack(
        self, *, fragment_index: int, packed_context_tokens: int
    ) -> GenerationWorkerPackReceipt:
        if (
            self._receipt is not None
            or not _nonnegative_int(fragment_index)
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
            self._resulted
            or authorization is None
            or receipt != authorization[0]
            or fragment_index != receipt.fragment_index
            or not isinstance(candidate, bytes)
            or len(candidate) > self._max_total_output_bytes
            or not _nonnegative_int(generated_tokens)
            or generated_tokens > authorization[1]
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        self._resulted = True
        return GenerationWorkerResult(candidate, generated_tokens)


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_int(value: object) -> bool:
    return _nonnegative_int(value) and value > 0
