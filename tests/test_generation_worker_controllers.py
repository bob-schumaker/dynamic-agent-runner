"""Platform-controller tests for bounded generation workers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationResourceBudget,
    GenerationResourceBudgetError,
)
from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerLaunchDescriptor,
    GenerationWorkerPackReceipt,
    GenerationWorkerProtocolError,
)
from dynamic_agent_runner.workflow_host.generation_worker_controllers import (
    CpuMultiprocessingGenerationWorkerController,
    GenerationWorkerControllerSet,
    MacMpsGenerationWorkerController,
    install_cpu_memory_limit,
    machine_generation_worker_controllers,
)
from dynamic_agent_runner.workflow_host.generation_worker_assets import (
    GenerationWorkerAssetHandleService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


class _CpuIpcRuntime:
    """Pickle-safe controlled child runtime used only by the transport test."""

    def install_bootstrap_limit(
        self, max_memory_bytes: int, execution_device: str
    ) -> None:
        if max_memory_bytes <= 0 or execution_device != "cpu":
            raise ValueError("invalid test runtime request")

    def pack(self) -> int:
        return 3

    def authorize(self, _receipt: object, remaining_generated_tokens: int) -> None:
        if remaining_generated_tokens != 2:
            raise ValueError("invalid test authorization")

    def generate(self) -> tuple[bytes, int]:
        return b"{}", 2


class _CpuOverAuthorizedRuntime(_CpuIpcRuntime):
    def generate(self) -> tuple[bytes, int]:
        return b"{}", 3


class _CpuInconsistentAggregateRuntime(_CpuIpcRuntime):
    def generate(self) -> tuple[bytes, int, int, int]:
        return b"{}", 2, 3, 1


def _descriptor(*, execution_device: str) -> GenerationWorkerLaunchDescriptor:
    return GenerationWorkerLaunchDescriptor(
        protocol_version="generation-worker-v1",
        invocation_digest="a" * 64,
        fragment_index=0,
        runner_id="runner-v1",
        capability_contract_digest="b" * 64,
        converter_id="converter-v1",
        converter_asset_digest="c" * 64,
        material_lock_digest="d" * 64,
        execution_descriptor_digest="e" * 64,
        execution_device=execution_device,
        budget=GenerationResourceBudget(
            max_new_tokens_per_fragment=4,
            max_continuations=1,
            max_total_generated_tokens=8,
            max_total_output_bytes=64,
            max_effective_context_tokens=32,
            max_runtime_milliseconds=1_000,
            max_memory_bytes=4_096,
        ),
        asset_handles=("asset-handle-1",),
    )


def test_cpu_resource_limit_caps_address_space_before_worker_entry() -> None:
    events: list[object] = []

    class Resource:
        RLIMIT_AS = 1
        RLIM_INFINITY = -1

        def getrlimit(self, limit: int) -> tuple[int, int]:
            events.append(("get", limit))
            return (8_192, 2_048)

        def setrlimit(self, limit: int, value: tuple[int, int]) -> None:
            events.append(("set", limit, value))

    install_cpu_memory_limit(4_096, resource_module=Resource())

    assert events == [("get", 1), ("set", 1, (2_048, 2_048))]


def test_cpu_entry_installs_the_cap_before_resolving_child_assets(monkeypatch) -> None:
    from dynamic_agent_runner.workflow_host import generation_worker_controllers

    descriptor = _descriptor(execution_device="cpu")
    events: list[str] = []

    class Connection:
        def send(self, _value: object) -> None:
            pass

        def recv(self) -> str:
            return "close"

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        generation_worker_controllers,
        "install_cpu_memory_limit",
        lambda _limit: events.append("limit"),
    )
    monkeypatch.setattr(
        generation_worker_controllers,
        "fixed_generation_worker_entry_point",
        lambda _wire, **_kwargs: events.append("entry") or descriptor,
    )

    generation_worker_controllers._cpu_worker_entry(
        Connection(),
        Connection(),
        Connection(),
        descriptor.to_wire(),
        object(),
        None,
    )

    assert events == ["limit", "entry"]


def test_cpu_controller_rejects_non_cpu_work_before_creating_a_process() -> None:
    class Context:
        def Process(self, *args: object, **kwargs: object) -> object:
            pytest.fail("MPS work must not enter the CPU process controller")

    controller = CpuMultiprocessingGenerationWorkerController(
        runner_id="runner-v1",
        process_context=Context(),
    )

    with pytest.raises(GenerationResourceBudgetError, match="unavailable"):
        controller.launch(_descriptor(execution_device="mps"))


def test_cpu_controller_starts_and_reaps_a_controlled_no_model_child() -> None:
    base_descriptor = _descriptor(execution_device="cpu")
    descriptor = replace(
        base_descriptor,
        budget=replace(base_descriptor.budget, max_memory_bytes=2**62),
    )
    controller = CpuMultiprocessingGenerationWorkerController(runner_id="runner-v1")
    child = controller.launch(descriptor)

    try:
        assert controller.wait_ready(child, 5.0) is True
    finally:
        assert controller.reap(child, 1.0) is True


def test_cpu_child_transports_pack_authorize_and_generate_frames() -> None:
    base_descriptor = _descriptor(execution_device="cpu")
    descriptor = replace(
        base_descriptor,
        budget=replace(base_descriptor.budget, max_memory_bytes=2**62),
    )
    controller = CpuMultiprocessingGenerationWorkerController(
        runner_id="runner-v1", worker_runtime=_CpuIpcRuntime()
    )
    child = controller.launch(descriptor)
    receipt = GenerationWorkerPackReceipt(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="c" * 64,
        material_lock_digest="d" * 64,
        execution_device="cpu",
        fragment_index=0,
        packed_context_tokens=3,
    )

    try:
        assert controller.wait_ready(child, 5.0) is True
        child.install_bootstrap_limit(2**62, "cpu")
        assert child.pack() == 3
        child.authorize(receipt, 2)
        assert child.generate() == (b"{}", 2)
    finally:
        assert controller.reap(child, 1.0) is True


def test_cpu_child_rejects_generation_before_authorization() -> None:
    base_descriptor = _descriptor(execution_device="cpu")
    descriptor = replace(
        base_descriptor,
        budget=replace(base_descriptor.budget, max_memory_bytes=2**62),
    )
    controller = CpuMultiprocessingGenerationWorkerController(
        runner_id="runner-v1", worker_runtime=_CpuIpcRuntime()
    )
    child = controller.launch(descriptor)

    try:
        assert controller.wait_ready(child, 5.0) is True
        with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
            child.generate()
    finally:
        assert controller.reap(child, 1.0) is True


def test_cpu_child_rejects_a_result_larger_than_its_authorization() -> None:
    base_descriptor = _descriptor(execution_device="cpu")
    descriptor = replace(
        base_descriptor,
        budget=replace(base_descriptor.budget, max_memory_bytes=2**62),
    )
    controller = CpuMultiprocessingGenerationWorkerController(
        runner_id="runner-v1", worker_runtime=_CpuOverAuthorizedRuntime()
    )
    child = controller.launch(descriptor)
    receipt = GenerationWorkerPackReceipt(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="c" * 64,
        material_lock_digest="d" * 64,
        execution_device="cpu",
        fragment_index=0,
        packed_context_tokens=3,
    )

    try:
        assert controller.wait_ready(child, 5.0) is True
        child.install_bootstrap_limit(2**62, "cpu")
        child.authorize(receipt, 2)
        with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
            child.generate()
    finally:
        assert controller.reap(child, 1.0) is True


def test_cpu_child_rejects_inconsistent_aggregate_result_scalars() -> None:
    base_descriptor = _descriptor(execution_device="cpu")
    descriptor = replace(
        base_descriptor,
        budget=replace(base_descriptor.budget, max_memory_bytes=2**62),
    )
    controller = CpuMultiprocessingGenerationWorkerController(
        runner_id="runner-v1", worker_runtime=_CpuInconsistentAggregateRuntime()
    )
    child = controller.launch(descriptor)
    receipt = GenerationWorkerPackReceipt(
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        converter_digest="c" * 64,
        material_lock_digest="d" * 64,
        execution_device="cpu",
        fragment_index=0,
        packed_context_tokens=3,
    )
    try:
        assert controller.wait_ready(child, 5.0) is True
        child.install_bootstrap_limit(2**62, "cpu")
        child.authorize(receipt, 2)
        with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
            child.generate()
    finally:
        assert controller.reap(child, 1.0) is True


def test_cpu_child_rejects_a_changed_configured_asset_before_readiness(
    tmp_path,
) -> None:
    asset = tmp_path / "converter.py"
    content = b"converter = object()\n"
    asset.write_bytes(content)
    now = datetime.now(UTC)
    service = GenerationWorkerAssetHandleService(
        store=PrivateStateStore(tmp_path / "state"), owner="test-owner"
    )
    base = replace(
        _descriptor(execution_device="cpu"),
        budget=replace(
            _descriptor(execution_device="cpu").budget, max_memory_bytes=2**62
        ),
    )
    handle = service.issue(
        descriptor=base,
        source_path=asset,
        expected_digest=sha256(content).hexdigest(),
        expires_at=now + timedelta(minutes=1),
        now=now,
    )
    descriptor = replace(base, asset_handles=(handle,))
    asset.write_bytes(b"changed")
    controller = CpuMultiprocessingGenerationWorkerController(
        runner_id="runner-v1", asset_handles=service
    )
    child = controller.launch(descriptor)
    try:
        assert controller.wait_ready(child, 5.0) is False
    finally:
        assert controller.reap(child, 1.0) is True


def test_mps_controller_requires_darwin_and_a_reviewed_memory_envelope() -> None:
    class Runtime:
        def install_memory_envelope(self, _budget: GenerationResourceBudget) -> bool:
            return True

        def launch(self, _descriptor: GenerationWorkerLaunchDescriptor) -> object:
            raise AssertionError("unavailable controller must not launch")

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            return True

        def terminate(self, _child: object) -> None:
            pass

        def kill(self, _child: object) -> None:
            pass

        def reap(self, _child: object, _timeout: float) -> bool:
            return True

    with pytest.raises(GenerationResourceBudgetError, match="unavailable"):
        MacMpsGenerationWorkerController(
            runner_id="runner-v1",
            metal_runtime=Runtime(),
            platform_system=lambda: "Linux",
        )


def test_mps_controller_installs_its_reviewed_envelope_before_launch() -> None:
    events: list[object] = []
    child = object()

    class Runtime:
        def install_memory_envelope(self, budget: GenerationResourceBudget) -> bool:
            events.append(("envelope", budget.max_memory_bytes))
            return True

        def launch(self, descriptor: GenerationWorkerLaunchDescriptor) -> object:
            events.append(("launch", descriptor.execution_device))
            return child

        def wait_ready(self, received: object, timeout: float) -> bool:
            events.append(("ready", received, timeout))
            return True

        def terminate(self, received: object) -> None:
            events.append(("terminate", received))

        def kill(self, received: object) -> None:
            events.append(("kill", received))

        def reap(self, received: object, timeout: float) -> bool:
            events.append(("reap", received, timeout))
            return True

    controller = MacMpsGenerationWorkerController(
        runner_id="runner-v1",
        metal_runtime=Runtime(),
        platform_system=lambda: "Darwin",
    )

    assert controller.launch(_descriptor(execution_device="mps")) is child
    assert controller.wait_ready(child, 0.5) is True
    controller.terminate(child)
    controller.kill(child)
    assert controller.reap(child, 0.25) is True
    assert events == [
        ("envelope", 4_096),
        ("launch", "mps"),
        ("ready", child, 0.5),
        ("terminate", child),
        ("kill", child),
        ("reap", child, 0.25),
    ]


def test_mps_controller_rejects_an_unenforceable_envelope_before_launch() -> None:
    class Runtime:
        def install_memory_envelope(self, _budget: GenerationResourceBudget) -> bool:
            return False

        def launch(self, _descriptor: GenerationWorkerLaunchDescriptor) -> object:
            pytest.fail("an unenforceable MPS budget must not launch")

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            return True

        def terminate(self, _child: object) -> None:
            pass

        def kill(self, _child: object) -> None:
            pass

        def reap(self, _child: object, _timeout: float) -> bool:
            return True

    controller = MacMpsGenerationWorkerController(
        runner_id="runner-v1",
        metal_runtime=Runtime(),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(GenerationResourceBudgetError, match="unavailable"):
        controller.launch(_descriptor(execution_device="mps"))


def test_mps_controller_rejects_cpu_work_before_installing_its_envelope() -> None:
    class Runtime:
        def install_memory_envelope(self, _budget: GenerationResourceBudget) -> bool:
            pytest.fail("CPU work must not enter the MPS controller")

        def launch(self, _descriptor: GenerationWorkerLaunchDescriptor) -> object:
            pytest.fail("CPU work must not launch through MPS")

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            return True

        def terminate(self, _child: object) -> None:
            pass

        def kill(self, _child: object) -> None:
            pass

        def reap(self, _child: object, _timeout: float) -> bool:
            return True

    controller = MacMpsGenerationWorkerController(
        runner_id="runner-v1",
        metal_runtime=Runtime(),
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(GenerationResourceBudgetError, match="unavailable"):
        controller.launch(_descriptor(execution_device="cpu"))


def test_controller_set_routes_only_to_the_controller_for_the_selected_device() -> None:
    events: list[object] = []

    class Controller:
        def __init__(self, device: str) -> None:
            self.runner_id = "runner-v1"
            self.supported_execution_devices = frozenset({device})
            self._device = device

        def launch(self, descriptor: GenerationWorkerLaunchDescriptor) -> object:
            events.append(("launch", self._device, descriptor.execution_device))
            return self._device

        def wait_ready(self, child: object, timeout: float) -> bool:
            events.append(("ready", self._device, child, timeout))
            return True

        def terminate(self, child: object) -> None:
            events.append(("terminate", self._device, child))

        def kill(self, child: object) -> None:
            events.append(("kill", self._device, child))

        def reap(self, child: object, timeout: float) -> bool:
            events.append(("reap", self._device, child, timeout))
            return True

    controller = GenerationWorkerControllerSet(
        runner_id="runner-v1",
        controllers={"cpu": Controller("cpu"), "mps": Controller("mps")},
    )
    child = controller.launch(_descriptor(execution_device="mps"))

    assert controller.wait_ready(child, 0.5) is True
    controller.terminate(child)
    controller.kill(child)
    assert controller.reap(child, 0.25) is True
    assert events == [
        ("launch", "mps", "mps"),
        ("ready", "mps", "mps", 0.5),
        ("terminate", "mps", "mps"),
        ("kill", "mps", "mps"),
        ("reap", "mps", "mps", 0.25),
    ]


def test_machine_controller_factory_exposes_mps_only_with_darwin_runtime_support() -> (
    None
):
    class Runtime:
        def install_memory_envelope(self, _budget: GenerationResourceBudget) -> bool:
            return True

        def launch(self, _descriptor: GenerationWorkerLaunchDescriptor) -> object:
            return object()

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            return True

        def terminate(self, _child: object) -> None:
            pass

        def kill(self, _child: object) -> None:
            pass

        def reap(self, _child: object, _timeout: float) -> bool:
            return True

    linux = machine_generation_worker_controllers(
        runner_id="runner-v1",
        metal_runtime=Runtime(),
        platform_system=lambda: "Linux",
    )
    darwin = machine_generation_worker_controllers(
        runner_id="runner-v1",
        metal_runtime=Runtime(),
        platform_system=lambda: "Darwin",
    )

    assert linux.supported_execution_devices == frozenset({"cpu"})
    assert darwin.supported_execution_devices == frozenset({"cpu", "mps"})
