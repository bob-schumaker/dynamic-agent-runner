"""Fake-only coverage for host-owned local-model preparation."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest


def _digest(content: bytes) -> str:
    return sha256(content).hexdigest()


def _transformers_peft_recipe() -> object:
    from dynamic_agent_runner.local_model_preparation import (
        LocalModelArtifact,
        LocalModelPreparationRecipe,
        TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
    )

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


QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE = _transformers_peft_recipe()


def _recipe() -> object:
    from dynamic_agent_runner.local_model_preparation import (
        LocalModelArtifact,
        LocalModelPreparationRecipe,
        LocalModelTransformation,
    )

    return LocalModelPreparationRecipe(
        model_id="example-floorplan",
        adapter_id="example-vision-adapter",
        artifacts=(
            LocalModelArtifact(
                role="base_model",
                repo_id="example/base",
                revision="base-revision",
                filename="base.gguf",
                sha256=_digest(b"base"),
            ),
            LocalModelArtifact(
                role="vision_projector",
                repo_id="example/base",
                revision="base-revision",
                filename="projector.gguf",
                sha256=_digest(b"projector"),
            ),
            LocalModelArtifact(
                role="source_lora",
                repo_id="example/adapter",
                revision="adapter-revision",
                filename="adapter.safetensors",
                sha256=_digest(b"adapter"),
            ),
            LocalModelArtifact(
                role="lora_metadata",
                repo_id="example/adapter",
                revision="adapter-revision",
                filename="adapter_config.json",
                sha256=_digest(b"metadata"),
            ),
        ),
        transformation=LocalModelTransformation(
            converter_revision="converter-revision",
            output_role="adapter",
            output_filename="adapter.gguf",
            output_sha256=_digest(b"GGUF converted"),
        ),
    )


def test_catalog_requires_unique_runner_aware_recipe_keys() -> None:
    from dynamic_agent_runner.local_model_preparation import (
        LocalModelPreparationCatalog,
        LocalModelPreparationUnavailable,
    )

    recipe = _recipe()
    duplicate = _recipe()

    with pytest.raises(LocalModelPreparationUnavailable, match="recipe_invalid"):
        LocalModelPreparationCatalog((recipe, duplicate))  # type: ignore[arg-type]


def test_native_recipe_is_ready_without_a_gguf_transformation(tmp_path: Path) -> None:
    from dynamic_agent_runner.local_model_preparation import (
        LocalModelArtifact,
        LocalModelPreparationCatalog,
        LocalModelPreparationRecipe,
        LocalModelPreparationService,
    )

    config = b'{"model_type":"qwen2_5_vl"}'
    weights = b"native weights"
    recipe = LocalModelPreparationRecipe(
        model_id="example-native-floorplan",
        adapter_id="example-native-adapter",
        runner_id="example-native-floorplan-runner-v1",
        recipe_id="example-native-floorplan-v1",
        artifacts=(
            LocalModelArtifact(
                role="base/config.json",
                repo_id="example/base",
                revision="base-revision",
                filename="config.json",
                sha256=_digest(config),
                group="base",
            ),
            LocalModelArtifact(
                role="base/model.safetensors",
                repo_id="example/base",
                revision="base-revision",
                filename="model.safetensors",
                sha256=_digest(weights),
                group="base",
            ),
        ),
        transformation=None,
    )
    service = LocalModelPreparationService(
        catalog=LocalModelPreparationCatalog((recipe,)), cache_root=tmp_path / "cache"
    )
    for artifact, content in zip(recipe.artifacts, (config, weights), strict=True):
        path = service.source_path(recipe, artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    prepared = service.resolve(
        model_id=recipe.model_id,
        adapter_id=recipe.adapter_id,
        runner_id=recipe.runner_id,
    )

    assert prepared.recipe_id == recipe.recipe_id
    assert prepared.recipe_digest == recipe.recipe_digest
    assert prepared.paths["base/config.json"].read_bytes() == config
    assert prepared.group_path("base") == prepared.paths["base/config.json"].parent


def test_qwen_native_recipe_uses_the_closed_transformers_peft_profile() -> None:
    from dynamic_agent_runner.local_model_preparation import (
        TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE

    assert recipe.runner_id == "transformers-peft-v1"
    assert recipe.loader_profile == TRANSFORMERS_PEFT_SINGLE_IMAGE_V1
    assert {item.role for item in recipe.artifacts if item.group == "adapter"} == {
        "adapter_config",
        "adapter_weights",
    }


def test_sealed_transformers_lock_derives_the_closed_preparation_recipe() -> None:
    from dynamic_agent_runner.local_model_preparation import (
        TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
        prepared_transformers_peft_recipe,
    )
    from dynamic_agent_runner.workflow_host.model_execution_binding import (
        ModelExecutionBinding,
    )
    from dynamic_agent_runner.workflow_host.model_materials import (
        parse_model_dependency_lock,
    )

    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "natural-language-workflow-authoring"
        / "floorplan-svg"
    )
    lock = parse_model_dependency_lock(
        json.loads((fixture / "model-materials.json").read_text(encoding="utf-8"))
    )
    binding = ModelExecutionBinding(
        logical_model_id=lock.logical_model_id,
        runner_contract_id=lock.runner_contract.contract_id,
        runner_contract_version=lock.runner_contract.version,
        loader_profile_contract_id=None,
        loader_profile_contract_version=None,
        material_lock_digest=lock.digest,
        capability_requirements_digest="a" * 64,
        runner_capability_id="model.execution.transformers-generate.v1",
        runner_capability_version="1",
        runner_capability_digest="b" * 64,
        execution_descriptor_digest="c" * 64,
        execution_abi_id="transformers-peft-generation-v1",
        execution_abi_version="1",
        execution_abi_contract_digest="d" * 64,
    )

    recipe = prepared_transformers_peft_recipe(lock=lock, binding=binding)

    assert recipe.model_id == lock.logical_model_id
    assert recipe.runner_id == "transformers-peft-v1"
    assert recipe.loader_profile == TRANSFORMERS_PEFT_SINGLE_IMAGE_V1
    assert tuple(item.role for item in recipe.artifacts) == tuple(
        source.role for source in lock.sources
    )


def test_catalog_rejects_incomplete_or_mismatched_transformers_peft_recipes() -> None:
    from dynamic_agent_runner.local_model_preparation import (
        LocalModelPreparationCatalog,
        LocalModelPreparationUnavailable,
        LocalModelPreparationRecipe,
        TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
    )

    recipe = QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE
    incomplete = LocalModelPreparationRecipe(
        model_id=recipe.model_id,
        adapter_id=recipe.adapter_id,
        runner_id="transformers-peft-v1",
        recipe_id=recipe.recipe_id,
        artifacts=recipe.artifacts[:-1],
        transformation=None,
        loader_profile=TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
    )
    mismatched = LocalModelPreparationRecipe(
        model_id=recipe.model_id,
        adapter_id=recipe.adapter_id,
        runner_id="llama-cpp-v1",
        recipe_id=recipe.recipe_id,
        artifacts=recipe.artifacts,
        transformation=None,
        loader_profile=TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
    )

    for candidate in (incomplete, mismatched):
        with pytest.raises(LocalModelPreparationUnavailable, match="recipe_invalid"):
            LocalModelPreparationCatalog((candidate,))


def test_transformers_peft_preparation_materializes_one_private_group_root(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_model_preparation import (
        LocalModelPreparationCatalog,
        LocalModelPreparationService,
    )

    content = b"fixture"
    recipe = replace(
        QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE,
        artifacts=tuple(
            replace(artifact, sha256=_digest(content))
            for artifact in QWEN25_VL_3B_FLOORPLAN_GRPO_TRANSFORMERS_PEFT_RECIPE.artifacts
        ),
    )
    external_cache = tmp_path / "external-cache"
    for artifact in recipe.artifacts:
        source = (
            external_cache
            / f"models--{artifact.repo_id.replace('/', '--')}"
            / "snapshots"
            / artifact.revision
            / artifact.filename
        )
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)
    service = LocalModelPreparationService(
        catalog=LocalModelPreparationCatalog((recipe,)),
        cache_root=tmp_path / "private-cache",
        approved_cache_roots=(external_cache,),
        download_file=lambda *_args: pytest.fail("must reuse verified cache files"),
    )

    assert (
        service.prepare(
            model_id=recipe.model_id,
            adapter_id=recipe.adapter_id,
            runner_id=recipe.runner_id,
            authorized=False,
        ).status
        == "preparation_not_authorized"
    )
    assert (
        service.prepare(
            model_id=recipe.model_id,
            adapter_id=recipe.adapter_id,
            runner_id=recipe.runner_id,
            authorized=True,
        ).status
        == "ready"
    )
    prepared = service.resolve(
        model_id=recipe.model_id,
        adapter_id=recipe.adapter_id,
        runner_id=recipe.runner_id,
    )
    assert all(
        path.parent == service.source_path(recipe, artifact).parent
        for artifact, path in zip(
            recipe.artifacts, prepared.paths.values(), strict=True
        )
    )


def test_public_preparation_status_never_contains_private_paths(tmp_path: Path) -> None:
    from dynamic_agent_runner.local_model_preparation import (
        LocalModelPreparationCatalog,
        LocalModelPreparationService,
    )

    result = LocalModelPreparationService(
        catalog=LocalModelPreparationCatalog((_recipe(),)),
        cache_root=tmp_path / "private-model-cache",
    ).prepare(
        model_id="example-floorplan",
        adapter_id="example-vision-adapter",
        authorized=False,
    )

    assert result.status == "preparation_not_authorized"
    assert result.model_id == "example-floorplan"
    assert str(tmp_path) not in repr(result)
    assert not hasattr(result, "paths")


def test_complete_preparation_cache_hits_without_downloading_or_conversion(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_model_preparation import (
        LocalModelPreparationCatalog,
        LocalModelPreparationService,
    )

    downloads: list[object] = []
    conversions: list[object] = []
    service = LocalModelPreparationService(
        catalog=LocalModelPreparationCatalog((_recipe(),)),
        cache_root=tmp_path / "cache",
        download_file=lambda reference, root: downloads.append((reference, root)),
        converter=lambda *_args: conversions.append("called"),
    )
    recipe = _recipe()
    for artifact in recipe.artifacts:  # type: ignore[union-attr]
        target = service.source_path(recipe, artifact)  # type: ignore[arg-type]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            {
                "base_model": b"base",
                "vision_projector": b"projector",
                "source_lora": b"adapter",
                "lora_metadata": b"metadata",
            }[artifact.role]
        )
    output = service.output_path(recipe)  # type: ignore[arg-type]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"GGUF converted")

    result = service.prepare(
        model_id="example-floorplan",
        adapter_id="example-vision-adapter",
        authorized=False,
    )

    assert result.status == "ready"
    assert downloads == []
    assert conversions == []
    assert (
        service.resolve(
            model_id="example-floorplan", adapter_id="example-vision-adapter"
        ).paths["adapter"]
        == output
    )


def test_partial_cache_requires_authority_before_any_download(tmp_path: Path) -> None:
    from dynamic_agent_runner.local_model_preparation import (
        LocalModelPreparationCatalog,
        LocalModelPreparationService,
    )

    downloads: list[object] = []
    service = LocalModelPreparationService(
        catalog=LocalModelPreparationCatalog((_recipe(),)),
        cache_root=tmp_path / "cache",
        download_file=lambda reference, root: downloads.append((reference, root)),
    )

    result = service.prepare(
        model_id="example-floorplan",
        adapter_id="example-vision-adapter",
        authorized=False,
    )

    assert result.status == "preparation_not_authorized"
    assert downloads == []


def test_downloads_only_declared_files_and_rejects_bad_conversion(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_model_preparation import (
        LocalModelPreparationCatalog,
        LocalModelPreparationService,
    )

    recipe = _recipe()
    downloads: list[tuple[object, Path]] = []

    def download(reference: object, root: Path) -> Path:
        downloads.append((reference, root))
        contents = {
            "base.gguf": b"base",
            "projector.gguf": b"projector",
            "adapter.safetensors": b"adapter",
            "adapter_config.json": b"metadata",
        }
        target = root / reference.filename  # type: ignore[union-attr]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents[reference.filename])  # type: ignore[union-attr]
        return target

    def bad_converter(_recipe: object, _sources: object, output: Path) -> None:
        output.write_bytes(b"not-a-gguf")

    service = LocalModelPreparationService(
        catalog=LocalModelPreparationCatalog((recipe,)),
        cache_root=tmp_path / "cache",
        download_file=download,
        converter=bad_converter,
    )

    result = service.prepare(
        model_id="example-floorplan",
        adapter_id="example-vision-adapter",
        authorized=True,
    )

    assert result.status == "integrity_failed"
    assert [item[0].filename for item in downloads] == [  # type: ignore[union-attr]
        "base.gguf",
        "projector.gguf",
        "adapter.safetensors",
        "adapter_config.json",
    ]
    assert not service.output_path(recipe).exists()


def test_pinned_converter_uses_uv_launcher_and_declared_inputs_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import dynamic_agent_runner.local_model_preparation as preparation
    from dynamic_agent_runner.local_model_preparation import PinnedLlamaCppLoraConverter

    checkout = tmp_path / "llama.cpp"
    checkout.mkdir()
    launcher = tmp_path / "launcher.py"
    launcher.write_text("# launcher\n", encoding="utf-8")
    sources = {
        "source_lora": tmp_path / "adapter.safetensors",
        "lora_metadata": tmp_path / "adapter_config.json",
        "base_configuration_metadata": tmp_path / "config.json",
    }
    for source in sources.values():
        source.write_bytes(b"source")
    calls: list[tuple[tuple[str, ...], Path]] = []
    monkeypatch.setattr(
        preparation, "_checkout_revision", lambda _checkout: "converter-revision"
    )

    PinnedLlamaCppLoraConverter(
        checkout=checkout,
        launcher=launcher,
        command_runner=lambda command, cwd: calls.append((tuple(command), cwd)),
    )(_recipe(), sources, tmp_path / "output.gguf")

    assert calls == [
        (
            (
                "uv",
                "run",
                "--script",
                str(launcher),
                "--converter-root",
                str(checkout),
                "--lora-model",
                str(sources["source_lora"]),
                "--lora-config",
                str(sources["lora_metadata"]),
                "--base-config",
                str(sources["base_configuration_metadata"]),
                "--output",
                str(tmp_path / "output.gguf"),
            ),
            checkout,
        )
    ]
