"""Tests for client-supplied prepared local-model runners."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.workflow_host.host import _create_model_adapter
from dynamic_agent_runner.workflow_host.local_model_runners import (
    LocalModelRunnerCatalog,
)
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationRunnerCapability,
)
from dynamic_agent_runner.workflow_host.profiles import LocalModelProfile


def test_host_delegates_a_nonstandard_model_to_the_client_runner() -> None:
    profile = LocalModelProfile(
        profile_id="profile",
        model_id="nonstandard-model",
        execution_model_id="nonstandard-model",
        adapter_id="nonstandard-adapter-v1",
        base_url=None,
        profile_requirement="local-multimodal-model-v1",
        capabilities=frozenset({"text_generation", "multimodal_input"}),
        runner_id="client-nonstandard-v1",
        profile_digest="digest",
    )
    prepared_set = object()
    adapter = object()
    observed: list[tuple[LocalModelProfile, object]] = []

    class ClientRunner:
        runner_id = profile.runner_id
        generation_capability = GenerationRunnerCapability(
            runner_id=runner_id,
            max_effective_context_tokens=64,
            memory_admission_method="conservative_reservation",
            pre_packing_containment_method="runtime_allocation_limit",
            supported_execution_devices=frozenset({"cpu"}),
            cancellation_phases=frozenset({"load", "generate"}),
        )

        def create_adapter(self, received_profile, resolve_prepared_set):
            observed.append((received_profile, resolve_prepared_set()))
            return adapter

    assert (
        _create_model_adapter(
            profile,
            resolve_prepared_set=lambda: prepared_set,
            runners=LocalModelRunnerCatalog((ClientRunner(),)),
        )
        is adapter
    )
    assert observed == [(profile, prepared_set)]


def test_host_rejects_a_nonstandard_model_without_its_client_runner() -> None:
    profile = LocalModelProfile(
        profile_id="profile",
        model_id="nonstandard-model",
        execution_model_id="nonstandard-model",
        adapter_id="nonstandard-adapter-v1",
        base_url=None,
        profile_requirement="local-multimodal-model-v1",
        capabilities=frozenset({"text_generation", "multimodal_input"}),
        runner_id="client-nonstandard-v1",
        profile_digest="digest",
    )

    with pytest.raises(ModelExecutionError, match="unavailable"):
        _create_model_adapter(
            profile,
            resolve_prepared_set=object,
            runners=LocalModelRunnerCatalog(()),
        )


def test_host_routes_the_qwen_profile_through_the_builtin_runner() -> None:
    profile = LocalModelProfile(
        profile_id="profile",
        model_id="qwen25-vl-3b-floorplan-grpo",
        execution_model_id="qwen25-vl-3b-floorplan-grpo",
        adapter_id="qwen25-vl-3b-floorplan-grpo-transformers-peft-adapter-v1",
        base_url=None,
        profile_requirement="local-multimodal-model-v1",
        capabilities=frozenset({"text_generation", "multimodal_input"}),
        runner_id="transformers-peft-v1",
        profile_digest="digest",
    )

    adapter = _create_model_adapter(
        profile,
        resolve_prepared_set=lambda: pytest.fail("resolution must be lazy"),
        runners=LocalModelRunnerCatalog(()),
    )

    assert adapter.models == (profile.model_id,)
    assert adapter.execution_profile_adapter_id == profile.adapter_id


def test_client_cannot_register_a_dar_owned_runner_id() -> None:
    class ClientRunner:
        runner_id = "transformers-peft-v1"

        def create_adapter(self, profile, resolve_prepared_set):
            raise AssertionError("must not be called")

    with pytest.raises(ModelExecutionError, match="unavailable"):
        LocalModelRunnerCatalog((ClientRunner(),))


def test_client_runner_requires_an_exact_generation_capability() -> None:
    class ClientRunner:
        runner_id = "client-nonstandard-v1"

        def create_adapter(self, profile, resolve_prepared_set):
            raise AssertionError("must not be called")

    with pytest.raises(ModelExecutionError, match="unavailable"):
        LocalModelRunnerCatalog((ClientRunner(),))

    class MismatchedRunner(ClientRunner):
        generation_capability = GenerationRunnerCapability(
            runner_id="other-runner-v1",
            max_effective_context_tokens=64,
            memory_admission_method="conservative_reservation",
            pre_packing_containment_method="runtime_allocation_limit",
            supported_execution_devices=frozenset({"cpu"}),
            cancellation_phases=frozenset({"load", "generate"}),
        )

    with pytest.raises(ModelExecutionError, match="unavailable"):
        LocalModelRunnerCatalog((MismatchedRunner(),))
