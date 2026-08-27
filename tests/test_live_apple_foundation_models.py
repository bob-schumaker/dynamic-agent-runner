from __future__ import annotations

import asyncio
import importlib
import json
import sys
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.apple_foundation_models import (
    create_apple_foundation_model_async_adapter,
)
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.hooks import WorkflowLifecycleHooks
from dynamic_agent_runner.executor import execute_workflow
from dynamic_agent_runner.models import LoadedAgentWorkflow, ToolDefinition
from dynamic_agent_runner.openai_client import build_openai_request
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
    ProviderToolTerminalError,
    tool_context,
)
from dynamic_agent_runner.tracing import WorkflowTracer


_LIVE_SYSTEM_MODEL: object | None = None


def _require_live_apple() -> object:
    if sys.platform != "darwin":
        pytest.skip("Apple Foundation Models live tests require macOS")
    try:
        sdk = importlib.import_module("apple_fm_sdk")
    except Exception as exc:  # pragma: no cover - host prerequisite branch.
        pytest.skip(f"apple-fm-sdk is unavailable: {exc}")
    global _LIVE_SYSTEM_MODEL
    _LIVE_SYSTEM_MODEL = sdk.SystemLanguageModel()
    available, reason = _LIVE_SYSTEM_MODEL.is_available()
    if not available:
        pytest.skip(f"Apple system model is unavailable: {reason}")
    return sdk


_LIVE_SENTINEL_SCHEMA = {
    "type": "object",
    "properties": {"token": {"type": "string"}},
    "required": ["token"],
    "additionalProperties": False,
}


def _live_tool_context(
    registry: InMemoryToolRegistry,
    tool: RegisteredTool,
    *,
    decision_collaborator: object,
    lifecycle_hooks: WorkflowLifecycleHooks | None = None,
):
    state = SimpleNamespace(run_id="live-apple", tool_results={}, trace_events=[])
    return tool_context(
        plan=SimpleNamespace(
            workflow=SimpleNamespace(
                runtime_manifest=SimpleNamespace(package_id="live-apple-agent")
            ),
            max_steps=1,
        ),
        node=SimpleNamespace(id="live-apple-node"),
        tools=(tool,),
        registry=registry,
        state=state,
        tracer=WorkflowTracer(events=state.trace_events),
        lifecycle_hooks=lifecycle_hooks,
        retry_policy=RetryPolicy(),
        decision_collaborator=decision_collaborator,  # type: ignore[arg-type]
        executor_loop=asyncio.get_running_loop(),
    )


def _live_tool_request(
    registry: InMemoryToolRegistry,
    context: object,
    *,
    prompt: str,
):
    return build_openai_request(
        model="apple-system-language-model",
        messages=[
            {
                "role": "system",
                "content": (
                    "You must call the supplied sentinel tool exactly once before "
                    "responding. Do not substitute text for the required tool call."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        tools=registry.to_openai_tools(("sentinel",)),
        adapter_context=context,
    )


@pytest.mark.apple_live
def test_live_apple_text_generation() -> None:
    _require_live_apple()
    adapter = create_apple_foundation_model_async_adapter()
    request = build_openai_request(
        model="apple-system-language-model",
        messages=[{"role": "user", "content": "Reply with exactly: READY"}],
    )

    response = asyncio.run(adapter.create_response(request))

    assert isinstance(response.content, str)
    assert response.content.strip()


@pytest.mark.apple_live
def test_live_apple_structured_generation() -> None:
    _require_live_apple()
    adapter = create_apple_foundation_model_async_adapter()
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

    assert isinstance(response.content, str)
    value = json.loads(response.content)
    assert isinstance(value.get("status"), str)


@pytest.mark.apple_live
def test_live_apple_strict_coverage_workflow() -> None:
    _require_live_apple()
    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "live-apple-agent",
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
        model_adapter=[create_apple_foundation_model_async_adapter()],
        model_adapter_coverage="strict",
    )

    assert isinstance(result.final_result, str)
    assert result.final_result.strip()


@pytest.mark.apple_live
def test_live_apple_tool_callback_sentinel() -> None:
    """Native callback smoke; this host requires elevated execution."""

    sdk = _require_live_apple()
    callbacks: list[dict[str, object]] = []

    @sdk.generable("sentinel arguments")
    class SentinelArguments:
        token: str

    class SentinelTool(sdk.Tool):
        name = "dar_tool_0"
        description = "Records one fixed local sentinel and has no side effects."

        @property
        def arguments_schema(self) -> object:
            return SentinelArguments.generation_schema()

        async def call(self, args: object) -> str:
            callbacks.append(json.loads(args.to_json()))
            return "DAR_SENTINEL_OK"

    async def run() -> object:
        session = sdk.LanguageModelSession(
            instructions=(
                "Call dar_tool_0 exactly once with token DAR_SENTINEL, then "
                "reply SENTINEL_COMPLETE."
            ),
            tools=[SentinelTool()],
        )
        return await session.respond("Call the required tool now.")

    response = asyncio.run(run())

    assert callbacks == [{"token": "DAR_SENTINEL"}]
    assert str(response).strip()


@pytest.mark.apple_live
def test_live_apple_dar_callback_sentinel() -> None:
    """Show a native callback enters DAR before a no-side-effect handler."""

    _require_live_apple()
    events: list[str] = []
    invocations: list[dict[str, object]] = []
    decisions: list[ProviderDecisionRequest] = []

    class Approver:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            decisions.append(request)
            return ProviderToolDecision(
                state=ProviderDecisionState.APPROVED,
                invocation_id=request.invocation_id,
                fingerprint=request.fingerprint,
            )

    def handler(arguments: dict[str, object]) -> ToolResult:
        assert events == ["before"]
        invocations.append(dict(arguments))
        return ToolResult(
            tool_id="sentinel",
            success=True,
            output={"status": "DAR_LIVE_SENTINEL_OK"},
        )

    tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "sentinel",
                "input_schema": _LIVE_SENTINEL_SCHEMA,
                "approval_required": "yes",
                "description_for_llm": "Record a fixed local sentinel token.",
            }
        ),
        handler,
    )
    registry = InMemoryToolRegistry([tool])

    async def run() -> tuple[object, object]:
        context = _live_tool_context(
            registry,
            registry.get_tool("sentinel"),
            decision_collaborator=Approver(),
            lifecycle_hooks=WorkflowLifecycleHooks(
                before_tool=lambda _context: events.append("before"),
                after_tool=lambda _context: events.append("after"),
            ),
        )
        response = await create_apple_foundation_model_async_adapter().create_response(
            _live_tool_request(
                registry,
                context,
                prompt=(
                    "Call the available sentinel tool now with token "
                    "DAR_LIVE_SENTINEL. Do not answer until it succeeds."
                ),
            )
        )
        return response, context

    response, context = asyncio.run(run())

    assert invocations == [{"token": "DAR_LIVE_SENTINEL"}]
    assert len(decisions) == 1
    assert events == ["before", "after"]
    assert [event.event_type for event in context.state.trace_events] == [
        "tool_started",
        "tool_result",
        "tool_finished",
    ]
    assert isinstance(response.content, str)
    assert response.content.strip()


@pytest.mark.apple_live
def test_live_apple_dar_callback_denied_approval_skips_handler() -> None:
    """Show a native Apple callback reaches DAR approval but not its handler."""

    _require_live_apple()
    invocations: list[dict[str, object]] = []
    decisions: list[ProviderDecisionRequest] = []

    class Denier:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            decisions.append(request)
            return ProviderToolDecision(
                state=ProviderDecisionState.DENIED,
                invocation_id=request.invocation_id,
                fingerprint=request.fingerprint,
            )

    def handler(arguments: dict[str, object]) -> ToolResult:
        invocations.append(dict(arguments))
        raise AssertionError("denied approval must not invoke the handler")

    tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "sentinel",
                "input_schema": _LIVE_SENTINEL_SCHEMA,
                "approval_required": "yes",
                "description_for_llm": "Record a fixed local sentinel token.",
            }
        ),
        handler,
    )
    registry = InMemoryToolRegistry([tool])

    async def run() -> object:
        context = _live_tool_context(
            registry,
            registry.get_tool("sentinel"),
            decision_collaborator=Denier(),
        )
        try:
            await create_apple_foundation_model_async_adapter().create_response(
                _live_tool_request(
                    registry,
                    context,
                    prompt=(
                        "Call the available sentinel tool now with token "
                        "DAR_LIVE_SENTINEL. Do not answer before calling it."
                    ),
                )
            )
        except (ModelExecutionError, ProviderToolTerminalError):
            pass
        return context

    context = asyncio.run(run())

    assert len(decisions) == 1
    assert invocations == []
    assert context.state.tool_results == {}
    assert all(
        event.event_type == "provider_callback_budget_exhausted"
        for event in context.state.trace_events
    )
