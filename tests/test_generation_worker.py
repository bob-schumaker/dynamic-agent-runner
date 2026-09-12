"""Fake-only conformance tests for the bounded generation worker protocol."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerLauncher,
    GenerationWorkerPackReceipt,
    GenerationWorkerProtocolError,
    GenerationWorkerResult,
    GenerationWorkerSession,
)
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationDeadline,
    GenerationMemoryReservationRequest,
)


def test_worker_requires_a_matching_pack_receipt_before_authorized_result() -> None:
    worker = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=4,
        max_total_output_bytes=2,
    )

    receipt = worker.pack(
        fragment_index=0,
        packed_context_tokens=3,
    )
    worker.authorize(
        receipt=receipt,
        fragment_index=0,
        remaining_generated_tokens=4,
    )
    result = worker.result(
        receipt=receipt,
        fragment_index=0,
        candidate=b"{}",
        generated_tokens=2,
    )

    assert result.candidate == b"{}"
    assert result.generated_tokens == 2

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        worker.result(
            receipt=receipt,
            fragment_index=0,
            candidate=b"{}",
            generated_tokens=1,
        )


def test_worker_rejects_stale_receipts_out_of_order_authorization_and_overage() -> None:
    worker = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=4,
        max_total_output_bytes=2,
    )
    receipt = worker.pack(fragment_index=0, packed_context_tokens=3)

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        worker.authorize(
            receipt=receipt,
            fragment_index=1,
            remaining_generated_tokens=4,
        )
    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        worker.result(
            receipt=receipt,
            fragment_index=0,
            candidate=b"{}",
            generated_tokens=1,
        )

    worker.authorize(
        receipt=receipt,
        fragment_index=0,
        remaining_generated_tokens=2,
    )
    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        worker.authorize(
            receipt=receipt,
            fragment_index=0,
            remaining_generated_tokens=2,
        )
    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        worker.result(
            receipt=receipt,
            fragment_index=0,
            candidate=b"{}",
            generated_tokens=3,
        )


def test_worker_rejects_a_candidate_over_its_authorized_byte_budget() -> None:
    worker = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=4,
        max_total_output_bytes=1,
    )
    receipt = worker.pack(fragment_index=0, packed_context_tokens=3)
    worker.authorize(
        receipt=receipt,
        fragment_index=0,
        remaining_generated_tokens=1,
    )

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        worker.result(
            receipt=receipt,
            fragment_index=0,
            candidate=b"{}",
            generated_tokens=1,
        )


def test_worker_binds_sequential_fragments_to_aggregate_token_and_byte_limits() -> None:
    worker = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=2,
        max_total_output_bytes=3,
    )
    first = worker.pack(fragment_index=0, packed_context_tokens=3)
    worker.authorize(
        receipt=first,
        fragment_index=0,
        remaining_generated_tokens=2,
    )
    assert worker.result(
        receipt=first,
        fragment_index=0,
        candidate=b"a",
        generated_tokens=1,
    ) == GenerationWorkerResult(
        candidate=b"a",
        generated_tokens=1,
        aggregate_generated_tokens=1,
        aggregate_output_bytes=1,
    )

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        worker.pack(fragment_index=2, packed_context_tokens=3)

    second = worker.pack(fragment_index=1, packed_context_tokens=3)
    worker.authorize(
        receipt=second,
        fragment_index=1,
        remaining_generated_tokens=2,
    )
    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        worker.result(
            receipt=second,
            fragment_index=1,
            candidate=b"xyz",
            generated_tokens=2,
        )


def test_launcher_keeps_a_successfully_packed_child_for_authorization() -> None:
    events: list[tuple[object, ...]] = []

    class Child:
        def install_bootstrap_limit(self, memory_bytes: int, device: str) -> None:
            events.append(("limit", memory_bytes, device))

        def pack(self) -> int:
            events.append(("pack",))
            return 3

        def reap(self) -> None:
            events.append(("reap",))

    child = Child()
    launcher = GenerationWorkerLauncher()

    assert launcher.pack(child=child, max_memory_bytes=8, execution_device="cpu") == 3
    assert events == [("limit", 8, "cpu"), ("pack",)]

    launcher.abort(child=child)
    assert events == [("limit", 8, "cpu"), ("pack",), ("reap",)]


def test_launcher_binds_packed_context_to_its_session_receipt() -> None:
    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            pass

        def pack(self) -> int:
            return 3

        def reap(self) -> None:
            pass

    session = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=4,
        max_total_output_bytes=8,
    )

    assert GenerationWorkerLauncher().pack_receipt(
        child=Child(),
        session=session,
        fragment_index=0,
        max_memory_bytes=8,
        execution_device="cpu",
    ) == GenerationWorkerPackReceipt(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        fragment_index=0,
        packed_context_tokens=3,
    )


def test_launcher_rejects_model_or_accelerator_entry_during_packing() -> None:
    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            pass

        def pack(self) -> tuple[int, bool]:
            return 3, True

        def reap(self) -> None:
            pass

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        GenerationWorkerLauncher().pack(
            child=Child(), max_memory_bytes=8, execution_device="cpu"
        )


def test_launcher_accepts_an_explicit_clean_packing_attestation() -> None:
    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            pass

        def pack(self) -> tuple[int, bool]:
            return 3, False

        def reap(self) -> None:
            pass

    assert (
        GenerationWorkerLauncher().pack(
            child=Child(), max_memory_bytes=8, execution_device="cpu"
        )
        == 3
    )


def test_launcher_reserves_memory_before_authorizing_a_packed_receipt() -> None:
    events: list[str] = []

    class Reservation:
        def release(self) -> None:
            events.append("release")

    class Provider:
        def reserve(self, _request: object) -> Reservation:
            events.append("reserve")
            return Reservation()

    worker = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=4,
        max_total_output_bytes=2,
    )
    receipt = worker.pack(fragment_index=0, packed_context_tokens=3)
    reservation = GenerationWorkerLauncher().authorize(
        session=worker,
        receipt=receipt,
        remaining_generated_tokens=2,
        provider=Provider(),
        request=GenerationMemoryReservationRequest(
            material_lock_digest="c" * 64,
            runner_identity="runner",
            execution_device="cpu",
            packed_context_tokens=3,
            requested_new_tokens=2,
            max_memory_bytes=8,
            deadline_monotonic=1.0,
        ),
    )

    assert events == ["reserve"]
    reservation.release()
    assert events == ["reserve", "release"]


def test_launcher_releases_reservation_after_authorized_generation() -> None:
    events: list[str] = []

    class Reservation:
        def release(self) -> None:
            events.append("release")

    class Provider:
        def reserve(self, _request: object) -> Reservation:
            events.append("reserve")
            return Reservation()

    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            events.append("limit")

        def pack(self) -> int:
            events.append("pack")
            return 3

        def generate(self) -> tuple[bytes, int]:
            events.append("generate")
            return b"{}", 1

        def reap(self) -> None:
            events.append("reap")

    worker = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=4,
        max_total_output_bytes=2,
    )
    child = Child()
    launcher = GenerationWorkerLauncher()
    receipt = launcher.pack_receipt(
        child=child,
        session=worker,
        fragment_index=0,
        max_memory_bytes=8,
        execution_device="cpu",
    )
    result = launcher.generate(
        child=child,
        session=worker,
        receipt=receipt,
        remaining_generated_tokens=1,
        provider=Provider(),
        request=GenerationMemoryReservationRequest(
            material_lock_digest="c" * 64,
            runner_identity="runner",
            execution_device="cpu",
            packed_context_tokens=3,
            requested_new_tokens=1,
            max_memory_bytes=8,
            deadline_monotonic=1.0,
        ),
        deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1),
        now=0.0,
    )
    assert result == GenerationWorkerResult(
        candidate=b"{}",
        generated_tokens=1,
        aggregate_generated_tokens=1,
        aggregate_output_bytes=2,
    )
    assert events == ["limit", "pack", "reserve", "generate", "reap", "release"]


def test_launcher_rejects_an_expired_deadline_before_child_generation() -> None:
    events: list[str] = []

    class Reservation:
        def release(self) -> None:
            events.append("release")

    class Provider:
        def reserve(self, _request: object) -> Reservation:
            events.append("reserve")
            return Reservation()

    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            events.append("limit")

        def pack(self) -> int:
            events.append("pack")
            return 3

        def generate(self) -> bytes:
            events.append("generate")
            return b"{}"

        def reap(self) -> None:
            events.append("reap")

    worker = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=4,
        max_total_output_bytes=2,
    )
    child = Child()
    launcher = GenerationWorkerLauncher()
    receipt = launcher.pack_receipt(
        child=child,
        session=worker,
        fragment_index=0,
        max_memory_bytes=8,
        execution_device="cpu",
    )
    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        launcher.generate(
            child=child,
            session=worker,
            receipt=receipt,
            remaining_generated_tokens=1,
            provider=Provider(),
            request=GenerationMemoryReservationRequest(
                material_lock_digest="c" * 64,
                runner_identity="runner",
                execution_device="cpu",
                packed_context_tokens=3,
                requested_new_tokens=1,
                max_memory_bytes=8,
                deadline_monotonic=1.0,
            ),
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1),
            now=0.001,
        )
    assert events == ["limit", "pack", "reserve", "reap", "release"]
