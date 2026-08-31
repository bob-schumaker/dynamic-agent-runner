#!/usr/bin/env python3
"""Run the standalone Apple Foundation Models release gate on an eligible Mac.

Run this command outside the Codex execution sandbox. It deliberately uses
direct runtime calls rather than pytest-native model generation.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from typing import Sequence

from dynamic_agent_runner import (
    AppleFoundationModelConfig,
    create_apple_foundation_model_async_adapter,
    execute_workflow,
)
from dynamic_agent_runner.artifacts import LoadedAgentWorkflow, load_runtime_manifest
from dynamic_agent_runner.openai_client import build_openai_request


class AppleLiveReleaseGateError(RuntimeError):
    """Raised when a required native release-gate check fails."""


class AppleLiveReleaseGateUnavailable(AppleLiveReleaseGateError):
    """Raised when the designated Mac cannot run the native release gate."""


def main(_argv: Sequence[str] | None = None) -> int:
    """Emit a redacted receipt for the standalone native release gate."""

    try:
        print(json.dumps(run_release_gate(), sort_keys=True, separators=(",", ":")))
    except AppleLiveReleaseGateUnavailable:
        print(
            json.dumps(
                {
                    "format_version": 1,
                    "reason": "native_model_unavailable",
                    "status": "unavailable",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    except Exception:  # noqa: BLE001 - native SDK failures vary by release.
        print(
            json.dumps(
                {
                    "format_version": 1,
                    "reason": "native_generation_failed",
                    "status": "failed",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1
    return 0


def run_release_gate() -> dict[str, object]:
    """Exercise real text, structured output, and strict workflow execution."""

    _require_eligible_apple()
    _run_text()
    _run_structured()
    _run_strict_workflow()
    return {
        "checks": ["text", "structured_output", "strict_workflow"],
        "format_version": 1,
        "status": "passed",
    }


def _require_eligible_apple() -> object:
    if sys.platform != "darwin":
        raise AppleLiveReleaseGateUnavailable("Apple Foundation Models require macOS")
    try:
        sdk = importlib.import_module("apple_fm_sdk")
    except Exception as error:  # noqa: BLE001 - optional native dependency.
        raise AppleLiveReleaseGateUnavailable("apple-fm-sdk is unavailable") from error
    available, _reason = sdk.SystemLanguageModel().is_available()
    if not available:
        raise AppleLiveReleaseGateUnavailable("Apple system model is unavailable")
    return sdk


def _run_text() -> None:
    adapter = create_apple_foundation_model_async_adapter(AppleFoundationModelConfig())
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "Reply with exactly: READY"}],
    )
    response = asyncio.run(adapter.create_response(request))
    if not isinstance(response.content, str) or not response.content.strip():
        raise AppleLiveReleaseGateError("Apple text generation returned no text")


def _run_structured() -> None:
    adapter = create_apple_foundation_model_async_adapter(AppleFoundationModelConfig())
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
    try:
        value = json.loads(response.content)
    except (TypeError, json.JSONDecodeError) as error:
        raise AppleLiveReleaseGateError(
            "Apple structured generation was invalid"
        ) from error
    if not isinstance(value, dict) or not isinstance(value.get("status"), str):
        raise AppleLiveReleaseGateError("Apple structured generation lacked status")


def _run_strict_workflow() -> None:
    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "apple-live-release-gate",
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
        model_adapter=[
            create_apple_foundation_model_async_adapter(AppleFoundationModelConfig())
        ],
        model_adapter_coverage="strict",
    )
    if not isinstance(result.final_result, str) or not result.final_result.strip():
        raise AppleLiveReleaseGateError("Apple strict workflow returned no text")


if __name__ == "__main__":
    raise SystemExit(main())
