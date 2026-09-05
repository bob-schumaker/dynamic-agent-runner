"""Pinned local llama.cpp model binding for Fastmail inbox triage."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from dynamic_agent_runner.local_models import (
    HuggingFaceModelFileReference,
    LlamaCppLocalModelConfig,
)


FASTMAIL_TRIAGE_MODEL_ALIAS = "fastmail-triage-qwen2.5-3b"
_REPOSITORY = "Qwen/Qwen2.5-3B-Instruct-GGUF"
_REVISION = "7dabda4d13d513e3e842b20f0d435c732f172cbe"
_FILENAME = "qwen2.5-3b-instruct-q4_k_m.gguf"
_SHA256 = "626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d"


def create_fastmail_triage_qwen_config(
    *,
    model_path: str | Path,
    model_kwargs: Mapping[str, object],
) -> LlamaCppLocalModelConfig:
    """Create the immutable offline Qwen GGUF binding for this workflow only."""

    return LlamaCppLocalModelConfig(
        model_aliases=(FASTMAIL_TRIAGE_MODEL_ALIAS,),
        model_path=model_path,
        model_filename=_FILENAME,
        huggingface_file=HuggingFaceModelFileReference(
            repo_id=_REPOSITORY,
            filename=_FILENAME,
            revision=_REVISION,
        ),
        expected_model_id=_REPOSITORY,
        expected_model_sha256=_SHA256,
        allow_network=False,
        model_kwargs=model_kwargs,
    )
