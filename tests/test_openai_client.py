"""Tests for the OpenAI client adapter boundary."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import (
    OpenAIClientAdapter,
    OpenAIMessage,
    build_openai_request,
    normalize_openai_response,
)
from dynamic_agent_runner.registry import openai_tool_schema
from dynamic_agent_runner.models import ToolDefinition


class FakeResponses:
    def __init__(self, response: object | None = None, error: Exception | None = None):
        self.response = response or {"id": "resp_1", "output_text": "hello"}
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, responses: FakeResponses):
        self.responses = responses


def test_build_openai_request_includes_messages_tools_and_options() -> None:
    tool_schema = openai_tool_schema(
        ToolDefinition.from_mapping(
            {
                "id": "search_repo",
                "description_for_llm": "Search repository files.",
                "input_schema": {"type": "object", "properties": {}},
            }
        )
    )

    request = build_openai_request(
        model="gpt-test",
        messages=[
            OpenAIMessage("system", "Be concise."),
            {"role": "user", "content": "Search for adapters."},
        ],
        tools=[tool_schema],
        tool_choice="auto",
        response_format={"type": "json_object"},
        temperature=0,
        unused=None,
    )

    assert request.to_kwargs() == {
        "model": "gpt-test",
        "input": [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Search for adapters."},
        ],
        "tools": [tool_schema],
        "tool_choice": "auto",
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }


def test_adapter_uses_injected_client_and_normalizes_response() -> None:
    responses = FakeResponses({"id": "resp_123", "output_text": "final answer"})
    adapter = OpenAIClientAdapter(FakeClient(responses))
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
    )

    result = adapter.create_response(request)

    assert responses.calls == [
        {"model": "gpt-test", "input": [{"role": "user", "content": "Hello"}]}
    ]
    assert result.response_id == "resp_123"
    assert result.content == "final answer"
    assert result.tool_calls == ()


def test_normalize_openai_response_extracts_message_text_and_tool_calls() -> None:
    raw_response = {
        "id": "resp_tools",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Need a tool."},
                ],
            },
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "search_repo",
                "arguments": '{"query":"adapter"}',
            },
        ],
    }

    response = normalize_openai_response(raw_response)

    assert response.response_id == "resp_tools"
    assert response.content == "Need a tool."
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "call_1"
    assert response.tool_calls[0].name == "search_repo"
    assert response.tool_calls[0].arguments == '{"query":"adapter"}'


def test_adapter_wraps_model_failures() -> None:
    responses = FakeResponses(error=RuntimeError("network unavailable"))
    adapter = OpenAIClientAdapter(FakeClient(responses))
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
    )

    with pytest.raises(ModelExecutionError, match="OpenAI model request failed"):
        adapter.create_response(request)


@pytest.mark.parametrize(
    ("model", "messages", "message"),
    [
        ("", [OpenAIMessage("user", "hi")], "requires a model"),
        ("gpt-test", [], "requires at least one message"),
        ("gpt-test", [{"role": "user"}], "requires role and content"),
    ],
)
def test_build_openai_request_validates_required_inputs(
    model: str,
    messages: list[object],
    message: str,
) -> None:
    with pytest.raises(ModelExecutionError, match=message):
        build_openai_request(model=model, messages=messages)
