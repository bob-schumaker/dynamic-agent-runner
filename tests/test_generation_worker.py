"""Fake-only conformance tests for the bounded generation worker protocol."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerDeadlineExceeded,
    GenerationWorkerLaunchDescriptor,
    GenerationWorkerLauncher,
    GenerationWorkerPackReceipt,
    GenerationWorkerProtocolError,
    GenerationWorkerResult,
    GenerationWorkerSession,
    fixed_generation_worker_entry_point,
)
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationDeadline,
    GenerationMemoryReservationRequest,
    GenerationRunnerCapability,
    GenerationResourceBudget,
    GenerationResourceBudgetError,
)


def _budget() -> GenerationResourceBudget:
    return GenerationResourceBudget(
        max_new_tokens_per_fragment=4,
        max_continuations=1,
        max_total_generated_tokens=8,
        max_total_output_bytes=64,
        max_effective_context_tokens=32,
        max_runtime_milliseconds=1_000,
        max_memory_bytes=1_024,
    )


def _worker_capability() -> GenerationRunnerCapability:
    return GenerationRunnerCapability(
        runner_id="runner-v1",
        max_effective_context_tokens=32,
        memory_admission_method="process_hard_limit",
        pre_packing_containment_method="process_hard_limit",
        supported_execution_devices=frozenset({"cpu"}),
        worker_protocol="generation-worker-v1",
        bootstrap_hard_limit_method="process_hard_limit",
        generation_hard_limit_method="process_hard_limit",
    )


def test_launch_descriptor_has_a_bounded_exact_non_executable_wire_mapping() -> None:
    descriptor = GenerationWorkerLaunchDescriptor(
        protocol_version="generation-worker-v1",
        invocation_digest="a" * 64,
        fragment_index=0,
        runner_id="runner-v1",
        capability_contract_digest="b" * 64,
        converter_id="converter-v1",
        converter_asset_digest="c" * 64,
        material_lock_digest="d" * 64,
        execution_descriptor_digest="e" * 64,
        execution_device="cpu",
        budget=_budget(),
        asset_handles=("asset-handle-1",),
    )

    encoded = descriptor.to_wire()

    assert GenerationWorkerLaunchDescriptor.from_wire(encoded) == descriptor
    assert set(encoded) == {
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
    for invalid in (
        {**encoded, "path": "/tmp/model"},
        {**encoded, "asset_handles": ("/tmp/model",)},
        {**encoded, "asset_handles": "asset-handle-1"},
        {**encoded, "asset_handles": (lambda: None,)},
        {**encoded, "unknown": "value"},
    ):
        with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
            GenerationWorkerLaunchDescriptor.from_wire(invalid)


def test_fixed_entry_resolves_every_opaque_asset_handle_before_ready() -> None:
    descriptor = GenerationWorkerLaunchDescriptor(
        "generation-worker-v1",
        "a" * 64,
        0,
        "runner-v1",
        "b" * 64,
        "converter-v1",
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "cpu",
        _budget(),
        ("asset-handle-1", "asset-handle-2"),
    )
    resolved: list[str] = []

    class Handles:
        def resolve(self, *, handle: str, descriptor: object, now: datetime) -> object:
            assert descriptor == descriptor_to_resolve
            assert now == datetime(2026, 1, 1, tzinfo=UTC)
            resolved.append(handle)
            return object()

    descriptor_to_resolve = descriptor
    assert (
        fixed_generation_worker_entry_point(
            descriptor.to_wire(),
            asset_handles=Handles(),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
        == descriptor
    )
    assert resolved == ["asset-handle-1", "asset-handle-2"]


def test_launcher_revalidates_a_factory_descriptor_before_controller_launch() -> None:
    worker_capability = _worker_capability()
    descriptor = GenerationWorkerLaunchDescriptor(
        protocol_version="generation-worker-v1",
        invocation_digest="a" * 64,
        fragment_index=0,
        runner_id="runner-v1",
        capability_contract_digest=worker_capability.contract_digest,
        converter_id="converter-v1",
        converter_asset_digest="c" * 64,
        material_lock_digest="d" * 64,
        execution_descriptor_digest="e" * 64,
        execution_device="cpu",
        budget=_budget(),
        asset_handles=("asset-handle-1",),
    )
    events: list[object] = []
    child = object()

    class Factory:
        runner_id = "runner-v1"
        capability = worker_capability

        def create_launch_descriptor(self) -> GenerationWorkerLaunchDescriptor:
            events.append("factory")
            return descriptor

    class Controller:
        runner_id = "runner-v1"
        supported_execution_devices = frozenset({"cpu"})

        def launch(self, received: GenerationWorkerLaunchDescriptor) -> object:
            events.append(received)
            return child

        def wait_ready(self, received: object, timeout: float) -> bool:
            events.append(("ready", received, timeout))
            return True

    assert (
        GenerationWorkerLauncher().launch(
            factory=Factory(),
            controller=Controller(),
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1_000),
            clock=lambda: 0.0,
        )
        is child
    )

    assert events == ["factory", descriptor, ("ready", child, 1.0)]


def test_launcher_rejects_an_untyped_factory_result_before_controller_launch() -> None:
    class Factory:
        def create_launch_descriptor(self) -> object:
            return {"path": "/tmp/model"}

    class Controller:
        def launch(self, _descriptor: object) -> object:
            pytest.fail("invalid descriptors must not launch")

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            pytest.fail("invalid descriptors must not wait")

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        GenerationWorkerLauncher().launch(
            factory=Factory(),
            controller=Controller(),
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1_000),
            clock=lambda: 0.0,
        )


def test_launcher_rejects_a_controller_that_cannot_enforce_the_selected_device() -> (
    None
):
    descriptor = GenerationWorkerLaunchDescriptor(
        "generation-worker-v1",
        "a" * 64,
        0,
        "runner-v1",
        "b" * 64,
        "converter-v1",
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "mps",
        _budget(),
        ("asset-handle-1",),
    )

    class Factory:
        runner_id = "runner-v1"

        def create_launch_descriptor(self) -> GenerationWorkerLaunchDescriptor:
            return descriptor

    class Controller:
        runner_id = "runner-v1"
        supported_execution_devices = frozenset({"cpu"})

        def launch(self, _descriptor: object) -> object:
            pytest.fail("an unmatched device must fail before launch")

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            pytest.fail("an unmatched device must not await readiness")

    with pytest.raises(GenerationResourceBudgetError, match="memory budget"):
        GenerationWorkerLauncher().launch(
            factory=Factory(),
            controller=Controller(),
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1_000),
            clock=lambda: 0.0,
        )


def test_launcher_rejects_a_factory_with_an_unbound_capability_contract() -> None:
    descriptor = GenerationWorkerLaunchDescriptor(
        "generation-worker-v1",
        "a" * 64,
        0,
        "runner-v1",
        "b" * 64,
        "converter-v1",
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "cpu",
        _budget(),
        ("asset-handle-1",),
    )

    class Factory:
        runner_id = "runner-v1"
        capability = _worker_capability()

        def create_launch_descriptor(self) -> GenerationWorkerLaunchDescriptor:
            return descriptor

    class Controller:
        runner_id = "runner-v1"
        supported_execution_devices = frozenset({"cpu"})

        def launch(self, _descriptor: object) -> object:
            pytest.fail("a mismatched capability must fail before launch")

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            pytest.fail("a mismatched capability must not await readiness")

    with pytest.raises(GenerationResourceBudgetError, match="memory budget"):
        GenerationWorkerLauncher().launch(
            factory=Factory(),
            controller=Controller(),
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1_000),
            clock=lambda: 0.0,
        )


def test_launcher_preserves_controller_memory_unavailability() -> None:
    descriptor = GenerationWorkerLaunchDescriptor(
        "generation-worker-v1",
        "a" * 64,
        0,
        "runner-v1",
        "b" * 64,
        "converter-v1",
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "cpu",
        _budget(),
        ("asset-handle-1",),
    )

    class Factory:
        runner_id = "runner-v1"

        def create_launch_descriptor(self) -> GenerationWorkerLaunchDescriptor:
            return descriptor

    class Controller:
        runner_id = "runner-v1"
        supported_execution_devices = frozenset({"cpu"})

        def launch(self, _descriptor: object) -> object:
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            )

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            pytest.fail("unavailable launch must not await readiness")

    with pytest.raises(GenerationResourceBudgetError, match="memory budget"):
        GenerationWorkerLauncher().launch(
            factory=Factory(),
            controller=Controller(),
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1_000),
            clock=lambda: 0.0,
        )


def test_launcher_reaps_a_child_when_readiness_fails() -> None:
    worker_capability = _worker_capability()
    descriptor = GenerationWorkerLaunchDescriptor(
        protocol_version="generation-worker-v1",
        invocation_digest="a" * 64,
        fragment_index=0,
        runner_id="runner-v1",
        capability_contract_digest=worker_capability.contract_digest,
        converter_id="converter-v1",
        converter_asset_digest="c" * 64,
        material_lock_digest="d" * 64,
        execution_descriptor_digest="e" * 64,
        execution_device="cpu",
        budget=_budget(),
        asset_handles=("asset-handle-1",),
    )
    events: list[str] = []
    child = object()

    class Factory:
        runner_id = "runner-v1"
        capability = worker_capability

        def create_launch_descriptor(self) -> GenerationWorkerLaunchDescriptor:
            return descriptor

    class Controller:
        runner_id = "runner-v1"
        supported_execution_devices = frozenset({"cpu"})

        def launch(self, _descriptor: object) -> object:
            events.append("launch")
            return child

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            events.append("wait_ready")
            return False

        def terminate(self, _child: object) -> None:
            events.append("terminate")

        def kill(self, _child: object) -> None:
            events.append("kill")

        def reap(self, _child: object, _timeout: float) -> bool:
            events.append("reap")
            return True

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        GenerationWorkerLauncher().launch(
            factory=Factory(),
            controller=Controller(),
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1_000),
            clock=lambda: 0.0,
        )

    assert events == ["launch", "wait_ready", "reap"]


def test_launcher_reaps_a_ready_child_when_its_deadline_expires() -> None:
    worker_capability = _worker_capability()
    descriptor = GenerationWorkerLaunchDescriptor(
        "generation-worker-v1",
        "a" * 64,
        0,
        "runner-v1",
        worker_capability.contract_digest,
        "converter-v1",
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "cpu",
        _budget(),
        ("asset-handle-1",),
    )
    events: list[str] = []
    child = object()

    class Factory:
        runner_id = "runner-v1"
        capability = worker_capability

        def create_launch_descriptor(self) -> GenerationWorkerLaunchDescriptor:
            return descriptor

    class Controller:
        runner_id = "runner-v1"
        supported_execution_devices = frozenset({"cpu"})

        def launch(self, _descriptor: object) -> object:
            events.append("launch")
            return child

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            events.append("wait_ready")
            return True

        def terminate(self, _child: object) -> None:
            events.append("terminate")

        def kill(self, _child: object) -> None:
            events.append("kill")

        def reap(self, _child: object, _timeout: float) -> bool:
            events.append("reap")
            return True

    ticks = iter((0.0, 0.0, 1.0, 1.0, 1.0))
    with pytest.raises(GenerationWorkerDeadlineExceeded, match="deadline exceeded"):
        GenerationWorkerLauncher().launch(
            factory=Factory(),
            controller=Controller(),
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1),
            clock=lambda: next(ticks),
        )
    assert events == ["launch", "wait_ready", "terminate", "reap"]


def test_launcher_terminates_and_confirms_reap_before_releasing_on_deadline() -> None:
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
            pytest.fail("controller lifecycle must own reap")

    class Controller:
        def terminate(self, _child: object) -> None:
            events.append("terminate")

        def kill(self, _child: object) -> None:
            events.append("kill")

        def reap(self, _child: object, _timeout: float) -> bool:
            events.append("reap")
            return True

    session = GenerationWorkerSession(
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
        session=session,
        fragment_index=0,
        max_memory_bytes=8,
        execution_device="cpu",
    )

    with pytest.raises(GenerationWorkerDeadlineExceeded, match="deadline exceeded"):
        launcher.generate(
            child=child,
            session=session,
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
            clock=lambda: 1.0,
            controller=Controller(),
        )

    assert events == [
        "limit",
        "pack",
        "reserve",
        "generate",
        "terminate",
        "reap",
        "release",
    ]


def test_launcher_keeps_its_reservation_when_reap_cannot_be_confirmed() -> None:
    events: list[str] = []

    class Reservation:
        def release(self) -> None:
            events.append("release")

    class Provider:
        def reserve(self, _request: object) -> Reservation:
            return Reservation()

    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            pass

        def pack(self) -> int:
            return 3

        def generate(self) -> tuple[bytes, int]:
            return b"{}", 1

        def reap(self) -> None:
            pytest.fail("controller lifecycle must own reap")

    class Controller:
        def terminate(self, _child: object) -> None:
            events.append("terminate")

        def kill(self, _child: object) -> None:
            events.append("kill")

        def reap(self, _child: object, _timeout: float) -> bool:
            events.append("reap")
            return False

    session = GenerationWorkerSession(
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
        session=session,
        fragment_index=0,
        max_memory_bytes=8,
        execution_device="cpu",
    )

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        launcher.generate(
            child=child,
            session=session,
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
            clock=lambda: 1.0,
            controller=Controller(),
        )

    assert events == ["terminate", "reap", "kill", "reap"]


def test_launcher_rejects_a_non_boolean_reap_confirmation() -> None:
    class Controller:
        def terminate(self, _child: object) -> None:
            pass

        def kill(self, _child: object) -> None:
            pass

        def reap(self, _child: object, _timeout: float) -> object:
            return "reaped"

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        GenerationWorkerLauncher()._close_with_controller(  # type: ignore[attr-defined]
            child=object(),
            controller=Controller(),
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1_000),
            clock=lambda: 0.0,
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


def test_launcher_reaps_a_packed_child_through_its_controller_on_protocol_failure() -> (
    None
):
    session = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=4,
        max_total_output_bytes=8,
    )
    receipt = session.pack(fragment_index=0, packed_context_tokens=3)
    events: list[str] = []

    class Child:
        def reap(self) -> None:
            events.append("child-reap")

    class Controller:
        def terminate(self, _child: object) -> None:
            events.append("terminate")

        def kill(self, _child: object) -> None:
            events.append("kill")

        def reap(self, _child: object, _timeout: float) -> bool:
            events.append("controller-reap")
            return True

    child = Child()
    launcher = GenerationWorkerLauncher()
    launcher._packed_receipts[id(child)] = receipt  # type: ignore[attr-defined]

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        launcher.generate(
            child=child,
            session=session,
            receipt=receipt,
            remaining_generated_tokens=4,
            provider=object(),
            request=GenerationMemoryReservationRequest(
                material_lock_digest="c" * 64,
                runner_identity="runner-v1",
                execution_device="cpu",
                packed_context_tokens=3,
                requested_new_tokens=4,
                max_memory_bytes=8,
                deadline_monotonic=1.0,
            ),
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1_000),
            clock=lambda: 0.0,
            controller=Controller(),
            now=0.0,
        )

    assert events == ["controller-reap"]


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
        worker.authorize(
            receipt=receipt,
            fragment_index=0,
            remaining_generated_tokens=4,
        )

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
        worker.result(
            receipt=receipt,
            fragment_index=0,
            candidate=b"{}",
            generated_tokens=1,
        )

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


def test_worker_recomputes_reported_aggregate_result_counters() -> None:
    worker = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=4,
        max_total_output_bytes=4,
    )
    receipt = worker.pack(fragment_index=0, packed_context_tokens=3)
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
            generated_tokens=2,
            reported_aggregate_generated_tokens=1,
            reported_aggregate_output_bytes=2,
        )

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        worker.result(
            receipt=receipt,
            fragment_index=0,
            candidate=b"{}",
            generated_tokens=2,
            reported_aggregate_generated_tokens=True,
            reported_aggregate_output_bytes=2,
        )

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        worker.result(
            receipt=receipt,
            fragment_index=0,
            candidate=b"{}",
            generated_tokens=2,
            reported_aggregate_generated_tokens=2,
            reported_aggregate_output_bytes=2,
        )


def test_worker_accepts_exact_reported_aggregate_result_counters() -> None:
    worker = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=4,
        max_total_output_bytes=4,
    )
    receipt = worker.pack(fragment_index=0, packed_context_tokens=3)
    worker.authorize(
        receipt=receipt,
        fragment_index=0,
        remaining_generated_tokens=2,
    )

    assert worker.result(
        receipt=receipt,
        fragment_index=0,
        candidate=b"{}",
        generated_tokens=2,
        reported_aggregate_generated_tokens=2,
        reported_aggregate_output_bytes=2,
    ) == GenerationWorkerResult(
        candidate=b"{}",
        generated_tokens=2,
        aggregate_generated_tokens=2,
        aggregate_output_bytes=2,
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


def test_launcher_reaps_a_packed_child_when_its_receipt_is_mismatched() -> None:
    events: list[str] = []

    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            events.append("limit")

        def pack(self) -> int:
            events.append("pack")
            return 3

        def generate(self) -> tuple[bytes, int]:
            pytest.fail("mismatched receipt must not dispatch")

        def reap(self) -> None:
            events.append("reap")

    session = GenerationWorkerSession(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_device="cpu",
        max_total_generated_tokens=4,
        max_total_output_bytes=8,
    )
    child = Child()
    launcher = GenerationWorkerLauncher()
    receipt = launcher.pack_receipt(
        child=child,
        session=session,
        fragment_index=0,
        max_memory_bytes=8,
        execution_device="cpu",
    )

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        launcher.generate(
            child=child,
            session=session,
            receipt=replace(receipt, packed_context_tokens=4),
            remaining_generated_tokens=1,
            provider=object(),
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

    assert events == ["limit", "pack", "reap"]


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


def test_launcher_preserves_unavailable_prepacking_containment() -> None:
    reaped: list[bool] = []

    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            )

        def pack(self) -> int:
            pytest.fail("packing must not start without containment")

        def reap(self) -> None:
            reaped.append(True)

    with pytest.raises(GenerationResourceBudgetError, match="memory budget"):
        GenerationWorkerLauncher().pack(
            child=Child(), max_memory_bytes=8, execution_device="cpu"
        )

    assert reaped == [True]


def test_launcher_uses_the_controller_to_clean_up_failed_packing() -> None:
    events: list[str] = []

    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            events.append("limit")
            raise GenerationResourceBudgetError(
                "generation memory budget is unavailable"
            )

        def pack(self) -> int:
            pytest.fail("packing must not proceed")

        def reap(self) -> None:
            pytest.fail("the controller owns cleanup")

    class Controller:
        def terminate(self, _child: object) -> None:
            events.append("terminate")

        def kill(self, _child: object) -> None:
            events.append("kill")

        def reap(self, _child: object, _timeout: float) -> bool:
            events.append("reap")
            return True

    with pytest.raises(GenerationResourceBudgetError, match="memory budget"):
        GenerationWorkerLauncher().pack(
            child=Child(),
            max_memory_bytes=8,
            execution_device="cpu",
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1_000),
            clock=lambda: 0.0,
            controller=Controller(),
        )

    assert events == ["limit", "reap"]


def test_launcher_deadline_covers_prepacking_containment_and_packing() -> None:
    events: list[str] = []

    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            events.append("limit")

        def pack(self) -> int:
            events.append("pack")
            return 3

        def reap(self) -> None:
            events.append("reap")

    ticks = iter((0.0, 0.001))
    with pytest.raises(GenerationWorkerDeadlineExceeded, match="deadline exceeded"):
        GenerationWorkerLauncher().pack(
            child=Child(),
            max_memory_bytes=8,
            execution_device="cpu",
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1),
            clock=lambda: next(ticks),
        )

    assert events == ["limit", "pack", "reap"]


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


def test_launcher_preserves_unavailable_memory_reservations() -> None:
    class Provider:
        def reserve(self, _request: object) -> None:
            return None

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

    with pytest.raises(GenerationResourceBudgetError, match="memory budget"):
        GenerationWorkerLauncher().authorize(
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


def test_launcher_reaps_a_packed_child_when_reservation_admission_fails() -> None:
    events: list[str] = []

    class Provider:
        def reserve(self, _request: object) -> None:
            events.append("reserve")
            return None

    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            events.append("limit")

        def pack(self) -> int:
            events.append("pack")
            return 3

        def generate(self) -> tuple[bytes, int]:
            pytest.fail("generation must not start without reservation")

        def reap(self) -> None:
            events.append("reap")

    session = GenerationWorkerSession(
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
        session=session,
        fragment_index=0,
        max_memory_bytes=8,
        execution_device="cpu",
    )

    with pytest.raises(GenerationResourceBudgetError, match="memory budget"):
        launcher.generate(
            child=child,
            session=session,
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
            deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1_000),
            now=0.0,
            clock=lambda: 0.0,
        )

    assert events == ["limit", "pack", "reserve", "reap"]


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
        clock=lambda: 0.0,
    )
    assert result == GenerationWorkerResult(
        candidate=b"{}",
        generated_tokens=1,
        aggregate_generated_tokens=1,
        aggregate_output_bytes=2,
    )
    assert events == ["limit", "pack", "reserve", "generate", "reap", "release"]


def test_launcher_discards_a_result_when_the_deadline_expires_during_generation() -> (
    None
):
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
    with pytest.raises(GenerationWorkerDeadlineExceeded, match="deadline exceeded"):
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
            now=0.0,
            clock=lambda: 0.001,
        )
    assert events == ["limit", "pack", "reserve", "generate", "reap", "release"]
