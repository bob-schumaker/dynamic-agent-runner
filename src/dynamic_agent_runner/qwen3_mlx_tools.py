"""Opt-in Qwen3 MLX tool calling for the pinned local artifact.

The upstream ``mlx_lm`` JSON parser accepts only the JSON within Qwen3's native
``<tool_call>`` envelope. This module owns the small, strict envelope boundary
for clients that explicitly select the pinned artifact. DAR continues to own
tool exposure, argument normalization, approval, invocation, and continuation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from dynamic_agent_runner.mlx_models import (
    MLXLocalBackend,
    MLXLocalModelAdapter,
    MLXLocalModelConfig,
    MLXToolCallCandidate,
    MLXToolCodecResponse,
    PlatformSystemCallable,
    create_mlx_local_adapter,
)
from dynamic_agent_runner.openai_client import OpenAIModelRequest


PINNED_QWEN3_MLX_MODEL_ID = "mlx-community/Qwen3-4B-Instruct-2507-nvfp4"
"""The only model identity supported by this owned codec."""

_CODEC_VERSION = "qwen3-mlx-tool-envelope-v1"
_TOOL_CALL_START = "<tool_call>"
_TOOL_CALL_END = "</tool_call>"


class Qwen3ChatTemplateTokenizer(Protocol):
    """The public tokenizer methods used by the Qwen3 MLX codec."""

    def apply_chat_template(
        self,
        conversation: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        add_generation_prompt: bool,
        tokenize: bool,
    ) -> str: ...


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_non_finite_number(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value!r}")


@dataclass(frozen=True)
class Qwen3MLXToolCodec:
    """Render Qwen3's native template and decode one native tool envelope."""

    tokenizer: Qwen3ChatTemplateTokenizer
    version: str = _CODEC_VERSION

    def render(self, request: OpenAIModelRequest) -> str:
        """Render the complete DAR transcript through Qwen3's native template."""

        if request.tool_choice is not None:
            raise ValueError(
                "Qwen3 MLX tool calling supports only an omitted DAR tool_choice"
            )
        return str(
            self.tokenizer.apply_chat_template(
                [dict(message) for message in request.messages],
                tools=[dict(tool) for tool in request.tools],
                add_generation_prompt=True,
                tokenize=False,
            )
        )

    def decode(self, generated: str) -> MLXToolCodecResponse:
        """Return ordinary text or exactly one unambiguous Qwen3 tool call."""

        if _TOOL_CALL_START not in generated and _TOOL_CALL_END not in generated:
            return MLXToolCodecResponse(content=generated)
        if (
            generated.count(_TOOL_CALL_START) != 1
            or generated.count(_TOOL_CALL_END) != 1
        ):
            raise ValueError("Qwen3 response must contain exactly one tool envelope")
        prefix, payload = generated.split(_TOOL_CALL_START, 1)
        payload, suffix = payload.split(_TOOL_CALL_END, 1)
        if prefix.strip() or suffix.strip():
            raise ValueError("Qwen3 tool envelope cannot be mixed with prose")
        decoded = json.loads(
            payload.strip(),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_number,
        )
        if not isinstance(decoded, dict) or set(decoded) != {"name", "arguments"}:
            raise ValueError("Qwen3 tool payload must contain only name and arguments")
        name = decoded["name"]
        arguments = decoded["arguments"]
        if not isinstance(name, str) or not name:
            raise ValueError("Qwen3 tool name must be a non-empty string")
        if not isinstance(arguments, dict):
            raise ValueError("Qwen3 tool arguments must be a JSON object")
        return MLXToolCodecResponse(
            tool_call=MLXToolCallCandidate(name=name, arguments=arguments)
        )


@dataclass
class Qwen3MLXBackend:
    """MLX backend explicitly compatible with :class:`Qwen3MLXToolCodec`."""

    model: object
    tokenizer: Qwen3ChatTemplateTokenizer
    model_id: str = PINNED_QWEN3_MLX_MODEL_ID
    tool_codec_versions = frozenset({_CODEC_VERSION})

    def generate(self, request: OpenAIModelRequest, **kwargs: object) -> str:
        """Generate ordinary text through the model's native chat template."""

        prompt = str(
            self.tokenizer.apply_chat_template(
                [dict(message) for message in request.messages],
                add_generation_prompt=True,
                tokenize=False,
            )
        )
        return self.generate_rendered(prompt, **kwargs)

    def generate_rendered(self, prompt: str, **kwargs: object) -> str:
        """Generate a codec-rendered prompt through public ``mlx_lm``."""

        from mlx_lm import generate

        kwargs.setdefault("verbose", False)
        return str(generate(self.model, self.tokenizer, prompt=prompt, **kwargs))


def create_qwen3_mlx_local_adapter(
    config: MLXLocalModelConfig,
    *,
    model: object,
    tokenizer: Qwen3ChatTemplateTokenizer,
    platform_system: PlatformSystemCallable | None = None,
) -> MLXLocalModelAdapter:
    """Create a pinned-Qwen3 adapter with DAR's owned native-envelope codec.

    The caller loads the model through ``mlx_lm.load`` and passes its exact
    ``(model, tokenizer)`` pair. Requiring the pinned expected model ID prevents
    this convenience helper from treating a model-family name as compatibility.
    """

    if config.expected_model_id != PINNED_QWEN3_MLX_MODEL_ID:
        raise ValueError(
            "Qwen3 MLX tool calling requires the pinned Qwen3 model ID as "
            "MLXLocalModelConfig.expected_model_id"
        )
    backend: MLXLocalBackend = Qwen3MLXBackend(model=model, tokenizer=tokenizer)
    return create_mlx_local_adapter(
        config,
        backend=backend,
        platform_system=platform_system,
        tool_codec=Qwen3MLXToolCodec(tokenizer=tokenizer),
    )
