"""Pinned llama.cpp vision binding for the image-to-floorplan workflow."""

from __future__ import annotations

import base64
from dataclasses import replace
from collections.abc import Callable
from pathlib import Path

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.local_model_preparation import (
    FLOORPLAN_VISION_RECIPE,
    PreparedArtifactSet,
)
from dynamic_agent_runner.local_models import (
    LlamaCppLocalModelAdapter,
    LlamaCppLocalModelConfig,
)
from dynamic_agent_runner.openai_client import ModelResponse, OpenAIModelRequest


FLOORPLAN_VISION_MODEL_ID = "qwen25-vl-3b-floorplan-grpo"
FLOORPLAN_VISION_LLAMA_CPP_ADAPTER_ID = "floorplan-vision-llama-cpp-adapter-v1"


def create_floorplan_vision_qwen_config(
    prepared_set: PreparedArtifactSet,
) -> LlamaCppLocalModelConfig:
    """Create the fixed offline configuration from one verified private set."""

    if prepared_set.recipe != FLOORPLAN_VISION_RECIPE:
        raise ModelExecutionError("floorplan prepared artifact set is unavailable")
    try:
        model_path = prepared_set.paths["base_model"]
        projector_path = prepared_set.paths["vision_projector"]
        lora_path = prepared_set.paths["adapter"]
    except KeyError as error:
        raise ModelExecutionError(
            "floorplan prepared artifact set is unavailable"
        ) from error

    return LlamaCppLocalModelConfig(
        model_aliases=(FLOORPLAN_VISION_MODEL_ID,),
        model_path=model_path,
        model_filename="qwen25-vl-3b-floorplan-grpo.gguf",
        huggingface_file=FLOORPLAN_VISION_RECIPE.artifacts[0].reference(),
        expected_model_id=FLOORPLAN_VISION_MODEL_ID,
        allow_network=False,
        model_kwargs={
            "clip_model_path": str(projector_path),
            "lora_path": str(lora_path),
            "n_ctx": 16384,
            "n_gpu_layers": -1,
            "verbose": False,
        },
    )


class FloorplanVisionLlamaCppAdapter(LlamaCppLocalModelAdapter):
    """Deliver one sealed image to the fixed local vision model and no other adapter."""

    def __init__(self, config: LlamaCppLocalModelConfig) -> None:
        super().__init__(config)
        self._sealed_image: tuple[bytes, str] | None = None

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"text_generation": True, "multimodal_input": True}

    @property
    def execution_profile_adapter_id(self) -> str:
        return FLOORPLAN_VISION_LLAMA_CPP_ADAPTER_ID

    def resolved_model_id(self, model_id: str) -> str:
        return (
            FLOORPLAN_VISION_MODEL_ID
            if model_id == FLOORPLAN_VISION_MODEL_ID
            else model_id
        )

    def bind_sealed_image(self, *, content: bytes, media_type: str) -> None:
        """Bind verified image bytes for the immediately following model request."""

        if not content or not media_type.startswith("image/"):
            raise ModelExecutionError("sealed image input is unavailable")
        projector = (self._config.model_kwargs or {}).get("clip_model_path")
        if (
            not isinstance(projector, str)
            or not projector
            or not Path(projector).is_file()
        ):
            raise ModelExecutionError("llama.cpp vision projector is unavailable")
        self._sealed_image = (content, media_type)

    def clear_sealed_image(self) -> None:
        """Discard image bytes after the enclosing workflow run."""

        self._sealed_image = None

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Attach the sealed image to a user message immediately before dispatch."""

        if self._sealed_image is None:
            raise ModelExecutionError("sealed image input is unavailable")
        content, media_type = self._sealed_image
        data_url = (
            f"data:{media_type};base64,{base64.b64encode(content).decode('ascii')}"
        )
        messages = list(request.messages)
        for index, message in enumerate(messages):
            if message.get("role") == "user" and isinstance(
                message.get("content"), str
            ):
                messages[index] = {
                    **message,
                    "content": [
                        {"type": "text", "text": message["content"]},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
                return super().create_response(
                    replace(request, messages=tuple(messages))
                )
        raise ModelExecutionError("vision request has no user message")


class DeferredFloorplanVisionLlamaCppAdapter:
    """Resolve a verified set only when a sealed floorplan request is executed."""

    def __init__(self, resolve_prepared_set: Callable[[], PreparedArtifactSet]) -> None:
        self._resolve_prepared_set = resolve_prepared_set
        self._adapter: FloorplanVisionLlamaCppAdapter | None = None

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"text_generation": True, "multimodal_input": True}

    @property
    def execution_profile_adapter_id(self) -> str:
        return FLOORPLAN_VISION_LLAMA_CPP_ADAPTER_ID

    @property
    def models(self) -> tuple[str, ...]:
        return (FLOORPLAN_VISION_MODEL_ID,)

    @property
    def is_local(self) -> bool:
        return True

    def resolved_model_id(self, model_id: str) -> str:
        return (
            FLOORPLAN_VISION_MODEL_ID
            if model_id == FLOORPLAN_VISION_MODEL_ID
            else model_id
        )

    def bind_sealed_image(self, *, content: bytes, media_type: str) -> None:
        self._resolved_adapter().bind_sealed_image(
            content=content, media_type=media_type
        )

    def clear_sealed_image(self) -> None:
        if self._adapter is not None:
            self._adapter.clear_sealed_image()

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        return self._resolved_adapter().create_response(request)

    def _resolved_adapter(self) -> FloorplanVisionLlamaCppAdapter:
        if self._adapter is None:
            self._adapter = create_floorplan_vision_llama_cpp_adapter(
                self._resolve_prepared_set()
            )
        return self._adapter


def create_floorplan_vision_llama_cpp_adapter(
    prepared_set: PreparedArtifactSet,
) -> FloorplanVisionLlamaCppAdapter:
    """Create the fixed image-capable adapter from a verified private set."""

    return FloorplanVisionLlamaCppAdapter(
        create_floorplan_vision_qwen_config(prepared_set)
    )
