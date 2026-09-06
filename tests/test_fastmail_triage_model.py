"""Tests for the pinned local Qwen binding used by Fastmail triage."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

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

    class FakeBackend:
        model_id = FLOORPLAN_VISION_MODEL_ID

        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def create_chat_completion(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            return {"choices": [{"message": {"content": "<svg/>"}}]}

    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"fake")
    adapter = FloorplanVisionLlamaCppAdapter(
        replace(create_floorplan_vision_qwen_config(), model_path=model_path)
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
