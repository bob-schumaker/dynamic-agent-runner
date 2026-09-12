"""Fake-only conformance tests for the bounded generation worker protocol."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerLauncher,
    GenerationWorkerProtocolError,
    GenerationWorkerSession,
)


def test_worker_requires_a_matching_pack_receipt_before_authorized_result() -> None:
    worker = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
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


def test_launcher_installs_bootstrap_limit_before_packing() -> None:
    events: list[tuple[object, ...]] = []

    class Child:
        def install_bootstrap_limit(self, memory_bytes: int, device: str) -> None:
            events.append(("limit", memory_bytes, device))

        def pack(self) -> int:
            events.append(("pack",))
            return 3

        def reap(self) -> None:
            events.append(("reap",))

    assert (
        GenerationWorkerLauncher().pack(
            child=Child(), max_memory_bytes=8, execution_device="cpu"
        )
        == 3
    )
    assert events == [("limit", 8, "cpu"), ("pack",), ("reap",)]
