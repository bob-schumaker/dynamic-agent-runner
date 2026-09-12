"""Fake-only tests for the generic Transformers + PEFT single-image runner."""

from __future__ import annotations

import asyncio
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import sys

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


def test_deferred_adapter_requires_a_manifest_bound_converter_package(
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

    with pytest.raises(ModelExecutionError, match="sealed converter input"):
        adapter.bind_sealed_payload(content=b"sealed image")

    adapter.bind_input_converter(package_root=tmp_path, converter=converter)
    adapter.bind_sealed_payload(content=b"sealed image")

    assert adapter._payload_bound is True
    adapter.clear_sealed_payload()


def test_converter_adapter_runs_one_packed_generation_and_clears_payload(
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

    adapter = TransformersPeftPackedInputAdapter(
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
    assert calls["max_new_tokens"] == 12
    assert adapter._sealed_payload is None


def test_converter_adapter_passes_json_mode_to_a_capable_runner(
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

    adapter = TransformersPeftPackedInputAdapter(
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
    assert calls["max_new_tokens"] == 12
    assert calls["json_mode"] is True
    assert adapter._sealed_payload is None


def test_converter_adapter_assembles_bounded_json_continuations(
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
    calls: list[tuple[tuple[object, ...], bytes]] = []
    json_modes: list[bool] = []
    chunks = iter(
        (
            GeneratedText('{"walls":', exhausted=True),
            GeneratedText("[]}", exhausted=False),
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

    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths), converter=Converter(), runner=Runner()
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


def test_converter_adapter_emits_redacted_mps_metadata_for_direct_response(
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
        uses_mps = True

        def generate_chunk(
            self, _packed: PackedModelInput, **_kwargs: object
        ) -> GeneratedText:
            return GeneratedText("{}", exhausted=False, generated_tokens=2)

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths), converter=Converter(), runner=Runner()
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


def test_converter_adapter_records_a_malformed_chunk_before_json_rejection(
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
    recorded: list[GeneratedText] = []

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

    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths), converter=Converter(), runner=Runner()
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

    assert recorded == [GeneratedText('{"walls":[', exhausted=True, generated_tokens=3)]
    assert adapter._sealed_payload is None


def test_converter_adapter_continues_an_incomplete_json_chunk(
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

    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths), converter=Converter(), runner=Runner()
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
        TransformersPeftPackedInputAdapter,
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
            return GeneratedText('{"walls":', exhausted=True)

    class Converter:
        def pack(self, **_kwargs: object) -> PackedModelInput:
            return PackedModelInput({"input_ids": SimpleNamespace(shape=(1, 2))})

    adapter = TransformersPeftPackedInputAdapter(
        PreparedArtifactSet(recipe, paths), converter=Converter(), runner=Runner()
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

    class Converter:
        def pack(self, **_kwargs: object) -> object:
            raise ValueError("bad image")

    adapter = TransformersPeftPackedInputAdapter(
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
                max_tokens=1_000_001,
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


def test_standard_runner_accepts_the_extended_generation_limits() -> None:
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        _max_continuations,
        _max_new_tokens,
    )

    request = build_openai_request(
        model="qwen25-vl-3b-floorplan-grpo",
        messages=[OpenAIMessage("user", "vectorize")],
        max_tokens=1_000_000,
        max_continuations=32,
    )

    assert _max_new_tokens(request) == 1_000_000
    assert _max_continuations(request) == 32

    with pytest.raises(ModelExecutionError, match="generation limit"):
        _max_new_tokens(
            build_openai_request(
                model="qwen25-vl-3b-floorplan-grpo",
                messages=[OpenAIMessage("user", "vectorize")],
                max_tokens=1_000_001,
            )
        )
    with pytest.raises(ModelExecutionError, match="continuation limit"):
        _max_continuations(
            build_openai_request(
                model="qwen25-vl-3b-floorplan-grpo",
                messages=[OpenAIMessage("user", "vectorize")],
                max_continuations=33,
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
