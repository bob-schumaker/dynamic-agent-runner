"""Tests for the pinned local Qwen binding used by Fastmail triage."""

from __future__ import annotations

from pathlib import Path

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request


def test_fastmail_triage_qwen_binding_is_pinned_and_offline(tmp_path: Path) -> None:
    from dynamic_agent_runner.workflow_host.fastmail_triage_model import (
        FASTMAIL_TRIAGE_MODEL_ALIAS,
        create_fastmail_triage_qwen_config,
    )

    config = create_fastmail_triage_qwen_config(
        model_path=tmp_path / "qwen.gguf",
        model_kwargs={"chat_format": "chatml-function-calling", "n_ctx": 8192},
    )

    assert config.model_aliases == (FASTMAIL_TRIAGE_MODEL_ALIAS,)
    assert config.allow_network is False
    assert config.expected_model_sha256 == (
        "626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d"
    )
    assert config.huggingface_file is not None
    assert config.huggingface_file.repo_id == "Qwen/Qwen2.5-3B-Instruct-GGUF"
    assert (
        config.huggingface_file.revision == "7dabda4d13d513e3e842b20f0d435c732f172cbe"
    )


def test_floorplan_vision_adapter_sends_only_sealed_image_bytes_to_llama_cpp(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.floorplan_vision_model import (
        FLOORPLAN_VISION_MODEL_ID,
        FloorplanVisionLlamaCppAdapter,
        create_floorplan_vision_qwen_config,
    )
    from dynamic_agent_runner.local_model_preparation import (
        FLOORPLAN_VISION_RECIPE,
        PreparedArtifactSet,
    )

    class FakeBackend:
        model_id = FLOORPLAN_VISION_MODEL_ID

        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def create_chat_completion(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            return {"choices": [{"message": {"content": "<svg/>"}}]}

    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"fake")
    projector_path = tmp_path / "projector.gguf"
    projector_path.write_bytes(b"fake projector")
    adapter = FloorplanVisionLlamaCppAdapter(
        create_floorplan_vision_qwen_config(
            PreparedArtifactSet(
                recipe=FLOORPLAN_VISION_RECIPE,
                paths={
                    "base_model": model_path,
                    "vision_projector": projector_path,
                    "adapter": tmp_path / "adapter.gguf",
                },
            )
        )
    )
    backend = FakeBackend()
    adapter._backend = backend  # type: ignore[assignment]
    adapter.bind_sealed_image(content=b"image-bytes", media_type="image/png")

    adapter.create_response(
        build_openai_request(
            model=FLOORPLAN_VISION_MODEL_ID,
            messages=[OpenAIMessage("user", "create a floorplan")],
        )
    )

    content = backend.calls[0]["messages"][0]["content"]  # type: ignore[index]
    assert content[1]["image_url"]["url"] == "data:image/png;base64,aW1hZ2UtYnl0ZXM="  # type: ignore[index]
    assert str(tmp_path) not in repr(content)


def test_floorplan_vision_adapter_rejects_a_missing_projector_before_model_call() -> (
    None
):
    from dynamic_agent_runner.workflow_host.floorplan_vision_model import (
        FloorplanVisionLlamaCppAdapter,
        create_floorplan_vision_qwen_config,
    )
    from dynamic_agent_runner.local_model_preparation import (
        FLOORPLAN_VISION_RECIPE,
        PreparedArtifactSet,
    )

    adapter = FloorplanVisionLlamaCppAdapter(
        create_floorplan_vision_qwen_config(
            PreparedArtifactSet(
                recipe=FLOORPLAN_VISION_RECIPE,
                paths={
                    "base_model": Path("missing-base.gguf"),
                    "vision_projector": Path("missing-projector.gguf"),
                    "adapter": Path("missing-adapter.gguf"),
                },
            )
        )
    )

    with pytest.raises(ModelExecutionError, match="projector"):
        adapter.bind_sealed_image(content=b"image-bytes", media_type="image/png")


def test_floorplan_vision_config_uses_only_a_verified_prepared_set(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_model_preparation import (
        FLOORPLAN_VISION_RECIPE,
        PreparedArtifactSet,
    )
    from dynamic_agent_runner.workflow_host.floorplan_vision_model import (
        create_floorplan_vision_qwen_config,
    )

    paths = {
        "base_model": tmp_path / "base.gguf",
        "vision_projector": tmp_path / "projector.gguf",
        "adapter": tmp_path / "adapter.gguf",
    }
    config = create_floorplan_vision_qwen_config(
        PreparedArtifactSet(recipe=FLOORPLAN_VISION_RECIPE, paths=paths)
    )

    assert config.model_path == paths["base_model"]
    assert config.huggingface_file == FLOORPLAN_VISION_RECIPE.artifacts[0].reference()
    assert config.allow_network is False
    assert config.model_kwargs == {
        "clip_model_path": str(paths["vision_projector"]),
        "lora_path": str(paths["adapter"]),
        "n_ctx": 16384,
        "n_gpu_layers": -1,
        "verbose": False,
    }


def test_floorplan_vision_config_rejects_a_mismatched_prepared_set(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.local_model_preparation import (
        LocalModelPreparationRecipe,
        LocalModelTransformation,
        PreparedArtifactSet,
    )
    from dynamic_agent_runner.workflow_host.floorplan_vision_model import (
        create_floorplan_vision_qwen_config,
    )

    mismatched = PreparedArtifactSet(
        recipe=LocalModelPreparationRecipe(
            model_id="other",
            adapter_id="other",
            artifacts=(),
            transformation=LocalModelTransformation(
                converter_revision="other",
                output_role="adapter",
                output_filename="other.gguf",
                output_sha256="0" * 64,
            ),
        ),
        paths={"base_model": tmp_path / "base.gguf"},
    )

    with pytest.raises(ModelExecutionError, match="prepared artifact set"):
        create_floorplan_vision_qwen_config(mismatched)
