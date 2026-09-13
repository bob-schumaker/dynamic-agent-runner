"""Fake-only contract tests for model-generation resource budgets."""

from __future__ import annotations

from dataclasses import replace

import pytest

from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationBudgetDescriptorValidator,
    GenerationDeadline,
    GenerationExecutionHostPolicy,
    GenerationMemoryReservationRequest,
    GenerationResourceBudget,
    GenerationResourceBudgetCap,
    GenerationResourceBudgetError,
    GenerationRunnerCapability,
    parse_generation_resource_budget,
    parse_generation_resource_budget_cap,
    reserve_generation_memory,
    resolve_generation_resource_budget,
    validate_generation_budget_field,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptor,
    ExecutionDescriptorAbi,
    ExecutionDescriptorError,
)


def _budget(**changes: int) -> GenerationResourceBudget:
    return replace(
        GenerationResourceBudget(
            max_new_tokens_per_fragment=8,
            max_continuations=2,
            max_total_generated_tokens=20,
            max_total_output_bytes=128,
            max_effective_context_tokens=64,
            max_runtime_milliseconds=1_000,
            max_memory_bytes=1_024,
        ),
        **changes,
    )


def _runner_capability(**changes: object) -> GenerationRunnerCapability:
    values = {
        "runner_id": "runner-v1",
        "max_effective_context_tokens": 64,
        "memory_admission_method": "conservative_reservation",
        "pre_packing_containment_method": "runtime_allocation_limit",
        "supported_execution_devices": frozenset({"cpu", "mps"}),
        "cancellation_phases": frozenset({"load", "generate"}),
    }
    return GenerationRunnerCapability(
        **(values | changes),
    )


def test_parse_generation_budget_requires_exact_non_boolean_fields() -> None:
    value = {
        "max_new_tokens_per_fragment": 8,
        "max_continuations": 0,
        "max_total_generated_tokens": 20,
        "max_total_output_bytes": 128,
        "max_effective_context_tokens": 64,
        "max_runtime_milliseconds": 1_000,
        "max_memory_bytes": 1_024,
    }

    assert parse_generation_resource_budget(value) == _budget(max_continuations=0)

    for invalid in (
        {},
        {**value, "unexpected": 1},
        {**value, "max_tokens": 8},
        {**value, "max_new_tokens_per_fragment": True},
        {**value, "max_continuations": True},
        {**value, "max_total_output_bytes": 0},
        {**value, "max_continuations": -1},
    ):
        with pytest.raises(GenerationResourceBudgetError, match="invalid"):
            parse_generation_resource_budget(invalid)


def test_resolver_takes_the_fieldwise_minimum_from_every_source() -> None:
    resolved = resolve_generation_resource_budget(
        declared=_budget(),
        material_profile=GenerationResourceBudgetCap(max_total_generated_tokens=19),
        runner_capability=_runner_capability(max_effective_context_tokens=63),
        host=_budget(max_memory_bytes=1_023),
        sealed_artifact_cap=GenerationResourceBudgetCap(max_runtime_milliseconds=999),
        execution_device="cpu",
    )

    assert resolved == _budget(
        max_total_generated_tokens=19,
        max_effective_context_tokens=63,
        max_runtime_milliseconds=999,
        max_memory_bytes=1_023,
    )


def test_partial_material_cap_and_runner_capability_limit_only_their_fields() -> None:
    material_cap = parse_generation_resource_budget_cap(
        {"max_total_generated_tokens": 19}
    )
    runner = _runner_capability(max_effective_context_tokens=63)

    assert material_cap == GenerationResourceBudgetCap(max_total_generated_tokens=19)
    assert resolve_generation_resource_budget(
        declared=_budget(),
        material_profile=material_cap,
        runner_capability=runner,
        host=_budget(),
        execution_device="cpu",
    ) == _budget(max_total_generated_tokens=19, max_effective_context_tokens=63)

    for invalid in (
        {},
        {"max_total_generated_tokens": True},
        {"max_total_generated_tokens": 0},
        {"not_a_budget_field": 1},
    ):
        with pytest.raises(GenerationResourceBudgetError, match="invalid"):
            parse_generation_resource_budget_cap(invalid)


def test_resolver_rejects_missing_sources_and_uncovered_devices() -> None:
    for changes in (
        {"runner_capability": None},
        {"host": None},
        {"execution_device": None},
        {"execution_device": "cuda"},
        {
            "sealed_artifact_cap": GenerationResourceBudgetCap(
                max_total_output_bytes=127
            )
        },
    ):
        with pytest.raises(GenerationResourceBudgetError, match="unavailable"):
            resolve_generation_resource_budget(
                **(
                    {
                        "declared": _budget(),
                        "runner_capability": _runner_capability(),
                        "host": _budget(),
                        "execution_device": "cpu",
                    }
                    | changes
                )
            )


def test_runner_capability_requires_one_valid_lifecycle_form() -> None:
    common = {
        "runner_id": "runner-v1",
        "max_effective_context_tokens": 64,
        "memory_admission_method": "conservative_reservation",
        "pre_packing_containment_method": "runtime_allocation_limit",
        "supported_execution_devices": frozenset({"cpu"}),
    }

    with pytest.raises(GenerationResourceBudgetError, match="invalid"):
        GenerationRunnerCapability(**common, cancellation_phases=frozenset())
    with pytest.raises(GenerationResourceBudgetError, match="invalid"):
        GenerationRunnerCapability(
            **common,
            cancellation_phases=frozenset({"load", "generate"}),
            worker_protocol="generation-worker-v1",
            bootstrap_hard_limit_method="process_hard_limit",
            generation_hard_limit_method="process_hard_limit",
        )
    with pytest.raises(GenerationResourceBudgetError, match="invalid"):
        GenerationRunnerCapability(
            **common,
            worker_protocol="generation-worker-v1",
            bootstrap_hard_limit_method="process_hard_limit",
        )


def test_legacy_aliases_only_reduce_fragment_and_continuation_limits() -> None:
    resolved = resolve_generation_resource_budget(
        declared=_budget(),
        runner_capability=_runner_capability(),
        host=_budget(),
        execution_device="cpu",
        max_tokens=4,
        max_continuations=1,
    )

    assert resolved == _budget(max_new_tokens_per_fragment=4, max_continuations=1)

    with pytest.raises(GenerationResourceBudgetError, match="invalid"):
        resolve_generation_resource_budget(
            declared=_budget(),
            runner_capability=_runner_capability(),
            host=_budget(),
            execution_device="cpu",
            max_tokens=9,
        )
    with pytest.raises(GenerationResourceBudgetError, match="invalid"):
        resolve_generation_resource_budget(
            declared=_budget(),
            runner_capability=_runner_capability(),
            host=_budget(),
            execution_device="cpu",
            max_continuations=3,
        )


def test_generation_budget_field_is_bound_by_the_canonical_descriptor() -> None:
    abi = ExecutionDescriptorAbi("test-generation-v1", "1", "a" * 64)
    first = ExecutionDescriptor(
        abi,
        ("weights",),
        {"generation_budget": _budget().__dict__},
    )
    second = ExecutionDescriptor(
        abi,
        ("weights",),
        {"generation_budget": _budget(max_total_output_bytes=127).__dict__},
    )

    assert validate_generation_budget_field(first) == _budget()
    assert first.digest != second.digest

    with pytest.raises(GenerationResourceBudgetError, match="invalid"):
        validate_generation_budget_field(
            ExecutionDescriptor(abi, ("weights",), {"generation_budget": {}})
        )


def test_generation_budget_descriptor_validator_rejects_bad_budgets_preflight() -> None:
    abi = ExecutionDescriptorAbi("test-generation-v1", "1", "a" * 64)
    validator = GenerationBudgetDescriptorValidator(abi)

    validator.validate(
        ExecutionDescriptor(
            abi,
            ("weights",),
            {"generation_budget": _budget().__dict__},
        )
    )

    with pytest.raises(ExecutionDescriptorError, match="generation budget"):
        validator.validate(
            ExecutionDescriptor(
                abi,
                ("weights",),
                {"generation_budget": {"max_tokens": 1}},
            )
        )


def test_memory_reservation_receives_only_generation_admission_facts() -> None:
    received: list[GenerationMemoryReservationRequest] = []
    released: list[object] = []

    class Reservation:
        def release(self) -> None:
            released.append(self)

    class Provider:
        def reserve(self, request: GenerationMemoryReservationRequest) -> Reservation:
            received.append(request)
            return Reservation()

    reservation = reserve_generation_memory(
        Provider(),
        GenerationMemoryReservationRequest(
            material_lock_digest="a" * 64,
            runner_identity="transformers-generate-v1",
            execution_device="mps",
            packed_context_tokens=12,
            requested_new_tokens=4,
            max_memory_bytes=1_024,
            deadline_monotonic=10.0,
        ),
    )

    reservation.release()
    reservation.release()

    assert received[0].packed_context_tokens == 12
    assert released == [released[0]]


def test_memory_reservation_rejects_missing_or_malformed_providers() -> None:
    request = GenerationMemoryReservationRequest(
        material_lock_digest="a" * 64,
        runner_identity="runner",
        execution_device="cpu",
        packed_context_tokens=1,
        requested_new_tokens=1,
        max_memory_bytes=1,
        deadline_monotonic=1.0,
    )

    with pytest.raises(GenerationResourceBudgetError, match="memory budget"):
        reserve_generation_memory(None, request)
    with pytest.raises(GenerationResourceBudgetError, match="memory budget"):
        reserve_generation_memory(object(), request)


def test_memory_reservation_redacts_a_cleanup_failure_without_retrying() -> None:
    calls = 0

    class Reservation:
        def release(self) -> None:
            nonlocal calls
            calls += 1
            raise RuntimeError("private receiver failure")

    class Provider:
        def reserve(self, _request: object) -> Reservation:
            return Reservation()

    reservation = reserve_generation_memory(
        Provider(),
        GenerationMemoryReservationRequest(
            material_lock_digest="a" * 64,
            runner_identity="runner",
            execution_device="cpu",
            packed_context_tokens=1,
            requested_new_tokens=1,
            max_memory_bytes=1,
            deadline_monotonic=1.0,
        ),
    )

    with pytest.raises(GenerationResourceBudgetError, match="memory budget"):
        reservation.release()
    reservation.release()

    assert calls == 1


def test_memory_reservation_request_redacts_a_non_string_material_lock_identity() -> (
    None
):
    with pytest.raises(GenerationResourceBudgetError, match="memory budget"):
        GenerationMemoryReservationRequest(
            material_lock_digest=1,  # type: ignore[arg-type]
            runner_identity="runner",
            execution_device="cpu",
            packed_context_tokens=1,
            requested_new_tokens=1,
            max_memory_bytes=1,
            deadline_monotonic=1.0,
        )


def test_generation_execution_host_policy_requires_a_private_budget_and_provider() -> (
    None
):
    class Provider:
        def reserve(self, _request: object) -> object:
            return object()

    with pytest.raises(GenerationResourceBudgetError, match="unavailable"):
        GenerationExecutionHostPolicy(
            ceiling=_budget(), execution_device="mps", memory_reservation_provider=None
        )
    with pytest.raises(GenerationResourceBudgetError, match="invalid"):
        GenerationExecutionHostPolicy(
            ceiling=_budget(),
            execution_device="",
            memory_reservation_provider=Provider(),
        )


def test_deadline_rejects_before_backend_dispatch_after_expiry() -> None:
    deadline = GenerationDeadline.start(100.0, max_runtime_milliseconds=10)

    assert deadline.remaining_seconds(100.009) > 0
    with pytest.raises(GenerationResourceBudgetError, match="deadline exceeded"):
        deadline.require_remaining(100.01)
