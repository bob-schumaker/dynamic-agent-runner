"""Fake-only tests for the trusted Qwen 2.5 VL 3B GRPO input converter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY

import pytest

from dynamic_agent_runner import load_agent_package_workflow
from dynamic_agent_runner.errors import ModelExecutionError


class FakeImage:
    width = 1
    height = 1

    def __init__(self, image_format: str = "PNG") -> None:
        self.format = image_format


def test_qwen_converter_packs_one_valid_sealed_image() -> None:
    from dynamic_agent_runner.workflow_host.qwen25_vl_3b_grpo_converter import (
        Qwen25Vl3bGrpoInputConverter,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TransformersGenerateInputContext,
    )

    calls: dict[str, object] = {}

    class Processor:
        def apply_chat_template(self, messages, **kwargs: object) -> object:
            calls["messages"] = messages
            calls["kwargs"] = kwargs
            return {"input_ids": SimpleNamespace(shape=(1, 4))}

    converter = Qwen25Vl3bGrpoInputConverter(image_decoder=lambda content: FakeImage())
    packed = converter.pack(
        messages=(
            {"role": "system", "content": "Return only structured JSON."},
            {"role": "user", "content": "Vectorize this floor plan."},
        ),
        payload=b"png-bytes",
        context=TransformersGenerateInputContext(Processor()),
    )

    assert packed.take()["input_ids"].shape == (1, 4)
    assert calls["messages"] == [
        {"role": "system", "content": "Return only structured JSON."},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": ANY},
                {"type": "text", "text": "Vectorize this floor plan."},
            ],
        },
    ]
    assert calls["kwargs"] == {
        "add_generation_prompt": True,
        "tokenize": True,
        "return_dict": True,
        "return_tensors": "pt",
    }


def test_floorplan_package_sets_the_qwen_generation_ceiling() -> None:
    package = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "natural-language-workflow-authoring"
        / "floorplan-svg"
    )

    workflow = load_agent_package_workflow(str(package))

    assert workflow.runtime_manifest.nodes[0].raw["model_parameters"] == {
        "max_tokens": 4096
    }


@pytest.mark.parametrize(
    "payload,decoded_image",
    [
        (b"", FakeImage()),
        (b"x" * (8 * 1024 * 1024 + 1), FakeImage()),
        (b"undecodable", ValueError("bad image")),
        (b"tiff", FakeImage("TIFF")),
    ],
)
def test_qwen_converter_rejects_invalid_or_unsupported_image_bytes(
    payload: bytes, decoded_image: object
) -> None:
    from dynamic_agent_runner.workflow_host.qwen25_vl_3b_grpo_converter import (
        Qwen25Vl3bGrpoInputConverter,
    )
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TransformersGenerateInputContext,
    )

    class Processor:
        def apply_chat_template(self, *_args: object, **_kwargs: object) -> object:
            pytest.fail("invalid image bytes must not reach the processor")

    def decode(_content: bytes) -> object:
        if isinstance(decoded_image, Exception):
            raise decoded_image
        return decoded_image

    converter = Qwen25Vl3bGrpoInputConverter(image_decoder=decode)

    with pytest.raises(ModelExecutionError, match="sealed image input"):
        converter.pack(
            messages=({"role": "user", "content": "vectorize"},),
            payload=payload,
            context=TransformersGenerateInputContext(Processor()),
        )
