"""Tests for lightweight model capability metadata."""

from __future__ import annotations

from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.executor import execute_workflow
from dynamic_agent_runner.models import LoadedAgentWorkflow, ModelCapabilities
from dynamic_agent_runner.openai_client import OpenAIClientAdapter


class FakeResponses:
    def __init__(self, response: object | None = None):
        self.response = response or {"id": "resp_1", "output_text": "done"}
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_model_capabilities_normalizes_supported_fields() -> None:
    """Capability metadata preserves supported model-behavior dimensions."""

    capabilities = ModelCapabilities.from_mapping(
        {
            "context_window": "128000",
            "structured_output": True,
            "reasoning": False,
            "modalities": ["text", "image"],
            "parallel_tool_calls": True,
            "provider": "openai-compatible",
        }
    )

    assert capabilities.context_window == 128000
    assert capabilities.structured_output is True
    assert capabilities.reasoning is False
    assert capabilities.modalities == ("text", "image")
    assert capabilities.parallel_tool_calls is True
    assert capabilities.raw["provider"] == "openai-compatible"


def test_runtime_manifest_preserves_model_capabilities_metadata() -> None:
    """Runtime manifests expose execution-policy model capability metadata."""

    manifest = load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "capabilities-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "model_capabilities": {
                        "context_window": 128000,
                        "structured_output": True,
                        "reasoning": True,
                        "modalities": ["text"],
                        "parallel_tool_calls": False,
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                }
            ],
            "edges": [],
        }
    )

    assert manifest.model_capabilities == ModelCapabilities(
        context_window=128000,
        structured_output=True,
        reasoning=True,
        modalities=("text",),
        parallel_tool_calls=False,
        raw={
            "context_window": 128000,
            "structured_output": True,
            "reasoning": True,
            "modalities": ["text"],
            "parallel_tool_calls": False,
        },
    )


def test_model_capabilities_do_not_leak_into_openai_request() -> None:
    """Capability metadata stays separate from provider request parameters."""

    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "capability-request-agent",
                "entrypoint": "answer",
                "packaging": {"mode": "hybrid_bundle"},
                "runtime": {
                    "execution_policy": {
                        "model": "gpt-test",
                        "model_capabilities": {
                            "context_window": 128000,
                            "structured_output": True,
                            "reasoning": True,
                            "modalities": ["text"],
                            "parallel_tool_calls": False,
                        },
                    }
                },
                "nodes": [
                    {
                        "id": "answer",
                        "kind": "llm_step",
                        "prompt": {"user_template": "Answer {prompt}"},
                    }
                ],
                "edges": [],
            }
        )
    )
    fake_client = FakeClient()
    adapter = OpenAIClientAdapter(fake_client)

    result = execute_workflow(workflow, prompt="Hi", model_adapter=adapter)

    assert result.final_result == "done"
    assert fake_client.responses.calls == [
        {
            "model": "gpt-test",
            "input": [{"role": "user", "content": "Answer Hi"}],
        }
    ]
