from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.errors import ModelExecutionError, WorkflowExecutionError
from dynamic_agent_runner.executor import execute_workflow, execute_workflow_async
from dynamic_agent_runner import (
    create_litellm_adapter as exported_create_litellm_adapter,
)
from dynamic_agent_runner.openai_client import (
    OpenAIMessage,
    OpenAIProviderConfig,
    build_openai_request,
)
from dynamic_agent_runner.openai_client import create_default_openai_provider
from dynamic_agent_runner.tracing import InMemoryTraceSink
from dynamic_agent_runner.litellm_client import (
    create_async_litellm_codex_adapter,
    create_async_litellm_adapter,
    create_litellm_codex_adapter,
    normalize_litellm_codex_model,
    create_litellm_adapter_from_provider_config,
    create_litellm_adapter,
)
from parity_support import (
    install_parity_io_blocker,
    parity_exposed_schemas,
    parity_loop_workflow,
    parity_no_tool_workflow,
    parity_contract_projection,
    parity_record,
    parity_registry,
)


def _litellm_tool_response(name: str, arguments: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-tool",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                }
            }
        ],
    }


def _litellm_text_response(text: str) -> dict[str, object]:
    return {"id": "chatcmpl-text", "choices": [{"message": {"content": text}}]}


def _run_litellm_parity(scenario: str, responses: list[object], *, asynchronous: bool):
    observed = []
    scripted = list(responses)
    calls = []

    def validator(_request, response) -> None:
        observed.extend(response.tool_calls)

    def completion(**_kwargs: object) -> object:
        calls.append(_kwargs)
        return scripted.pop(0)

    async def acompletion(**_kwargs: object) -> object:
        calls.append(_kwargs)
        return scripted.pop(0)

    registry, invocations, results = parity_registry()
    sink = InMemoryTraceSink()
    error = None
    try:
        if asynchronous:
            adapter = create_async_litellm_adapter(
                acompletion=acompletion,
                models=["gpt-test"],
                response_validator=validator,
            )
            result = asyncio.run(
                execute_workflow_async(
                    parity_no_tool_workflow()
                    if scenario == "S5"
                    else parity_loop_workflow(),
                    prompt="controlled parity",
                    tool_registry=registry,
                    model_adapter=adapter,
                    trace_sink=sink,
                )
            )
        else:
            adapter = create_litellm_adapter(
                completion=completion,
                models=["gpt-test"],
                response_validator=validator,
            )
            result = execute_workflow(
                parity_no_tool_workflow()
                if scenario == "S5"
                else parity_loop_workflow(),
                prompt="controlled parity",
                tool_registry=registry,
                model_adapter=adapter,
                trace_sink=sink,
            )
    except Exception as caught:
        result = None
        error = caught
    return (
        result,
        parity_record(
            interface="litellm_scripted_completion",
            scenario=scenario,
            asynchronous=asynchronous,
            normalized_calls=tuple((call.name, call.arguments) for call in observed),
            exposed_schemas=parity_exposed_schemas(calls[0]["tools"]),
            invocations=invocations,
            results=results,
            result=result,
            error=error,
            sink=sink,
        ),
        error,
        calls,
    )


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    ("scenario", "responses", "invoked", "fails"),
    [
        ("S5", [_litellm_text_response("no tool")], (), False),
        (
            "S1",
            [
                _litellm_tool_response(
                    "create_record", '{"title":"DAR","body":"controlled"}'
                ),
                _litellm_text_response("created"),
            ],
            ("create_record",),
            False,
        ),
        (
            "S2",
            [
                _litellm_tool_response(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase"}',
                ),
                _litellm_text_response("transformed"),
            ],
            ("transform_record",),
            False,
        ),
        (
            "S2-invalid",
            [_litellm_tool_response("transform_record", '{"record_id":"record-seed"}')],
            (),
            True,
        ),
        (
            "S2-wrong-type",
            [
                _litellm_tool_response(
                    "transform_record", '{"record_id":1,"operation":"uppercase"}'
                )
            ],
            (),
            True,
        ),
        (
            "S2-invalid-enum",
            [
                _litellm_tool_response(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"lowercase"}',
                )
            ],
            (),
            True,
        ),
        (
            "S2-unknown",
            [
                _litellm_tool_response(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase","unknown":true}',
                )
            ],
            (),
            True,
        ),
        (
            "S2-malformed",
            [_litellm_tool_response("transform_record", "not-json")],
            (),
            True,
        ),
        (
            "S3",
            [
                _litellm_tool_response("lookup_record", '{"key":"seed"}'),
                _litellm_tool_response(
                    "transform_record",
                    '{"record_id":"record-seed","operation":"uppercase"}',
                ),
                _litellm_text_response("SEED"),
            ],
            ("lookup_record", "transform_record"),
            False,
        ),
        (
            "S4",
            [_litellm_tool_response("fail_controlled", '{"code":"planned"}')],
            ("fail_controlled",),
            True,
        ),
        ("S6", [_litellm_tool_response("lookup_record", "not-json")], (), True),
    ],
)
def test_model_interface_parity_litellm_native_scenarios(
    scenario: str,
    responses: list[object],
    invoked: tuple[str, ...],
    fails: bool,
    asynchronous: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_parity_io_blocker(monkeypatch)
    result, record, error, calls = _run_litellm_parity(
        scenario, responses, asynchronous=asynchronous
    )
    assert tuple(name for name, _ in record.invocations) == invoked
    assert (error is not None) is fails
    assert (result is None) is fails
    if fails:
        assert isinstance(error, WorkflowExecutionError)
        assert record.error_class == "WorkflowExecutionError"
    if scenario == "S4":
        assert record.stop_reasons == ("tool_failure",)
        assert len(calls) == 1
        assert isinstance(error, WorkflowExecutionError)
        assert "planned controlled failure" in str(error)
        assert record.trace_event_types.count("model_tool_loop_tool_call") == 1
    if scenario == "S6":
        assert "tool_started" not in record.trace_event_types
        assert "model_tool_loop_tool_call" not in record.trace_event_types
        assert len(calls) == 1
    if scenario == "S3":
        assert len(calls) == 3
        assert "record-seed" in str(calls[1])
    if not asynchronous:
        _, async_record, _, _ = _run_litellm_parity(
            scenario, responses, asynchronous=True
        )
        assert parity_contract_projection(record) == parity_contract_projection(
            async_record
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
    assert calls[0].get("stream") is not True


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


def test_litellm_adapter_uses_supplied_native_responses_transport() -> None:
    calls: list[dict[str, object]] = []

    def responses(**kwargs: object) -> object:
        calls.append(kwargs)
        return {
            "id": "resp_generic",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "native"}],
                }
            ],
        }

    tool = {
        "type": "function",
        "name": "search_repo",
        "description": "Search repository files.",
        "parameters": {"type": "object", "properties": {}},
    }
    adapter = create_litellm_adapter(
        responses=responses,
        config=OpenAIProviderConfig(
            api_key="provider-key",
            base_url="https://provider.example/v1",
            provider_name="openai",
        ),
    )

    result = adapter.create_response(
        build_openai_request(
            model="openai/gpt-test",
            messages=[OpenAIMessage("user", "Search")],
            tools=[tool],
            parallel_tool_calls=True,
        )
    )

    assert calls[0]["api_key"] == "provider-key"
    assert calls[0]["api_base"] == "https://provider.example/v1"
    assert calls[0]["custom_llm_provider"] == "openai"
    assert calls[0]["model"] == "openai/gpt-test"
    assert calls[0]["input"] == [{"role": "user", "content": "Search"}]
    assert calls[0]["tools"] == [tool]
    assert calls[0]["parallel_tool_calls"] is True
    assert result.content == "native"
    assert result.response_id == "resp_generic"


def test_async_litellm_adapter_uses_supplied_native_responses_transport() -> None:
    calls: list[dict[str, object]] = []

    async def aresponses(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "resp_async_generic", "output": []}

    adapter = create_async_litellm_adapter(aresponses=aresponses)
    result = asyncio.run(
        adapter.create_response(
            build_openai_request(
                model="openai/gpt-test",
                messages=[OpenAIMessage("user", "Hello")],
                parallel_tool_calls=True,
            )
        )
    )

    assert calls[0]["model"] == "openai/gpt-test"
    assert calls[0]["input"] == [{"role": "user", "content": "Hello"}]
    assert calls[0]["parallel_tool_calls"] is True
    assert result.response_id == "resp_async_generic"


def test_litellm_adapter_rejects_conflicting_transport_callables() -> None:
    with pytest.raises(ValueError, match="only one LiteLLM transport"):
        create_litellm_adapter(
            completion=lambda **kwargs: {},
            responses=lambda **kwargs: {},
        )

    with pytest.raises(ValueError, match="only one LiteLLM transport"):
        create_async_litellm_adapter(
            acompletion=lambda **kwargs: None,
            aresponses=lambda **kwargs: None,
        )


def test_litellm_provider_config_factory_forwards_native_responses() -> None:
    calls: list[dict[str, object]] = []

    def responses(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"id": "provider-config", "output": []}

    adapter = create_litellm_adapter_from_provider_config(
        OpenAIProviderConfig(api_key="provider-key"),
        responses=responses,
    )
    adapter.create_response(
        build_openai_request(
            model="openai/gpt-test",
            messages=[OpenAIMessage("user", "Hello")],
        )
    )

    assert calls[0]["api_key"] == "provider-key"


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


def test_litellm_router_lists_models_through_existing_adapter_cache() -> None:
    calls: list[object] = []

    def completion(**kwargs: object) -> object:
        return {"id": "router_response", "choices": [{"message": {"content": "ok"}}]}

    def get_model_list() -> object:
        calls.append(object())
        return [
            {"model_name": "gpt-5.5"},
            {"model_name": "gpt-5.4"},
            {"model_name": "gpt-5.5"},
            {"model_name": ""},
        ]

    adapter = create_litellm_adapter(
        router=SimpleNamespace(completion=completion, get_model_list=get_model_list)
    )

    assert adapter.list_supported_models() == ("gpt-5.4", "gpt-5.5")
    assert adapter.default_model() == "gpt-5.4"
    assert adapter.list_supported_models(refresh=True) == ("gpt-5.4", "gpt-5.5")
    assert len(calls) == 2


def test_async_litellm_router_lists_models_through_existing_adapter_cache() -> None:
    calls: list[object] = []

    async def acompletion(**kwargs: object) -> object:
        return {"id": "router_response", "choices": [{"message": {"content": "ok"}}]}

    def get_model_list() -> object:
        calls.append(object())
        return [{"model_name": "gpt-5.5"}, {"model_name": "gpt-5.4"}]

    adapter = create_async_litellm_adapter(
        router=SimpleNamespace(acompletion=acompletion, get_model_list=get_model_list)
    )

    assert asyncio.run(adapter.list_supported_models()) == ("gpt-5.4", "gpt-5.5")
    assert asyncio.run(adapter.list_supported_models(refresh=True)) == (
        "gpt-5.4",
        "gpt-5.5",
    )
    assert len(calls) == 2


def test_litellm_router_listing_respects_explicit_models_metadata() -> None:
    calls: list[object] = []
    router = SimpleNamespace(
        completion=lambda **kwargs: {"choices": []},
        get_model_list=lambda: calls.append(object()),
    )

    adapter = create_litellm_adapter(router=router, models=["configured-model"])

    assert adapter.list_supported_models() == ("configured-model",)
    assert calls == []


@pytest.mark.parametrize(
    "router",
    [
        SimpleNamespace(completion=lambda **kwargs: {"choices": []}),
        SimpleNamespace(
            completion=lambda **kwargs: {"choices": []},
            get_model_list=lambda: [{"model_name": ""}, {}],
        ),
    ],
)
def test_litellm_router_listing_reports_unavailable_models(router: object) -> None:
    adapter = create_litellm_adapter(router=router)

    with pytest.raises(ModelExecutionError):
        adapter.default_model()


def test_litellm_router_listing_normalizes_router_failure() -> None:
    def get_model_list() -> object:
        raise RuntimeError("router unavailable")

    adapter = create_litellm_adapter(
        router=SimpleNamespace(
            completion=lambda **kwargs: {"choices": []},
            get_model_list=get_model_list,
        )
    )

    with pytest.raises(
        ModelExecutionError, match="OpenAI available model listing failed"
    ):
        adapter.list_supported_models()


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
