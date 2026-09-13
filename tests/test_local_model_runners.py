"""Tests for client-supplied prepared local-model runners."""

from __future__ import annotations

import platform

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.workflow_host.host import (
    LocalWorkflowHostError,
    _dar_owned_generation_worker_pair,
    _create_model_adapter,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore
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


def test_host_binds_a_reviewed_worker_pair_to_the_builtin_runner() -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TRANSFORMERS_GENERATE_CAPABILITY,
    )

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

    class Factory:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        capability = TRANSFORMERS_GENERATE_CAPABILITY

        def create_for_invocation(self, **_kwargs: object) -> object:
            raise AssertionError("binding must not construct a worker")

    class Controller:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        supported_execution_devices = frozenset({"cpu", "mps"})

        def launch(self, _descriptor: object) -> object:
            raise AssertionError("binding must not launch a worker")

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            raise AssertionError("binding must not wait")

        def terminate(self, _child: object) -> None:
            raise AssertionError("binding must not terminate")

        def kill(self, _child: object) -> None:
            raise AssertionError("binding must not kill")

        def reap(self, _child: object, _timeout: float) -> bool:
            raise AssertionError("binding must not reap")

    adapter = _create_model_adapter(
        profile,
        resolve_prepared_set=lambda: pytest.fail("resolution must be lazy"),
        generation_worker_factory=Factory(),
        generation_worker_controller=Controller(),
    )

    assert adapter._generation_worker_factory is not None
    assert adapter._generation_worker_controller is not None


def test_host_rejects_a_partial_builtin_worker_pair() -> None:
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

    with pytest.raises(LocalWorkflowHostError, match="generation worker"):
        _create_model_adapter(
            profile,
            resolve_prepared_set=lambda: pytest.fail("resolution must be lazy"),
            generation_worker_factory=object(),
        )


def test_host_builds_a_cpu_gated_dar_owned_worker_pair(tmp_path, monkeypatch) -> None:
    from dynamic_agent_runner.workflow_host import generation_worker_controllers
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TRANSFORMERS_GENERATE_CAPABILITY,
    )

    original_factory = (
        generation_worker_controllers.machine_generation_worker_controllers
    )
    monkeypatch.setattr(
        generation_worker_controllers,
        "machine_generation_worker_controllers",
        lambda **kwargs: original_factory(**kwargs, platform_system=lambda: "Linux"),
    )

    factory, controller = _dar_owned_generation_worker_pair(
        store=PrivateStateStore(tmp_path), owner="test-owner"
    )

    assert factory.capability is TRANSFORMERS_GENERATE_CAPABILITY
    assert factory.runner_id == TRANSFORMERS_GENERATE_CAPABILITY.runner_id
    assert controller.runner_id == TRANSFORMERS_GENERATE_CAPABILITY.runner_id
    assert "cpu" in controller.supported_execution_devices


@pytest.mark.skipif(platform.system() != "Darwin", reason="requires Darwin MPS")
def test_host_builds_the_separate_dar_owned_mps_worker_pair(tmp_path) -> None:
    factory, controller = _dar_owned_generation_worker_pair(
        store=PrivateStateStore(tmp_path), owner="test-owner"
    )

    assert factory.runner_id == "transformers-generate-v1"
    assert controller.supported_execution_devices == frozenset({"mps"})


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


def test_worker_runner_requires_a_parent_invocation_factory_and_controller() -> None:
    worker_capability = GenerationRunnerCapability(
        runner_id="client-worker-v1",
        max_effective_context_tokens=64,
        memory_admission_method="process_hard_limit",
        pre_packing_containment_method="process_hard_limit",
        supported_execution_devices=frozenset({"cpu"}),
        worker_protocol="generation-worker-v1",
        bootstrap_hard_limit_method="process_hard_limit",
        generation_hard_limit_method="process_hard_limit",
    )

    class MissingWorkerBindings:
        runner_id = worker_capability.runner_id
        generation_capability = worker_capability

        def create_adapter(self, profile, resolve_prepared_set):
            raise AssertionError("must not be called")

    with pytest.raises(ModelExecutionError, match="unavailable"):
        LocalModelRunnerCatalog((MissingWorkerBindings(),))

    class Factory:
        runner_id = worker_capability.runner_id
        capability = worker_capability

        def create_launch_descriptor(self, **_kwargs):
            raise AssertionError("must not be called")

    class Controller:
        runner_id = worker_capability.runner_id
        supported_execution_devices = frozenset({"cpu"})

        def launch(self, _descriptor):
            raise AssertionError("must not be called")

        def wait_ready(self, _child, _timeout):
            raise AssertionError("must not be called")

        def terminate(self, _child):
            raise AssertionError("must not be called")

        def kill(self, _child):
            raise AssertionError("must not be called")

        def reap(self, _child, _timeout):
            raise AssertionError("must not be called")

    class WorkerRunner(MissingWorkerBindings):
        generation_worker_factory = Factory()
        generation_worker_controller = Controller()

    with pytest.raises(ModelExecutionError, match="unavailable"):
        LocalModelRunnerCatalog((WorkerRunner(),))


def test_worker_runner_accepts_an_exact_invocation_factory() -> None:
    worker_capability = GenerationRunnerCapability(
        runner_id="client-worker-v1",
        max_effective_context_tokens=64,
        memory_admission_method="process_hard_limit",
        pre_packing_containment_method="process_hard_limit",
        supported_execution_devices=frozenset({"cpu"}),
        worker_protocol="generation-worker-v1",
        bootstrap_hard_limit_method="process_hard_limit",
        generation_hard_limit_method="process_hard_limit",
    )

    class Factory:
        runner_id = worker_capability.runner_id
        capability = worker_capability

        def create_for_invocation(self, **_kwargs: object) -> object:
            raise AssertionError("binding must not construct a worker")

    class Controller:
        runner_id = worker_capability.runner_id
        supported_execution_devices = frozenset({"cpu"})

        def launch(self, _descriptor: object) -> object:
            raise AssertionError("binding must not launch a worker")

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            raise AssertionError("binding must not wait")

        def terminate(self, _child: object) -> None:
            raise AssertionError("binding must not terminate")

        def kill(self, _child: object) -> None:
            raise AssertionError("binding must not kill")

        def reap(self, _child: object, _timeout: float) -> bool:
            raise AssertionError("binding must not reap")

    class WorkerRunner:
        runner_id = worker_capability.runner_id
        generation_capability = worker_capability
        generation_worker_factory = Factory()
        generation_worker_controller = Controller()

        def create_adapter(self, _profile: object, _resolve: object) -> object:
            raise AssertionError("catalog construction must not create an adapter")

    assert LocalModelRunnerCatalog((WorkerRunner(),))


def test_cancellation_runner_cannot_bind_worker_components() -> None:
    worker_capability = GenerationRunnerCapability(
        runner_id="client-cancellable-v1",
        max_effective_context_tokens=64,
        memory_admission_method="runtime_allocation_limit",
        pre_packing_containment_method="runtime_allocation_limit",
        supported_execution_devices=frozenset({"cpu"}),
        cancellation_phases=frozenset({"load", "generate"}),
    )

    class CancellableRunner:
        runner_id = worker_capability.runner_id
        generation_capability = worker_capability
        generation_worker_factory = object()
        generation_worker_controller = object()

        def create_adapter(self, profile, resolve_prepared_set):
            raise AssertionError("must not be called")

    with pytest.raises(ModelExecutionError, match="unavailable"):
        LocalModelRunnerCatalog((CancellableRunner(),))


def test_worker_runner_binds_its_exact_factory_controller_and_capability() -> None:
    profile = LocalModelProfile(
        profile_id="profile",
        model_id="nonstandard-model",
        execution_model_id="nonstandard-model",
        adapter_id="nonstandard-adapter-v1",
        base_url=None,
        profile_requirement="local-multimodal-model-v1",
        capabilities=frozenset({"text_generation"}),
        runner_id="client-worker-v1",
        profile_digest="digest",
    )
    worker_capability = GenerationRunnerCapability(
        runner_id=profile.runner_id,
        max_effective_context_tokens=64,
        memory_admission_method="process_hard_limit",
        pre_packing_containment_method="process_hard_limit",
        supported_execution_devices=frozenset({"cpu"}),
        worker_protocol="generation-worker-v1",
        bootstrap_hard_limit_method="process_hard_limit",
        generation_hard_limit_method="process_hard_limit",
    )

    class Factory:
        runner_id = profile.runner_id
        capability = worker_capability

        def create_for_invocation(self, **_kwargs: object) -> object:
            raise AssertionError("binding must not construct a worker")

    class Controller:
        runner_id = profile.runner_id
        supported_execution_devices = frozenset({"cpu"})

        def launch(self, _descriptor: object) -> object:
            raise AssertionError("binding must not launch a worker")

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            return True

        def terminate(self, _child: object) -> None:
            pass

        def kill(self, _child: object) -> None:
            pass

        def reap(self, _child: object, _timeout: float) -> bool:
            return True

    bindings: list[object] = []

    class Adapter:
        def bind_generation_worker(self, **kwargs: object) -> None:
            bindings.append(kwargs)

    adapter = Adapter()

    class WorkerRunner:
        runner_id = profile.runner_id
        generation_capability = worker_capability
        generation_worker_factory = Factory()
        generation_worker_controller = Controller()

        def create_adapter(self, _profile: object, _resolve: object) -> object:
            return adapter

    catalog = LocalModelRunnerCatalog((WorkerRunner(),))

    assert catalog.create_adapter(profile, lambda: object()) is adapter
    assert bindings == [
        {
            "factory": WorkerRunner.generation_worker_factory,
            "controller": WorkerRunner.generation_worker_controller,
            "capability": worker_capability,
        }
    ]


def test_worker_runner_rejects_an_adapter_that_cannot_accept_its_binding() -> None:
    profile = LocalModelProfile(
        profile_id="profile",
        model_id="nonstandard-model",
        execution_model_id="nonstandard-model",
        adapter_id="nonstandard-adapter-v1",
        base_url=None,
        profile_requirement="local-multimodal-model-v1",
        capabilities=frozenset({"text_generation"}),
        runner_id="client-worker-v1",
        profile_digest="digest",
    )
    worker_capability = GenerationRunnerCapability(
        runner_id=profile.runner_id,
        max_effective_context_tokens=64,
        memory_admission_method="process_hard_limit",
        pre_packing_containment_method="process_hard_limit",
        supported_execution_devices=frozenset({"cpu"}),
        worker_protocol="generation-worker-v1",
        bootstrap_hard_limit_method="process_hard_limit",
        generation_hard_limit_method="process_hard_limit",
    )

    class Factory:
        runner_id = profile.runner_id
        capability = worker_capability

        def create_for_invocation(self, **_kwargs: object) -> object:
            raise AssertionError("binding must not construct a worker")

    class Controller:
        runner_id = profile.runner_id
        supported_execution_devices = frozenset({"cpu"})

        def launch(self, _descriptor: object) -> object:
            raise AssertionError("must not launch")

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            return True

        def terminate(self, _child: object) -> None:
            pass

        def kill(self, _child: object) -> None:
            pass

        def reap(self, _child: object, _timeout: float) -> bool:
            return True

    class WorkerRunner:
        runner_id = profile.runner_id
        generation_capability = worker_capability
        generation_worker_factory = Factory()
        generation_worker_controller = Controller()

        def create_adapter(self, _profile: object, _resolve: object) -> object:
            return object()

    catalog = LocalModelRunnerCatalog((WorkerRunner(),))

    with pytest.raises(ModelExecutionError, match="unavailable"):
        catalog.create_adapter(profile, lambda: object())
