"""Trusted Qwen 2.5 VL 3B GRPO image input converter fixture."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.workflow_host.transformers_peft_model import (
    PackedModelInput,
    TransformersGenerateInputContext,
)


ImageDecoder = Callable[[bytes], object]
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_IMAGE_PIXELS = 32_000_000


class Qwen25Vl3bGrpoInputConverter:
    """Pack one JPEG or PNG payload for the matching Qwen processor."""

    def __init__(self, *, image_decoder: ImageDecoder | None = None) -> None:
        self._image_decoder = image_decoder or _decode_image

    def pack(
        self,
        *,
        prompt: str,
        payload: bytes,
        context: TransformersGenerateInputContext,
    ) -> PackedModelInput:
        """Decode and pack one sealed payload without exposing its format to DAR."""

        image = self._decode_payload(payload)
        try:
            inputs = context.processor.apply_chat_template(  # type: ignore[attr-defined]
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": image},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            )
        except Exception as error:  # noqa: BLE001 - processor errors vary.
            raise ModelExecutionError("sealed image input is unavailable") from error
        return context.pack(inputs)

    def _decode_payload(self, payload: bytes) -> object:
        if not payload or len(payload) > _MAX_IMAGE_BYTES:
            raise ModelExecutionError("sealed image input is unavailable")
        try:
            image = self._image_decoder(payload)
            image_format = getattr(image, "format", None)
            width = getattr(image, "width", None)
            height = getattr(image, "height", None)
            if (
                image_format not in {"JPEG", "PNG"}
                or not isinstance(width, int)
                or not isinstance(height, int)
                or width < 1
                or height < 1
                or width * height > _MAX_IMAGE_PIXELS
            ):
                raise ValueError("image is invalid")
        except Exception as error:  # noqa: BLE001 - decoders vary.
            raise ModelExecutionError("sealed image input is unavailable") from error
        return image


def _decode_image(payload: bytes) -> object:
    from PIL import Image

    image = Image.open(BytesIO(payload))
    image.load()
    return image
