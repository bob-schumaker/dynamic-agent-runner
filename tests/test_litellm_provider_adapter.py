from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner import (
    create_litellm_adapter as exported_create_litellm_adapter,
)
from dynamic_agent_runner.openai_client import (
    OpenAIMessage,
    OpenAIProviderConfig,
    build_openai_request,
)
from dynamic_agent_runner.openai_client import create_default_openai_provider
from dynamic_agent_runner.litellm_client import (
    create_async_litellm_codex_adapter,
    create_async_litellm_adapter,
    create_litellm_codex_adapter,
    normalize_litellm_codex_model,
    create_litellm_adapter_from_provider_config,
    create_litellm_adapter,
)


def test_litellm_codex_model_alias_preserves_public_ids() -> None:
    assert normalize_litellm_codex_model("codex-mini-latest") == (
        "chatgpt/codex-mini-latest"
    )
    assert normalize_litellm_codex_model("chatgpt/codex-mini-latest") == (
        "chatgpt/codex-mini-latest"
    )
    assert normalize_litellm_codex_model("openai/gpt-test") == "openai/gpt-test"


def test_litellm_adapter_passes_configured_provider_name() -> None:
    """A local OpenAI-compatible endpoint needs an explicit LiteLLM provider."""

    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "local", "choices": [{"message": {"content": "ok"}}]}

    adapter = create_litellm_adapter_from_provider_config(
        OpenAIProviderConfig(
            base_url="http://localhost:11434/v1",
            provider_name="openai",
            discover_default_auth=False,
        ),
        completion=completion,
        models=["local-qwen-chat"],
        is_local=True,
    )

    adapter.create_response(
        build_openai_request(
            model="local-qwen-chat",
            messages=[OpenAIMessage("user", "Hello")],
        )
    )

    assert calls[0]["api_base"] == "http://localhost:11434/v1"
    assert calls[0]["custom_llm_provider"] == "openai"


def test_litellm_codex_adapter_translates_only_outbound_model_alias() -> None:
    calls: list[dict[str, object]] = []

    def responses(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "alias", "output": []}

    adapter = create_litellm_codex_adapter(
        token="codex-token",
        model="codex-mini-latest",
        responses=responses,
    )
    request = build_openai_request(
        model="codex-mini-latest",
        messages=[OpenAIMessage("user", "Hello")],
    )

    adapter.create_response(request)

    assert adapter.models == ("codex-mini-latest",)
    assert calls[0]["model"] == "chatgpt/codex-mini-latest"
    assert calls[0]["store"] is False
    assert calls[0]["stream"] is True


def test_litellm_codex_adapter_folds_instructions_and_preserves_tool_transcript() -> (
    None
):
    calls: list[dict[str, object]] = []

    def responses(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "parity", "output": []}

    adapter = create_litellm_codex_adapter(token="token", responses=responses)
    request = build_openai_request(
        model="codex-mini-latest",
        messages=[
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Search"},
            {"role": "tool", "tool_call_id": "call-1", "content": "ok"},
        ],
    )

    adapter.create_response(request)

    assert calls[0]["instructions"] == "Be concise."
    assert calls[0]["input"] == [
        {"role": "user", "content": "Search"},
        {"role": "tool", "tool_call_id": "call-1", "content": "ok"},
    ]


def test_litellm_codex_auth_factory_uses_dar_resolved_chatgpt_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner import litellm_client

    monkeypatch.setattr(
        litellm_client,
        "_resolve_codex_provider_for_litellm",
        lambda config: SimpleNamespace(
            config=OpenAIProviderConfig(
                base_url="https://chatgpt.example/backend-api/codex",
                provider_name="chatgpt-codex",
                chatgpt_account_id="acct-2",
            ),
            chatgpt_token="resolved-token",
            api_key=None,
        ),
    )
    calls: list[dict[str, object]] = []

    def responses(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "auth", "output": []}

    def model_list(**kwargs: object) -> object:
        del kwargs
        return {"data": [{"id": "codex-mini-latest"}]}

    adapter = litellm_client.create_litellm_codex_adapter_from_codex_auth(
        responses=responses,
        model_list=model_list,
    )
    request = build_openai_request(
        model="codex-mini-latest",
        messages=[OpenAIMessage("user", "Hello")],
    )

    adapter.create_response(request)

    assert calls[0]["api_key"] == "resolved-token"
    assert calls[0]["extra_headers"] == {"ChatGPT-Account-ID": "acct-2"}


def test_litellm_codex_auth_factory_keeps_api_key_on_ordinary_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agent_runner import litellm_client

    monkeypatch.setattr(
        litellm_client,
        "_resolve_codex_provider_for_litellm",
        lambda config: SimpleNamespace(
            config=OpenAIProviderConfig(
                api_key="api-key",
                base_url="http://localhost:4000/v1",
            ),
            chatgpt_token=None,
        ),
    )
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    adapter = litellm_client.create_litellm_codex_adapter_from_codex_auth(
        completion=completion,
    )
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
    )

    assert adapter.create_response(request).content == "ok"
    assert calls[0]["api_key"] == "api-key"


def test_litellm_adapter_requires_installed_completion_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace())

    adapter = create_litellm_adapter()
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "hello")],
    )

    with pytest.raises(
        ModelExecutionError,
        match="LiteLLM Chat Completions transport is not available",
    ):
        adapter.create_response(request)


def test_async_litellm_adapter_requires_installed_completion_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace())

    adapter = create_async_litellm_adapter()
    request = build_openai_request(
        model="gpt-test",
        messages=[OpenAIMessage("user", "hello")],
    )

    with pytest.raises(
        ModelExecutionError,
        match="LiteLLM async Chat Completions transport is not available",
    ):
        asyncio.run(adapter.create_response(request))


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


def test_litellm_codex_adapter_uses_native_responses_transport() -> None:
    calls: list[dict[str, object]] = []

    def responses(**kwargs: object) -> object:
        calls.append(kwargs)
        return {
            "id": "resp_codex",
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "ok"}]}
            ],
        }

    adapter = create_litellm_codex_adapter(
        token="codex-token",
        model="chatgpt/codex-mini-latest",
        responses=responses,
        config=OpenAIProviderConfig(
            base_url="https://chatgpt.example/backend-api/codex",
            chatgpt_account_id="acct-1",
        ),
    )
    request = build_openai_request(
        model="chatgpt/codex-mini-latest",
        messages=[OpenAIMessage("user", "Hello")],
    )

    result = adapter.create_response(request)

    assert calls == [
        {
            "api_key": "codex-token",
            "api_base": "https://chatgpt.example/backend-api/codex",
            "custom_llm_provider": "chatgpt",
            "extra_headers": {"ChatGPT-Account-ID": "acct-1"},
            "model": "chatgpt/codex-mini-latest",
            "input": [{"role": "user", "content": "Hello"}],
            "store": False,
            "stream": True,
            "instructions": "You are a helpful assistant.",
        }
    ]
    assert result.response_id == "resp_codex"


def test_async_litellm_codex_adapter_uses_native_responses_transport() -> None:
    calls: list[dict[str, object]] = []

    async def aresponses(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "resp_async", "output": []}

    adapter = create_async_litellm_codex_adapter(
        token="codex-token",
        aresponses=aresponses,
    )
    request = build_openai_request(
        model="chatgpt/codex-mini-latest",
        messages=[OpenAIMessage("user", "Hello")],
    )

    result = asyncio.run(adapter.create_response(request))

    assert calls == [
        {
            "api_key": "codex-token",
            "custom_llm_provider": "chatgpt",
            "model": "chatgpt/codex-mini-latest",
            "input": [{"role": "user", "content": "Hello"}],
            "store": False,
            "stream": True,
            "instructions": "You are a helpful assistant.",
        }
    ]
    assert result.response_id == "resp_async"


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


def test_litellm_adapter_translates_tools_and_normalizes_tool_calls() -> None:
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {
            "id": "chatcmpl_tool",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "search_repo",
                                    "arguments": '{"query":"adapter"}',
                                },
                            }
                        ],
                    }
                }
            ],
        }

    tool = {
        "type": "function",
        "function": {
            "name": "search_repo",
            "description": "Search repository files.",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    adapter = create_litellm_adapter(completion=completion)
    request = build_openai_request(
        model="openai/gpt-test",
        messages=[OpenAIMessage("user", "Search")],
        tools=[tool],
        tool_choice="auto",
    )

    result = adapter.create_response(request)

    assert calls == [
        {
            "model": "openai/gpt-test",
            "messages": [{"role": "user", "content": "Search"}],
            "tools": [tool],
            "tool_choice": "auto",
        }
    ]
    assert result.content is None
    assert result.tool_calls[0].id == "call_1"
    assert result.tool_calls[0].name == "search_repo"
    assert result.tool_calls[0].arguments == '{"query":"adapter"}'


def test_litellm_adapter_normalizes_flat_response_function_tools() -> None:
    """Responses-style tool schemas are nested for Chat Completions transport."""

    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "chatcmpl", "choices": [{"message": {"content": "ok"}}]}

    flat_tool = {
        "type": "function",
        "name": "search_repo",
        "description": "Search repository files.",
        "parameters": {"type": "object", "properties": {}},
    }
    adapter = create_litellm_adapter(completion=completion)

    adapter.create_response(
        build_openai_request(
            model="openai/gpt-test",
            messages=[OpenAIMessage("user", "Search")],
            tools=[flat_tool],
        )
    )

    assert calls[0]["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search_repo",
                "description": "Search repository files.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


def test_litellm_adapter_redacts_provider_secrets() -> None:
    def completion(**kwargs: object) -> object:
        del kwargs
        raise RuntimeError("401 bearer secret-token")

    adapter = create_litellm_adapter(completion=completion)
    request = build_openai_request(
        model="openai/gpt-test",
        messages=[OpenAIMessage("user", "Hello")],
    )

    with pytest.raises(
        ModelExecutionError, match="LiteLLM model request failed"
    ) as error:
        adapter.create_response(request)

    assert "secret-token" not in str(error.value)
    assert "REDACTED" in str(error.value)


def test_default_openai_provider_uses_litellm_for_ordinary_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")
    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(completion=lambda **kwargs: kwargs),
    )

    provider = create_default_openai_provider()

    assert provider.__class__.__name__ == "LiteLLMClientProvider"


def test_litellm_adapter_accepts_router_and_provider_config() -> None:
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "router_response", "choices": [{"message": {"content": "ok"}}]}

    router = SimpleNamespace(completion=completion)
    adapter = create_litellm_adapter_from_provider_config(
        OpenAIProviderConfig(api_key="router-key"),
        router=router,
    )
    request = build_openai_request(
        model="openai/router-model",
        messages=[OpenAIMessage("user", "Route")],
    )

    result = adapter.create_response(request)

    assert result.content == "ok"
    assert calls == [
        {
            "api_key": "router-key",
            "model": "openai/router-model",
            "messages": [{"role": "user", "content": "Route"}],
        }
    ]
    assert adapter._provider.config.api_key == "router-key"


def test_litellm_adapter_forwards_provider_credentials_and_base_url() -> None:
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "configured", "choices": [{"message": {"content": "ok"}}]}

    adapter = create_litellm_adapter(
        completion=completion,
        config=OpenAIProviderConfig(
            api_key="provider-key",
            base_url="http://localhost:4000/v1",
        ),
    )
    request = build_openai_request(
        model="openai/configured",
        messages=[OpenAIMessage("user", "Configured")],
    )

    adapter.create_response(request)

    assert calls == [
        {
            "api_key": "provider-key",
            "api_base": "http://localhost:4000/v1",
            "model": "openai/configured",
            "messages": [{"role": "user", "content": "Configured"}],
        }
    ]


def test_litellm_factory_is_public_and_model_is_metadata_only() -> None:
    def completion(**kwargs: object) -> object:
        return {"id": "metadata", "choices": [{"message": {"content": "ok"}}]}

    adapter = exported_create_litellm_adapter(
        model="metadata-model",
        completion=completion,
    )
    request = build_openai_request(
        model="request-model",
        messages=[OpenAIMessage("user", "Authoritative")],
    )

    result = adapter.create_response(request)

    assert adapter.models == ("metadata-model",)
    assert result.content == "ok"
