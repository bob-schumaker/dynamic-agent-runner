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
    OpenAIResponsesResource,
    OpenAIProviderConfig,
    ResponseValidator,
)


LiteLLMCompletion = Callable[..., Any]
LiteLLMAsyncCompletion = Callable[..., Awaitable[Any]]
LiteLLMResponses = Callable[..., Any]
LiteLLMAsyncResponses = Callable[..., Awaitable[Any]]
LiteLLMModelList = Callable[..., Any]
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


class _LiteLLMNativeResponsesResource:
    def __init__(self, responses: LiteLLMResponses) -> None:
        self._responses = responses

    def create(self, **kwargs: Any) -> Any:
        return self._responses(**kwargs)


class _LiteLLMNativeAsyncResponsesResource:
    def __init__(self, aresponses: LiteLLMAsyncResponses) -> None:
        self._aresponses = aresponses

    async def create(self, **kwargs: Any) -> Any:
        return await self._aresponses(**kwargs)


class _LiteLLMClient(OpenAIClientProtocol):
    def __init__(
        self,
        completion: LiteLLMCompletion,
        models: LiteLLMModelList | None = None,
    ) -> None:
        self.responses = _LiteLLMResponsesResource(completion)
        if models is not None:
            self.models = _LiteLLMModelsResource(models)


class _LiteLLMAsyncClient(AsyncOpenAIClientProtocol):
    def __init__(
        self,
        completion: LiteLLMAsyncCompletion,
        models: LiteLLMModelList | None = None,
    ) -> None:
        self.responses = _LiteLLMAsyncResponsesResource(completion)
        if models is not None:
            self.models = _LiteLLMModelsResource(models)


class _LiteLLMNativeClient(OpenAIClientProtocol):
    def __init__(
        self,
        responses: OpenAIResponsesResource,
        models: LiteLLMModelList | None = None,
    ) -> None:
        self.responses = responses
        if models is not None:
            self.models = _LiteLLMModelsResource(models)


class _LiteLLMNativeAsyncClient(AsyncOpenAIClientProtocol):
    def __init__(
        self,
        responses: AsyncOpenAIResponsesResource,
        models: LiteLLMModelList | None = None,
    ) -> None:
        self.responses = responses
        if models is not None:
            self.models = _LiteLLMModelsResource(models)


class _LiteLLMModelsResource:
    def __init__(self, model_list: LiteLLMModelList) -> None:
        self._model_list = model_list

    def list(self, **kwargs: Any) -> Any:
        return self._model_list(**kwargs)


@dataclass(frozen=True)
class LiteLLMClientProvider(OpenAIClientProvider):
    config: OpenAIProviderConfig = field(default_factory=OpenAIProviderConfig)
    completion: LiteLLMCompletion | None = field(default=None, repr=False)
    responses: LiteLLMResponses | None = field(default=None, repr=False)
    router: object | None = field(default=None, repr=False)
    litellm_kwargs: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def get_client(self) -> OpenAIClientProtocol:
        _validate_litellm_transport(self.completion, self.responses)
        configured = _provider_litellm_kwargs(self.config, self.litellm_kwargs)
        if self.responses is not None:
            return _LiteLLMNativeClient(
                _LiteLLMNativeResponsesResource(
                    _bind_litellm_responses(self.responses, configured)
                ),
                _router_model_list(self.router),
            )
        completion = (
            self.completion
            or _router_callable(self.router, "completion")
            or _load_completion()
        )
        return _LiteLLMClient(
            _bind_litellm_kwargs(completion, configured),
            _router_model_list(self.router),
        )


@dataclass(frozen=True)
class AsyncLiteLLMClientProvider(AsyncOpenAIClientProvider):
    config: OpenAIProviderConfig = field(default_factory=OpenAIProviderConfig)
    acompletion: LiteLLMAsyncCompletion | None = field(default=None, repr=False)
    aresponses: LiteLLMAsyncResponses | None = field(default=None, repr=False)
    router: object | None = field(default=None, repr=False)
    litellm_kwargs: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def get_client(self) -> AsyncOpenAIClientProtocol:
        _validate_litellm_transport(self.acompletion, self.aresponses)
        configured = _provider_litellm_kwargs(self.config, self.litellm_kwargs)
        if self.aresponses is not None:
            return _LiteLLMNativeAsyncClient(
                _LiteLLMNativeAsyncResponsesResource(
                    _bind_async_litellm_responses(self.aresponses, configured)
                ),
                _router_model_list(self.router),
            )
        acompletion = (
            self.acompletion
            or _router_callable(self.router, "acompletion")
            or _load_async_completion()
        )
        return _LiteLLMAsyncClient(
            _bind_async_litellm_kwargs(acompletion, configured),
            _router_model_list(self.router),
        )


@dataclass(frozen=True)
class LiteLLMCodexClientProvider(OpenAIClientProvider):
    """Responses-native LiteLLM provider for an already-resolved Codex token."""

    manages_codex_response_stream: bool = field(default=False, repr=False)
    config: OpenAIProviderConfig = field(default_factory=OpenAIProviderConfig)
    token: str = field(repr=False, default="")
    responses: LiteLLMResponses | None = field(default=None, repr=False)
    model_list: LiteLLMModelList | None = field(default=None, repr=False)
    litellm_kwargs: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def get_client(self) -> OpenAIClientProtocol:
        responses = self.responses or _load_responses()
        return _LiteLLMNativeClient(
            _LiteLLMNativeResponsesResource(
                _bind_codex_responses(
                    responses,
                    _codex_litellm_kwargs(self),
                    manages_codex_response_stream=self.manages_codex_response_stream,
                )
            ),
            self.model_list,
        )


@dataclass(frozen=True)
class AsyncLiteLLMCodexClientProvider(AsyncOpenAIClientProvider):
    """Async Responses-native LiteLLM provider for a resolved Codex token."""

    manages_codex_response_stream: bool = field(default=False, repr=False)
    config: OpenAIProviderConfig = field(default_factory=OpenAIProviderConfig)
    token: str = field(repr=False, default="")
    aresponses: LiteLLMAsyncResponses | None = field(default=None, repr=False)
    model_list: LiteLLMModelList | None = field(default=None, repr=False)
    litellm_kwargs: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def get_client(self) -> AsyncOpenAIClientProtocol:
        aresponses = self.aresponses or _load_async_responses()
        return _LiteLLMNativeAsyncClient(
            _LiteLLMNativeAsyncResponsesResource(
                _bind_async_codex_responses(
                    aresponses,
                    _codex_litellm_kwargs(self),
                    manages_codex_response_stream=self.manages_codex_response_stream,
                )
            ),
            self.model_list,
        )


def create_litellm_adapter(
    *,
    model: str | None = None,
    completion: LiteLLMCompletion | None = None,
    responses: LiteLLMResponses | None = None,
    router: object | None = None,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    config: OpenAIProviderConfig | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> OpenAIClientAdapter:
    _validate_litellm_transport(completion, responses)
    adapter_models = models or ((model,) if model is not None else None)
    provider = LiteLLMClientProvider(
        config=config or OpenAIProviderConfig(),
        completion=completion,
        responses=responses,
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
    aresponses: LiteLLMAsyncResponses | None = None,
    router: object | None = None,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    config: OpenAIProviderConfig | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> AsyncOpenAIClientAdapter:
    _validate_litellm_transport(acompletion, aresponses)
    adapter_models = models or ((model,) if model is not None else None)
    provider = AsyncLiteLLMClientProvider(
        config=config or OpenAIProviderConfig(),
        acompletion=acompletion,
        aresponses=aresponses,
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


def create_litellm_codex_adapter(
    *,
    token: str,
    model: str | None = None,
    responses: LiteLLMResponses | None = None,
    model_list: LiteLLMModelList | None = None,
    models: Sequence[str] | None = None,
    config: OpenAIProviderConfig | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
    manages_codex_response_stream: bool = False,
) -> OpenAIClientAdapter:
    adapter_models = models or ((model,) if model is not None else None)
    provider = LiteLLMCodexClientProvider(
        config=config or OpenAIProviderConfig(),
        token=token,
        responses=responses,
        model_list=model_list,
        litellm_kwargs=dict(litellm_kwargs or {}),
        manages_codex_response_stream=manages_codex_response_stream,
    )
    return OpenAIClientAdapter(
        provider=provider,
        models=adapter_models,
        error_translator=error_translator,
        response_validator=response_validator,
    )


def create_async_litellm_codex_adapter(
    *,
    token: str,
    model: str | None = None,
    aresponses: LiteLLMAsyncResponses | None = None,
    model_list: LiteLLMModelList | None = None,
    models: Sequence[str] | None = None,
    config: OpenAIProviderConfig | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
    manages_codex_response_stream: bool = False,
) -> AsyncOpenAIClientAdapter:
    adapter_models = models or ((model,) if model is not None else None)
    provider = AsyncLiteLLMCodexClientProvider(
        config=config or OpenAIProviderConfig(),
        token=token,
        aresponses=aresponses,
        model_list=model_list,
        litellm_kwargs=dict(litellm_kwargs or {}),
        manages_codex_response_stream=manages_codex_response_stream,
    )
    return AsyncOpenAIClientAdapter(
        provider=provider,
        models=adapter_models,
        error_translator=error_translator,
        response_validator=response_validator,
    )


def create_litellm_codex_adapter_from_codex_auth(
    *,
    config: OpenAIProviderConfig | None = None,
    responses: LiteLLMResponses | None = None,
    completion: LiteLLMCompletion | None = None,
    model_list: LiteLLMModelList | None = None,
    models: Sequence[str] | None = None,
    model: str | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> OpenAIClientAdapter:
    resolved = _resolve_codex_provider_for_litellm(config)
    if resolved.chatgpt_token is None:
        return create_litellm_adapter(
            model=model,
            models=models,
            config=resolved.config,
            completion=completion,
            litellm_kwargs=litellm_kwargs,
            error_translator=error_translator,
            response_validator=response_validator,
        )
    return create_litellm_codex_adapter(
        token=resolved.chatgpt_token,
        model=model,
        responses=responses,
        model_list=model_list,
        models=models,
        config=resolved.config,
        litellm_kwargs=litellm_kwargs,
        error_translator=error_translator,
        response_validator=response_validator,
        manages_codex_response_stream=True,
    )


def create_async_litellm_codex_adapter_from_codex_auth(
    *,
    config: OpenAIProviderConfig | None = None,
    aresponses: LiteLLMAsyncResponses | None = None,
    acompletion: LiteLLMAsyncCompletion | None = None,
    model_list: LiteLLMModelList | None = None,
    models: Sequence[str] | None = None,
    model: str | None = None,
    litellm_kwargs: Mapping[str, Any] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> AsyncOpenAIClientAdapter:
    resolved = _resolve_codex_provider_for_litellm(config)
    if resolved.chatgpt_token is None:
        return create_async_litellm_adapter(
            model=model,
            models=models,
            config=resolved.config,
            acompletion=acompletion,
            litellm_kwargs=litellm_kwargs,
            error_translator=error_translator,
            response_validator=response_validator,
        )
    return create_async_litellm_codex_adapter(
        token=resolved.chatgpt_token,
        model=model,
        aresponses=aresponses,
        model_list=model_list,
        models=models,
        config=resolved.config,
        litellm_kwargs=litellm_kwargs,
        error_translator=error_translator,
        response_validator=response_validator,
        manages_codex_response_stream=True,
    )


def create_litellm_adapter_from_provider_config(
    config: OpenAIProviderConfig,
    *,
    completion: LiteLLMCompletion | None = None,
    responses: LiteLLMResponses | None = None,
    router: object | None = None,
    models: Sequence[str] | None = None,
    is_local: bool = False,
    litellm_kwargs: Mapping[str, Any] | None = None,
    error_translator: ErrorTranslator | None = None,
    response_validator: ResponseValidator | None = None,
) -> OpenAIClientAdapter:
    return create_litellm_adapter(
        completion=completion,
        responses=responses,
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
        kwargs["tools"] = [_chat_completion_tool_schema(tool) for tool in request.tools]
    if request.tool_choice is not None:
        kwargs["tool_choice"] = request.tool_choice
    if request.response_format is not None:
        kwargs["response_format"] = dict(request.response_format)
    return kwargs


def _chat_completion_tool_schema(tool: Mapping[str, Any]) -> dict[str, Any]:
    """Nest one DAR Responses-style function tool for LiteLLM Chat Completions."""

    normalized = dict(tool)
    if normalized.get("type") != "function" or "function" in normalized:
        return normalized
    function = {
        key: normalized.pop(key)
        for key in ("name", "description", "parameters")
        if key in normalized
    }
    return {**normalized, "function": function}


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


def _validate_litellm_transport(
    completion: object | None,
    responses: object | None,
) -> None:
    if completion is not None and responses is not None:
        raise ValueError("provide only one LiteLLM transport callable")


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


def _bind_litellm_responses(
    responses: LiteLLMResponses,
    configured: Mapping[str, Any],
) -> LiteLLMResponses:
    def bound(**kwargs: Any) -> Any:
        request_kwargs = dict(configured)
        request_kwargs.update(kwargs)
        try:
            return responses(**request_kwargs)
        except ModelExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider exceptions vary.
            raise ModelExecutionError(
                f"LiteLLM Responses request failed: {_redact(str(exc))}"
            ) from exc

    return bound


def _bind_async_litellm_responses(
    aresponses: LiteLLMAsyncResponses,
    configured: Mapping[str, Any],
) -> LiteLLMAsyncResponses:
    async def bound(**kwargs: Any) -> Any:
        request_kwargs = dict(configured)
        request_kwargs.update(kwargs)
        try:
            return await aresponses(**request_kwargs)
        except ModelExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider exceptions vary.
            raise ModelExecutionError(
                f"LiteLLM Responses request failed: {_redact(str(exc))}"
            ) from exc

    return bound


def _bind_codex_responses(
    responses: LiteLLMResponses,
    configured: Mapping[str, Any],
    *,
    manages_codex_response_stream: bool = False,
) -> LiteLLMResponses:
    def bound(**kwargs: Any) -> Any:
        request_kwargs = dict(configured)
        request_kwargs.update(kwargs)
        request_kwargs = _prepare_codex_responses_kwargs(request_kwargs)
        if manages_codex_response_stream:
            request_kwargs.pop("stream", None)
        request_kwargs["model"] = normalize_litellm_codex_model(
            str(request_kwargs["model"])
        )
        try:
            return responses(**request_kwargs)
        except Exception as exc:  # noqa: BLE001 - provider exceptions vary.
            raise ModelExecutionError(
                f"LiteLLM Codex Responses request failed: {_redact(str(exc))}"
            ) from exc

    return bound


def _bind_async_codex_responses(
    aresponses: LiteLLMAsyncResponses,
    configured: Mapping[str, Any],
    *,
    manages_codex_response_stream: bool = False,
) -> LiteLLMAsyncResponses:
    async def bound(**kwargs: Any) -> Any:
        request_kwargs = dict(configured)
        request_kwargs.update(kwargs)
        request_kwargs = _prepare_codex_responses_kwargs(request_kwargs)
        if manages_codex_response_stream:
            request_kwargs.pop("stream", None)
        request_kwargs["model"] = normalize_litellm_codex_model(
            str(request_kwargs["model"])
        )
        try:
            return await aresponses(**request_kwargs)
        except Exception as exc:  # noqa: BLE001 - provider exceptions vary.
            raise ModelExecutionError(
                f"LiteLLM Codex Responses request failed: {_redact(str(exc))}"
            ) from exc

    return bound


def _load_completion() -> LiteLLMCompletion:
    try:
        from litellm import completion
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise ModelExecutionError(
            "LiteLLM Chat Completions transport is not available"
        ) from exc
    return completion


def _router_callable(router: object | None, name: str) -> Callable[..., Any] | None:
    if router is None:
        return None
    candidate = getattr(router, name, None)
    if not callable(candidate):
        raise ModelExecutionError(f"LiteLLM router does not expose {name}")
    return candidate


def _router_model_list(router: object | None) -> LiteLLMModelList | None:
    if router is None:
        return None
    get_model_list = getattr(router, "get_model_list", None)
    if not callable(get_model_list):
        return None

    def model_list(**_kwargs: Any) -> dict[str, list[dict[str, str]]]:
        return {
            "data": [
                {"id": model_name}
                for deployment in get_model_list() or ()
                if isinstance((model_name := _read(deployment, "model_name")), str)
                and model_name.strip()
            ]
        }

    return model_list


def _provider_litellm_kwargs(
    config: OpenAIProviderConfig,
    configured: Mapping[str, Any],
) -> dict[str, Any]:
    kwargs = dict(configured)
    if config.provider_name is not None:
        kwargs.setdefault("custom_llm_provider", config.provider_name)
    if config.api_key is not None:
        kwargs.setdefault("api_key", config.api_key)
    if config.base_url is not None:
        kwargs.setdefault("api_base", config.base_url)
    return kwargs


def _load_async_completion() -> LiteLLMAsyncCompletion:
    try:
        from litellm import acompletion
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise ModelExecutionError(
            "LiteLLM async Chat Completions transport is not available"
        ) from exc
    return acompletion


def _load_responses() -> LiteLLMResponses:
    try:
        from litellm import responses
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise ModelExecutionError(
            "LiteLLM Responses transport is not available"
        ) from exc
    return responses


def _load_async_responses() -> LiteLLMAsyncResponses:
    try:
        from litellm import aresponses
    except Exception as exc:  # noqa: BLE001 - import errors vary by environment.
        raise ModelExecutionError(
            "LiteLLM async Responses transport is not available"
        ) from exc
    return aresponses


def _codex_litellm_kwargs(
    provider: LiteLLMCodexClientProvider | AsyncLiteLLMCodexClientProvider,
) -> dict[str, Any]:
    kwargs = dict(provider.litellm_kwargs)
    kwargs.setdefault("api_key", provider.token)
    if provider.config.base_url is not None:
        kwargs.setdefault("api_base", provider.config.base_url)
    kwargs.setdefault("custom_llm_provider", "chatgpt")
    kwargs.setdefault("store", False)
    if not provider.manages_codex_response_stream:
        kwargs.setdefault("stream", True)
    if provider.config.chatgpt_account_id is not None:
        headers = dict(kwargs.get("extra_headers") or {})
        headers.setdefault("ChatGPT-Account-ID", provider.config.chatgpt_account_id)
        kwargs["extra_headers"] = headers
    return kwargs


def _prepare_codex_responses_kwargs(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    request = dict(kwargs)
    input_items = request.get("input")
    if not isinstance(input_items, list):
        return request
    instructions: list[str] = []
    preserved: list[Any] = []
    for item in input_items:
        if not isinstance(item, Mapping):
            preserved.append(item)
            continue
        role = str(item.get("role") or "")
        if role in {"system", "developer"}:
            content = item.get("content")
            if content is not None and str(content).strip():
                instructions.append(str(content).strip())
        else:
            preserved.append(item)
    request["input"] = preserved or input_items
    existing = request.get("instructions")
    if existing is not None and str(existing).strip():
        instructions.insert(0, str(existing).strip())
    request["instructions"] = (
        "\n\n".join(instructions) or "You are a helpful assistant."
    )
    return request


def normalize_litellm_codex_model(model: str) -> str:
    """Map public unprefixed Codex ids to LiteLLM's ChatGPT route."""

    if "/" in model:
        return model
    return f"chatgpt/{model}"


def _resolve_codex_provider_for_litellm(
    config: OpenAIProviderConfig | None,
) -> Any:
    from dynamic_agent_runner.openai_client import (
        _resolve_default_openai_provider_defaults,
    )

    return _resolve_default_openai_provider_defaults(config or OpenAIProviderConfig())


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
