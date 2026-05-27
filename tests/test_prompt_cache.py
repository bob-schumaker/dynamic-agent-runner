"""Tests for prompt-cache intent parsing and trace observation."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.errors import WorkflowValidationError
from dynamic_agent_runner.executor import execute_workflow
from dynamic_agent_runner.models import LoadedAgentWorkflow
from dynamic_agent_runner.openai_client import OpenAIClientAdapter
from dynamic_agent_runner.prompt_cache import (
    PromptCachePolicy,
    prompt_cache_policy_from_value,
)
from dynamic_agent_runner.validation import validate_runtime_manifest


class FakeResponses:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)

    def create(self, **_kwargs: object) -> object:
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses: list[object]):
        self.responses = FakeResponses(responses)


def make_adapter(responses: list[object]) -> OpenAIClientAdapter:
    return OpenAIClientAdapter(FakeClient(responses))


def workflow_from(data: dict[str, object]) -> LoadedAgentWorkflow:
    return LoadedAgentWorkflow(runtime_manifest=load_runtime_manifest(data))


def cache_manifest(**prompt_cache: object) -> dict[str, object]:
    return {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "cache-agent",
        "entrypoint": "answer",
        "packaging": {"mode": "hybrid_bundle"},
        "execution_policy": {
            "model": "gpt-test",
            "prompt_cache": {
                "enabled": True,
                "strategy": "stable_prefix",
                "min_prefix_tokens": 1,
                "prefix_parts": [
                    "system",
                    "developer",
                    "skill_instructions",
                    "x-custom",
                ],
                "variable_parts": ["user_prompt", "run_state"],
                "cache_key_hint": "package_id",
                "provider_hints": {"openai": {"retention": "auto"}},
                **prompt_cache,
            },
        },
        "skills": [
            {
                "id": "cache-skill",
                "prompt_role": "developer",
                "instructions": "Stable instructions.",
            }
        ],
        "nodes": [
            {
                "id": "answer",
                "kind": "llm_step",
                "skill_refs": ["cache-skill"],
                "prompt": {
                    "system": "Stable system.",
                    "developer": "Stable developer.",
                    "user_template": "Variable {prompt}",
                },
            }
        ],
        "edges": [],
    }


def test_prompt_cache_policy_parses_provider_neutral_metadata() -> None:
    policy = prompt_cache_policy_from_value(
        {
            "enabled": True,
            "strategy": "stable_prefix",
            "min_prefix_tokens": 1024,
            "prefix_parts": ["system", "developer", "x-extra"],
            "variable_parts": ["user_prompt", "run_state"],
            "cache_key_hint": "package_id",
            "provider_hints": {"openai": {"retention": "auto"}},
        }
    )

    assert policy == PromptCachePolicy(
        enabled=True,
        strategy="stable_prefix",
        min_prefix_tokens=1024,
        prefix_parts=("system", "developer", "x-extra"),
        variable_parts=("user_prompt", "run_state"),
        cache_key_hint="package_id",
        provider_hints={"openai": {"retention": "auto"}},
    )


@pytest.mark.parametrize(
    "prompt_cache, message",
    [
        ({"enabled": "yes"}, "enabled"),
        ({"strategy": "unknown"}, "strategy"),
        ({"min_prefix_tokens": 0}, "min_prefix_tokens"),
        ({"prefix_parts": ["system", "bad_part"]}, "bad_part"),
        ({"provider_hints": ["openai"]}, "provider_hints"),
    ],
)
def test_prompt_cache_metadata_validation_fails_closed(
    prompt_cache: dict[str, object], message: str
) -> None:
    manifest = load_runtime_manifest(cache_manifest(**prompt_cache))

    with pytest.raises(WorkflowValidationError, match=message):
        validate_runtime_manifest(manifest)


def test_prompt_cache_trace_records_eligibility_and_prefix_evidence() -> None:
    workflow = workflow_from(cache_manifest())

    result = execute_workflow(
        workflow,
        prompt="question",
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
    )

    cache_events = [
        event
        for event in result.state.trace_events
        if event.event_type == "prompt_cache_checked"
    ]
    assert len(cache_events) == 1
    payload = cache_events[0].payload
    assert payload["enabled"] is True
    assert payload["eligible"] is True
    assert payload["strategy"] == "stable_prefix"
    assert payload["stable_prefix_part_names"] == [
        "system",
        "developer",
        "skill_instructions",
    ]
    assert payload["first_variable_part"] == "user_prompt"
    assert payload["estimated_prefix_tokens"] > 0
    assert len(payload["prefix_hash"]) == 64
    assert payload["provider_hints"] == ["openai"]
    assert payload["caller_override"] == "manifest"
    assert payload["adapter_fallback"] == "not_applied"


def test_prompt_cache_can_be_disabled_per_execution_request() -> None:
    workflow = workflow_from(cache_manifest())

    result = execute_workflow(
        workflow,
        prompt="question",
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
        prompt_cache=False,
    )

    cache_event = next(
        event
        for event in result.state.trace_events
        if event.event_type == "prompt_cache_checked"
    )
    assert cache_event.payload["enabled"] is False
    assert cache_event.payload["eligible"] is False
    assert cache_event.payload["caller_override"] == "disabled"


def test_prompt_cache_trace_records_ineligible_small_prefix() -> None:
    workflow = workflow_from(cache_manifest(min_prefix_tokens=1_000_000))

    result = execute_workflow(
        workflow,
        prompt="question",
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
    )

    cache_event = next(
        event
        for event in result.state.trace_events
        if event.event_type == "prompt_cache_checked"
    )
    assert cache_event.payload["enabled"] is True
    assert cache_event.payload["eligible"] is False
    assert cache_event.payload["ineligibility_reason"] == "below_min_prefix_tokens"


def test_prompt_cache_records_missing_token_estimator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("estimator unavailable")

    monkeypatch.setattr(
        "dynamic_agent_runner.prompt_cache.estimate_messages_tokens", unavailable
    )
    workflow = workflow_from(cache_manifest())

    result = execute_workflow(
        workflow,
        prompt="question",
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
    )

    cache_event = next(
        event
        for event in result.state.trace_events
        if event.event_type == "prompt_cache_checked"
    )
    assert cache_event.payload["eligible"] is False
    assert cache_event.payload["estimated_prefix_tokens"] is None
    assert cache_event.payload["ineligibility_reason"] == "token_estimation_unavailable"
    assert "estimator unavailable" in cache_event.payload["estimation_error"]


def test_prompt_cache_records_provider_cache_telemetry_when_exposed() -> None:
    workflow = workflow_from(cache_manifest())

    result = execute_workflow(
        workflow,
        prompt="question",
        model_adapter=make_adapter(
            [
                {
                    "id": "resp",
                    "output_text": "done",
                    "usage": {
                        "input_tokens_details": {
                            "cached_tokens": 128,
                        }
                    },
                }
            ]
        ),
    )

    telemetry_event = next(
        event
        for event in result.state.trace_events
        if event.event_type == "prompt_cache_provider_telemetry"
    )
    assert telemetry_event.payload == {"cached_tokens": 128}
