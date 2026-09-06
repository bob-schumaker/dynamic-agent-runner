"""Pinned llama.cpp vision binding for the image-to-floorplan workflow."""

from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.local_models import (
    LlamaCppLocalModelAdapter,
    LlamaCppLocalModelConfig,
)
from dynamic_agent_runner.openai_client import ModelResponse, OpenAIModelRequest


FLOORPLAN_VISION_MODEL_ID = "qwen25-vl-3b-floorplan-grpo"
FLOORPLAN_VISION_LLAMA_CPP_ADAPTER_ID = "floorplan-vision-llama-cpp-adapter-v1"


def create_floorplan_vision_qwen_config() -> LlamaCppLocalModelConfig:
    """Create the fixed offline model/projector configuration for floorplans."""

    return LlamaCppLocalModelConfig(
        model_aliases=(FLOORPLAN_VISION_MODEL_ID,),
        model_path=Path(".floorplan-vision-qwen-unset.gguf"),
        model_filename="qwen25-vl-3b-floorplan-grpo.gguf",
        expected_model_id=FLOORPLAN_VISION_MODEL_ID,
        allow_network=False,
        model_kwargs={
            "clip_model_path": ".floorplan-vision-projector-unset.gguf",
            "n_ctx": 2048,
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
        if not isinstance(projector, str) or not projector:
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


def create_floorplan_vision_llama_cpp_adapter() -> FloorplanVisionLlamaCppAdapter:
    """Create the fixed image-capable llama.cpp adapter."""

    return FloorplanVisionLlamaCppAdapter(create_floorplan_vision_qwen_config())
