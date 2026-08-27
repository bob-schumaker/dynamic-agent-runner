from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, get_args, get_origin, get_type_hints

import pytest

from dynamic_agent_runner.errors import ModelExecutionError, ToolRegistryError
from dynamic_agent_runner.models import ToolDefinition
from dynamic_agent_runner.openai_client import build_openai_request
from dynamic_agent_runner.apple_foundation_models import (
    AppleFoundationModelConfig,
    create_apple_foundation_model_async_adapter,
)
from dynamic_agent_runner.hooks import WorkflowLifecycleHooks
from dynamic_agent_runner.registry import (
    InMemoryToolRegistry,
    RegisteredTool,
    ToolResult,
)
from dynamic_agent_runner.retry import RetryPolicy
from dynamic_agent_runner.tool_invocation import (
    ProviderDecisionRequest,
    ProviderDecisionState,
    ProviderToolDecision,
    coordinate_tool_invocation_async,
    tool_context,
)
from dynamic_agent_runner.tracing import WorkflowTracer


@pytest.fixture(autouse=True)
def eligible_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models.sys.platform", "darwin"
    )


def test_apple_config_and_factory_are_importable_without_sdk() -> None:
    config = AppleFoundationModelConfig()
    adapter = create_apple_foundation_model_async_adapter(config)

    assert config.model_aliases == ("apple-system-language-model",)
    assert adapter.models == ("apple-system-language-model",)
    assert adapter.is_local is True


def test_factory_accepts_injected_availability_and_session_seams() -> None:
    config = AppleFoundationModelConfig(
        availability_checker=lambda: (True, None),
        session_factory=lambda _instructions: object(),
    )

    adapter = create_apple_foundation_model_async_adapter(config)

    assert adapter.is_local is True


def test_non_darwin_generation_fails_before_sdk_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models.sys.platform", "linux"
    )
    adapter = create_apple_foundation_model_async_adapter()
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "hello"}],
    )

    with pytest.raises(ModelExecutionError, match="macOS"):
        asyncio.run(adapter.create_response(request))


def test_unavailable_system_model_reports_actionable_reason() -> None:
    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (False, "Apple Intelligence is disabled")
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "hello"}],
    )

    with pytest.raises(ModelExecutionError, match="Apple Intelligence is disabled"):
        asyncio.run(adapter.create_response(request))


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"tools": [{"type": "function", "name": "lookup"}]},
        {"response_format": {"type": "json_object"}},
        {"extra": {"stream": True}},
        {"extra": {"top_p": 0.5}},
    ],
)
def test_unsupported_request_features_fail_before_session_creation(
    request_kwargs: dict[str, object],
) -> None:
    calls: list[str] = []
    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None),
            session_factory=lambda _instructions: calls.append("session") or object(),
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "hello"}],
        **request_kwargs,
    )

    with pytest.raises(ModelExecutionError):
        asyncio.run(adapter.create_response(request))
    assert calls == []


def test_public_import_does_not_require_apple_sdk() -> None:
    assert Path("src/dynamic_agent_runner/apple_foundation_models.py").exists()


@dataclass
class FakeGeneratedJSON:
    value: str

    def to_json(self) -> str:
        return self.value


class FakeSession:
    def __init__(self, instructions: str | None, result: object = "answer") -> None:
        self.instructions = instructions
        self.result = result
        self.prompts: list[tuple[str, object]] = []

    async def respond(self, prompt: str, **kwargs: object) -> object:
        self.prompts.append((prompt, kwargs))
        return self.result


class CancelledSession(FakeSession):
    async def respond(self, prompt: str, **kwargs: object) -> object:
        raise asyncio.CancelledError


class FakeAppleToolSession:
    def __init__(
        self,
        instructions: str | None,
        *,
        tools: list[object] | tuple[object, ...] = (),
    ) -> None:
        self.instructions = instructions
        self.tools = tuple(tools)
        for tool in self.tools:
            if not isinstance(tool, FakeAppleToolSDK.Tool):
                raise TypeError("Apple tool must subclass sdk.Tool")
            if not isinstance(getattr(tool, "name", None), str) or not tool.name:
                raise TypeError("Apple tool name must be a non-empty string")
            if (
                not isinstance(getattr(tool, "description", None), str)
                or not tool.description
            ):
                raise TypeError("Apple tool description must be a non-empty string")
            if not isinstance(tool.arguments_schema, FakeAppleGenerationSchema):
                raise TypeError("Apple tool must provide a GenerationSchema")
            if not inspect.iscoroutinefunction(tool.call):
                raise TypeError("Apple tool call must be async")

    async def respond(self, _prompt: str, **_kwargs: object) -> str:
        return "answer"


@dataclass(frozen=True)
class FakeAppleGeneratedContent:
    payload: str

    def to_json(self) -> str:
        return self.payload


class FakeAppleCallbackSession(FakeAppleToolSession):
    def __init__(
        self,
        instructions: str | None,
        *,
        tools: list[object] | tuple[object, ...] = (),
        callback_arguments: tuple[tuple[int, str], ...],
    ) -> None:
        super().__init__(instructions, tools=tools)
        self.callback_arguments = callback_arguments
        self.callback_results: list[object] = []

    async def respond(self, _prompt: str, **_kwargs: object) -> str:
        for tool_index, arguments in self.callback_arguments:
            self.callback_results.append(
                await self.tools[tool_index].call(FakeAppleGeneratedContent(arguments))
            )
        return "answer"


class FakeAppleToolSDK:
    class Tool:
        pass

    def __init__(self) -> None:
        self.sessions: list[FakeAppleToolSession] = []

    def SystemLanguageModel(self) -> object:
        return SimpleNamespace(is_available=lambda: (True, None))

    def LanguageModelSession(
        self,
        *,
        instructions: str | None,
        tools: list[object] | tuple[object, ...] = (),
    ) -> FakeAppleToolSession:
        session = FakeAppleToolSession(instructions, tools=tools)
        self.sessions.append(session)
        return session

    @staticmethod
    def generable(_description: str):
        def decorate(cls: type[object]) -> type[object]:
            cls.generation_schema = classmethod(
                lambda _cls: FakeAppleGenerationSchema(_cls)
            )
            return cls

        return decorate

    @staticmethod
    def guide(**values: object) -> "FakeAppleGuide":
        return FakeAppleGuide(values)


class FakeAppleCallbackSDK(FakeAppleToolSDK):
    def __init__(self, callback_arguments: tuple[tuple[int, str], ...]) -> None:
        super().__init__()
        self.callback_arguments = callback_arguments

    def LanguageModelSession(
        self,
        *,
        instructions: str | None,
        tools: list[object] | tuple[object, ...] = (),
    ) -> FakeAppleCallbackSession:
        session = FakeAppleCallbackSession(
            instructions,
            tools=tools,
            callback_arguments=self.callback_arguments,
        )
        self.sessions.append(session)
        return session


@dataclass(frozen=True)
class FakeAppleGenerationSchema:
    generated_type: type[object]


@dataclass(frozen=True)
class FakeAppleGuide:
    values: dict[str, object]


def _annotation_base(annotation: object) -> object:
    if get_origin(annotation) is Annotated:
        return get_args(annotation)[0]
    return annotation


def _annotation_guides(annotation: object) -> dict[str, object]:
    if get_origin(annotation) is not Annotated:
        return {}
    values: dict[str, object] = {}
    for metadata in get_args(annotation)[1:]:
        if isinstance(metadata, FakeAppleGuide):
            values.update(metadata.values)
    return values


def _has_cause(error: BaseException, error_type: type[BaseException]) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, error_type):
            return True
        current = current.__cause__
    return False


def _tool(
    tool_id: str,
    input_schema: dict[str, object],
    *,
    approval_required: bool = False,
    handler: object | None = None,
) -> RegisteredTool:
    definition: dict[str, object] = {"id": tool_id, "input_schema": input_schema}
    if approval_required:
        definition["approval_required"] = "yes"
    return RegisteredTool(
        ToolDefinition.from_mapping(definition),
        handler if handler is not None else lambda _arguments: {"ok": True},  # type: ignore[arg-type]
    )


def _active_tool_context(
    registry: InMemoryToolRegistry,
    tools: tuple[RegisteredTool, ...],
    *,
    decision_collaborator: object | None = None,
    lifecycle_hooks: WorkflowLifecycleHooks | None = None,
):
    state = SimpleNamespace(run_id="run-1", tool_results={}, trace_events=[])
    return tool_context(
        plan=SimpleNamespace(
            workflow=SimpleNamespace(
                runtime_manifest=SimpleNamespace(package_id="workflow-1")
            )
        ),
        node=SimpleNamespace(id="node-1"),
        tools=tools,
        registry=registry,
        state=state,
        tracer=WorkflowTracer(events=state.trace_events),
        lifecycle_hooks=lifecycle_hooks,
        retry_policy=RetryPolicy(),
        decision_collaborator=decision_collaborator,  # type: ignore[arg-type]
    )


def _tool_request(
    registry: InMemoryToolRegistry,
    *,
    descriptor_ids: tuple[str, ...],
    adapter_context: object,
):
    return build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "Use the available tool."}],
        tools=registry.to_openai_tools(descriptor_ids),
        adapter_context=adapter_context,
    )


def test_text_request_preserves_instructions_and_ordered_history() -> None:
    sessions: list[FakeSession] = []

    def make_session(instructions: str | None) -> FakeSession:
        session = FakeSession(instructions)
        sessions.append(session)
        return session

    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None), session_factory=make_session
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[
            {"role": "system", "content": "Be concise."},
            {"role": "developer", "content": "Use plain language."},
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Earlier"},
            {"role": "user", "content": "Now"},
        ],
    )

    asyncio.run(adapter.create_response(request))

    assert len(sessions) == 1
    assert sessions[0].instructions == "Be concise.\nUse plain language."
    assert sessions[0].prompts[0][0] == "user: First\nassistant: Earlier\nuser: Now"


def test_each_request_gets_a_fresh_session_and_maps_generation_options() -> None:
    sessions: list[FakeSession] = []

    def make_session(instructions: str | None) -> FakeSession:
        session = FakeSession(instructions)
        sessions.append(session)
        return session

    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None), session_factory=make_session
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_output_tokens=32,
    )

    asyncio.run(adapter.create_response(request))
    asyncio.run(adapter.create_response(request))

    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    assert sessions[0].prompts[0][1] == {
        "options": {"temperature": 0.2, "max_output_tokens": 32}
    }


def test_structured_generation_uses_explicit_schema_and_normalizes_json() -> None:
    sessions: list[FakeSession] = []

    def make_session(instructions: str | None) -> FakeSession:
        session = FakeSession(instructions, FakeGeneratedJSON('{"ok": true}'))
        sessions.append(session)
        return session

    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None), session_factory=make_session
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "return json"}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "result", "schema": {"type": "object"}},
        },
    )

    response = asyncio.run(adapter.create_response(request))

    assert response.content == '{"ok": true}'
    assert sessions[0].prompts[0][1]["json_schema"] == {"type": "object"}


def test_cancellation_propagates_without_provider_retry() -> None:
    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None),
            session_factory=lambda _instructions: CancelledSession(None),
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "cancel"}],
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(adapter.create_response(request))


def test_adapter_exposes_conservative_apple_capabilities() -> None:
    adapter = create_apple_foundation_model_async_adapter()

    assert adapter.capabilities == {
        "provider": "apple_foundation_models",
        "execution": "in_process",
        "local": True,
        "model_identity": "system_managed",
        "structured_output": True,
        "streaming": False,
        "tool_calling": False,
        "multimodal": False,
        "embeddings": False,
    }


def test_sdk_import_failure_preserves_package_error_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk",
        lambda: (_ for _ in ()).throw(ModelExecutionError("apple-fm-sdk is required")),
    )
    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(availability_checker=lambda: (True, None))
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "hello"}],
    )

    with pytest.raises(ModelExecutionError) as raised:
        asyncio.run(adapter.create_response(request))
    assert isinstance(raised.value.__cause__, ModelExecutionError)


def test_native_json_schema_gets_foundation_models_metadata() -> None:
    from dynamic_agent_runner.apple_foundation_models import _normalize_apple_schema

    assert _normalize_apple_schema(
        {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        }
    ) == {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
        "x-order": ["status"],
        "title": "GeneratedResponse",
    }


@pytest.mark.parametrize(
    "extra",
    [{"temperature": "hot"}, {"temperature": -0.1}, {"max_tokens": 0}],
)
def test_invalid_generation_options_fail_before_session_creation(
    extra: dict[str, object],
) -> None:
    calls: list[str] = []
    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None),
            session_factory=lambda _instructions: calls.append("session") or object(),
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "hello"}],
        **extra,
    )

    with pytest.raises(ModelExecutionError):
        asyncio.run(adapter.create_response(request))
    assert calls == []


def test_invalid_structured_output_is_rejected() -> None:
    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None),
            session_factory=lambda _instructions: FakeSession(
                None, FakeGeneratedJSON("not json")
            ),
        )
    )
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "return json"}],
        response_format={
            "type": "json_schema",
            "json_schema": {"schema": {"type": "object"}},
        },
    )

    with pytest.raises(ModelExecutionError, match="valid JSON"):
        asyncio.run(adapter.create_response(request))


_ADMITTED_APPLE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "enum": ["brief", "full"]},
        "count": {"type": "integer", "minimum": 1, "maximum": 5},
        "scores": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 1,
            "maxItems": 3,
        },
        "target": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
            "additionalProperties": False,
        },
        "recipients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"address": {"type": "string"}},
                "required": ["address"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "count", "scores", "target", "recipients"],
    "additionalProperties": False,
}


def test_apple_tool_bridge_constructs_only_opaque_active_wrappers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = _tool("email/send-with spaces", _ADMITTED_APPLE_TOOL_SCHEMA)
    second_active = _tool("review@2", _ADMITTED_APPLE_TOOL_SCHEMA)
    inactive = _tool("inactive_tool", _ADMITTED_APPLE_TOOL_SCHEMA)
    registry = InMemoryToolRegistry([active, second_active, inactive])
    active = registry.get_tool("email/send-with spaces")
    second_active = registry.get_tool("review@2")
    context = _active_tool_context(registry, (active, second_active))
    sdk = FakeAppleToolSDK()
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk", lambda: sdk
    )

    response = asyncio.run(
        create_apple_foundation_model_async_adapter().create_response(
            _tool_request(
                registry,
                descriptor_ids=(
                    "email/send-with spaces",
                    "review@2",
                    "inactive_tool",
                ),
                adapter_context=context,
            )
        )
    )

    assert response.content == "answer"
    assert len(sdk.sessions) == 1
    wrappers = sdk.sessions[0].tools
    assert [wrapper.name for wrapper in wrappers] == ["dar_tool_0", "dar_tool_1"]
    assert all(
        wrapper.name not in {"email/send-with spaces", "review@2", "inactive_tool"}
        for wrapper in wrappers
    )
    generated_type = wrappers[0].arguments_schema.generated_type
    annotations = get_type_hints(generated_type, include_extras=True)
    assert set(annotations) == {"title", "count", "scores", "target", "recipients"}
    assert _annotation_base(annotations["title"]) is str
    assert _annotation_guides(annotations["title"]) == {"anyOf": ["brief", "full"]}
    assert _annotation_base(annotations["count"]) is int
    assert _annotation_guides(annotations["count"]) == {
        "minimum": 1,
        "maximum": 5,
    }
    scores_type = _annotation_base(annotations["scores"])
    assert get_origin(scores_type) is list
    assert get_args(scores_type) == (float,)
    assert _annotation_guides(annotations["scores"]) == {
        "minItems": 1,
        "maxItems": 3,
    }
    target_type = _annotation_base(annotations["target"])
    target_annotations = get_type_hints(target_type, include_extras=True)
    assert target_annotations == {"enabled": bool}
    assert isinstance(target_type.generation_schema(), FakeAppleGenerationSchema)
    recipients_type = _annotation_base(annotations["recipients"])
    assert get_origin(recipients_type) is list
    recipient_type = _annotation_base(get_args(recipients_type)[0])
    assert get_type_hints(recipient_type, include_extras=True) == {"address": str}
    assert isinstance(recipient_type.generation_schema(), FakeAppleGenerationSchema)


def test_apple_tool_bridge_uses_active_context_without_wire_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool("write", _ADMITTED_APPLE_TOOL_SCHEMA)
    registry = InMemoryToolRegistry([tool])
    active = registry.get_tool("write")
    context = _active_tool_context(registry, (active,))
    sdk = FakeAppleToolSDK()
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk", lambda: sdk
    )

    response = asyncio.run(
        create_apple_foundation_model_async_adapter().create_response(
            _tool_request(
                registry,
                descriptor_ids=(),
                adapter_context=context,
            )
        )
    )

    assert response.content == "answer"
    assert [wrapper.name for wrapper in sdk.sessions[0].tools] == ["dar_tool_0"]


_APPLE_CALLBACK_SCHEMA = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": False,
}


@pytest.mark.xfail(
    strict=True,
    reason="B3.2 must route Apple callbacks through DAR's coordinator",
)
def test_apple_callbacks_approved_dispatch_preserve_dar_state_and_model_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocations: list[tuple[str, dict[str, object]]] = []
    hook_events: list[str] = []
    decisions: list[ProviderDecisionRequest] = []
    coordinated_requests: list[object] = []

    async def coordinate(request: object) -> object:
        coordinated_requests.append(request)
        return await coordinate_tool_invocation_async(request)  # type: ignore[arg-type]

    def send_handler(arguments: dict[str, object]) -> ToolResult:
        invocations.append(("send", dict(arguments)))
        return ToolResult(
            tool_id="send",
            success=True,
            output={"secret": "not-for-the-model"},
            model_output={"visible": "sent"},
            raw_output={"secret": "not-for-the-model"},
        )

    def archive_handler(arguments: dict[str, object]) -> ToolResult:
        invocations.append(("archive", dict(arguments)))
        return ToolResult(
            tool_id="archive",
            success=True,
            output={"secret": "not-for-the-model"},
            model_output={"visible": "archived"},
            raw_output={"secret": "not-for-the-model"},
        )

    class Approver:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            decisions.append(request)
            return ProviderToolDecision(
                state=ProviderDecisionState.APPROVED,
                invocation_id=request.invocation_id,
                fingerprint=request.fingerprint,
            )

    send = _tool(
        "send",
        _APPLE_CALLBACK_SCHEMA,
        approval_required=True,
        handler=send_handler,
    )
    archive = _tool(
        "archive",
        _APPLE_CALLBACK_SCHEMA,
        approval_required=True,
        handler=archive_handler,
    )
    registry = InMemoryToolRegistry([send, archive])
    context = _active_tool_context(
        registry,
        (registry.get_tool("send"), registry.get_tool("archive")),
        decision_collaborator=Approver(),
        lifecycle_hooks=WorkflowLifecycleHooks(
            before_tool=lambda _context: hook_events.append("before"),
            after_tool=lambda _context: hook_events.append("after"),
        ),
    )
    sdk = FakeAppleCallbackSDK(
        ((0, '{"message": "hello"}'), (1, '{"message": "again"}'))
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk", lambda: sdk
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models.coordinate_tool_invocation_async",
        coordinate,
        raising=False,
    )

    response = asyncio.run(
        create_apple_foundation_model_async_adapter().create_response(
            _tool_request(
                registry,
                descriptor_ids=("send", "archive"),
                adapter_context=context,
            )
        )
    )

    assert response.content == "answer"
    assert len(coordinated_requests) == 2
    assert [request.tool_id for request in coordinated_requests] == [  # type: ignore[union-attr]
        "send",
        "archive",
    ]
    assert [request.arguments for request in coordinated_requests] == [  # type: ignore[union-attr]
        {"message": "hello"},
        {"message": "again"},
    ]
    action_ids = [request.action_id for request in coordinated_requests]  # type: ignore[union-attr]
    result_keys = [request.result_key for request in coordinated_requests]  # type: ignore[union-attr]
    assert all(isinstance(action_id, str) and action_id for action_id in action_ids)
    assert len(set(action_ids)) == 2
    assert len(set(result_keys)) == 2
    assert invocations == [
        ("send", {"message": "hello"}),
        ("archive", {"message": "again"}),
    ]
    assert len(decisions) == 2
    assert hook_events == ["before", "after", "before", "after"]
    assert set(context.state.tool_results) == set(result_keys)
    assert {
        result.tool_id: result.model_facing_output
        for result in context.state.tool_results.values()
    } == {
        "send": {"visible": "sent"},
        "archive": {"visible": "archived"},
    }
    assert [json.loads(result) for result in sdk.sessions[0].callback_results] == [
        {"visible": "sent"},
        {"visible": "archived"},
    ]
    assert [event.event_type for event in context.state.trace_events] == [
        "tool_started",
        "tool_result",
        "tool_finished",
        "tool_started",
        "tool_result",
        "tool_finished",
    ]


@pytest.mark.xfail(
    strict=True,
    reason="B3.2 must run callback arguments through DAR validation first",
)
def test_apple_callback_rejects_invalid_arguments_before_decision_or_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocations: list[dict[str, object]] = []
    hook_events: list[str] = []
    decisions: list[ProviderDecisionRequest] = []
    coordinated_requests: list[object] = []

    async def coordinate(request: object) -> object:
        coordinated_requests.append(request)
        return await coordinate_tool_invocation_async(request)  # type: ignore[arg-type]

    def handler(arguments: dict[str, object]) -> ToolResult:
        invocations.append(dict(arguments))
        return ToolResult(tool_id="send", success=True, output={"ok": True})

    class Approver:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            decisions.append(request)
            raise AssertionError("invalid arguments must not reach approval")

    tool = _tool(
        "send",
        _APPLE_CALLBACK_SCHEMA,
        approval_required=True,
        handler=handler,
    )
    registry = InMemoryToolRegistry([tool])
    context = _active_tool_context(
        registry,
        (registry.get_tool("send"),),
        decision_collaborator=Approver(),
        lifecycle_hooks=WorkflowLifecycleHooks(
            before_tool=lambda _context: hook_events.append("before"),
            after_tool=lambda _context: hook_events.append("after"),
        ),
    )
    sdk = FakeAppleCallbackSDK(((0, '{"message": 3}'),))
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk", lambda: sdk
    )
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models.coordinate_tool_invocation_async",
        coordinate,
        raising=False,
    )

    with pytest.raises(ModelExecutionError) as raised:
        asyncio.run(
            create_apple_foundation_model_async_adapter().create_response(
                _tool_request(
                    registry,
                    descriptor_ids=("send",),
                    adapter_context=context,
                )
            )
        )

    assert _has_cause(raised.value, ToolRegistryError)
    assert len(coordinated_requests) == 1
    assert decisions == []
    assert invocations == []
    assert hook_events == []
    assert context.state.tool_results == {}
    assert context.state.trace_events == []


def test_apple_tool_bridge_rejects_non_identifier_property_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = {
        "type": "object",
        "properties": {
            "email-address": {"type": "string"},
            "recipient name": {
                "type": "object",
                "properties": {"given-name": {"type": "string"}},
                "required": ["given-name"],
                "additionalProperties": False,
            },
        },
        "required": ["email-address", "recipient name"],
        "additionalProperties": False,
    }
    tool = _tool("write", schema)
    registry = InMemoryToolRegistry([tool])
    active = registry.get_tool("write")
    context = _active_tool_context(registry, (active,))
    sdk = FakeAppleToolSDK()
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk", lambda: sdk
    )

    with pytest.raises(ModelExecutionError, match="untranslatable.*schema"):
        asyncio.run(
            create_apple_foundation_model_async_adapter().create_response(
                _tool_request(
                    registry,
                    descriptor_ids=("write",),
                    adapter_context=context,
                )
            )
        )

    assert sdk.sessions == []


def test_apple_tool_bridge_rejects_keyword_property_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = {
        "type": "object",
        "properties": {"class": {"type": "string"}},
        "required": ["class"],
        "additionalProperties": False,
    }
    tool = _tool("write", schema)
    registry = InMemoryToolRegistry([tool])
    context = _active_tool_context(registry, (registry.get_tool("write"),))
    sdk = FakeAppleToolSDK()
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk", lambda: sdk
    )

    with pytest.raises(ModelExecutionError, match="untranslatable.*schema"):
        asyncio.run(
            create_apple_foundation_model_async_adapter().create_response(
                _tool_request(
                    registry,
                    descriptor_ids=("write",),
                    adapter_context=context,
                )
            )
        )

    assert sdk.sessions == []


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": "#/definitions/value"},
        {
            "type": "object",
            "properties": {"value": {"anyOf": [{"type": "string"}]}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": ["string", "null"]}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string", "enum": [1]}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string", "const": "fixed"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string", "format": "email"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string", "pattern": "[a-z]+"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string", "minLength": 1}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string", "maxLength": 12}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"allOf": [{"type": "string"}]}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"oneOf": [{"type": "string"}]}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": "null"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string", "x-future": True}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": {"type": "string"},
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": True,
        },
    ],
)
def test_apple_tool_bridge_rejects_untranslatable_schema_before_session_creation(
    monkeypatch: pytest.MonkeyPatch,
    schema: dict[str, object],
) -> None:
    tool = _tool("write", schema)
    registry = InMemoryToolRegistry([tool])
    tool = registry.get_tool("write")
    context = _active_tool_context(registry, (tool,))
    sdk = FakeAppleToolSDK()
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk", lambda: sdk
    )

    with pytest.raises(ModelExecutionError, match="untranslatable.*schema"):
        asyncio.run(
            create_apple_foundation_model_async_adapter().create_response(
                _tool_request(
                    registry,
                    descriptor_ids=("write",),
                    adapter_context=context,
                )
            )
        )

    assert sdk.sessions == []


def test_apple_tool_bridge_rejects_stale_or_raw_context_before_session_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool("write", _ADMITTED_APPLE_TOOL_SCHEMA)
    registry = InMemoryToolRegistry([tool])
    active = registry.get_tool("write")
    stale_context = _active_tool_context(registry, (active,))
    registry.register(_tool("write", _ADMITTED_APPLE_TOOL_SCHEMA), replace=True)
    sdk = FakeAppleToolSDK()
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk", lambda: sdk
    )

    for adapter_context in (
        stale_context,
        {"tools": registry.to_openai_tools(("write",))},
    ):
        with pytest.raises(ModelExecutionError, match="active tool context"):
            asyncio.run(
                create_apple_foundation_model_async_adapter().create_response(
                    _tool_request(
                        registry,
                        descriptor_ids=("write",),
                        adapter_context=adapter_context,
                    )
                )
            )

    assert sdk.sessions == []


def test_apple_tool_bridge_rejects_colliding_active_tool_mapping_before_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool("write", _ADMITTED_APPLE_TOOL_SCHEMA)
    registry = InMemoryToolRegistry([tool])
    tool = registry.get_tool("write")
    context = _active_tool_context(registry, (tool, tool))
    sdk = FakeAppleToolSDK()
    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models._load_sdk", lambda: sdk
    )

    with pytest.raises(ModelExecutionError, match="duplicate active tool"):
        asyncio.run(
            create_apple_foundation_model_async_adapter().create_response(
                _tool_request(
                    registry,
                    descriptor_ids=("write",),
                    adapter_context=context,
                )
            )
        )

    assert sdk.sessions == []
