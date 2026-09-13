"""Fake-only tests for the generic Transformers + PEFT single-image runner."""

from __future__ import annotations

import asyncio
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import sys
import time

import pytest

from dynamic_agent_runner.errors import ModelExecutionError

from dynamic_agent_runner.local_model_preparation import (
    LocalModelArtifact,
    LocalModelPreparationRecipe,
    PreparedArtifactSet,
    TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
)
from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request
from dynamic_agent_runner.workflow_host.descriptor import DeclaredInputConverter


class FakeImage:
    width = 1
    height = 1


def _test_transformers_recipe() -> LocalModelPreparationRecipe:
    base_roles = (
        "base_config",
        "base_generation_config",
        "base_chat_template",
        "base_weight_index",
        "base_weight_1",
        "base_weight_2",
        "processor_config",
        "processor_tokenizer",
        "processor_tokenizer_config",
        "processor_vocab",
        "processor_merges",
    )
    artifacts = tuple(
        LocalModelArtifact(
            role, "test/model", "0" * 40, f"{role}.bin", "0" * 64, "base"
        )
        for role in base_roles
    ) + tuple(
        LocalModelArtifact(
            role, "test/adapter", "1" * 40, f"{role}.bin", "1" * 64, "adapter"
        )
        for role in ("adapter_config", "adapter_weights")
    )
    return LocalModelPreparationRecipe(
        model_id="test-multimodal-model",
        adapter_id="test-transformers-peft-adapter",
        runner_id="transformers-peft-v1",
        artifacts=artifacts,
        transformation=None,
        loader_profile=TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
    )


def _generation_budget(**changes: int):
    from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
        GenerationResourceBudget,
    )

    values = {
        "max_new_tokens_per_fragment": 4,
        "max_continuations": 1,
        "max_total_generated_tokens": 8,
        "max_total_output_bytes": 64,
        "max_effective_context_tokens": 8,
        "max_runtime_milliseconds": 1_000,
        "max_memory_bytes": 1_024,
    }
    values.update(changes)
    return GenerationResourceBudget(**values)


def _generation_host_policy(budget: object):
    from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
        GenerationExecutionHostPolicy,
    )

    class Reservation:
        def release(self) -> None:
            pass

    class Provider:
        def reserve(self, _request: object) -> Reservation:
            return Reservation()

    return GenerationExecutionHostPolicy(
        ceiling=budget, execution_device="cpu", memory_reservation_provider=Provider()
    )


def _bound_packed_adapter(prepared_set, *, converter, runner, budget=None):
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        GeneratedText,
        TransformersPeftPackedInputAdapter,
    )

    if not callable(getattr(runner, "generate_chunk", None)):
        generate = runner.generate

        def generate_chunk(packed, *, max_new_tokens, json_mode=False, **_kwargs):
            kwargs = {"max_new_tokens": max_new_tokens}
            if getattr(runner, "supports_json_mode", False):
                kwargs["json_mode"] = json_mode
            return GeneratedText(
                generate(packed, **kwargs), exhausted=False, generated_tokens=1
            )

        runner.generate_chunk = generate_chunk
    runner.supports_generation_resource_budgets = True
    runner.supports_generation_deadline = True
    budget = budget or _generation_budget(max_continuations=0)
    return TransformersPeftPackedInputAdapter(
        prepared_set,
        converter=converter,
        runner=runner,
        generation_budget=budget,
        generation_material_lock_digest="a" * 64,
        generation_host_policy=_generation_host_policy(budget),
    )


QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE = _test_transformers_recipe()


def test_packed_runner_rejects_context_before_backend_dispatch(tmp_path: Path) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        PackedModelInput,
        TransformersGenerateRunner,
    )

    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE.artifacts
    }
    calls: list[object] = []

    class Backend:
        processor = object()

        def generate_packed(self, _inputs: object, **_kwargs: object) -> str:
            calls.append(_inputs)
            return "unreachable"

    runner = TransformersGenerateRunner(
        PreparedArtifactSet(
            QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE, paths
        ),
        dependency_loader=lambda _base, _adapter: Backend(),
    )
    packed = PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 5))})

    with pytest.raises(ModelExecutionError, match="context"):
        runner.generate_chunk(
            packed,
            max_new_tokens=4,
            budget=_generation_budget(max_effective_context_tokens=8),
        )

    assert calls == []
    assert packed.is_cleared


def test_packed_runner_loads_processor_without_loading_the_model_backend(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TransformersGenerateRunner,
    )

    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE.artifacts
    }
    processor = object()
    calls: list[str] = []

    runner = TransformersGenerateRunner(
        PreparedArtifactSet(
            QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE, paths
        ),
        dependency_loader=lambda _base, _adapter: (_ for _ in ()).throw(
            AssertionError("packing must not load the model backend")
        ),
        processor_loader=lambda _base: calls.append("processor") or processor,
    )

    assert runner.input_context.processor is processor
    assert calls == ["processor"]


def test_deferred_adapter_exposes_the_converter_payload_contract(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id=recipe.model_id,
        adapter_id=recipe.adapter_id,
        resolve_prepared_set=lambda: PreparedArtifactSet(recipe, paths),
    )

    assert adapter.input_converter_contract_id == "transformers-generate-v1"


def test_deferred_adapter_binds_only_a_valid_sealed_generation_budget(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.execution_descriptors import (
        ExecutionDescriptor,
        ExecutionDescriptorAbi,
    )
    from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
        GenerationExecutionHostPolicy,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id=recipe.model_id,
        adapter_id=recipe.adapter_id,
        resolve_prepared_set=lambda: PreparedArtifactSet(recipe, paths),
    )
    descriptor = ExecutionDescriptor(
        ExecutionDescriptorAbi("test-generation-v1", "1", "a" * 64),
        ("weights",),
        {"generation_budget": _generation_budget().__dict__},
    )

    class Provider:
        def reserve(self, _request: object) -> object:
            return object()

    host_policy = GenerationExecutionHostPolicy(
        ceiling=_generation_budget(),
        execution_device="mps",
        memory_reservation_provider=Provider(),
    )
    adapter.bind_generation_budget(
        descriptor=descriptor,
        material_lock_digest="b" * 64,
        host_policy=host_policy,
    )

    assert adapter._generation_budget == _generation_budget()
    assert adapter._generation_material_lock_digest == "b" * 64
    assert adapter._generation_host_policy is host_policy


def test_deferred_adapter_rejects_converter_payload_without_a_generation_budget(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id=recipe.model_id,
        adapter_id=recipe.adapter_id,
        resolve_prepared_set=lambda: PreparedArtifactSet(recipe, paths),
    )

    with pytest.raises(ModelExecutionError, match="generation budget"):
        adapter.bind_sealed_payload(content=b"sealed image")


def test_deferred_adapter_requires_a_manifest_bound_converter_package(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.execution_descriptors import (
        ExecutionDescriptor,
        ExecutionDescriptorAbi,
    )
    from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
        GenerationExecutionHostPolicy,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    asset = tmp_path / "converter.py"
    asset.write_text(
        "converter_contract_version = 'v1'\n"
        "compatible_runner_contract_id = 'transformers-generate-v1'\n"
        "class Converter:\n"
        "    def pack(self, *, prompt, payload, context):\n"
        "        return context.pack({})\n"
        "converter = Converter\n",
        encoding="utf-8",
    )
    converter = DeclaredInputConverter(
        converter_id="converter-v1",
        converter_contract_version="v1",
        compatible_runner_contract_id="transformers-generate-v1",
        entrypoint=asset.name,
        asset_digest=sha256(asset.read_bytes()).hexdigest(),
        max_input_bytes=1024,
        max_output_bytes=1024,
        timeout_seconds=1,
    )
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id=recipe.model_id,
        adapter_id=recipe.adapter_id,
        resolve_prepared_set=lambda: PreparedArtifactSet(recipe, paths),
    )

    class Reservation:
        def release(self) -> None:
            pass

    class Provider:
        def reserve(self, _request: object) -> Reservation:
            return Reservation()

    budget = _generation_budget()
    adapter.bind_generation_budget(
        descriptor=ExecutionDescriptor(
            ExecutionDescriptorAbi("test-generation-v1", "1", "a" * 64),
            ("weights",),
            {"generation_budget": budget.__dict__},
        ),
        material_lock_digest="b" * 64,
        host_policy=GenerationExecutionHostPolicy(budget, "cpu", Provider()),
    )

    with pytest.raises(ModelExecutionError, match="sealed converter input"):
        adapter.bind_sealed_payload(content=b"sealed image")

    adapter.bind_input_converter(package_root=tmp_path, converter=converter)
    adapter.bind_sealed_payload(content=b"sealed image")

    assert adapter._payload_bound is True
    adapter.clear_sealed_payload()


def test_deferred_adapter_rejects_a_child_descriptor_factory() -> None:
    from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
        GenerationRunnerCapability,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
        TRANSFORMERS_GENERATE_CAPABILITY,
    )

    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )

    class Factory:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        capability = TRANSFORMERS_GENERATE_CAPABILITY

        def create_launch_descriptor(self) -> object:
            return object()

    class Controller:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        supported_execution_devices = frozenset({"cpu", "mps"})

    with pytest.raises(ModelExecutionError, match="unavailable"):
        adapter.bind_generation_worker(
            factory=Factory(),
            controller=Controller(),
            capability=TRANSFORMERS_GENERATE_CAPABILITY,
        )

    with pytest.raises(ModelExecutionError, match="unavailable"):
        adapter.bind_generation_worker(
            factory=Factory(),
            controller=Controller(),
            capability=GenerationRunnerCapability(
                runner_id="wrong",
                max_effective_context_tokens=1,
                memory_admission_method="conservative_reservation",
                pre_packing_containment_method="runtime_allocation_limit",
                supported_execution_devices=frozenset({"cpu"}),
                cancellation_phases=frozenset({"load", "generate"}),
            ),
        )


def test_deferred_worker_adapter_defers_converter_loading_until_child_start(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
        TRANSFORMERS_GENERATE_CAPABILITY,
    )

    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )

    class Factory:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        capability = TRANSFORMERS_GENERATE_CAPABILITY

        def create_for_invocation(self, **_kwargs: object) -> object:
            return object()

    class Controller:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        supported_execution_devices = frozenset({"cpu", "mps"})

    adapter.bind_generation_worker(
        factory=Factory(),
        controller=Controller(),
        capability=TRANSFORMERS_GENERATE_CAPABILITY,
    )
    converter = DeclaredInputConverter(
        converter_id="converter-v1",
        converter_contract_version="1",
        compatible_runner_contract_id="transformers-generate-v1",
        entrypoint="converter.py",
        asset_digest="a" * 64,
        max_input_bytes=64,
        max_output_bytes=64,
        timeout_seconds=1,
    )

    adapter.bind_worker_converter_payload(
        package_root=tmp_path, converter=converter, content=b"sealed"
    )

    assert adapter._worker_converter_package_root == tmp_path
    assert adapter._worker_converter == converter
    assert adapter._worker_sealed_payload == b"sealed"


def test_deferred_adapter_accepts_an_exact_invocation_worker_factory() -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
        TRANSFORMERS_GENERATE_CAPABILITY,
    )

    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )

    class Factory:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        capability = TRANSFORMERS_GENERATE_CAPABILITY

        def create_for_invocation(self, **_kwargs: object) -> object:
            raise AssertionError("binding must not construct a worker")

    class Controller:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        supported_execution_devices = frozenset({"cpu", "mps"})

    adapter.bind_generation_worker(
        factory=Factory(),
        controller=Controller(),
        capability=TRANSFORMERS_GENERATE_CAPABILITY,
    )

    assert adapter._generation_worker_factory is not None


def test_deferred_adapter_accepts_a_controller_for_one_supported_device() -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
        TRANSFORMERS_GENERATE_CAPABILITY,
    )

    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )

    class Factory:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        capability = TRANSFORMERS_GENERATE_CAPABILITY

        def create_for_invocation(self, **_kwargs: object) -> object:
            raise AssertionError("binding must not construct a worker")

    class Controller:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        supported_execution_devices = frozenset({"cpu"})

    adapter.bind_generation_worker(
        factory=Factory(),
        controller=Controller(),
        capability=TRANSFORMERS_GENERATE_CAPABILITY,
    )

    assert adapter._generation_worker_controller is not None


def test_deferred_adapter_rejects_a_worker_controller_without_the_selected_device() -> (
    None
):
    from dynamic_agent_runner.workflow_host.execution_descriptors import (
        ExecutionDescriptor,
        ExecutionDescriptorAbi,
    )
    from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
        GenerationExecutionHostPolicy,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
        TRANSFORMERS_GENERATE_CAPABILITY,
    )

    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )

    class Factory:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        capability = TRANSFORMERS_GENERATE_CAPABILITY

        def create_for_invocation(self, **_kwargs: object) -> object:
            raise AssertionError("binding must not construct a worker")

    class Controller:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        supported_execution_devices = frozenset({"cpu"})

    adapter.bind_generation_worker(
        factory=Factory(),
        controller=Controller(),
        capability=TRANSFORMERS_GENERATE_CAPABILITY,
    )
    descriptor = ExecutionDescriptor(
        ExecutionDescriptorAbi("test-generation-v1", "1", "a" * 64),
        ("weights",),
        {"generation_budget": _generation_budget().__dict__},
    )

    class Provider:
        def reserve(self, _request: object) -> object:
            return object()

    with pytest.raises(ModelExecutionError, match="generation worker is unavailable"):
        adapter.bind_generation_budget(
            descriptor=descriptor,
            material_lock_digest="b" * 64,
            host_policy=GenerationExecutionHostPolicy(
                ceiling=_generation_budget(),
                execution_device="mps",
                memory_reservation_provider=Provider(),
            ),
        )

    assert adapter._generation_budget is None
    assert adapter._worker_sealed_payload is None


def test_deferred_worker_adapter_builds_an_invocation_factory_from_private_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dynamic_agent_runner.workflow_host.execution_descriptors import (
        ExecutionDescriptor,
        ExecutionDescriptorAbi,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
        TRANSFORMERS_GENERATE_CAPABILITY,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    prepared_set = PreparedArtifactSet(recipe, paths)
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id=recipe.model_id,
        adapter_id=recipe.adapter_id,
        resolve_prepared_set=lambda: prepared_set,
    )
    captured: dict[str, object] = {}
    invocation_ids: list[object] = []

    class Factory:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        capability = TRANSFORMERS_GENERATE_CAPABILITY

        def create_for_invocation(self, **kwargs: object) -> object:
            captured.update(kwargs)
            invocation_ids.append(kwargs["invocation_id"])
            return object()

    class Controller:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        supported_execution_devices = frozenset({"cpu", "mps"})

    adapter.bind_generation_worker(
        factory=Factory(),
        controller=Controller(),
        capability=TRANSFORMERS_GENERATE_CAPABILITY,
    )
    descriptor = ExecutionDescriptor(
        ExecutionDescriptorAbi("test-generation-v1", "1", "a" * 64),
        ("weights",),
        {"generation_budget": _generation_budget().__dict__},
    )
    adapter.bind_generation_budget(
        descriptor=descriptor,
        material_lock_digest="b" * 64,
        host_policy=_generation_host_policy(_generation_budget()),
    )
    converter = DeclaredInputConverter(
        converter_id="converter-v1",
        converter_contract_version="1",
        compatible_runner_contract_id="transformers-generate-v1",
        entrypoint="converter.py",
        asset_digest="c" * 64,
        max_input_bytes=64,
        max_output_bytes=64,
        timeout_seconds=1,
    )
    adapter.bind_worker_converter_payload(
        package_root=tmp_path, converter=converter, content=b"sealed"
    )
    request = build_openai_request(
        model=recipe.model_id,
        messages=[OpenAIMessage("user", "vectorize")],
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.transformers_peft_model.time.monotonic",
        lambda: 1.0,
    )

    factory = adapter._create_worker_invocation_factory(request)
    second_factory = adapter._create_worker_invocation_factory(request)

    assert factory is not None
    assert captured["prepared_set"] is prepared_set
    assert captured["converter"] is converter
    assert captured["package_root"] == tmp_path
    assert captured["sealed_payload"] == b"sealed"
    assert captured["sealed_payload_digest"] == sha256(b"sealed").hexdigest()
    assert captured["material_lock_digest"] == "b" * 64
    assert captured["execution_descriptor_digest"] == descriptor.digest
    assert captured["execution_device"] == "cpu"
    assert captured["budget"] == _generation_budget()
    assert captured["messages"] == request.messages
    assert factory is not second_factory
    assert invocation_ids[0] != invocation_ids[1]
    assert "packed_input" not in captured
    assert "converter_state" not in captured


def test_deferred_worker_adapter_runs_one_fragment_in_the_selected_worker(  # noqa: C901
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.execution_descriptors import (
        ExecutionDescriptor,
        ExecutionDescriptorAbi,
    )
    from dynamic_agent_runner.workflow_host.generation_worker import (
        GenerationWorkerLaunchDescriptor,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
        TRANSFORMERS_GENERATE_CAPABILITY,
    )

    budget = _generation_budget(max_continuations=0)
    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    prepared_set = PreparedArtifactSet(
        recipe,
        {
            artifact.role: tmp_path / artifact.group / artifact.filename
            for artifact in recipe.artifacts
        },
    )
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id=recipe.model_id,
        adapter_id=recipe.adapter_id,
        resolve_prepared_set=lambda: prepared_set,
    )
    events: list[str] = []

    class Child:
        def install_bootstrap_limit(
            self, max_memory_bytes: int, execution_device: str
        ) -> None:
            assert max_memory_bytes == budget.max_memory_bytes
            assert execution_device == "cpu"
            events.append("limit")

        def pack(self) -> int:
            events.append("pack")
            return 2

        def authorize(self, _receipt: object, remaining: int) -> None:
            assert remaining == budget.max_new_tokens_per_fragment
            events.append("authorize")

        def generate(self) -> tuple[bytes, int, int, int]:
            events.append("generate")
            candidate = b'{"walls":[]}'
            return candidate, 2, 2, len(candidate)

        def reap(self) -> None:
            events.append("child-reap")

    class InvocationFactory:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        capability = TRANSFORMERS_GENERATE_CAPABILITY

        def create_launch_descriptor(self) -> GenerationWorkerLaunchDescriptor:
            return GenerationWorkerLaunchDescriptor(
                protocol_version="generation-worker-v1",
                invocation_id="invocation-1",
                invocation_digest="d" * 64,
                fragment_index=0,
                runner_id=self.runner_id,
                capability_contract_digest=self.capability.contract_digest,
                converter_id="converter-v1",
                converter_asset_digest="c" * 64,
                material_lock_digest="b" * 64,
                execution_descriptor_digest="e" * 64,
                execution_device="cpu",
                budget=budget,
                asset_handles=("opaque-handle",),
            )

    class Factory:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        capability = TRANSFORMERS_GENERATE_CAPABILITY

        def create_for_invocation(self, **_kwargs: object) -> InvocationFactory:
            events.append("factory")
            return InvocationFactory()

    class Controller:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        supported_execution_devices = frozenset({"cpu", "mps"})

        def launch(self, descriptor: GenerationWorkerLaunchDescriptor) -> Child:
            assert isinstance(descriptor, GenerationWorkerLaunchDescriptor)
            events.append("launch")
            return Child()

        def wait_ready(self, _child: Child, _timeout: float) -> bool:
            events.append("ready")
            return True

        def terminate(self, _child: Child) -> None:
            events.append("terminate")

        def kill(self, _child: Child) -> None:
            events.append("kill")

        def reap(self, _child: Child, _timeout: float) -> bool:
            events.append("controller-reap")
            return True

    adapter.bind_generation_worker(
        factory=Factory(),
        controller=Controller(),
        capability=TRANSFORMERS_GENERATE_CAPABILITY,
    )
    descriptor = ExecutionDescriptor(
        ExecutionDescriptorAbi("test-generation-v1", "1", "a" * 64),
        ("weights",),
        {"generation_budget": budget.__dict__},
    )
    adapter.bind_generation_budget(
        descriptor=descriptor,
        material_lock_digest="b" * 64,
        host_policy=_generation_host_policy(budget),
    )
    adapter.bind_worker_converter_payload(
        package_root=tmp_path,
        converter=DeclaredInputConverter(
            converter_id="converter-v1",
            converter_contract_version="1",
            compatible_runner_contract_id="transformers-generate-v1",
            entrypoint="converter.py",
            asset_digest="c" * 64,
            max_input_bytes=64,
            max_output_bytes=64,
            timeout_seconds=1,
        ),
        content=b"sealed",
    )

    response = adapter.create_response(
        build_openai_request(
            model=recipe.model_id,
            messages=[OpenAIMessage("user", "vectorize")],
        )
    )

    assert response.content == '{"walls":[]}'
    assert response.metadata == {
        "generation": {
            "chunk_count": 1,
            "generated_tokens": 2,
            "output_bytes": len(b'{"walls":[]}'),
        }
    }
    assert events == [
        "factory",
        "launch",
        "ready",
        "limit",
        "pack",
        "authorize",
        "generate",
        "controller-reap",
    ]
    assert adapter._worker_sealed_payload is None


def test_deferred_worker_adapter_continues_with_parent_aggregate_accounting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.workflow_host.generation_worker import (
        GenerationWorkerResult,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
    )

    budget = _generation_budget(max_continuations=1)
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )
    adapter._payload_bound = True
    adapter._generation_worker_factory = object()
    adapter._generation_budget = budget
    adapter._generation_host_policy = _generation_host_policy(budget)
    factories: list[dict[str, object]] = []
    results = iter(
        (
            GenerationWorkerResult(b"first ", 2, 2, len(b"first "), True),
            GenerationWorkerResult(b"second", 2, 2, len(b"second"), False),
        )
    )

    def create_factory(
        _request: object, *, budget: object = None, **kwargs: object
    ) -> object:
        factories.append(kwargs)
        return object()

    monkeypatch.setattr(adapter, "_create_worker_invocation_factory", create_factory)
    monkeypatch.setattr(
        adapter, "_run_worker_fragment", lambda **_kwargs: next(results)
    )

    response = adapter.create_response(
        build_openai_request(
            model="model", messages=[OpenAIMessage("user", "vectorize")]
        )
    )

    assert response.content == "first second"
    assert response.metadata == {
        "generation": {
            "chunk_count": 2,
            "generated_tokens": 4,
            "output_bytes": len(b"first second"),
        }
    }
    assert [factory["fragment_index"] for factory in factories] == [0, 1]
    assert factories[1]["messages"] == (
        {"role": "user", "content": "vectorize"},
        {"role": "assistant", "content": "first "},
        {
            "role": "user",
            "content": "Continue the exact response from where it stopped. "
            "Return only the remaining text.",
        },
    )


def test_deferred_worker_adapter_packs_the_descriptor_fragment_index() -> None:
    from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
        GenerationDeadline,
    )
    from dynamic_agent_runner.workflow_host.generation_worker import (
        GenerationWorkerLaunchDescriptor,
        GenerationWorkerLauncher,
        GenerationWorkerSession,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
        TRANSFORMERS_GENERATE_CAPABILITY,
    )

    budget = _generation_budget()
    descriptor = GenerationWorkerLaunchDescriptor(
        protocol_version="generation-worker-v1",
        invocation_id="invocation-1",
        invocation_digest="a" * 64,
        fragment_index=1,
        runner_id=TRANSFORMERS_GENERATE_CAPABILITY.runner_id,
        capability_contract_digest=TRANSFORMERS_GENERATE_CAPABILITY.contract_digest,
        converter_id="converter-v1",
        converter_asset_digest="b" * 64,
        material_lock_digest="c" * 64,
        execution_descriptor_digest="d" * 64,
        execution_device="cpu",
        budget=budget,
        asset_handles=("opaque",),
    )
    session = GenerationWorkerSession(
        invocation_id=descriptor.invocation_id,
        invocation_digest=descriptor.invocation_digest,
        converter_digest=descriptor.converter_asset_digest,
        material_lock_digest=descriptor.material_lock_digest,
        execution_device=descriptor.execution_device,
        max_total_generated_tokens=budget.max_total_generated_tokens,
        max_total_output_bytes=budget.max_total_output_bytes,
        initial_fragment_index=descriptor.fragment_index,
    )
    events: list[str] = []

    class Child:
        def install_bootstrap_limit(self, _memory_bytes: int, _device: str) -> None:
            events.append("limit")

        def pack(self) -> int:
            events.append("pack")
            return 2

        def reap(self) -> None:
            events.append("reap")

    receipt = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )._worker_pack_receipt(
        launcher=GenerationWorkerLauncher(),
        child=Child(),
        controller=None,
        session=session,
        descriptor=descriptor,
        budget=budget,
        deadline=GenerationDeadline.start(
            time.monotonic(), max_runtime_milliseconds=1_000
        ),
        remaining_generated_tokens=budget.max_new_tokens_per_fragment,
    )

    assert receipt.fragment_index == 1
    assert events == ["limit", "pack"]


def test_deferred_worker_adapter_binds_each_child_to_remaining_output_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.workflow_host.generation_worker import (
        GenerationWorkerResult,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
    )

    budget = _generation_budget(max_continuations=1, max_total_output_bytes=10)
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )
    adapter._payload_bound = True
    adapter._generation_worker_factory = object()
    adapter._generation_budget = budget
    adapter._generation_host_policy = _generation_host_policy(budget)
    child_budgets: list[object] = []
    results = iter(
        (
            GenerationWorkerResult(b"first!", 2, 2, 6, True),
            GenerationWorkerResult(b"last", 2, 2, 4, False),
        )
    )

    def create_factory(
        _request: object, *, budget: object = None, **_kwargs: object
    ) -> object:
        child_budgets.append(budget)
        return object()

    monkeypatch.setattr(adapter, "_create_worker_invocation_factory", create_factory)
    monkeypatch.setattr(
        adapter, "_run_worker_fragment", lambda **_kwargs: next(results)
    )

    response = adapter.create_response(
        build_openai_request(model="model", messages=[OpenAIMessage("user", "go")])
    )

    assert response.content == "first!last"
    assert child_budgets == [
        budget,
        _generation_budget(max_continuations=1, max_total_output_bytes=4),
    ]


def test_deferred_worker_adapter_stops_before_binding_a_late_continuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
        GenerationResourceBudgetError,
    )
    from dynamic_agent_runner.workflow_host.generation_worker import (
        GenerationWorkerResult,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
    )

    budget = _generation_budget(max_continuations=1)
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )
    adapter._payload_bound = True
    adapter._generation_worker_factory = object()
    adapter._generation_budget = budget
    adapter._generation_host_policy = _generation_host_policy(budget)
    factories: list[object] = []

    class Deadline:
        expires_at = 1.0

        def __init__(self) -> None:
            self._checks = 0

        def require_remaining(self, _now: float) -> None:
            self._checks += 1
            if self._checks > 1:
                raise GenerationResourceBudgetError("generation deadline exceeded")

    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.transformers_peft_model.GenerationDeadline.start",
        lambda *_args, **_kwargs: Deadline(),
    )
    monkeypatch.setattr(
        adapter,
        "_create_worker_invocation_factory",
        lambda *_args, **_kwargs: factories.append(object()) or object(),
    )
    monkeypatch.setattr(
        adapter,
        "_run_worker_fragment",
        lambda **_kwargs: GenerationWorkerResult(b"first", 1, 1, 5, True),
    )

    with pytest.raises(ModelExecutionError, match="deadline exceeded"):
        adapter.create_response(
            build_openai_request(model="model", messages=[OpenAIMessage("user", "go")])
        )

    assert len(factories) == 1


def test_deferred_worker_adapter_shapes_worker_deadline_as_a_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.workflow_host.generation_worker import (
        GenerationWorkerDeadlineExceeded,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
    )

    budget = _generation_budget(max_continuations=0)
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )
    adapter._payload_bound = True
    adapter._generation_worker_factory = object()
    adapter._generation_budget = budget
    adapter._generation_host_policy = _generation_host_policy(budget)
    monkeypatch.setattr(
        adapter, "_create_worker_invocation_factory", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        adapter,
        "_run_worker_fragment",
        lambda **_kwargs: (_ for _ in ()).throw(
            GenerationWorkerDeadlineExceeded("generation deadline exceeded")
        ),
    )

    with pytest.raises(ModelExecutionError, match="model generation deadline exceeded"):
        adapter.create_response(
            build_openai_request(model="model", messages=[OpenAIMessage("user", "go")])
        )


def test_deferred_worker_adapter_shapes_an_oversized_child_result_as_output_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.workflow_host.generation_worker import (
        GenerationWorkerOutputLimitExceeded,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
    )

    budget = _generation_budget(max_continuations=0)
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )
    adapter._payload_bound = True
    adapter._generation_worker_factory = object()
    adapter._generation_budget = budget
    adapter._generation_host_policy = _generation_host_policy(budget)
    monkeypatch.setattr(
        adapter, "_create_worker_invocation_factory", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        adapter,
        "_run_worker_fragment",
        lambda **_kwargs: (_ for _ in ()).throw(
            GenerationWorkerOutputLimitExceeded("generation output limit exceeded")
        ),
    )

    with pytest.raises(
        ModelExecutionError, match="model generation output limit exceeded"
    ):
        adapter.create_response(
            build_openai_request(model="model", messages=[OpenAIMessage("user", "go")])
        )


def test_deferred_worker_adapter_preserves_memory_admission_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
        GenerationResourceBudgetError,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
    )

    budget = _generation_budget(max_continuations=0)
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )
    adapter._payload_bound = True
    adapter._generation_worker_factory = object()
    adapter._generation_budget = budget
    adapter._generation_host_policy = _generation_host_policy(budget)
    monkeypatch.setattr(
        adapter, "_create_worker_invocation_factory", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        adapter,
        "_run_worker_fragment",
        lambda **_kwargs: (_ for _ in ()).throw(
            GenerationResourceBudgetError("generation memory budget is unavailable")
        ),
    )

    with pytest.raises(
        ModelExecutionError, match="model generation memory budget is unavailable"
    ):
        adapter.create_response(
            build_openai_request(model="model", messages=[OpenAIMessage("user", "go")])
        )


def test_transformers_worker_runtime_keeps_converter_and_packed_input_in_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.generation_worker import (
        GenerationWorkerPackReceipt,
    )
    from dynamic_agent_runner.workflow_host.generation_worker_assets import (
        GenerationWorkerCoLocatedAssets,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        GeneratedText,
        PackedModelInput,
        TransformersPeftGenerationWorkerRuntimeFactory,
    )

    packed = PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 3))})
    events: list[str] = []

    class Converter:
        def pack(self, **kwargs: object) -> PackedModelInput:
            assert kwargs["messages"] == ({"role": "user", "content": "go"},)
            assert kwargs["payload"] == b"sealed"
            events.append("pack")
            return packed

    class Runner:
        input_context = object()

        def __init__(self, _prepared_set: object, **kwargs: object) -> None:
            assert callable(kwargs["processor_loader"])
            events.append("runner")

        def generate_chunk(
            self, received: PackedModelInput, *, max_new_tokens: int, json_mode: bool
        ) -> GeneratedText:
            assert received is packed
            assert max_new_tokens == 4
            assert json_mode is True
            events.append("generate")
            return GeneratedText(
                '{"message":"answer"}', exhausted=True, generated_tokens=2
            )

    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.transformers_peft_model.TransformersGenerateRunner",
        Runner,
    )
    assets = GenerationWorkerCoLocatedAssets(
        package_root=tmp_path,
        converter=DeclaredInputConverter(
            converter_id="converter-v1",
            converter_contract_version="1",
            compatible_runner_contract_id="transformers-generate-v1",
            entrypoint="converter.py",
            asset_digest="a" * 64,
            max_input_bytes=64,
            max_output_bytes=64,
            timeout_seconds=1,
        ),
        prepared_set=SimpleNamespace(),
        messages=({"role": "user", "content": "go"},),
        sealed_payload=b"sealed",
        json_mode=True,
    )
    runtime = TransformersPeftGenerationWorkerRuntimeFactory().create_runtime(
        assets=assets, converter=Converter()
    )

    runtime.install_bootstrap_limit(1_024, "cpu")
    assert runtime.pack() == 3
    runtime.authorize(
        GenerationWorkerPackReceipt(
            invocation_id="invocation",
            invocation_digest="a" * 64,
            converter_digest="a" * 64,
            material_lock_digest="b" * 64,
            execution_device="cpu",
            fragment_index=0,
            packed_context_tokens=3,
        ),
        4,
    )

    assert runtime.generate() == (
        b'{"message":"answer"}',
        2,
        2,
        len(b'{"message":"answer"}'),
        True,
    )
    assert packed.is_cleared is True
    assert events == ["runner", "pack", "generate"]


def test_deferred_worker_adapter_records_only_verified_fragment_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.workflow_host.generation_worker import (
        GenerationWorkerResult,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
        GenerationDebugFragment,
    )

    budget = _generation_budget(max_continuations=0)
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )
    adapter._payload_bound = True
    adapter._generation_worker_factory = object()
    adapter._generation_budget = budget
    adapter._generation_host_policy = _generation_host_policy(budget)
    facts: list[GenerationDebugFragment] = []
    adapter.set_debug_fragment_recorder(facts.append)
    monkeypatch.setattr(
        adapter, "_create_worker_invocation_factory", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        adapter,
        "_run_worker_fragment",
        lambda **_kwargs: GenerationWorkerResult(
            b"ok", 1, 1, 2, False, packed_context_tokens=3
        ),
    )

    response = adapter.create_response(
        build_openai_request(model="model", messages=[OpenAIMessage("user", "go")])
    )

    assert response.content == "ok"
    assert len(facts) == 1
    assert facts[0].fragment_index == 0
    assert facts[0].exhausted is False
    assert facts[0].generated_tokens == 1
    assert facts[0].output_bytes == 2
    assert facts[0].packed_context_tokens == 3
    assert facts[0].stop_classification == "completed"
    assert isinstance(facts[0].elapsed_milliseconds, int)
    assert facts[0].elapsed_milliseconds >= 0


def test_deferred_worker_adapter_rejects_a_factory_budget_broader_than_effective() -> (
    None
):
    from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
        GenerationDeadline,
    )
    from dynamic_agent_runner.workflow_host.generation_worker import (
        GenerationWorkerLaunchDescriptor,
        GenerationWorkerProtocolError,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        DeferredTransformersPeftSingleImageAdapter,
        TRANSFORMERS_GENERATE_CAPABILITY,
    )

    effective_budget = _generation_budget(max_new_tokens_per_fragment=2)
    adapter = DeferredTransformersPeftSingleImageAdapter(
        model_id="model", adapter_id="adapter", resolve_prepared_set=lambda: object()
    )
    launched: list[object] = []

    class Factory:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        capability = TRANSFORMERS_GENERATE_CAPABILITY

        def create_launch_descriptor(self) -> GenerationWorkerLaunchDescriptor:
            return GenerationWorkerLaunchDescriptor(
                protocol_version="generation-worker-v1",
                invocation_id="invocation-1",
                invocation_digest="a" * 64,
                fragment_index=0,
                runner_id=self.runner_id,
                capability_contract_digest=self.capability.contract_digest,
                converter_id="converter-v1",
                converter_asset_digest="b" * 64,
                material_lock_digest="c" * 64,
                execution_descriptor_digest="d" * 64,
                execution_device="cpu",
                budget=_generation_budget(),
                asset_handles=("opaque",),
            )

    class Controller:
        runner_id = TRANSFORMERS_GENERATE_CAPABILITY.runner_id
        supported_execution_devices = frozenset({"cpu", "mps"})

        def launch(self, _descriptor: object) -> object:
            launched.append(object())
            raise AssertionError("a broader worker descriptor must not launch")

        def wait_ready(self, _child: object, _timeout: float) -> bool:
            return True

    with pytest.raises(GenerationWorkerProtocolError, match="protocol invalid"):
        adapter._run_worker_fragment(
            factory=Factory(),
            controller=Controller(),
            budget=effective_budget,
            deadline=GenerationDeadline.start(
                time.monotonic(),
                max_runtime_milliseconds=effective_budget.max_runtime_milliseconds,
            ),
            host_policy=_generation_host_policy(effective_budget),
            remaining_generated_tokens=effective_budget.max_total_generated_tokens,
        )

    assert launched == []


def test_converter_adapter_runs_one_packed_generation_and_clears_payload(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        PackedModelInput,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    calls: dict[str, object] = {}

    class Runner:
        input_context = object()

        def generate(self, packed: PackedModelInput, *, max_new_tokens: int) -> str:
            calls["packed"] = packed
            calls["max_new_tokens"] = max_new_tokens
            return "generated floorplan"

    class Converter:
        def pack(
            self, *, messages: tuple[object, ...], payload: bytes, context: object
        ) -> PackedModelInput:
            calls["converter"] = (messages, payload, context)
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = _bound_packed_adapter(
        PreparedArtifactSet(recipe, paths), converter=Converter(), runner=Runner()
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    response = adapter.create_response(
        build_openai_request(
            model=recipe.model_id,
            messages=[
                OpenAIMessage("system", "Return only SVG."),
                OpenAIMessage("user", "vectorize"),
            ],
            max_tokens=12,
        )
    )

    assert adapter.input_converter_contract_id == "transformers-generate-v1"
    assert response.content == "generated floorplan"
    assert calls["converter"] == (
        (
            {"role": "system", "content": "Return only SVG."},
            {"role": "user", "content": "vectorize"},
        ),
        b"sealed image",
        Runner.input_context,
    )
    assert calls["max_new_tokens"] == 4
    assert adapter._sealed_payload is None


def test_converter_adapter_rejects_unbound_generation_budget_before_packing(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        PackedModelInput,
        TransformersPeftPackedInputAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }

    class Runner:
        input_context = object()

        def generate(self, **_kwargs: object) -> str:
            pytest.fail("unbound generation must not reach the runner")

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            pytest.fail("unbound generation must not pack sealed input")

    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths), converter=Converter(), runner=Runner()
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    with pytest.raises(ModelExecutionError, match="generation budget"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
            )
        )


def test_converter_adapter_passes_json_mode_to_a_capable_runner(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        PackedModelInput,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    calls: dict[str, object] = {}

    class Runner:
        input_context = object()
        supports_json_mode = True

        def generate(
            self,
            packed: PackedModelInput,
            *,
            max_new_tokens: int,
            json_mode: bool,
        ) -> str:
            calls["packed"] = packed
            calls["max_new_tokens"] = max_new_tokens
            calls["json_mode"] = json_mode
            return "{}"

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = _bound_packed_adapter(
        PreparedArtifactSet(recipe, paths), converter=Converter(), runner=Runner()
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    response = adapter.create_response(
        build_openai_request(
            model=recipe.model_id,
            messages=[OpenAIMessage("user", "vectorize")],
            response_format={"type": "json_object"},
            max_tokens=12,
        )
    )

    assert adapter.capabilities["json_mode"] is True
    assert response.content == "{}"
    assert calls["max_new_tokens"] == 4
    assert calls["json_mode"] is True
    assert adapter._sealed_payload is None


def test_converter_adapter_assembles_bounded_json_continuations(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        GeneratedText,
        PackedModelInput,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    calls: list[tuple[tuple[object, ...], bytes]] = []
    json_modes: list[bool] = []
    chunks = iter(
        (
            GeneratedText('{"walls":', exhausted=True, generated_tokens=4),
            GeneratedText("[]}", exhausted=False, generated_tokens=2),
        )
    )

    class Runner:
        input_context = object()
        supports_json_mode = True

        def generate_chunk(
            self,
            _packed: PackedModelInput,
            *,
            max_new_tokens: int,
            json_mode: bool,
            **_kwargs: object,
        ) -> GeneratedText:
            assert max_new_tokens == 4
            json_modes.append(json_mode)
            return next(chunks)

    class Converter:
        def pack(
            self, *, messages: tuple[object, ...], payload: bytes, context: object
        ) -> PackedModelInput:
            assert context is Runner.input_context
            calls.append((messages, payload))
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = _bound_packed_adapter(
        PreparedArtifactSet(recipe, paths),
        converter=Converter(),
        runner=Runner(),
        budget=_generation_budget(max_continuations=1),
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    response = adapter.create_response(
        build_openai_request(
            model=recipe.model_id,
            messages=[OpenAIMessage("user", "vectorize")],
            response_format={"type": "json_object"},
            max_tokens=4,
            max_continuations=1,
        )
    )

    assert response.content == '{"walls":[]}'
    assert json_modes == [True, False]
    assert calls == [
        (({"role": "user", "content": "vectorize"},), b"sealed image"),
        (
            (
                {"role": "user", "content": "vectorize"},
                {"role": "assistant", "content": '{"walls":'},
                {
                    "role": "user",
                    "content": "Continue the exact response from where it stopped. "
                    "Return only the remaining text.",
                },
            ),
            b"sealed image",
        ),
    ]
    assert adapter._sealed_payload is None


def test_converter_adapter_discards_an_oversized_budgeted_completion(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        GeneratedText,
        PackedModelInput,
        TransformersPeftPackedInputAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }

    class Runner:
        input_context = object()
        supports_json_mode = True
        supports_generation_resource_budgets = True
        supports_generation_deadline = True

        def generate_chunk(
            self, _packed: PackedModelInput, **_kwargs: object
        ) -> GeneratedText:
            return GeneratedText("oversized", exhausted=False, generated_tokens=1)

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths),
        converter=Converter(),
        runner=Runner(),
        generation_budget=_generation_budget(max_total_output_bytes=3),
        generation_material_lock_digest="a" * 64,
        generation_host_policy=_generation_host_policy(
            _generation_budget(max_total_output_bytes=3)
        ),
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    with pytest.raises(ModelExecutionError, match="output"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
            )
        )

    assert adapter._sealed_payload is None


def test_budgeted_converter_adapter_rejects_a_noninterruptible_runner(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        PackedModelInput,
        TransformersPeftPackedInputAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.filename for artifact in recipe.artifacts
    }

    class Runner:
        input_context = object()
        supports_json_mode = True
        supports_generation_resource_budgets = True

        def generate_chunk(
            self, _packed: PackedModelInput, **_kwargs: object
        ) -> object:
            raise AssertionError("backend must not run")

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths),
        converter=Converter(),
        runner=Runner(),
        generation_budget=_generation_budget(),
        generation_material_lock_digest="a" * 64,
        generation_host_policy=_generation_host_policy(_generation_budget()),
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    with pytest.raises(ModelExecutionError, match="deadline"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id, messages=[OpenAIMessage("user", "go")]
            )
        )


def test_budgeted_converter_adapter_rejects_an_expired_deadline_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dynamic_agent_runner.workflow_host.transformers_peft_model as module
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        PackedModelInput,
        TransformersPeftPackedInputAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.filename for artifact in recipe.artifacts
    }
    calls: list[object] = []

    class Runner:
        input_context = object()
        supports_json_mode = True
        supports_generation_resource_budgets = True
        supports_generation_deadline = True

        def generate_chunk(
            self, _packed: PackedModelInput, **_kwargs: object
        ) -> object:
            calls.append(_packed)
            raise AssertionError("expired generation must not dispatch")

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    budget = _generation_budget(max_runtime_milliseconds=1)
    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths),
        converter=Converter(),
        runner=Runner(),
        generation_budget=budget,
        generation_material_lock_digest="a" * 64,
        generation_host_policy=_generation_host_policy(budget),
    )
    monkeypatch.setattr(module.time, "monotonic", iter((1.0, 1.001)).__next__)
    adapter.bind_sealed_payload(content=b"sealed image")

    with pytest.raises(ModelExecutionError, match="deadline exceeded"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id, messages=[OpenAIMessage("user", "go")]
            )
        )

    assert calls == []


def test_converter_adapter_stops_at_the_remaining_aggregate_token_budget(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        GeneratedText,
        PackedModelInput,
        TransformersPeftPackedInputAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    requested: list[int] = []
    chunks = iter(
        (
            GeneratedText("first", exhausted=True, generated_tokens=4),
            GeneratedText("second", exhausted=False, generated_tokens=2),
        )
    )

    class Runner:
        input_context = object()
        supports_json_mode = True
        supports_generation_resource_budgets = True
        supports_generation_deadline = True

        def generate_chunk(
            self, _packed: PackedModelInput, **kwargs: object
        ) -> GeneratedText:
            requested.append(kwargs["max_new_tokens"])
            return next(chunks)

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths),
        converter=Converter(),
        runner=Runner(),
        generation_budget=_generation_budget(max_total_generated_tokens=5),
        generation_material_lock_digest="a" * 64,
        generation_host_policy=_generation_host_policy(
            _generation_budget(max_total_generated_tokens=5)
        ),
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    with pytest.raises(ModelExecutionError, match="token budget"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
            )
        )

    assert requested == [4, 1]
    assert adapter._sealed_payload is None


def test_converter_adapter_rejects_over_context_continuation_before_dispatch(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        GeneratedText,
        PackedModelInput,
        TransformersPeftPackedInputAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    calls = 0
    packed: list[PackedModelInput] = []

    class Runner:
        input_context = object()
        supports_json_mode = True
        supports_generation_resource_budgets = True
        supports_generation_deadline = True

        def generate_chunk(
            self, _packed: PackedModelInput, **_kwargs: object
        ) -> GeneratedText:
            nonlocal calls
            calls += 1
            return GeneratedText("first", exhausted=True, generated_tokens=1)

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            item = PackedModelInput(
                {"input_ids": SimpleNamespace(shape=(1, 2 if not packed else 5))}
            )
            packed.append(item)
            return item

    budget = _generation_budget(max_continuations=2, max_effective_context_tokens=8)
    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths),
        converter=Converter(),
        runner=Runner(),
        generation_budget=budget,
        generation_material_lock_digest="a" * 64,
        generation_host_policy=_generation_host_policy(budget),
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    with pytest.raises(ModelExecutionError, match="context"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
                max_tokens=4,
            )
        )

    assert calls == 1
    assert packed[1].is_cleared
    assert adapter._sealed_payload is None


def test_converter_adapter_emits_redacted_mps_metadata_for_direct_response(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        GeneratedText,
        PackedModelInput,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }

    class Runner:
        input_context = object()
        supports_json_mode = True
        uses_mps = True

        def generate_chunk(
            self, _packed: PackedModelInput, **_kwargs: object
        ) -> GeneratedText:
            return GeneratedText("{}", exhausted=False, generated_tokens=2)

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = _bound_packed_adapter(
        PreparedArtifactSet(recipe, paths),
        converter=Converter(),
        runner=Runner(),
        budget=_generation_budget(max_continuations=1),
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    response = adapter.create_response(
        build_openai_request(
            model=recipe.model_id,
            messages=[OpenAIMessage("user", "vectorize")],
            response_format={"type": "json_object"},
        )
    )

    assert response.content == "{}"
    assert response.metadata == {
        "generation": {
            "device": "mps",
            "chunk_count": 1,
            "chunk_exhausted": [False],
            "generated_tokens": [2],
        }
    }
    assert adapter._sealed_payload is None


def test_converter_adapter_records_only_scalar_debug_fragment_facts(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        GeneratedText,
        PackedModelInput,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    recorded: list[object] = []

    class Runner:
        input_context = object()
        supports_json_mode = True
        uses_mps = True

        def generate_chunk(
            self, _packed: PackedModelInput, **_kwargs: object
        ) -> GeneratedText:
            return GeneratedText('{"walls":[', exhausted=True, generated_tokens=3)

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = _bound_packed_adapter(
        PreparedArtifactSet(recipe, paths),
        converter=Converter(),
        runner=Runner(),
        budget=_generation_budget(max_continuations=0),
    )
    adapter.set_debug_fragment_recorder(recorded.append)
    adapter.bind_sealed_payload(content=b"sealed image")

    with pytest.raises(ModelExecutionError, match="invalid JSON"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
                response_format={"type": "json_object"},
            )
        )

    assert len(recorded) == 1
    assert not hasattr(recorded[0], "content")
    assert recorded[0].generated_tokens == 3
    assert recorded[0].output_bytes == len('{"walls":['.encode())
    assert recorded[0].exhausted is True
    assert recorded[0].fragment_index == 0
    assert adapter._sealed_payload is None


def test_converter_adapter_continues_an_incomplete_json_chunk(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        GeneratedText,
        PackedModelInput,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    chunks = iter(
        (
            GeneratedText('{"walls":', exhausted=False, generated_tokens=4),
            GeneratedText("[]}", exhausted=False, generated_tokens=3),
        )
    )

    class Runner:
        input_context = object()
        supports_json_mode = True
        uses_mps = True

        def generate_chunk(
            self, _packed: PackedModelInput, **_kwargs: object
        ) -> GeneratedText:
            return next(chunks)

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = _bound_packed_adapter(
        PreparedArtifactSet(recipe, paths),
        converter=Converter(),
        runner=Runner(),
        budget=_generation_budget(max_continuations=1),
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    response = adapter.create_response(
        build_openai_request(
            model=recipe.model_id,
            messages=[OpenAIMessage("user", "vectorize")],
            response_format={"type": "json_object"},
            max_continuations=1,
        )
    )

    assert response.content == '{"walls":[]}'
    assert response.metadata == {
        "generation": {
            "device": "mps",
            "chunk_count": 2,
            "chunk_exhausted": [False, False],
            "generated_tokens": [4, 3],
        }
    }


def test_converter_adapter_rejects_an_exhausted_continuation_budget(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        GeneratedText,
        PackedModelInput,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    generated = 0

    class Runner:
        input_context = object()

        def generate_chunk(
            self, _packed: PackedModelInput, **_kwargs: object
        ) -> GeneratedText:
            nonlocal generated
            generated += 1
            return GeneratedText('{"walls":', exhausted=True, generated_tokens=1)

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = _bound_packed_adapter(
        PreparedArtifactSet(recipe, paths),
        converter=Converter(),
        runner=Runner(),
        budget=_generation_budget(max_continuations=1),
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    with pytest.raises(ModelExecutionError, match="continuation limit") as error:
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
                max_continuations=1,
            )
        )

    assert generated == 2
    assert '{"walls":' not in str(error.value)
    assert adapter._sealed_payload is None


def test_converter_adapter_rejects_json_mode_before_packing_for_incapable_runner(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TransformersPeftPackedInputAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }

    class Runner:
        input_context = object()
        supports_json_mode = False

    class Converter:
        def pack(self, **_kwargs: object) -> object:
            pytest.fail("an incapable runner must reject before converter packing")

    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths), converter=Converter(), runner=Runner()
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    with pytest.raises(ModelExecutionError, match="does not support JSON"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
                response_format={"type": "json_object"},
            )
        )

    assert adapter.capabilities["json_mode"] is False
    assert adapter._sealed_payload is None


def test_standard_runner_rejects_non_json_output_without_exposing_it(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        PackedModelInput,
        TransformersGenerateRunner,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths: dict[str, Path] = {}
    for artifact in recipe.artifacts:
        path = tmp_path / artifact.group / artifact.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
        paths[artifact.role] = path

    class Backend:
        processor = object()

        def generate_packed(
            self, _packed: object, *, max_new_tokens: int, json_mode: bool
        ) -> str:
            assert max_new_tokens == 12
            assert json_mode is True
            return "not-json"

    packed = PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})
    runner = TransformersGenerateRunner(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=lambda _base, _adapter: Backend(),
    )

    with pytest.raises(ModelExecutionError, match="invalid JSON") as error:
        runner.generate(packed, max_new_tokens=12, json_mode=True)

    assert "not-json" not in str(error.value)
    assert packed.is_cleared is True


def test_converter_adapter_clears_payload_after_converter_failure(
    tmp_path: Path,
) -> None:

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }

    class Runner:
        input_context = object()

        def generate_chunk(self, **_kwargs: object) -> object:
            pytest.fail("converter failure must precede runner dispatch")

    class Converter:
        def pack(self, **_kwargs: object) -> object:
            raise ValueError("bad image")

    adapter = _bound_packed_adapter(
        PreparedArtifactSet(recipe, paths), converter=Converter(), runner=Runner()
    )
    adapter.bind_sealed_payload(content=b"sealed image")

    with pytest.raises(ModelExecutionError, match="local model generation failed"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
            )
        )

    assert adapter._sealed_payload is None


def test_standard_runner_consumes_and_clears_private_packed_input(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TRANSFORMERS_GENERATE_V1,
        PackedModelInput,
        TransformersGenerateRunner,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths: dict[str, Path] = {}
    for artifact in recipe.artifacts:
        path = tmp_path / artifact.group / artifact.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
        paths[artifact.role] = path

    processor = object()
    inputs = {"input_ids": SimpleNamespace(shape=(1, 3))}
    calls: list[tuple[object, int]] = []

    class Backend:
        @property
        def processor(self) -> object:
            return processor

        def generate_packed(self, packed: object, *, max_new_tokens: int) -> str:
            calls.append((packed, max_new_tokens))
            return "floorplan"

    packed_input = PackedModelInput(inputs)
    runner = TransformersGenerateRunner(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=lambda _base, _adapter: Backend(),
    )

    assert runner.contract_id == TRANSFORMERS_GENERATE_V1
    assert runner.processor is processor
    assert runner.generate(packed_input, max_new_tokens=12) == "floorplan"
    assert calls == [(inputs, 12)]
    assert packed_input.is_cleared is True


@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        (ModelExecutionError("packed model input is invalid"), ModelExecutionError),
        (TimeoutError(), ModelExecutionError),
        (asyncio.CancelledError(), asyncio.CancelledError),
    ],
)
def test_standard_runner_clears_private_packed_input_after_failure(
    tmp_path: Path, failure: BaseException, expected_error: type[BaseException]
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        PackedModelInput,
        TransformersGenerateRunner,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths: dict[str, Path] = {}
    for artifact in recipe.artifacts:
        path = tmp_path / artifact.group / artifact.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
        paths[artifact.role] = path

    class Backend:
        processor = object()

        def generate_packed(self, _packed: object, *, max_new_tokens: int) -> str:
            raise failure

    packed_input = PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 3))})
    runner = TransformersGenerateRunner(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=lambda _base, _adapter: Backend(),
    )

    with pytest.raises(expected_error):
        runner.generate(packed_input, max_new_tokens=12)

    assert packed_input.is_cleared is True


def test_standard_runner_records_the_limits_at_both_generation_boundaries(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        GeneratedText,
        PackedModelInput,
        TransformersGenerateRunner,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }

    class Backend:
        processor = object()

        def generate_packed(
            self, _packed: object, *, max_new_tokens: int
        ) -> GeneratedText:
            return GeneratedText(
                "floorplan",
                exhausted=False,
                backend_max_new_tokens=max_new_tokens,
            )

    runner = TransformersGenerateRunner(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=lambda _base, _adapter: Backend(),
    )
    generated = runner.generate_chunk(
        PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 3))}),
        max_new_tokens=65_536,
    )

    assert generated.runner_max_new_tokens == 65_536
    assert generated.backend_max_new_tokens == 65_536


def test_standard_runner_clears_private_packed_input_on_runner_rejection(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        PackedModelInput,
        TransformersGenerateRunner,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    packed_input = PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 3))})
    runner = TransformersGenerateRunner(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=lambda _base, _adapter: pytest.fail("must not load"),
    )

    with pytest.raises(ModelExecutionError, match="generation limit"):
        runner.generate(packed_input, max_new_tokens=0)

    assert packed_input.is_cleared is True


def test_generic_runner_uses_verified_groups_and_clears_sealed_image(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TransformersPeftSingleImageAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths: dict[str, Path] = {}
    for artifact in recipe.artifacts:
        path = tmp_path / artifact.group / artifact.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
        paths[artifact.role] = path

    calls: list[tuple[str, object, int]] = []

    class Backend:
        def generate(self, prompt: str, image: object, *, max_new_tokens: int) -> str:
            calls.append((prompt, image, max_new_tokens))
            return '{"walls":[]}'

    adapter = TransformersPeftSingleImageAdapter(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=lambda _base, _adapter: Backend(),
        image_decoder=lambda content: FakeImage(),
    )
    adapter.bind_sealed_image(content=b"image", media_type="image/png")
    response = adapter.create_response(
        build_openai_request(
            model=recipe.model_id,
            messages=[OpenAIMessage("user", "vectorize")],
            max_tokens=4096,
        )
    )

    assert response.content == '{"walls":[]}'
    assert calls[0][0] == "vectorize"
    assert isinstance(calls[0][1], FakeImage)
    assert calls[0][2] == 4096
    assert adapter._sealed_image is None
    with pytest.raises(ModelExecutionError, match="sealed image"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id, messages=[OpenAIMessage("user", "x")]
            )
        )


def test_generic_runner_rejects_invalid_media_and_limits(tmp_path: Path) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TransformersPeftSingleImageAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.filename for artifact in recipe.artifacts
    }
    adapter = TransformersPeftSingleImageAdapter(
        PreparedArtifactSet(recipe, paths), image_decoder=lambda content: FakeImage()
    )

    with pytest.raises(ModelExecutionError, match="sealed image"):
        adapter.bind_sealed_image(content=b"x", media_type="image/gif")
    with pytest.raises(ModelExecutionError, match="sealed image"):
        adapter.bind_sealed_image(
            content=b"x" * (8 * 1024 * 1024 + 1), media_type="image/png"
        )

    adapter.bind_sealed_image(content=b"jpeg", media_type="image/jpeg")
    with pytest.raises(ModelExecutionError, match="sealed image"):
        adapter.bind_sealed_image(content=b"second", media_type="image/jpeg")
    adapter.clear_sealed_image()


def test_generic_runner_rejects_bad_decodes_and_generation_limits(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TransformersPeftSingleImageAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    loader_calls = 0

    def load(_base, _adapter):
        nonlocal loader_calls
        loader_calls += 1
        raise AssertionError("invalid input must not load a model")

    oversized = SimpleNamespace(width=32_000_001, height=1)
    adapter = TransformersPeftSingleImageAdapter(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=load,
        image_decoder=lambda _: oversized,
    )
    with pytest.raises(ModelExecutionError, match="sealed image"):
        adapter.bind_sealed_image(content=b"image", media_type="image/png")
    assert loader_calls == 0

    adapter = TransformersPeftSingleImageAdapter(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=load,
        image_decoder=lambda _: FakeImage(),
    )
    adapter.bind_sealed_image(content=b"image", media_type="image/png")
    with pytest.raises(ModelExecutionError, match="generation limit"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
                max_tokens=0,
            )
        )
    assert adapter._sealed_image is None
    assert loader_calls == 0

    adapter = TransformersPeftSingleImageAdapter(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=load,
        image_decoder=lambda _: (_ for _ in ()).throw(ValueError("malformed")),
    )
    with pytest.raises(ModelExecutionError, match="sealed image"):
        adapter.bind_sealed_image(content=b"not-a-png", media_type="image/png")
    assert loader_calls == 0

    adapter = TransformersPeftSingleImageAdapter(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=load,
        image_decoder=lambda _: FakeImage(),
    )
    adapter.bind_sealed_image(content=b"image", media_type="image/png")
    with pytest.raises(ModelExecutionError, match="generation limit"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
                max_tokens=0,
            )
        )
    assert adapter._sealed_image is None
    assert loader_calls == 0


def test_standard_runner_does_not_own_generation_ceiling_constants() -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        _max_new_tokens,
    )

    request = build_openai_request(
        model="qwen25-vl-3b-floorplan-grpo",
        messages=[OpenAIMessage("user", "vectorize")],
        max_tokens=1_000_001,
    )

    assert _max_new_tokens(request) == 1_000_001

    with pytest.raises(ModelExecutionError, match="generation limit"):
        _max_new_tokens(
            build_openai_request(
                model="qwen25-vl-3b-floorplan-grpo",
                messages=[OpenAIMessage("user", "vectorize")],
                max_tokens=0,
            )
        )


def test_default_loader_uses_only_local_nonremote_framework_arguments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import dynamic_agent_runner.workflow_host.transformers_peft_model as runner

    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        _load_default_backend,
    )

    calls: list[tuple[str, Path, dict[str, object]]] = []

    class Processor:
        @classmethod
        def from_pretrained(cls, path: Path, **kwargs: object) -> object:
            calls.append(("processor", path, kwargs))
            return object()

    class Model:
        @classmethod
        def from_pretrained(cls, path: Path, **kwargs: object) -> object:
            calls.append(("model", path, kwargs))
            return object()

    class Peft:
        @classmethod
        def from_pretrained(cls, model: object, path: Path, **kwargs: object) -> object:
            calls.append(("adapter", path, {"model": model, **kwargs}))
            return object()

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoModelForImageTextToText=Model, AutoProcessor=Processor),
    )
    monkeypatch.setitem(sys.modules, "peft", SimpleNamespace(PeftModel=Peft))
    monkeypatch.setattr(runner, "_mps_available", lambda: False)

    base = tmp_path / "base"
    adapter = tmp_path / "adapter"
    _load_default_backend(base, adapter)

    assert calls[0] == (
        "processor",
        base,
        {"local_files_only": True, "trust_remote_code": False},
    )
    assert calls[1] == (
        "model",
        base,
        {
            "local_files_only": True,
            "trust_remote_code": False,
            "device_map": "auto",
            "torch_dtype": "auto",
        },
    )
    assert calls[2][0:2] == ("adapter", adapter)
    assert calls[2][2]["is_trainable"] is False
    assert calls[2][2]["local_files_only"] is True


def test_default_loader_attaches_peft_before_placing_the_complete_model_on_mps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import dynamic_agent_runner.workflow_host.transformers_peft_model as runner

    calls: list[tuple[str, object, object]] = []

    class Processor:
        @classmethod
        def from_pretrained(cls, path: Path, **kwargs: object) -> object:
            calls.append(("processor", path, kwargs))
            return object()

    class Model:
        @classmethod
        def from_pretrained(cls, path: Path, **kwargs: object) -> "Model":
            calls.append(("model", path, kwargs))
            return cls()

        def to(self, device: str) -> "Model":
            calls.append(("move", device, self))
            return self

    class Peft:
        @classmethod
        def from_pretrained(cls, model: object, path: Path, **kwargs: object) -> object:
            calls.append(("adapter", model, {"path": path, **kwargs}))

            class WrappedModel:
                device = "mps"

                def to(self, device: str) -> "WrappedModel":
                    calls.append(("move", device, self))
                    return self

                def eval(self) -> "WrappedModel":
                    calls.append(("eval", self, None))
                    return self

            return WrappedModel()

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoModelForImageTextToText=Model, AutoProcessor=Processor),
    )
    monkeypatch.setitem(sys.modules, "peft", SimpleNamespace(PeftModel=Peft))
    monkeypatch.setattr(runner, "_mps_available", lambda: True)

    runner._load_default_backend(tmp_path / "base", tmp_path / "adapter")

    assert calls[1] == (
        "model",
        tmp_path / "base",
        {
            "local_files_only": True,
            "trust_remote_code": False,
            "torch_dtype": "auto",
        },
    )
    assert calls[2][0] == "adapter"
    assert calls[2][1] is not None
    assert calls[3][0:2] == ("move", "mps")
    assert calls[3][2] is not calls[2][1]
    assert calls[4][0] == "eval"
    assert calls[4][1] is calls[3][2]


def test_mps_loader_targets_wrapped_model_device_for_generation(  # noqa: C901
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import dynamic_agent_runner.workflow_host.transformers_peft_model as runner

    calls: list[tuple[str, object]] = []

    class Inputs(dict[str, object]):
        def to(self, device: str) -> "Inputs":
            calls.append(("inputs", device))
            return self

    class Processor:
        @classmethod
        def from_pretrained(cls, _path: Path, **_kwargs: object) -> "Processor":
            return cls()

        def apply_chat_template(self, *_args: object, **_kwargs: object) -> Inputs:
            return Inputs(input_ids=SimpleNamespace(shape=(1, 1)))

        def batch_decode(self, _tokens: object, **_kwargs: object) -> list[str]:
            return ['{"walls":[]}']

    class Model:
        @classmethod
        def from_pretrained(cls, _path: Path, **_kwargs: object) -> "Model":
            return cls()

        def to(self, device: str) -> "Model":
            calls.append(("move", device))
            return self

    class WrappedModel:
        device = "mps"

        def to(self, device: str) -> "WrappedModel":
            calls.append(("move", device))
            return self

        def eval(self) -> "WrappedModel":
            calls.append(("eval", "mps"))
            return self

        def generate(self, **_kwargs: object) -> object:
            return Generated()

    class Generated:
        def __getitem__(self, _index: object) -> object:
            return object()

    class Peft:
        @classmethod
        def from_pretrained(
            cls, _model: object, _path: Path, **_kwargs: object
        ) -> WrappedModel:
            return WrappedModel()

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoModelForImageTextToText=Model, AutoProcessor=Processor),
    )
    monkeypatch.setitem(sys.modules, "peft", SimpleNamespace(PeftModel=Peft))
    monkeypatch.setattr(runner, "_mps_available", lambda: True)

    backend = runner._load_default_backend(tmp_path / "base", tmp_path / "adapter")
    backend.generate("vectorize", FakeImage(), max_new_tokens=4)

    assert calls == [("move", "mps"), ("eval", "mps"), ("inputs", "mps")]


def test_loaded_backend_generates_inside_torch_inference_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        _LoadedTransformersPeftBackend,
    )

    state = {"active": False, "entered": 0, "exited": 0}

    class InferenceMode:
        def __enter__(self) -> None:
            state["active"] = True
            state["entered"] += 1

        def __exit__(self, *_args: object) -> None:
            state["active"] = False
            state["exited"] += 1

    class Inputs(dict[str, object]):
        def to(self, _device: object) -> "Inputs":
            return self

    class Generated:
        shape = (1, 2)

        def __getitem__(self, _item: object) -> object:
            return object()

    class Model:
        device = "mps"

        def generate(self, **_kwargs: object) -> Generated:
            assert state["active"] is True
            return Generated()

    class Processor:
        def batch_decode(self, _tokens: object, **_kwargs: object) -> list[str]:
            return ['{"walls":[]}']

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(inference_mode=lambda: InferenceMode()),
    )

    result = _LoadedTransformersPeftBackend(
        model=Model(), processor=Processor()
    ).generate_packed(Inputs(input_ids=SimpleNamespace(shape=(1, 1))), max_new_tokens=4)

    assert result.content == '{"walls":[]}'
    assert state == {"active": False, "entered": 1, "exited": 1}


def test_loaded_backend_recognizes_the_indexed_mps_device() -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        _LoadedTransformersPeftBackend,
    )

    backend = _LoadedTransformersPeftBackend(
        model=SimpleNamespace(device="mps:0"), processor=object()
    )

    assert backend.uses_mps is True


@pytest.mark.parametrize("failure_step", ["move", "adapter"])
def test_mps_loader_failure_clears_sealed_image_and_redacts_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure_step: str
) -> None:
    import dynamic_agent_runner.workflow_host.transformers_peft_model as runner

    class Processor:
        @classmethod
        def from_pretrained(cls, _path: Path, **_kwargs: object) -> object:
            return object()

    class Model:
        @classmethod
        def from_pretrained(cls, _path: Path, **_kwargs: object) -> "Model":
            return cls()

        def to(self, _device: str) -> "Model":
            if failure_step == "move":
                raise RuntimeError("vendor MPS move failure")
            return self

    class Peft:
        @classmethod
        def from_pretrained(
            cls, _model: object, _path: Path, **_kwargs: object
        ) -> object:
            if failure_step == "adapter":
                raise RuntimeError("vendor adapter failure")
            return object()

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoModelForImageTextToText=Model, AutoProcessor=Processor),
    )
    monkeypatch.setitem(sys.modules, "peft", SimpleNamespace(PeftModel=Peft))
    monkeypatch.setattr(runner, "_mps_available", lambda: True)

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.filename for artifact in recipe.artifacts
    }
    adapter = runner.TransformersPeftSingleImageAdapter(
        PreparedArtifactSet(recipe, paths), image_decoder=lambda _content: FakeImage()
    )
    adapter.bind_sealed_image(content=b"image", media_type="image/png")

    with pytest.raises(ModelExecutionError) as error:
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "private prompt")],
            )
        )

    assert str(error.value) == "local model generation failed"
    assert "vendor" not in str(error.value)
    assert "private prompt" not in str(error.value)
    assert str(tmp_path) not in str(error.value)
    assert adapter._sealed_image is None


def test_generic_runner_rejects_an_invalid_closure_before_loading(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TransformersPeftSingleImageAdapter,
    )

    recipe = LocalModelPreparationRecipe(
        model_id="model",
        adapter_id="adapter",
        runner_id="transformers-peft-v1",
        loader_profile=QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE.loader_profile,
        transformation=None,
        artifacts=(
            LocalModelArtifact(
                "base_config", "repo", "revision", "config.json", "a", "base"
            ),
        ),
    )
    loader_called = False

    def load(_base, _adapter):
        nonlocal loader_called
        loader_called = True
        raise AssertionError("invalid closure must not load")

    with pytest.raises(ModelExecutionError, match="incompatible"):
        TransformersPeftSingleImageAdapter(
            PreparedArtifactSet(recipe, {}), dependency_loader=load
        )
    assert loader_called is False


def test_loaded_backend_uses_deterministic_template_and_decodes_only_suffix() -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        _LoadedTransformersPeftBackend,
    )

    calls: dict[str, object] = {}
    image = FakeImage()

    class Inputs(dict):
        def to(self, device: object) -> "Inputs":
            calls["device"] = device
            return self

    class Generated:
        def __getitem__(self, item: object) -> object:
            calls["slice"] = item
            return "generated-suffix"

    class Model:
        device = "device"

        def generate(self, **kwargs: object) -> Generated:
            calls["generate"] = kwargs
            return Generated()

    class Processor:
        def apply_chat_template(self, messages, **kwargs: object) -> Inputs:
            calls["messages"] = messages
            calls["template"] = kwargs
            return Inputs(input_ids=SimpleNamespace(shape=(1, 7)))

        def batch_decode(self, tokens: object, **kwargs: object) -> list[str]:
            calls["decode"] = (tokens, kwargs)
            return ["  output  "]

    backend = _LoadedTransformersPeftBackend(model=Model(), processor=Processor())

    assert backend.generate("describe", image, max_new_tokens=12) == "output"
    assert calls["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "describe"},
            ],
        }
    ]
    assert calls["template"] == {
        "add_generation_prompt": True,
        "tokenize": True,
        "return_dict": True,
        "return_tensors": "pt",
    }
    assert calls["generate"]["do_sample"] is False
    assert calls["generate"]["max_new_tokens"] == 12
    assert calls["generate"]["input_ids"].shape == (1, 7)
    assert calls["slice"] == (slice(None), slice(7, None))
    assert calls["decode"] == ("generated-suffix", {"skip_special_tokens": True})


def test_loaded_backend_adds_json_prefix_filter_only_for_json_mode(  # noqa: C901
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        _LoadedTransformersPeftBackend,
    )

    calls: dict[str, object] = {}

    class Parser:
        def __init__(self, schema: object) -> None:
            calls["schema"] = schema

    class TokenData:
        def __init__(self, *args: object) -> None:
            calls["token_data"] = args

    class Enforcer:
        def __init__(self, token_data: object, parser: object) -> None:
            calls["token_data_instance"] = token_data
            calls["parser"] = parser

        def get_allowed_tokens(self, _tokens: object) -> object:
            return SimpleNamespace(allowed_tokens=(1, 2))

    monkeypatch.setitem(
        sys.modules, "lmformatenforcer", SimpleNamespace(JsonSchemaParser=Parser)
    )
    monkeypatch.setitem(
        sys.modules,
        "lmformatenforcer.tokenenforcer",
        SimpleNamespace(TokenEnforcer=Enforcer, TokenEnforcerTokenizerData=TokenData),
    )

    class Inputs(dict):
        def to(self, _device: object) -> "Inputs":
            return self

    class Generated:
        def __getitem__(self, _item: object) -> object:
            return "generated-suffix"

    class Model:
        device = "device"

        def generate(self, **kwargs: object) -> Generated:
            calls["generate"] = kwargs
            return Generated()

    class Tokenizer:
        all_special_ids = ()
        eos_token_id = 3

        @staticmethod
        def encode(_value: str) -> list[int]:
            return [0]

        @staticmethod
        def decode(tokens: list[int]) -> str:
            return "0" if tokens == [0] else "a"

        def __len__(self) -> int:
            return 2

    class Processor:
        tokenizer = Tokenizer()

        def batch_decode(self, _tokens: object, **_kwargs: object) -> list[str]:
            return ["{}"]

    backend = _LoadedTransformersPeftBackend(model=Model(), processor=Processor())

    generated = backend.generate_packed(
        Inputs(input_ids=SimpleNamespace(shape=(1, 2))),
        max_new_tokens=12,
        json_mode=True,
    )
    assert generated.content == "{}"
    assert generated.exhausted is False
    assert calls["schema"] is None
    assert calls["token_data"][-2:] == (False, 2)
    assert calls["generate"]["prefix_allowed_tokens_fn"](
        0, SimpleNamespace(tolist=lambda: [0])
    ) == [1, 2]


def test_loaded_backend_generates_from_private_packed_inputs() -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        _LoadedTransformersPeftBackend,
    )

    calls: dict[str, object] = {}

    class Inputs(dict):
        def to(self, device: object) -> "Inputs":
            calls["device"] = device
            return self

    class Generated:
        def __getitem__(self, item: object) -> object:
            calls["slice"] = item
            return "suffix"

    class Model:
        device = "private-device"

        def generate(self, **kwargs: object) -> Generated:
            calls["generate"] = kwargs
            return Generated()

    class Processor:
        def batch_decode(self, tokens: object, **kwargs: object) -> list[str]:
            calls["decode"] = (tokens, kwargs)
            return [" output "]

    backend = _LoadedTransformersPeftBackend(model=Model(), processor=Processor())
    packed = Inputs(input_ids=SimpleNamespace(shape=(1, 3)))

    generated = backend.generate_packed(packed, max_new_tokens=7)
    assert generated.content == " output "
    assert generated.exhausted is False
    assert generated.backend_max_new_tokens == 7
    assert calls["device"] == "private-device"
    assert calls["generate"]["max_new_tokens"] == 7
    assert calls["slice"] == (slice(None), slice(3, None))


def test_loaded_backend_reports_when_generation_reaches_its_token_ceiling() -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        _LoadedTransformersPeftBackend,
    )

    class Inputs(dict):
        def to(self, _device: object) -> "Inputs":
            return self

    class Generated:
        shape = (1, 7)

        def __getitem__(self, _item: object) -> object:
            return "suffix"

    class Model:
        device = "private-device"

        def generate(self, **_kwargs: object) -> Generated:
            return Generated()

    class Processor:
        def batch_decode(self, _tokens: object, **_kwargs: object) -> list[str]:
            return [" output "]

    backend = _LoadedTransformersPeftBackend(model=Model(), processor=Processor())

    generated = backend.generate_packed(
        Inputs(input_ids=SimpleNamespace(shape=(1, 3))), max_new_tokens=4
    )

    assert generated.content == " output "
    assert generated.exhausted is True


def test_loaded_backend_exposes_only_its_reviewed_processor() -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        _LoadedTransformersPeftBackend,
    )

    processor = object()
    backend = _LoadedTransformersPeftBackend(model=object(), processor=processor)

    assert backend.processor is processor
    assert not hasattr(backend, "model")


@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (RuntimeError("generation failed"), ModelExecutionError),
        (asyncio.CancelledError(), asyncio.CancelledError),
    ],
)
def test_generic_runner_clears_sealed_image_after_backend_failures(
    tmp_path: Path, error: BaseException, expected_error: type[BaseException]
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TransformersPeftSingleImageAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }

    class FailingBackend:
        def generate(self, prompt: str, image: object, *, max_new_tokens: int) -> str:
            raise error

    adapter = TransformersPeftSingleImageAdapter(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=lambda _base, _adapter: FailingBackend(),
        image_decoder=lambda _: FakeImage(),
    )
    adapter.bind_sealed_image(content=b"image", media_type="image/png")

    with pytest.raises(expected_error):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
            )
        )
    assert adapter._sealed_image is None


def test_loaded_backend_rejects_empty_generated_output() -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        _LoadedTransformersPeftBackend,
    )

    class Inputs(dict):
        def to(self, device: object) -> "Inputs":
            return self

    class Generated:
        def __getitem__(self, item: object) -> object:
            return object()

    class Model:
        device = "device"

        def generate(self, **kwargs: object) -> Generated:
            return Generated()

    class Processor:
        def apply_chat_template(self, messages, **kwargs: object) -> Inputs:
            return Inputs(input_ids=SimpleNamespace(shape=(1, 1)))

        def batch_decode(self, tokens: object, **kwargs: object) -> list[str]:
            return ["  "]

    backend = _LoadedTransformersPeftBackend(model=Model(), processor=Processor())

    with pytest.raises(ModelExecutionError, match="empty"):
        backend.generate("describe", FakeImage(), max_new_tokens=1)


def test_generic_runner_clears_sealed_image_after_loader_failure(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TransformersPeftSingleImageAdapter,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    paths = {
        artifact.role: tmp_path / artifact.group / artifact.filename
        for artifact in recipe.artifacts
    }
    adapter = TransformersPeftSingleImageAdapter(
        PreparedArtifactSet(recipe, paths),
        dependency_loader=lambda _base, _adapter: (_ for _ in ()).throw(ImportError()),
        image_decoder=lambda _: FakeImage(),
    )
    adapter.bind_sealed_image(content=b"image", media_type="image/png")

    with pytest.raises(ModelExecutionError, match="dependencies unavailable"):
        adapter.create_response(
            build_openai_request(
                model=recipe.model_id,
                messages=[OpenAIMessage("user", "vectorize")],
            )
        )
    assert adapter._sealed_image is None
