"""Fake-only conformance tests for the bounded generation worker protocol."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.generation_worker import (
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
