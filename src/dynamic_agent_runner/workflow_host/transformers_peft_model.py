"""Generic local Transformers + PEFT single-image model adapter."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.local_model_preparation import (
    PreparedArtifactSet,
    TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
    _valid_loader_profile,
)
from dynamic_agent_runner.openai_client import ModelResponse, OpenAIModelRequest
from dynamic_agent_runner.workflow_host.descriptor import DeclaredInputConverter


TRANSFORMERS_GENERATE_V1 = "transformers-generate-v1"
_CONTINUATION_INSTRUCTION = (
    "Continue the exact response from where it stopped. Return only the remaining text."
)
_MAX_CONTINUATIONS = 3


class TransformersPeftBackend(Protocol):
    """Minimal normalized generation boundary for the standard runner."""

    def generate(self, prompt: str, image: object, *, max_new_tokens: int) -> str:
        """Generate one text response from one in-memory image."""


class TransformersGenerateBackend(Protocol):
    """Private packed-input boundary for the standard runner."""

    @property
    def processor(self) -> object:
        """Return the reviewed processor used by the compatible converter."""

    def generate_packed(
        self, inputs: object, *, max_new_tokens: int, json_mode: bool = False
    ) -> str | GeneratedText:
        """Generate one response from converter-packed framework inputs."""


class PackedInputConverter(Protocol):
    """One workflow-bound converter compatible with the standard runner."""

    def pack(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        payload: bytes,
        context: TransformersGenerateInputContext,
    ) -> PackedModelInput:
        """Return one private packed input for the compatible runner."""


@dataclass(frozen=True)
class GeneratedText:
    """One private generated fragment with its token-ceiling outcome."""

    content: str
    exhausted: bool
    generated_tokens: int | None = None


@dataclass(frozen=True)
class GeneratedCompletion:
    """One assembled completion with safe generation metadata."""

    content: str
    metadata: Mapping[str, object]


DependencyLoader = Callable[[Path, Path], TransformersPeftBackend]
PackedDependencyLoader = Callable[[Path, Path], TransformersGenerateBackend]
ImageDecoder = Callable[[bytes], object]


class PackedModelInput:
    """One worker-private packed input that the runner consumes exactly once."""

    def __init__(self, inputs: object) -> None:
        self._inputs: object | None = inputs

    @property
    def is_cleared(self) -> bool:
        """Return whether this private input has been disposed."""

        return self._inputs is None

    def take(self) -> object:
        """Return the packed value until the runner clears it."""

        if self._inputs is None:
            raise ModelExecutionError("packed model input is unavailable")
        return self._inputs

    def clear(self) -> None:
        """Discard the private packed framework value."""

        self._inputs = None


class TransformersGenerateInputContext:
    """Restricted processor and packing facilities for a compatible converter."""

    def __init__(self, processor: object) -> None:
        self._processor = processor

    @property
    def processor(self) -> object:
        """Return the reviewed processor for this exact prepared model set."""

        return self._processor

    def pack(self, inputs: object) -> PackedModelInput:
        """Wrap one processor-produced value for the standard runner."""

        return PackedModelInput(inputs)


class TransformersGenerateRunner:
    """Run one verified Transformers + PEFT set from private packed inputs."""

    contract_id = TRANSFORMERS_GENERATE_V1
    supports_json_mode = True

    def __init__(
        self,
        prepared_set: PreparedArtifactSet,
        *,
        dependency_loader: PackedDependencyLoader | None = None,
    ) -> None:
        self._base, self._adapter = _verified_prepared_paths(prepared_set)
        self._dependency_loader = dependency_loader or _load_default_backend
        self._backend: TransformersGenerateBackend | None = None

    @property
    def processor(self) -> object:
        """Expose the reviewed processor and no model-loading controls."""

        return self._get_backend().processor

    @property
    def input_context(self) -> TransformersGenerateInputContext:
        """Return the restricted converter context for this runner."""

        return TransformersGenerateInputContext(self.processor)

    def generate(
        self,
        packed_input: PackedModelInput,
        *,
        max_new_tokens: int,
        json_mode: bool = False,
    ) -> str:
        """Consume one packed input and clear it on every exit path."""

        generated = self.generate_chunk(
            packed_input,
            max_new_tokens=max_new_tokens,
            json_mode=json_mode,
        )
        completion = generated.content.strip()
        return _validated_json_object(completion) if json_mode else completion

    def generate_chunk(
        self,
        packed_input: PackedModelInput,
        *,
        max_new_tokens: int,
        json_mode: bool = False,
    ) -> GeneratedText:
        """Generate one private fragment and report whether it hit its ceiling."""

        try:
            _validate_max_new_tokens(max_new_tokens)
            backend = self._get_backend()
            if json_mode:
                generated = backend.generate_packed(
                    packed_input.take(),
                    max_new_tokens=max_new_tokens,
                    json_mode=True,
                )
            else:
                generated = backend.generate_packed(
                    packed_input.take(), max_new_tokens=max_new_tokens
                )
            return _generated_text(generated)
        except ModelExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - backend errors vary.
            raise ModelExecutionError("local model generation failed") from error
        finally:
            packed_input.clear()

    def _get_backend(self) -> TransformersGenerateBackend:
        if self._backend is None:
            try:
                self._backend = self._dependency_loader(self._base, self._adapter)
            except ImportError as error:
                raise ModelExecutionError(
                    "Transformers + PEFT dependencies unavailable"
                ) from error
        return self._backend

    @property
    def uses_mps(self) -> bool:
        """Return whether the loaded backend selected the Apple MPS device."""

        return bool(getattr(self._get_backend(), "uses_mps", False))


class TransformersPeftPackedInputAdapter:
    """Expose one converter-bound Transformers generation runner as an adapter."""

    input_converter_contract_id = TRANSFORMERS_GENERATE_V1

    def __init__(
        self,
        prepared_set: PreparedArtifactSet,
        *,
        converter: PackedInputConverter,
        runner: TransformersGenerateRunner | None = None,
    ) -> None:
        _verified_prepared_paths(prepared_set)
        self._model_id = prepared_set.recipe.model_id
        self._adapter_id = prepared_set.recipe.adapter_id
        self._converter = converter
        self._runner = runner or TransformersGenerateRunner(prepared_set)
        self._sealed_payload: bytes | None = None

    @property
    def models(self) -> tuple[str, ...]:
        return (self._model_id,)

    @property
    def is_local(self) -> bool:
        return True

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "text_generation": True,
            "multimodal_input": True,
            "json_mode": bool(getattr(self._runner, "supports_json_mode", False)),
        }

    @property
    def execution_profile_adapter_id(self) -> str:
        return self._adapter_id

    def resolved_model_id(self, model_id: str) -> str:
        return self._model_id if model_id == self._model_id else model_id

    def bind_sealed_payload(self, *, content: bytes) -> None:
        if not content or self._sealed_payload is not None:
            raise ModelExecutionError("sealed converter input is unavailable")
        self._sealed_payload = content

    def clear_sealed_payload(self) -> None:
        self._sealed_payload = None

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        if self._sealed_payload is None:
            raise ModelExecutionError("sealed converter input is unavailable")
        payload = self._sealed_payload
        try:
            json_mode = _json_mode_requested(
                request.response_format,
                supported=bool(getattr(self._runner, "supports_json_mode", False)),
            )
            generation_kwargs: dict[str, object] = {
                "max_new_tokens": _max_new_tokens(request)
            }
            if json_mode:
                generation_kwargs["json_mode"] = True
            messages = tuple(request.messages)
            max_continuations = _max_continuations(request)
            if max_continuations:
                completion = self._generate_with_continuations(
                    messages=messages,
                    payload=payload,
                    max_continuations=max_continuations,
                    **generation_kwargs,
                )
                return ModelResponse(
                    content=completion.content,
                    metadata=completion.metadata,
                )
            packed = self._converter.pack(
                messages=messages,
                payload=payload,
                context=self._runner.input_context,
            )
            if bool(getattr(self._runner, "uses_mps", False)):
                generated = self._runner.generate_chunk(packed, **generation_kwargs)
                content = generated.content.strip()
                if json_mode:
                    content = _validated_json_object(content)
                return ModelResponse(
                    content=content,
                    metadata={
                        "generation": {
                            "device": "mps",
                            "chunk_count": 1,
                            "chunk_exhausted": [generated.exhausted],
                            "generated_tokens": [generated.generated_tokens],
                        }
                    },
                )
            return ModelResponse(
                content=self._runner.generate(packed, **generation_kwargs)
            )
        except ModelExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - converter errors vary.
            raise ModelExecutionError("local model generation failed") from error
        finally:
            self.clear_sealed_payload()

    def _generate_with_continuations(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        payload: bytes,
        max_new_tokens: int,
        max_continuations: int,
        json_mode: bool = False,
    ) -> GeneratedCompletion:
        fragments: list[str] = []
        chunk_exhausted: list[bool] = []
        generated_tokens: list[int | None] = []
        continuation_messages = messages
        for continuation in range(max_continuations + 1):
            packed = self._converter.pack(
                messages=continuation_messages,
                payload=payload,
                context=self._runner.input_context,
            )
            generated = self._runner.generate_chunk(
                packed,
                max_new_tokens=max_new_tokens,
                json_mode=json_mode,
            )
            fragments.append(generated.content)
            chunk_exhausted.append(generated.exhausted)
            generated_tokens.append(generated.generated_tokens)
            completion = "".join(fragments).strip()
            incomplete_json = json_mode and _is_incomplete_json_object(completion)
            if not generated.exhausted and not incomplete_json:
                content = (
                    _validated_json_object(completion) if json_mode else completion
                )
                generation: dict[str, object] = {
                    "chunk_count": len(fragments),
                    "chunk_exhausted": chunk_exhausted,
                    "generated_tokens": generated_tokens,
                }
                if bool(getattr(self._runner, "uses_mps", False)):
                    generation["device"] = "mps"
                return GeneratedCompletion(
                    content=content, metadata={"generation": generation}
                )
            if continuation == max_continuations:
                raise ModelExecutionError("local model continuation limit exceeded")
            continuation_messages = (
                *continuation_messages,
                {"role": "assistant", "content": generated.content},
                {"role": "user", "content": _CONTINUATION_INSTRUCTION},
            )
        raise AssertionError("continuation loop must return or raise")


class TransformersPeftSingleImageAdapter:
    """Expose the closed generic profile through DAR's existing adapter contract."""

    def __init__(
        self,
        prepared_set: PreparedArtifactSet,
        *,
        dependency_loader: DependencyLoader | None = None,
        image_decoder: ImageDecoder | None = None,
    ) -> None:
        self._base, self._adapter = _verified_prepared_paths(prepared_set)
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
        return {"text_generation": True, "multimodal_input": True, "json_mode": False}

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
    user_messages = [
        message for message in request.messages if message.get("role") == "user"
    ]
    if len(user_messages) != 1:
        raise ModelExecutionError("model request must contain one user message")
    prompt = user_messages[0].get("content")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ModelExecutionError("model request has no user message")
    return prompt


def _max_new_tokens(request: OpenAIModelRequest) -> int:
    value = request.extra.get("max_tokens", 1024)
    _validate_max_new_tokens(value)
    return value


def _max_continuations(request: OpenAIModelRequest) -> int:
    value = request.extra.get("max_continuations", 0)
    if not isinstance(value, int) or not 0 <= value <= _MAX_CONTINUATIONS:
        raise ModelExecutionError("model continuation limit is invalid")
    return value


def _validate_max_new_tokens(value: object) -> None:
    if not isinstance(value, int) or not 1 <= value <= 4096:
        raise ModelExecutionError("model generation limit is invalid")


def _json_mode_requested(
    response_format: Mapping[str, object] | None, *, supported: bool
) -> bool:
    if response_format is None:
        return False
    if dict(response_format) != {"type": "json_object"}:
        raise ModelExecutionError("local model response format is unsupported")
    if not supported:
        raise ModelExecutionError("local model runner does not support JSON mode")
    return True


def _validated_json_object(value: str) -> str:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as error:
        raise ModelExecutionError("local model returned invalid JSON") from error
    if not isinstance(parsed, dict):
        raise ModelExecutionError("local model returned invalid JSON")
    return value


def _is_incomplete_json_object(value: str) -> bool:
    """Return whether a JSON object prefix ends only because it is incomplete."""

    normalized = value.rstrip()
    try:
        json.loads(normalized)
    except json.JSONDecodeError as error:
        return error.pos == len(normalized)
    return False


def _generated_text(value: str | GeneratedText) -> GeneratedText:
    if isinstance(value, GeneratedText):
        return value
    if not isinstance(value, str):
        raise ModelExecutionError("local model returned an invalid response")
    return GeneratedText(value, exhausted=False)


def _generation_exhausted(
    generated: object, prefix_length: int, max_new_tokens: int
) -> bool:
    shape = getattr(generated, "shape", None)
    try:
        return shape[1] - prefix_length >= max_new_tokens
    except (IndexError, TypeError):
        return False


def _generated_token_count(generated: object, prefix_length: int) -> int | None:
    shape = getattr(generated, "shape", None)
    try:
        return shape[1] - prefix_length
    except (IndexError, TypeError):
        return None


def _json_mode_prefix_filter(processor: object) -> object:
    try:
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.tokenenforcer import (
            TokenEnforcer,
            TokenEnforcerTokenizerData,
        )

        tokenizer = processor.tokenizer  # type: ignore[attr-defined]
        token_zero = tokenizer.encode("0")[-1]
        regular_tokens = []
        for token_id in range(len(tokenizer)):
            if token_id in tokenizer.all_special_ids:
                continue
            after_zero = tokenizer.decode([token_zero, token_id])[1:]
            decoded = tokenizer.decode([token_id])
            regular_tokens.append(
                (token_id, after_zero, len(after_zero) > len(decoded))
            )
        token_data = TokenEnforcerTokenizerData(
            regular_tokens,
            lambda tokens: tokenizer.decode(tokens).rstrip("�"),
            tokenizer.eos_token_id,
            False,
            len(tokenizer),
        )
        return _TransformersPrefixAllowedTokensFn(
            TokenEnforcer(token_data, JsonSchemaParser(None))
        )
    except (AttributeError, ImportError, TypeError, ValueError) as error:
        raise ModelExecutionError("local model JSON mode is unavailable") from error


class _TransformersPrefixAllowedTokensFn:
    """Adapt lm-format-enforcer to Transformers' public tokenizer API."""

    def __init__(self, token_enforcer: object) -> None:
        self._token_enforcer = token_enforcer

    def __call__(self, _batch_id: int, sent: object) -> list[int]:
        tokens = sent.tolist()  # type: ignore[attr-defined]
        allowed = self._token_enforcer.get_allowed_tokens(tokens)
        return list(allowed.allowed_tokens)


def _verified_prepared_paths(prepared_set: PreparedArtifactSet) -> tuple[Path, Path]:
    if (
        prepared_set.recipe.loader_profile != TRANSFORMERS_PEFT_SINGLE_IMAGE_V1
        or not _valid_loader_profile(prepared_set.recipe)
    ):
        raise ModelExecutionError("prepared artifact set is incompatible")
    try:
        return prepared_set.group_path("base"), prepared_set.group_path("adapter")
    except KeyError as error:
        raise ModelExecutionError("prepared artifact set is incompatible") from error


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
    mps = _mps_available()
    if mps:
        model = AutoModelForImageTextToText.from_pretrained(base, **model_arguments)
    else:
        model = AutoModelForImageTextToText.from_pretrained(
            base, device_map="auto", **model_arguments
        )
    model = PeftModel.from_pretrained(
        model, adapter, is_trainable=False, local_files_only=True
    )
    if mps:
        model.to("mps")
        model.eval()
    return _LoadedTransformersPeftBackend(
        model=model,
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

    @property
    def processor(self) -> object:
        """Expose only the reviewed processor to the converter contract."""

        return self._processor

    @property
    def uses_mps(self) -> bool:
        """Return whether this loaded model is executing on Apple MPS."""

        return str(getattr(self._model, "device", "")).split(":", 1)[0] == "mps"

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
        return self.generate_packed(
            inputs, max_new_tokens=max_new_tokens
        ).content.strip()

    def generate_packed(
        self, inputs: object, *, max_new_tokens: int, json_mode: bool = False
    ) -> GeneratedText:
        """Generate from converter-owned processor inputs within one worker."""

        move = getattr(inputs, "to", None)
        try:
            input_ids = inputs["input_ids"]  # type: ignore[index]
            packed = move(self._model.device) if callable(move) else inputs
            prefix_length = input_ids.shape[1]
        except (AttributeError, KeyError, TypeError, IndexError) as error:
            raise ModelExecutionError("packed model input is invalid") from error
        generation_kwargs: dict[str, object] = {
            "do_sample": False,
            "max_new_tokens": max_new_tokens,
        }
        if json_mode:
            generation_kwargs["prefix_allowed_tokens_fn"] = _json_mode_prefix_filter(
                self._processor
            )
        import torch

        with torch.inference_mode():
            generated = self._model.generate(
                **packed,
                **generation_kwargs,
            )
        decoded = self._processor.batch_decode(
            generated[:, prefix_length:], skip_special_tokens=True
        )
        if not decoded or not isinstance(decoded[0], str) or not decoded[0].strip():
            raise ModelExecutionError("local model returned an empty response")
        generated_tokens = _generated_token_count(generated, prefix_length)
        return GeneratedText(
            decoded[0],
            exhausted=_generation_exhausted(generated, prefix_length, max_new_tokens),
            generated_tokens=generated_tokens,
        )


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
        self._packed_adapter: TransformersPeftPackedInputAdapter | None = None
        self._converter: PackedInputConverter | None = None
        self._payload_bound = False

    @property
    def input_converter_contract_id(self) -> str:
        return TRANSFORMERS_GENERATE_V1

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"text_generation": True, "multimodal_input": True, "json_mode": True}

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

    def bind_input_converter(
        self, *, package_root: Path, converter: DeclaredInputConverter
    ) -> None:
        """Load the exact manifest-bound converter before accepting payload bytes."""

        if (
            self._payload_bound
            or converter.compatible_runner_contract_id != TRANSFORMERS_GENERATE_V1
        ):
            raise ModelExecutionError("sealed converter input is unavailable")
        from dynamic_agent_runner.workflow_host.input_converter_loader import (
            InputConverterLoadError,
            load_input_converter,
        )

        try:
            loaded = load_input_converter(
                package_root=package_root, converter=converter
            )
        except InputConverterLoadError as error:
            raise ModelExecutionError(
                "sealed converter input is unavailable"
            ) from error
        self._converter = loaded  # type: ignore[assignment]
        self._packed_adapter = None

    def bind_sealed_payload(self, *, content: bytes) -> None:
        if self._payload_bound:
            raise ModelExecutionError("sealed converter input is unavailable")
        self._resolved_packed_adapter().bind_sealed_payload(content=content)
        self._payload_bound = True

    def clear_sealed_payload(self) -> None:
        if self._packed_adapter is not None:
            self._packed_adapter.clear_sealed_payload()
        self._payload_bound = False

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        if self._payload_bound:
            try:
                return self._resolved_packed_adapter().create_response(request)
            finally:
                self._payload_bound = False
        return self._resolved_adapter().create_response(request)

    def _resolved_adapter(self) -> TransformersPeftSingleImageAdapter:
        if self._adapter is None:
            self._adapter = TransformersPeftSingleImageAdapter(
                self._resolve_prepared_set()
            )
        return self._adapter

    def _resolved_packed_adapter(self) -> TransformersPeftPackedInputAdapter:
        if self._packed_adapter is None:
            if self._converter is None:
                raise ModelExecutionError("sealed converter input is unavailable")
            self._packed_adapter = TransformersPeftPackedInputAdapter(
                self._resolve_prepared_set(), converter=self._converter
            )
        return self._packed_adapter
