from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys

import pytest

from dynamic_agent_runner.apple_foundation_models import (
    create_apple_foundation_model_async_adapter,
)
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.executor import execute_workflow
from dynamic_agent_runner.models import LoadedAgentWorkflow
from dynamic_agent_runner.openai_client import build_openai_request


def _require_live_apple() -> object:
    if os.environ.get("DAR_RUN_LIVE_APPLE") != "1":
        pytest.skip("set DAR_RUN_LIVE_APPLE=1 to run live Apple tests")
    if sys.platform != "darwin":
        pytest.skip("Apple Foundation Models live tests require macOS")
    try:
        sdk = importlib.import_module("apple_fm_sdk")
    except Exception as exc:  # pragma: no cover - host prerequisite branch.
        pytest.skip(f"apple-fm-sdk is unavailable: {exc}")
    available, reason = sdk.SystemLanguageModel().is_available()
    if not available:
        pytest.skip(f"Apple system model is unavailable: {reason}")
    return sdk


@pytest.mark.apple_live
def test_live_apple_text_generation() -> None:
    _require_live_apple()
    adapter = create_apple_foundation_model_async_adapter()
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "Reply with exactly: READY"}],
    )

    response = asyncio.run(adapter.create_response(request))

    assert isinstance(response.content, str)
    assert response.content.strip()


@pytest.mark.apple_live
def test_live_apple_structured_generation() -> None:
    _require_live_apple()
    adapter = create_apple_foundation_model_async_adapter()
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "Return a successful status."}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "status",
                "schema": {
                    "type": "object",
                    "properties": {"status": {"type": "string"}},
                    "required": ["status"],
                    "additionalProperties": False,
                },
            },
        },
    )

    response = asyncio.run(adapter.create_response(request))

    assert isinstance(response.content, str)
    value = json.loads(response.content)
    assert isinstance(value.get("status"), str)


@pytest.mark.apple_live
def test_live_apple_strict_coverage_workflow() -> None:
    _require_live_apple()
    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "live-apple-agent",
                "entrypoint": "answer",
                "packaging": {"mode": "hybrid_bundle"},
                "runtime": {
                    "execution_policy": {"default_model": "apple-system-language-model"}
                },
                "nodes": [
                    {
                        "id": "answer",
                        "kind": "llm_step",
                        "prompt": {"user_template": "Reply with one short sentence."},
                    }
                ],
                "edges": [],
            }
        )
    )

    result = execute_workflow(
        workflow,
        prompt="Say hello.",
        model_adapter=[create_apple_foundation_model_async_adapter()],
        model_adapter_coverage="strict",
    )

    assert isinstance(result.final_result, str)
    assert result.final_result.strip()
