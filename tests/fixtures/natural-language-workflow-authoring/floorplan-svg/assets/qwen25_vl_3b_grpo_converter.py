"""Scenario-local Qwen image converter used only by the floorplan harness."""

from collections.abc import Callable, Mapping, Sequence
from io import BytesIO

from dynamic_agent_runner.errors import ModelExecutionError


ImageDecoder = Callable[[bytes], object]
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_IMAGE_PIXELS = 32_000_000


class Qwen25Vl3bGrpoInputConverter:
    """Pack one JPEG or PNG payload for this scenario's processor."""

    def __init__(self, *, image_decoder: ImageDecoder | None = None) -> None:
        self._image_decoder = image_decoder or _decode_image

    def pack(
        self,
        *,
        messages: Sequence[Mapping[str, object]],
        payload: bytes,
        context: object,
    ) -> object:
        image = self._decode_payload(payload)
        try:
            inputs = context.processor.apply_chat_template(  # type: ignore[attr-defined]
                _qwen_chat_messages(messages, image),
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            )
            return context.pack(inputs)  # type: ignore[attr-defined]
        except Exception as error:  # noqa: BLE001 - processor errors vary.
            raise ModelExecutionError("sealed image input is unavailable") from error

    def _decode_payload(self, payload: bytes) -> object:
        if not payload or len(payload) > _MAX_IMAGE_BYTES:
            raise ModelExecutionError("sealed image input is unavailable")
        try:
            image = self._image_decoder(payload)
            if (
                getattr(image, "format", None) not in {"JPEG", "PNG"}
                or not isinstance(getattr(image, "width", None), int)
                or not isinstance(getattr(image, "height", None), int)
                or image.width < 1
                or image.height < 1
                or image.width * image.height > _MAX_IMAGE_PIXELS
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


def _qwen_chat_messages(
    messages: Sequence[Mapping[str, object]], image: object
) -> list[dict[str, object]]:
    rendered: list[dict[str, object]] = []
    state = "system_or_initial_user"
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            raise ModelExecutionError("sealed image input is unavailable")
        if role == "system" and state == "system_or_initial_user":
            rendered.append({"role": role, "content": content})
        elif role == "user" and state == "system_or_initial_user":
            rendered.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": content},
                    ],
                }
            )
            state = "assistant_or_end"
        elif role == "assistant" and state == "assistant_or_end":
            rendered.append({"role": role, "content": content})
            state = "continuation_user"
        elif role == "user" and state == "continuation_user":
            rendered.append({"role": role, "content": content})
            state = "assistant_or_end"
        else:
            raise ModelExecutionError("sealed image input is unavailable")
    if state != "assistant_or_end":
        raise ModelExecutionError("sealed image input is unavailable")
    return rendered


converter_contract_version = "v1"
compatible_runner_contract_id = "transformers-generate-v1"
converter = Qwen25Vl3bGrpoInputConverter
