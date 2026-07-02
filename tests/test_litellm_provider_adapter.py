from __future__ import annotations

import asyncio

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import OpenAIMessage, build_openai_request
from dynamic_agent_runner.litellm_client import (
    create_async_litellm_adapter,
    create_litellm_adapter,
)


def test_litellm_adapter_translates_chat_request_and_normalizes_response() -> None:
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {
            "id": "chatcmpl_1",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "hello",
                    }
                }
            ],
        }

    adapter = create_litellm_adapter(completion=completion)
    request = build_openai_request(
        model="openai/gpt-test",
        messages=[OpenAIMessage("user", "Say hello")],
        temperature=0,
    )

    result = adapter.create_response(request)

    assert calls == [
        {
            "model": "openai/gpt-test",
            "messages": [{"role": "user", "content": "Say hello"}],
            "temperature": 0,
        }
    ]
    assert result.content == "hello"
    assert result.response_id == "chatcmpl_1"


def test_async_litellm_adapter_translates_and_normalizes_response() -> None:
    calls: list[dict[str, object]] = []

    async def acompletion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {
            "id": "chatcmpl_async",
            "choices": [{"message": {"role": "assistant", "content": "done"}}],
        }

    adapter = create_async_litellm_adapter(acompletion=acompletion)
    request = build_openai_request(
        model="openai/gpt-test",
        messages=[OpenAIMessage("user", "Finish")],
    )

    result = asyncio.run(adapter.create_response(request))

    assert calls == [
        {
            "model": "openai/gpt-test",
            "messages": [{"role": "user", "content": "Finish"}],
        }
    ]
    assert result.content == "done"
    assert result.response_id == "chatcmpl_async"


def test_litellm_adapter_rejects_responses_only_request_fields_before_dispatch() -> (
    None
):
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {}

    adapter = create_litellm_adapter(completion=completion)
    request = build_openai_request(
        model="openai/gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
        parallel_tool_calls=True,
    )

    with pytest.raises(ModelExecutionError, match="unsupported LiteLLM request field"):
        adapter.create_response(request)

    assert calls == []
