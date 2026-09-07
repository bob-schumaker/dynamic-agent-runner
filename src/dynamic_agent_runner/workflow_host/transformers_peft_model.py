"""Generic local Transformers + PEFT single-image model adapter."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.local_model_preparation import (
    PreparedArtifactSet,
    TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
    _valid_loader_profile,
)
from dynamic_agent_runner.openai_client import ModelResponse, OpenAIModelRequest


class TransformersPeftBackend(Protocol):
    """Minimal normalized generation boundary for the standard runner."""

    def generate(self, prompt: str, image: object, *, max_new_tokens: int) -> str:
        """Generate one text response from one in-memory image."""


DependencyLoader = Callable[[Path, Path], TransformersPeftBackend]
ImageDecoder = Callable[[bytes], object]


class TransformersPeftSingleImageAdapter:
    """Expose the closed generic profile through DAR's existing adapter contract."""

    def __init__(
        self,
        prepared_set: PreparedArtifactSet,
        *,
        dependency_loader: DependencyLoader | None = None,
        image_decoder: ImageDecoder | None = None,
    ) -> None:
        if (
            prepared_set.recipe.loader_profile != TRANSFORMERS_PEFT_SINGLE_IMAGE_V1
            or not _valid_loader_profile(prepared_set.recipe)
        ):
            raise ModelExecutionError("prepared artifact set is incompatible")
        try:
            self._base = prepared_set.group_path("base")
            self._adapter = prepared_set.group_path("adapter")
        except KeyError as error:
            raise ModelExecutionError(
                "prepared artifact set is incompatible"
            ) from error
        self._dependency_loader = dependency_loader or _load_default_backend
        self._image_decoder = image_decoder or _decode_image
        self._model_id = prepared_set.recipe.model_id
        self._adapter_id = prepared_set.recipe.adapter_id
        self._backend: TransformersPeftBackend | None = None
        self._sealed_image: object | None = None

    @property
    def models(self) -> tuple[str, ...]:
        return (self._model_id,)

    @property
    def is_local(self) -> bool:
        return True

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"text_generation": True, "multimodal_input": True}

    @property
    def execution_profile_adapter_id(self) -> str:
        return self._adapter_id

    def resolved_model_id(self, model_id: str) -> str:
        return self._model_id if model_id == self._model_id else model_id

    def bind_sealed_image(self, *, content: bytes, media_type: str) -> None:
        if (
            not content
            or len(content) > 8 * 1024 * 1024
            or media_type not in {"image/jpeg", "image/png"}
            or self._sealed_image is not None
        ):
            raise ModelExecutionError("sealed image input is unavailable")
        try:
            self._sealed_image = _validate_decoded_image(self._image_decoder(content))
        except Exception as error:  # noqa: BLE001 - decoders vary.
            raise ModelExecutionError("sealed image input is unavailable") from error

    def clear_sealed_image(self) -> None:
        self._sealed_image = None

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        if self._sealed_image is None:
            raise ModelExecutionError("sealed image input is unavailable")
        image = self._sealed_image
        try:
            prompt = _user_prompt(request)
            max_new_tokens = _max_new_tokens(request)
            return ModelResponse(
                content=self._get_backend().generate(
                    prompt, image, max_new_tokens=max_new_tokens
                )
            )
        except ModelExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - backend errors vary.
            raise ModelExecutionError("local model generation failed") from error
        finally:
            self.clear_sealed_image()

    def _get_backend(self) -> TransformersPeftBackend:
        if self._backend is None:
            try:
                self._backend = self._dependency_loader(self._base, self._adapter)
            except ImportError as error:
                raise ModelExecutionError(
                    "Transformers + PEFT dependencies unavailable"
                ) from error
        return self._backend


def _user_prompt(request: OpenAIModelRequest) -> str:
    if len(request.messages) != 1:
        raise ModelExecutionError("model request must contain one user message")
    message = request.messages[0]
    prompt = message.get("content") if message.get("role") == "user" else None
    if not isinstance(prompt, str) or not prompt.strip():
        raise ModelExecutionError("model request has no user message")
    return prompt


def _max_new_tokens(request: OpenAIModelRequest) -> int:
    value = request.extra.get("max_tokens", 1024)
    if not isinstance(value, int) or not 1 <= value <= 1024:
        raise ModelExecutionError("model generation limit is invalid")
    return value


def _decode_image(content: bytes) -> object:
    from io import BytesIO

    from PIL import Image

    image = Image.open(BytesIO(content))
    return image.copy()


def _validate_decoded_image(image: object) -> object:
    width = getattr(image, "width", None)
    height = getattr(image, "height", None)
    if (
        not isinstance(width, int)
        or not isinstance(height, int)
        or width < 1
        or height < 1
        or width * height > 32_000_000
    ):
        raise ValueError("image is invalid")
    return image


def _load_default_backend(base: Path, adapter: Path) -> TransformersPeftBackend:
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(
        base, local_files_only=True, trust_remote_code=False
    )
    model_arguments: dict[str, object] = {
        "local_files_only": True,
        "trust_remote_code": False,
        "torch_dtype": "auto",
    }
    if _mps_available():
        model = AutoModelForImageTextToText.from_pretrained(base, **model_arguments)
        model.to("mps")
    else:
        model = AutoModelForImageTextToText.from_pretrained(
            base, device_map="auto", **model_arguments
        )
    return _LoadedTransformersPeftBackend(
        model=PeftModel.from_pretrained(
            model, adapter, is_trainable=False, local_files_only=True
        ),
        processor=processor,
    )


def _mps_available() -> bool:
    try:
        import torch

        return torch.backends.mps.is_available()
    except (AttributeError, ImportError):
        return False


class _LoadedTransformersPeftBackend:
    """Run the documented standard multimodal chat-template flow locally."""

    def __init__(self, *, model: object, processor: object) -> None:
        self._model = model
        self._processor = processor

    def generate(self, prompt: str, image: object, *, max_new_tokens: int) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        inputs = self._processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        )
        generated = self._model.generate(
            **inputs.to(self._model.device),
            do_sample=False,
            max_new_tokens=max_new_tokens,
        )
        prefix_length = inputs["input_ids"].shape[1]
        decoded = self._processor.batch_decode(
            generated[:, prefix_length:], skip_special_tokens=True
        )
        if not decoded or not isinstance(decoded[0], str) or not decoded[0].strip():
            raise ModelExecutionError("local model returned an empty response")
        return decoded[0].strip()


class DeferredTransformersPeftSingleImageAdapter:
    """Resolve the verified set only when the workflow consumes sealed input."""

    def __init__(
        self,
        *,
        model_id: str,
        adapter_id: str,
        resolve_prepared_set: Callable[[], PreparedArtifactSet],
    ) -> None:
        self._model_id = model_id
        self._adapter_id = adapter_id
        self._resolve_prepared_set = resolve_prepared_set
        self._adapter: TransformersPeftSingleImageAdapter | None = None

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"text_generation": True, "multimodal_input": True}

    @property
    def execution_profile_adapter_id(self) -> str:
        return self._adapter_id

    @property
    def models(self) -> tuple[str, ...]:
        return (self._model_id,)

    @property
    def is_local(self) -> bool:
        return True

    def resolved_model_id(self, model_id: str) -> str:
        return self._model_id if model_id == self._model_id else model_id

    def bind_sealed_image(self, *, content: bytes, media_type: str) -> None:
        self._resolved_adapter().bind_sealed_image(
            content=content, media_type=media_type
        )

    def clear_sealed_image(self) -> None:
        if self._adapter is not None:
            self._adapter.clear_sealed_image()

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        return self._resolved_adapter().create_response(request)

    def _resolved_adapter(self) -> TransformersPeftSingleImageAdapter:
        if self._adapter is None:
            self._adapter = TransformersPeftSingleImageAdapter(
                self._resolve_prepared_set()
            )
        return self._adapter
