"""LiteLLM transport behind the repository-owned OpenAI adapter boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
import re
from typing import Any

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    AsyncOpenAIClientProtocol,
    AsyncOpenAIClientProvider,
    AsyncOpenAIResponsesResource,
    ErrorTranslator,
    ModelResponse,
    ModelToolCall,
    OpenAIClientAdapter,
    OpenAIClientProtocol,
    OpenAIClientProvider,
    OpenAIModelRequest,
    OpenAIProviderConfig,
    ResponseValidator,
)


LiteLLMCompletion = Callable[..., Any]
LiteLLMAsyncCompletion = Callable[..., Awaitable[Any]]
_SUPPORTED_EXTRA_FIELDS = frozenset(
    {
        "api_base",
        "api_key",
        "base_url",
        "custom_llm_provider",
        "frequency_penalty",
        "max_completion_tokens",
        "max_tokens",
        "n",
        "presence_penalty",
        "seed",
        "stop",
        "stream",
        "temperature",
        "timeout",
        "top_p",
        "user",
    }
)
_SECRET_PATTERN = re.compile(r"(?i)(bearer\s+|sk-|token[=:]\s*)([^\s,;]+)")


class _LiteLLMResponsesResource(AsyncOpenAIResponsesResource):
    def __init__(self, completion: LiteLLMCompletion) -> None:
        self._completion = completion

    def create(self, **kwargs: Any) -> Any:
        return self._completion(**_translate_openai_kwargs(kwargs))


class _LiteLLMAsyncResponsesResource:
    def __init__(self, completion: LiteLLMAsyncCompletion) -> None:
        self._completion = completion

    async def create(self, **kwargs: Any) -> Any:
        return await self._completion(**kwargs)


class _LiteLLMClient(OpenAIClientProtocol):
    def __init__(self, completion: LiteLLMCompletion) -> None:
        self.responses = _LiteLLMResponsesResource(completion)


class _LiteLLMAsyncClient(AsyncOpenAIClientProtocol):
    def __init__(self, completion: LiteLLMAsyncCompletion) -> None:
        self.responses = _LiteLLMAsyncResponsesResource(completion)


@dataclass(frozen=True)
class LiteLLMClientProvider(OpenAIClientProvider):
    config: OpenAIProviderConfig = field(default_factory=OpenAIProviderConfig)
    completion: LiteLLMCompletion | None = field(default=None, repr=False)
    router: object | None = field(default=None, repr=False)
    litellm_kwargs: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def get_client(self) -> OpenAIClientProtocol:
        completion = (
            self.completion
            or _router_callable(self.router, "completion")
            or _load_completion()
        )
        return _LiteLLMClient(
            _bind_litellm_kwargs(
                completion,
                _provider_litellm_kwargs(self.config, self.litellm_kwargs),
            )
        )


@dataclass(frozen=True)
class AsyncLiteLLMClientProvider(AsyncOpenAIClientProvider):
    config: OpenAIProviderConfig = field(default_factory=OpenAIProviderConfig)
    acompletion: LiteLLMAsyncCompletion | None = field(default=None, repr=False)
    router: object | None = field(default=None, repr=False)
    litellm_kwargs: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def get_client(self) -> AsyncOpenAIClientProtocol:
        acompletion = (
            self.acompletion
            or _router_callable(self.router, "acompletion")
            or _load_async_completion()
        )
        return _LiteLLMAsyncClient(
            _bind_async_litellm_kwargs(
                acompletion,
                _provider_litellm_kwargs(self.config, self.litellm_kwargs),
            )
        )


def create_litellm_adapter(
    *,
    model: str | None = None,
    completion: LiteLLMCompletion | None = None,
    router: object | None = None,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    config: OpenAIProviderConfig | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> OpenAIClientAdapter:
    adapter_models = models or ((model,) if model is not None else None)
    provider = LiteLLMClientProvider(
        config=config or OpenAIProviderConfig(),
        completion=completion,
        router=router,
        litellm_kwargs=dict(litellm_kwargs or {}),
    )
    return OpenAIClientAdapter(
        provider=provider,
        models=adapter_models,
        is_local=is_local,
        error_translator=error_translator,
        response_validator=response_validator,
    )


def create_async_litellm_adapter(
    *,
    model: str | None = None,
    acompletion: LiteLLMAsyncCompletion | None = None,
    router: object | None = None,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    config: OpenAIProviderConfig | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> AsyncOpenAIClientAdapter:
    adapter_models = models or ((model,) if model is not None else None)
    provider = AsyncLiteLLMClientProvider(
        config=config or OpenAIProviderConfig(),
        acompletion=acompletion,
        router=router,
        litellm_kwargs=dict(litellm_kwargs or {}),
    )
    return AsyncOpenAIClientAdapter(
        provider=provider,
        models=adapter_models,
        is_local=is_local,
        error_translator=error_translator,
        response_validator=response_validator,
    )


def create_litellm_adapter_from_provider_config(
    config: OpenAIProviderConfig,
    *,
    completion: LiteLLMCompletion | None = None,
    router: object | None = None,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    litellm_kwargs: Mapping[str, Any] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> OpenAIClientAdapter:
    return create_litellm_adapter(
        completion=completion,
        router=router,
        models=models,
        is_local=is_local,
        config=config,
        litellm_kwargs=litellm_kwargs,
        error_translator=error_translator,
        response_validator=response_validator,
    )


def normalize_litellm_response(raw_response: Any) -> ModelResponse:
    choices = _read(raw_response, "choices") or ()
    first_choice = next(iter(choices), None)
    message = _read(first_choice, "message") if first_choice is not None else None
    content = _read(message, "content")
    if isinstance(content, list):
        content = "".join(
            str(_read(item, "text"))
            for item in content
            if _read(item, "text") is not None
        )
    if content is not None and not isinstance(content, str):
        content = str(content)
    tool_calls = tuple(
        _normalize_tool_call(item) for item in (_read(message, "tool_calls") or ())
    )
    return ModelResponse(
        content=content,
        tool_calls=tool_calls,
        response_id=_as_optional_string(_read(raw_response, "id")),
        raw=raw_response,
    )


def _translate_request(request: OpenAIModelRequest) -> dict[str, Any]:
    unsupported = sorted(set(request.extra) - _SUPPORTED_EXTRA_FIELDS)
    if unsupported:
        raise ModelExecutionError(
            "unsupported LiteLLM request field(s): " + ", ".join(unsupported)
        )
    kwargs = dict(request.extra)
    kwargs["model"] = request.model
    kwargs["messages"] = [dict(message) for message in request.messages]
    if request.tools:
        kwargs["tools"] = [dict(tool) for tool in request.tools]
    if request.tool_choice is not None:
        kwargs["tool_choice"] = request.tool_choice
    if request.response_format is not None:
        kwargs["response_format"] = dict(request.response_format)
    return kwargs


def _translate_openai_kwargs(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    input_messages = kwargs.get("input")
    if not isinstance(input_messages, list):
        raise ModelExecutionError("LiteLLM request requires OpenAI input messages")
    request = OpenAIModelRequest(
        model=str(kwargs.get("model") or ""),
        messages=tuple(
            message for message in input_messages if isinstance(message, Mapping)
        ),
        tools=tuple(
            tool for tool in kwargs.get("tools", ()) if isinstance(tool, Mapping)
        ),
        tool_choice=kwargs.get("tool_choice"),
        response_format=(
            kwargs.get("response_format")
            if isinstance(kwargs.get("response_format"), Mapping)
            else None
        ),
        extra={
            key: value
            for key, value in kwargs.items()
            if key not in {"model", "input", "tools", "tool_choice", "response_format"}
        },
    )
    return _translate_request(request)


def _bind_litellm_kwargs(
    completion: Callable[..., Any],
    configured: Mapping[str, Any],
) -> Callable[..., Any]:
    def bound(**kwargs: Any) -> Any:
        request_kwargs = dict(configured)
        request_kwargs.update(kwargs)
        try:
            return normalize_litellm_response(completion(**request_kwargs))
        except ModelExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider exceptions vary.
            raise ModelExecutionError(
                f"LiteLLM model request failed: {_redact(str(exc))}"
            ) from exc

    return bound


def _bind_async_litellm_kwargs(
    completion: LiteLLMAsyncCompletion,
    configured: Mapping[str, Any],
) -> LiteLLMAsyncCompletion:
    async def bound(**kwargs: Any) -> ModelResponse:
        request_kwargs = dict(configured)
        request_kwargs.update(_translate_openai_kwargs(kwargs))
        try:
            return normalize_litellm_response(await completion(**request_kwargs))
        except ModelExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider exceptions vary.
            raise ModelExecutionError(
                f"LiteLLM model request failed: {_redact(str(exc))}"
            ) from exc

    return bound


def _load_completion() -> LiteLLMCompletion:
    try:
        from litellm import completion
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise ModelExecutionError("litellm package is not available") from exc
    return completion


def _router_callable(router: object | None, name: str) -> Callable[..., Any] | None:
    if router is None:
        return None
    candidate = getattr(router, name, None)
    if not callable(candidate):
        raise ModelExecutionError(f"LiteLLM router does not expose {name}")
    return candidate


def _provider_litellm_kwargs(
    config: OpenAIProviderConfig,
    configured: Mapping[str, Any],
) -> dict[str, Any]:
    kwargs = dict(configured)
    if config.api_key is not None:
        kwargs.setdefault("api_key", config.api_key)
    if config.base_url is not None:
        kwargs.setdefault("api_base", config.base_url)
    return kwargs


def _load_async_completion() -> LiteLLMAsyncCompletion:
    try:
        from litellm import acompletion
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise ModelExecutionError("litellm package is not available") from exc
    return acompletion


def _normalize_tool_call(raw_call: Any) -> ModelToolCall:
    function = _read(raw_call, "function") or raw_call
    return ModelToolCall(
        id=_as_optional_string(_read(raw_call, "id")),
        name=str(_read(function, "name") or ""),
        arguments=_read(function, "arguments") or "{}",
    )


def _read(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _as_optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _redact(value: str) -> str:
    return _SECRET_PATTERN.sub(r"\1[REDACTED]", value)
