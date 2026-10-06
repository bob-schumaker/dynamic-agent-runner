"""Tests for workflow executor behavior."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from dynamic_agent_runner.api import (
    compile_agent_workflow,
    load_agent_package_workflow,
    run_agent_workflow,
    run_agent_workflow_async,
)
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.context_selection import (
    ContextSelection,
    ContextSelectionCandidate,
)
from dynamic_agent_runner.decision_models import (
    DecisionExecutionLimits,
    DecisionModelBinding,
    DecisionModelIdentity,
    DecisionModelProfile,
    DecisionModelResult,
    DecisionModelResultItem,
    DecisionModelScore,
    DecisionMode,
    DecisionModelUse,
)
from dynamic_agent_runner.workflow_host.jevstyle_decision_adapter import (
    JEVSTYLE_V3_GGUF_PROFILE,
    JevStyleBackend,
    JevStyleMachineConfiguration,
    JevStyleModelCandidate,
    load_jevstyle_v3_binding,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
)
from dynamic_agent_runner.errors import (
    EmbeddingResultError,
    GuardrailExecutionError,
    LocalModelIdentityMismatchError,
    LocalModelOfflinePolicyError,
    LocalModelResolutionError,
    ModelExecutionError,
    WorkflowExecutionError,
)
from dynamic_agent_runner.executor import (
    ApprovalInterruption,
    ApprovalInterruptionState,
    _execute_model_tool_loop_async,
    _invoke_model_tool_call_async,
    execute_workflow,
    execute_workflow_async,
    WorkflowInterruptedResult,
    WorkflowExecutionState,
    prepare_model_input,
)
from dynamic_agent_runner.guardrails import (
    GuardrailDecision,
    GuardrailResult,
    InMemoryGuardrailRegistry,
)
from dynamic_agent_runner.hooks import NodeHookContext, WorkflowLifecycleHooks
from dynamic_agent_runner.host_integration import summarize_trace_events
from dynamic_agent_runner.local_models import (
    EmbeddingBatchResult,
    EmbeddingInputItem,
    EmbeddingVectorItem,
    LlamaCppLocalModelConfig,
    create_local_embedding_tool,
    create_llama_cpp_local_adapter,
)
import dynamic_agent_runner.hugging_face_support as hugging_face_support
import dynamic_agent_runner.local_models as local_models
from dynamic_agent_runner.mlx_models import (
    MLXLocalModelConfig,
    MLXToolCallCandidate,
    MLXToolCodecResponse,
    create_mlx_local_adapter,
)
from dynamic_agent_runner.apple_foundation_models import (
    AppleFoundationModelConfig,
    create_apple_foundation_model_async_adapter,
)
from dynamic_agent_runner.models import (
    LoadedAgentWorkflow,
    ToolDefinition,
    prepare_execution_plan,
)
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    ModelToolCall,
    ModelResponse,
    OpenAIClientAdapter,
    OpenAIMessage,
    OpenAIModelRequest,
    OpenAIProviderConfig,
)
from dynamic_agent_runner.tool_invocation import (
    ActiveAdapterToolContext,
    ProviderDecisionRequest,
    ProviderDecisionState,
    ProviderToolDecision,
    ProviderToolInterruption,
    ProviderToolTerminalError,
    tool_context,
)
from dynamic_agent_runner.registry import (
    InMemoryToolRegistry,
    RegisteredTool,
    ToolResult,
    tool_from_function,
)
from dynamic_agent_runner.retry import RetryPolicy
from dynamic_agent_runner.tracing import InMemoryTraceSink, WorkflowTracer
from parity_support import (
    ParityRecord,
    assert_parity_semantic_projection,
    parity_exposed_schemas,
    parity_contract_projection as shared_parity_contract_projection,
    install_parity_io_blocker,
    parity_loop_workflow as shared_parity_loop_workflow,
    parity_registry as shared_parity_registry,
    parity_tool_definitions as shared_parity_tool_definitions,
)


class FakeResponses:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses: list[object], models: object | None = None):
        self.responses = FakeResponses(responses)
        if models is not None:
            self.models = models


class FakeModels:
    def __init__(self, models: object):
        self.models = models
        self.calls: list[dict[str, object]] = []

    def list(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        return self.models


class FakeProvider:
    def __init__(
        self,
        responses: list[object],
        config: OpenAIProviderConfig,
        models: object | None = None,
    ) -> None:
        self.config = config
        self.client = FakeClient(responses, models=models)
        self.calls = 0

    def get_client(self) -> FakeClient:
        self.calls += 1
        return self.client


class AsyncFakeResponses:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        await asyncio.sleep(0)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AsyncFakeClient:
    def __init__(self, responses: list[object]):
        self.responses = AsyncFakeResponses(responses)


class FakeMLXBackend:
    def __init__(self, content: str = "mlx local") -> None:
        self.content = content
        self.requests: list[object] = []

    def generate(self, request: object) -> str:
        self.requests.append(request)
        return self.content


class FakeToolCapableMLXBackend(FakeMLXBackend):
    tool_codec_versions = frozenset({"test-v1"})

    def __init__(self, generated: str = "native tool response") -> None:
        super().__init__()
        self.generated = generated
        self.rendered_prompts: list[str] = []

    def generate_rendered(self, prompt: str, **_kwargs: object) -> str:
        self.rendered_prompts.append(prompt)
        return self.generated


class FakeMLXToolCodec:
    version = "test-v1"

    def __init__(self, *decoded: MLXToolCodecResponse) -> None:
        self.decoded = list(decoded)
        self.rendered_requests: list[OpenAIModelRequest] = []

    def render(self, request: OpenAIModelRequest) -> str:
        self.rendered_requests.append(request)
        return "<tool-aware-prompt>"

    def decode(self, _generated: str) -> MLXToolCodecResponse:
        return self.decoded.pop(0)


class FakeLlamaCppBackend:
    def __init__(self, content: str = "llama.cpp local") -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    def create_chat_completion(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return {"choices": [{"message": {"content": self.content}}]}


def test_approval_interruption_contract_shape() -> None:
    """Approval interruptions expose stable, inspectable pause metadata."""

    state = WorkflowExecutionState(prompt="Run", run_id="run-1")
    interruption = ApprovalInterruption(
        interruption_id="approval-1",
        run_id="run-1",
        workflow_id="approval-agent",
        node_id="write",
        tool_id="workspace_write",
        arguments={"path": "notes.txt", "content": "hello"},
        policy={"approval_required": "yes", "side_effect": "write"},
        reason="tool requires approval",
    )
    result = WorkflowInterruptedResult(
        final_result=None,
        state=state,
        interruption=interruption,
    )

    assert interruption.schema_version == 1
    assert interruption.state is ApprovalInterruptionState.PENDING
    assert result.final_result is None
    assert result.interruption.tool_id == "workspace_write"


def package_fixture_path(pattern_id: str = "basic-reasoning-agent") -> Path:
    return Path(__file__).parent / "fixtures" / "agent-patterns" / pattern_id


def make_adapter(responses: list[object]) -> OpenAIClientAdapter:
    return OpenAIClientAdapter(FakeClient(responses))


def _contains_identity(value: object, *candidates: object) -> bool:
    if any(value is candidate for candidate in candidates):
        return True
    if isinstance(value, Mapping):
        return any(
            _contains_identity(item, *candidates)
            for pair in value.items()
            for item in pair
        )
    if isinstance(value, list | tuple):
        return any(_contains_identity(item, *candidates) for item in value)
    return False


def make_async_adapter(responses: list[object]) -> AsyncOpenAIClientAdapter:
    return AsyncOpenAIClientAdapter(AsyncFakeClient(responses))


def make_named_adapter(
    responses: list[object],
    *,
    models: list[str],
    is_local: bool = False,
) -> OpenAIClientAdapter:
    return OpenAIClientAdapter(FakeClient(responses), models=models, is_local=is_local)


def make_tool(
    tool_id: str,
    output: object | None = None,
    *,
    raw: dict[str, object] | None = None,
) -> RegisteredTool:
    tool_raw: dict[str, object] = {
        "id": tool_id,
        "description_for_llm": f"Use {tool_id}",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    tool_raw.update(raw or {})
    return RegisteredTool(
        ToolDefinition.from_mapping(tool_raw),
        lambda args: output if output is not None else {"result": args["query"]},
    )


def make_flaky_tool(
    tool_id: str,
    outputs: list[object | Exception],
    *,
    raw: dict[str, object] | None = None,
) -> RegisteredTool:
    tool_raw: dict[str, object] = {
        "id": tool_id,
        "description_for_llm": f"Use {tool_id}",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    tool_raw.update(raw or {})

    def handler(_args: object) -> object:
        output = outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output

    return RegisteredTool(ToolDefinition.from_mapping(tool_raw), handler)


def make_async_tool(
    tool_id: str,
    output: object | None = None,
    *,
    raw: dict[str, object] | None = None,
) -> RegisteredTool:
    tool_raw: dict[str, object] = {
        "id": tool_id,
        "description_for_llm": f"Use {tool_id}",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    tool_raw.update(raw or {})

    async def handler(args: object) -> object:
        await asyncio.sleep(0)
        return output if output is not None else {"result": args["query"]}

    return RegisteredTool(ToolDefinition.from_mapping(tool_raw), handler)


def workflow_from(data: dict[str, object]) -> LoadedAgentWorkflow:
    return LoadedAgentWorkflow(runtime_manifest=load_runtime_manifest(data))


def decision_workflow(profile_id: str = "local.test.v1") -> LoadedAgentWorkflow:
    return workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "decision-model-agent",
            "entrypoint": "decide",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "decide",
                    "kind": "decision_step",
                    "decision_subtype": "decision_model",
                    "decision_profile": profile_id,
                    "context_from": "prompt",
                    "question": {
                        "id": "route-choice",
                        "text": "Choose a route.",
                        "options": [
                            {"id": "left", "label": "Left"},
                            {"id": "right", "label": "Right"},
                        ],
                    },
                },
                *[
                    {
                        "id": target,
                        "kind": "llm_step",
                        "prompt": {"user_template": target},
                    }
                    for target in ("left", "right")
                ],
            ],
            "edges": [
                {
                    "source": "decide",
                    "target": target,
                    "edge_kind": "branch",
                    "condition": target,
                }
                for target in ("left", "right")
            ],
        }
    )


def scored_decision_workflow(
    *,
    output_mode: str = "scores",
    policy: dict[str, object] | None = None,
    options: tuple[str, str] = ("left", "right"),
    profile_id: str = "local.test.v1",
) -> LoadedAgentWorkflow:
    left, right = options
    return workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "scored-decision-model-agent",
            "entrypoint": "decide",
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "decide",
                    "kind": "decision_step",
                    "decision_subtype": "decision_model",
                    "decision_profile": profile_id,
                    "decision_output_mode": output_mode,
                    "decision_route_policy": policy or {"kind": "argmax"},
                    "context_from": "prompt",
                    "question": {
                        "id": "route-choice",
                        "text": "Choose a route.",
                        "options": [
                            {"id": left, "label": left.title()},
                            {"id": right, "label": right.title()},
                        ],
                    },
                },
                *[
                    {
                        "id": target,
                        "kind": "llm_step",
                        "prompt": {"user_template": target},
                    }
                    for target in options
                ],
            ],
            "edges": [
                {
                    "source": "decide",
                    "target": target,
                    "edge_kind": "branch",
                    "condition": target,
                }
                for target in options
            ],
        }
    )


def decision_binding(
    adapter: object,
    *,
    modes: frozenset[DecisionMode] = frozenset({DecisionMode.CHOICE}),
    limits: DecisionExecutionLimits | None = None,
    permitted_uses: frozenset[DecisionModelUse] = frozenset(
        {DecisionModelUse.WORKFLOW_DECISION}
    ),
) -> DecisionModelBinding:
    return DecisionModelBinding(
        profile=DecisionModelProfile(
            identity=DecisionModelIdentity(
                "local.test.v1", "test-adapter", "test-model", "rev1", "test-runtime"
            ),
            max_input_bytes=1024,
            max_input_tokens=32,
            max_questions=1,
            max_options_per_question=2,
            max_result_bytes=1024,
            supported_modes=modes,
        ),
        adapter=adapter,
        execution_limits=limits or DecisionExecutionLimits(),
        permitted_uses=permitted_uses,
    )


def _jevstyle_test_binding(
    engine: object, *, limits: DecisionExecutionLimits | None = None
) -> DecisionModelBinding:
    execution_binding = ModelExecutionBinding(
        logical_model_id=JEVSTYLE_V3_GGUF_PROFILE.identity.model_id,
        runner_contract_id="jevstyle-gguf-v1",
        runner_contract_version="1",
        loader_profile_contract_id="jevstyle-gguf-loader-v1",
        loader_profile_contract_version="1",
        material_lock_digest="a" * 64,
        capability_requirements_digest="b" * 64,
        runner_capability_id="jevstyle-gguf-runner-v1",
        runner_capability_version="1",
        runner_capability_digest="c" * 64,
    )
    candidate = JevStyleModelCandidate(
        backend=JevStyleBackend.GGUF,
        profile=JEVSTYLE_V3_GGUF_PROFILE,
        execution_binding=execution_binding,
        materials_admitted=True,
        resource_admitted=True,
        load_engine=lambda _binding: engine,
    )
    selected = load_jevstyle_v3_binding(
        JevStyleMachineConfiguration("darwin", "arm64", False), (candidate,)
    )
    return DecisionModelBinding(
        profile=selected.profile,
        adapter=selected.adapter,
        execution_limits=limits or DecisionExecutionLimits(),
        permitted_uses=selected.permitted_uses,
    )


def retention_scoring_binding(
    adapter: object, *, profile_id: str = "local.retention.v1"
) -> DecisionModelBinding:
    return DecisionModelBinding(
        profile=DecisionModelProfile(
            identity=DecisionModelIdentity(
                profile_id, "retention-test", "test-model", "rev1", "test-runtime"
            ),
            max_input_bytes=10000,
            max_input_tokens=1000,
            max_questions=2,
            max_options_per_question=2,
            max_result_bytes=10000,
            supported_modes=frozenset({DecisionMode.SCORES}),
        ),
        adapter=adapter,
        permitted_uses=frozenset({DecisionModelUse.CONTEXT_RETENTION}),
    )


def context_scoring_workflow(
    decision_scoring: dict[str, object] | None,
) -> LoadedAgentWorkflow:
    context_compaction: dict[str, object] = {"strategy": "basic"}
    if decision_scoring is not None:
        context_compaction["decision_scoring"] = decision_scoring
    return workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "context-scoring-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": context_compaction,
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


def test_decision_model_step_uses_exact_binding_and_routes_to_mapped_edge() -> None:
    class Adapter:
        called_with = None

        def decide(self, request: object) -> DecisionModelResult:
            self.called_with = request
            return DecisionModelResult(
                decision_binding(self).profile.identity,
                (DecisionModelResultItem("route-choice", choice="right"),),
            )

    decision_adapter = Adapter()
    binding = decision_binding(decision_adapter)
    result = execute_workflow(
        decision_workflow(),
        prompt="private decision context",
        model_adapter=make_adapter([{"id": "final", "output_text": "right result"}]),
        decision_model_bindings={"local.test.v1": binding},
    )

    assert result.final_result == "right result"
    assert [execution.node_id for execution in result.state.executions] == [
        "decide",
        "right",
    ]
    assert decision_adapter.called_with.context == "private decision context"
    assert decision_adapter.called_with.execution_limits.max_input_tokens == 32
    decision_event = next(
        event for event in result.state.trace_events if event.event_type == "decision"
    )
    assert "private decision context" not in str(decision_event.payload)


def test_scores_decision_step_routes_argmax_and_resolves_ties_by_option_order() -> None:
    class Adapter:
        def decide(self, _request: object) -> DecisionModelResult:
            return DecisionModelResult(
                decision_binding(self).profile.identity,
                (
                    DecisionModelResultItem(
                        "route-choice",
                        scores=(
                            DecisionModelScore("left", 0.5),
                            DecisionModelScore("right", 0.5),
                        ),
                        score_semantics="ranking_score",
                    ),
                ),
            )

    adapter = Adapter()
    result = execute_workflow(
        scored_decision_workflow(),
        prompt="choose",
        model_adapter=make_adapter([{"id": "final", "output_text": "left result"}]),
        decision_model_bindings={
            "local.test.v1": decision_binding(
                adapter, modes=frozenset({DecisionMode.SCORES})
            )
        },
    )

    assert result.final_result == "left result"


def test_scores_threshold_routes_probability_and_noul_routes_no_below_threshold() -> None:
    class Adapter:
        def __init__(self, yes_probability: float) -> None:
            self.yes_probability = yes_probability

        def decide(self, _request: object) -> DecisionModelResult:
            return DecisionModelResult(
                decision_binding(self).profile.identity,
                (
                    DecisionModelResultItem(
                        "route-choice",
                        scores=(
                            DecisionModelScore("yes", self.yes_probability),
                            DecisionModelScore("no", 1.0 - self.yes_probability),
                        ),
                        score_semantics="probability",
                    ),
                ),
            )

    workflow = scored_decision_workflow(
        output_mode="noul",
        policy={"kind": "threshold", "option": "yes", "threshold": 0.7},
        options=("yes", "no"),
    )
    for probability, expected in ((0.8, "yes result"), (0.2, "no result")):
        adapter = Adapter(probability)
        result = execute_workflow(
            workflow,
            prompt="choose",
            model_adapter=make_adapter([{"id": "final", "output_text": expected}]),
            decision_model_bindings={
                "local.test.v1": decision_binding(
                    adapter, modes=frozenset({DecisionMode.SCORES})
                )
            },
        )
        assert result.final_result == expected


def test_jevstyle_binding_runs_through_the_workflow_decision_host() -> None:
    class Engine:
        def decide(self, _state: object, _question: object) -> dict[str, object]:
            return {
                "answer": "right",
                "probabilities": {"left": 0.1, "right": 0.9},
            }

    binding = _jevstyle_test_binding(Engine())
    profile_id = binding.profile.identity.profile_id
    result = execute_workflow(
        decision_workflow(profile_id),
        prompt="choose the right branch",
        model_adapter=make_adapter([{"id": "final", "output_text": "selected"}]),
        decision_model_bindings={profile_id: binding},
    )

    assert result.final_result == "selected"
    assert [execution.node_id for execution in result.state.executions] == [
        "decide",
        "right",
    ]


@pytest.mark.parametrize(
    ("limits", "message"),
    [
        (DecisionExecutionLimits(max_input_bytes=1), "bounded request"),
        (DecisionExecutionLimits(deadline_monotonic=0.0), "deadline"),
        (
            DecisionExecutionLimits(cancellation=SimpleNamespace(cancelled=True)),
            "cancelled",
        ),
    ],
)
def test_jevstyle_binding_obeys_workflow_host_limits(
    limits: DecisionExecutionLimits, message: str
) -> None:
    class Engine:
        calls = 0

        def decide(self, _state: object, _question: object) -> dict[str, object]:
            self.calls += 1
            raise AssertionError("host-rejected request reached the model")

    engine = Engine()
    binding = _jevstyle_test_binding(engine, limits=limits)
    profile_id = binding.profile.identity.profile_id

    with pytest.raises(WorkflowExecutionError, match=message):
        execute_workflow(
            decision_workflow(profile_id),
            prompt="private decision context",
            model_adapter=make_adapter([{"id": "final", "output_text": "unused"}]),
            decision_model_bindings={profile_id: binding},
        )

    assert engine.calls == 0


def test_jevstyle_engine_errors_are_redacted_by_the_workflow_host() -> None:
    class Engine:
        def decide(self, _state: object, _question: object) -> dict[str, object]:
            raise RuntimeError("private model payload")

    binding = _jevstyle_test_binding(Engine())
    profile_id = binding.profile.identity.profile_id

    with pytest.raises(WorkflowExecutionError, match="adapter failed") as error:
        execute_workflow(
            decision_workflow(profile_id),
            prompt="private decision context",
            model_adapter=make_adapter([{"id": "final", "output_text": "unused"}]),
            decision_model_bindings={profile_id: binding},
        )

    assert "private model payload" not in str(error.value)


def test_decision_model_step_rejects_retention_only_binding_before_inference() -> None:
    class Adapter:
        called = False

        def decide(self, _request: object) -> DecisionModelResult:
            self.called = True
            raise AssertionError("adapter must not be called")

    adapter = Adapter()
    with pytest.raises(Exception, match="workflow decision use"):
        execute_workflow(
            decision_workflow(),
            prompt="decision context",
            model_adapter=make_adapter([{"id": "final", "output_text": "done"}]),
            decision_model_bindings={
                "local.test.v1": decision_binding(
                    adapter,
                    permitted_uses=frozenset({DecisionModelUse.CONTEXT_RETENTION}),
                )
            },
        )
    assert not adapter.called


def test_async_decision_model_adapter_is_supported() -> None:
    class Adapter:
        async def decide(self, _request: object) -> DecisionModelResult:
            return DecisionModelResult(
                decision_binding(self).profile.identity,
                (DecisionModelResultItem("route-choice", choice="left"),),
            )

    async def run() -> object:
        return await execute_workflow_async(
            decision_workflow(),
            prompt="Pick",
            model_adapter=make_async_adapter(
                [{"id": "final", "output_text": "left result"}]
            ),
            decision_model_bindings={"local.test.v1": decision_binding(Adapter())},
        )

    result = asyncio.run(run())

    assert result.final_result == "left result"
    assert [execution.node_id for execution in result.state.executions] == [
        "decide",
        "left",
    ]


def test_prepare_model_input_scoring_keeps_pins_recent_turns_and_atomic_tool_turns() -> (
    None
):
    class Scorer:
        requests = []

        def decide(self, request) -> DecisionModelResult:
            self.requests.append(request)
            keep_turn = next(
                message["turn_id"]
                for message in request.context["candidate_messages"]
                if "preserve this old turn" in message["content"]
            )
            items = []
            for question in request.questions:
                keep_score = 4.0 if question.id == keep_turn else 1.0
                items.append(
                    DecisionModelResultItem(
                        question.id,
                        scores=(
                            DecisionModelScore("keep", keep_score),
                            DecisionModelScore("drop", 0.0),
                        ),
                        score_semantics="ranking_score",
                    )
                )
            return DecisionModelResult(binding.profile.identity, tuple(items))

    scorer = Scorer()
    binding = retention_scoring_binding(scorer)
    workflow = context_scoring_workflow(
        {
            "enabled": True,
            "profile_id": "local.retention.v1",
            "selection": "bounded_ranking",
            "max_selected_turns": 1,
            "max_candidates": 10,
            "batch_size": 2,
            "fallback": "recency",
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="continue the active task",
        session_messages=(
            OpenAIMessage("system", "pinned instruction"),
            OpenAIMessage("user", "preserve this old turn"),
            OpenAIMessage("assistant", "matching old answer"),
            OpenAIMessage("assistant", "tool call"),
            OpenAIMessage("tool", "tool result"),
            OpenAIMessage("user", "recent user"),
            OpenAIMessage("assistant", "recent answer"),
        ),
    )
    model_adapter = make_adapter([])

    prepared = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(model_adapter,),
        decision_model_bindings={"local.retention.v1": binding},
    )

    contents = [message.content for message in prepared.messages]
    assert "pinned instruction" in contents
    assert contents[-3:-1] == ["recent user", "recent answer"]
    assert contents.index("preserve this old turn") < contents.index(
        "matching old answer"
    )
    assert "tool call" in contents and "tool result" in contents
    assert prepared.preparation.compaction["decision_scoring"] == {
        "status": "scored",
        "scored_turns": 1,
        "selected_turns": 1,
    }
    assert "preserve this old turn" not in str(prepared.preparation.compaction)
    assert model_adapter.client.responses.calls == []


def test_prepare_model_input_low_scores_cannot_remove_pins_recent_or_unresolved_state() -> (
    None
):
    class Scorer:
        def decide(self, request) -> DecisionModelResult:
            return DecisionModelResult(
                binding.profile.identity,
                tuple(
                    DecisionModelResultItem(
                        question.id,
                        scores=(
                            DecisionModelScore("keep", 0.0),
                            DecisionModelScore("drop", 1.0),
                        ),
                        score_semantics="ranking_score",
                    )
                    for question in request.questions
                ),
            )

    scorer = Scorer()
    binding = retention_scoring_binding(scorer)
    workflow = context_scoring_workflow(
        {
            "enabled": True,
            "profile_id": "local.retention.v1",
            "selection": "bounded_ranking",
            "max_selected_turns": 1,
            "max_candidates": 10,
            "batch_size": 2,
            "fallback": "recency",
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="continue",
        node_outputs={"prior": {"unresolved": "must remain available"}},
        session_messages=(
            OpenAIMessage("system", "pinned instruction"),
            OpenAIMessage("user", "old candidate"),
            OpenAIMessage("assistant", "old answer"),
            OpenAIMessage("user", "recent request"),
            OpenAIMessage("assistant", "recent response"),
        ),
    )

    prepared = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(make_adapter([]),),
        decision_model_bindings={"local.retention.v1": binding},
    )

    contents = [message.content for message in prepared.messages]
    assert "pinned instruction" in contents
    assert contents[-3:-1] == ["recent request", "recent response"]
    assert "old candidate" not in contents and "old answer" not in contents
    assert state.node_outputs["prior"]["unresolved"] == "must remain available"
    assert prepared.preparation.compaction["decision_scoring"]["selected_turns"] == 0


def test_prepare_model_input_scoring_without_selection_is_diagnostic_only() -> None:
    class Scorer:
        def decide(self, request) -> DecisionModelResult:
            return DecisionModelResult(
                binding.profile.identity,
                tuple(
                    DecisionModelResultItem(
                        question.id,
                        scores=(
                            DecisionModelScore("keep", 100.0),
                            DecisionModelScore("drop", 0.0),
                        ),
                        score_semantics="ranking_score",
                    )
                    for question in request.questions
                ),
            )

    binding = retention_scoring_binding(Scorer())
    workflow = context_scoring_workflow(
        {
            "enabled": True,
            "profile_id": "local.retention.v1",
            "max_candidates": 10,
            "batch_size": 2,
            "fallback": "recency",
        }
    )
    plan = prepare_execution_plan(workflow)
    prepared = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        WorkflowExecutionState(
            prompt="continue",
            session_messages=(
                OpenAIMessage("user", "old request"),
                OpenAIMessage("assistant", "old answer"),
                OpenAIMessage("user", "recent request"),
                OpenAIMessage("assistant", "recent answer"),
            ),
        ),
        model_adapters=(make_adapter([]),),
        decision_model_bindings={"local.retention.v1": binding},
    )

    contents = [message.content for message in prepared.messages]
    assert "old request" in next(
        content
        for content in contents
        if content.startswith("Compacted earlier session context:")
    )
    assert "old request" not in [
        message.content
        for message in prepared.messages
        if message.role in {"user", "assistant"}
    ]
    assert "recent request" in contents and "recent answer" in contents
    assert prepared.preparation.compaction["decision_scoring"] == {
        "status": "diagnostic_only",
        "scored_turns": 1,
        "selected_turns": 0,
    }


@pytest.mark.parametrize("failure", ["missing", "invalid", "abstained", "timeout"])
def test_prepare_model_input_scoring_failure_falls_back_to_recency(
    failure: str,
) -> None:
    class Scorer:
        def decide(self, request) -> DecisionModelResult:
            if failure == "missing":
                return DecisionModelResult(binding.profile.identity, ())
            if failure == "invalid":
                return DecisionModelResult(
                    binding.profile.identity,
                    (DecisionModelResultItem("missing", choice="keep"),),
                )
            if failure == "abstained":
                return DecisionModelResult(
                    binding.profile.identity,
                    (
                        DecisionModelResultItem(
                            request.questions[0].id, status="abstained"
                        ),
                    ),
                )
            raise TimeoutError("private timeout details")

    scorer = Scorer()
    binding = retention_scoring_binding(scorer)
    workflow = context_scoring_workflow(
        {
            "enabled": True,
            "profile_id": "local.retention.v1",
            "selection": "bounded_ranking",
            "max_selected_turns": 1,
            "max_candidates": 10,
            "batch_size": 2,
            "fallback": "recency",
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="continue",
        session_messages=(
            OpenAIMessage("system", "pinned instruction"),
            OpenAIMessage("user", "old request"),
            OpenAIMessage("assistant", "old response"),
            OpenAIMessage("user", "recent request"),
            OpenAIMessage("assistant", "recent response"),
        ),
    )

    prepared = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(make_adapter([]),),
        decision_model_bindings={"local.retention.v1": binding},
    )

    contents = [message.content for message in prepared.messages]
    assert "pinned instruction" in contents
    assert contents[-3:-1] == ["recent request", "recent response"]
    assert "old request" not in contents
    assert "old response" not in contents
    assert prepared.preparation.compaction["decision_scoring"] == {
        "status": "fallback_recency",
        "scored_turns": 0,
        "selected_turns": 0,
    }


def test_prepare_model_input_scoring_is_diagnostic_without_policy() -> None:
    workflow = context_scoring_workflow(None)
    plan = prepare_execution_plan(workflow)
    prepared = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        WorkflowExecutionState(
            prompt="continue",
            session_messages=(
                OpenAIMessage("user", "old"),
                OpenAIMessage("assistant", "old answer"),
                OpenAIMessage("user", "recent"),
                OpenAIMessage("assistant", "recent answer"),
            ),
        ),
        model_adapters=(make_adapter([]),),
    )
    assert not prepared.preparation.compaction.get("decision_scoring")
    assert prepared.part_names[-3:] == (
        "session_message_1",
        "session_message_2",
        "user_prompt",
    )


def test_decision_model_step_rejects_missing_binding_and_scores_only_profile() -> None:
    workflow = decision_workflow()
    with pytest.raises(WorkflowExecutionError, match="profile"):
        execute_workflow(workflow, prompt="Pick")

    class Adapter:
        called = False

        def decide(self, _request: object) -> DecisionModelResult:
            self.called = True
            raise AssertionError("scores-only profile must fail before inference")

    adapter = Adapter()
    with pytest.raises(WorkflowExecutionError, match="choice"):
        execute_workflow(
            workflow,
            prompt="Pick",
            decision_model_bindings={
                "local.test.v1": decision_binding(
                    adapter, modes=frozenset({DecisionMode.SCORES})
                )
            },
        )
    assert not adapter.called


@pytest.mark.parametrize("limit", [DecisionExecutionLimits(max_input_bytes=1)])
def test_decision_model_host_limit_blocks_inference(
    limit: DecisionExecutionLimits,
) -> None:
    class Adapter:
        called = False

        def decide(self, _request: object) -> DecisionModelResult:
            self.called = True
            raise AssertionError("over-limit request must not reach adapter")

    adapter = Adapter()
    with pytest.raises(WorkflowExecutionError, match="bounded request"):
        execute_workflow(
            decision_workflow(),
            prompt="Pick",
            decision_model_bindings={
                "local.test.v1": decision_binding(adapter, limits=limit)
            },
        )
    assert not adapter.called


def test_decision_model_host_result_limit_prevents_routing() -> None:
    class Adapter:
        def decide(self, _request: object) -> DecisionModelResult:
            return DecisionModelResult(
                decision_binding(self).profile.identity,
                (DecisionModelResultItem("route-choice", choice="right"),),
            )

    with pytest.raises(WorkflowExecutionError, match="invalid adapter result"):
        execute_workflow(
            decision_workflow(),
            prompt="Pick",
            decision_model_bindings={
                "local.test.v1": decision_binding(
                    Adapter(), limits=DecisionExecutionLimits(max_result_bytes=1)
                )
            },
        )


@pytest.mark.parametrize(
    "limits",
    [
        DecisionExecutionLimits(deadline_monotonic=0.0),
        DecisionExecutionLimits(cancellation=SimpleNamespace(cancelled=True)),
    ],
)
def test_decision_model_lifecycle_limits_block_inference(
    limits: DecisionExecutionLimits,
) -> None:
    class Adapter:
        called = False

        def decide(self, _request: object) -> DecisionModelResult:
            self.called = True
            raise AssertionError("cancelled or expired request must not reach adapter")

    adapter = Adapter()
    with pytest.raises(WorkflowExecutionError, match="cancelled|deadline"):
        execute_workflow(
            decision_workflow(),
            prompt="Pick",
            decision_model_bindings={
                "local.test.v1": decision_binding(adapter, limits=limits)
            },
        )
    assert not adapter.called


def test_decision_model_adapter_and_result_failures_are_redacted() -> None:
    class FailedAdapter:
        def decide(self, _request: object) -> DecisionModelResult:
            raise RuntimeError("adapter leaked private payload")

    with pytest.raises(WorkflowExecutionError, match="adapter failed") as error:
        execute_workflow(
            decision_workflow(),
            prompt="Pick",
            decision_model_bindings={
                "local.test.v1": decision_binding(FailedAdapter())
            },
        )
    assert "private payload" not in str(error.value)

    class InvalidAdapter:
        def decide(self, _request: object) -> DecisionModelResult:
            return DecisionModelResult(
                decision_binding(self).profile.identity,
                (DecisionModelResultItem("route-choice", choice="not-mapped"),),
            )

    with pytest.raises(WorkflowExecutionError, match="invalid adapter result"):
        execute_workflow(
            decision_workflow(),
            prompt="Pick",
            decision_model_bindings={
                "local.test.v1": decision_binding(InvalidAdapter())
            },
        )


def test_execute_workflow_emits_safe_generation_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "generation-metadata",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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

    async def fake_create_model_response(_adapter: object, _request: object):
        return ModelResponse(
            content="private completion",
            metadata={
                "generation": {
                    "chunk_count": 2,
                    "chunk_exhausted": [True, False],
                    "generated_tokens": [4096, 7],
                }
            },
        )

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._create_model_response_async",
        fake_create_model_response,
    )

    result = execute_workflow(
        workflow,
        prompt="Trace this",
        model_adapter=make_named_adapter([], models=["gpt-test"]),
    )

    response_event = next(
        event
        for event in result.state.trace_events
        if event.event_type == "model_response"
    )
    assert response_event.payload["generation"] == {
        "chunk_count": 2,
        "chunk_exhausted": [True, False],
        "generated_tokens": [4096, 7],
    }
    assert response_event.sensitive_fields == ("content",)


class _RecordingEmbeddingProducer:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[EmbeddingInputItem, ...]] = []

    def embed(self, items: tuple[EmbeddingInputItem, ...]) -> object:
        self.calls.append(items)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _AsyncRecordingEmbeddingProducer(_RecordingEmbeddingProducer):
    async def embed(self, items: tuple[EmbeddingInputItem, ...]) -> object:
        self.calls.append(items)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _BlockingAsyncEmbeddingProducer(_AsyncRecordingEmbeddingProducer):
    def __init__(self, result: object) -> None:
        super().__init__(result)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def embed(self, items: tuple[EmbeddingInputItem, ...]) -> object:
        self.calls.append(items)
        self.started.set()
        await self.release.wait()
        return self.result


class _ClosableEmbeddingAwaitable:
    def __init__(self) -> None:
        self.closed = False

    def __await__(self):
        if False:
            yield None
        return embedding_result()

    def close(self) -> None:
        self.closed = True


def embedding_step_workflow(
    *,
    profile: str = "host-embedding",
    input_key: str = "documents",
) -> LoadedAgentWorkflow:
    """Return one terminal embedding step for T5.5 execution coverage."""

    return workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "embedding-step-agent",
            "entrypoint": "embed",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "embed",
                    "kind": "embedding_step",
                    "embedding_profile": profile,
                    "embedding_input_from": input_key,
                }
            ],
            "edges": [],
        }
    )


def embedding_items() -> tuple[EmbeddingInputItem, ...]:
    """Return one bounded test-only embedding batch."""

    return (EmbeddingInputItem(id="entry-1", text="private embedding text"),)


def embedding_result() -> EmbeddingBatchResult:
    """Return the typed result paired with ``embedding_items``."""

    return EmbeddingBatchResult(
        model="embedding-test",
        items=(EmbeddingVectorItem(id="entry-1", vector=(0.25, 0.75)),),
    )


def test_embedding_step_sync_returns_typed_terminal_result_once() -> None:
    """A host-bound sync producer supplies the ordinary terminal result."""

    batch = embedding_items()
    expected = embedding_result()
    producer = _RecordingEmbeddingProducer(expected)
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="sync",
    )

    result = execute_workflow(
        context,
        prompt="Embed the controlled batch",
        embedding_inputs={"documents": batch},
    )

    assert result.final_result is expected
    assert result.state.node_outputs["embed"] is expected
    assert result.state.executions[0].output is expected
    assert producer.calls == [batch]


def test_embedding_step_async_accepts_async_producer_once() -> None:
    """The async executor awaits one host-bound async producer."""

    batch = embedding_items()
    expected = embedding_result()
    producer = _AsyncRecordingEmbeddingProducer(expected)
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="async",
    )

    result = asyncio.run(
        execute_workflow_async(
            context,
            prompt="Embed the controlled batch",
            embedding_inputs={"documents": batch},
        )
    )

    assert result.final_result is expected
    assert producer.calls == [batch]


def test_embedding_step_async_accepts_direct_producer_result_once() -> None:
    """Async execution also accepts the host's direct producer result."""

    batch = embedding_items()
    expected = embedding_result()
    producer = _RecordingEmbeddingProducer(expected)
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="async",
    )

    result = asyncio.run(
        execute_workflow_async(
            context,
            prompt="Embed the controlled batch",
            embedding_inputs={"documents": batch},
        )
    )

    assert result.final_result is expected
    assert producer.calls == [batch]


def test_embedding_step_sync_rejects_async_binding_before_producer_dispatch() -> None:
    """The sync executor refuses an async binding before calling its producer."""

    producer = _AsyncRecordingEmbeddingProducer(embedding_result())
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="async",
    )

    with pytest.raises(WorkflowExecutionError, match="embedding"):
        execute_workflow(
            context,
            prompt="Embed the controlled batch",
            embedding_inputs={"documents": embedding_items()},
        )

    assert producer.calls == []


def test_embedding_step_rejects_unbound_profile_before_producer_dispatch() -> None:
    """The manifest cannot retarget the single host-bound embedding profile."""

    producer = _RecordingEmbeddingProducer(embedding_result())
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(profile="other-profile"),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="sync",
    )

    with pytest.raises(WorkflowExecutionError, match="embedding"):
        execute_workflow(
            context,
            prompt="Embed the controlled batch",
            embedding_inputs={"documents": embedding_items()},
        )

    assert producer.calls == []


def test_embedding_step_rejects_invalid_batch_before_producer_dispatch() -> None:
    """Host input values must be tuple-backed embedding batches."""

    producer = _RecordingEmbeddingProducer(embedding_result())
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="sync",
    )

    with pytest.raises(WorkflowExecutionError, match="embedding") as raised:
        execute_workflow(
            context,
            prompt="Embed the controlled batch",
            embedding_inputs={
                "documents": [EmbeddingInputItem("entry-1", "sentinel-host-text")]
            },
        )

    assert producer.calls == []
    assert "sentinel-host-text" not in str(raised.value)


def test_embedding_step_rejects_unsupported_producer_before_dispatch() -> None:
    """A context binding must expose the one standalone producer operation."""

    sink = InMemoryTraceSink()
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=object(),
        embedding_producer_mode="sync",
        trace_sink=sink,
    )

    with pytest.raises(WorkflowExecutionError, match="embedding"):
        execute_workflow(
            context,
            prompt="Embed the controlled batch",
            embedding_inputs={"documents": embedding_items()},
        )

    assert not any(event.event_type == "node_completed" for event in sink.events)


@pytest.mark.parametrize(
    "inputs",
    [
        {},
        {"other": embedding_items()},
        {"documents": (object(),)},
        {"": embedding_items(), "documents": embedding_items()},
    ],
)
def test_embedding_step_rejects_missing_or_unknown_input_before_producer_dispatch(
    inputs: dict[str, object],
) -> None:
    """The declared input key must resolve to one host-supplied batch."""

    producer = _RecordingEmbeddingProducer(embedding_result())
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="sync",
    )

    with pytest.raises(WorkflowExecutionError, match="embedding"):
        execute_workflow(
            context, prompt="Embed the controlled batch", embedding_inputs=inputs
        )

    assert producer.calls == []


@pytest.mark.parametrize("asynchronous", [False, True])
def test_embedding_step_rejects_invalid_producer_mode_before_dispatch(
    asynchronous: bool,
) -> None:
    """Only the two declared host producer modes may reach an embedding call."""

    producer = _RecordingEmbeddingProducer(embedding_result())
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="invalid",
    )

    if asynchronous:
        invocation = execute_workflow_async(
            context,
            prompt="Embed the controlled batch",
            embedding_inputs={"documents": embedding_items()},
        )
        with pytest.raises(WorkflowExecutionError, match="embedding"):
            asyncio.run(invocation)
    else:
        with pytest.raises(WorkflowExecutionError, match="embedding"):
            execute_workflow(
                context,
                prompt="Embed the controlled batch",
                embedding_inputs={"documents": embedding_items()},
            )

    assert producer.calls == []


def test_embedding_step_rejects_non_typed_producer_result_before_output() -> None:
    """A producer cannot install an untyped terminal result."""

    producer = _RecordingEmbeddingProducer(
        {
            "model": "embedding-test",
            "text": "sentinel-producer-text",
            "vector": [0.375],
        }
    )
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="sync",
    )

    with pytest.raises(WorkflowExecutionError, match="embedding") as raised:
        execute_workflow(
            context,
            prompt="Embed the controlled batch",
            embedding_inputs={"documents": embedding_items()},
        )

    assert producer.calls == [embedding_items()]
    assert "sentinel-producer-text" not in str(raised.value)
    assert "0.375" not in str(raised.value)


@pytest.mark.parametrize(
    ("error", "error_type"),
    [
        (EmbeddingResultError("embedding result is invalid"), EmbeddingResultError),
        (
            LocalModelResolutionError("model resolution failed"),
            LocalModelResolutionError,
        ),
        (
            LocalModelOfflinePolicyError("offline policy rejected resolution"),
            LocalModelOfflinePolicyError,
        ),
        (
            LocalModelIdentityMismatchError("model identity differs"),
            LocalModelIdentityMismatchError,
        ),
    ],
)
def test_embedding_step_preserves_producer_error_without_partial_output(
    error: Exception, error_type: type[Exception]
) -> None:
    """Existing embedding, resolution, offline, and identity errors pass through."""

    producer = _RecordingEmbeddingProducer(error)
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="sync",
    )

    with pytest.raises(error_type) as raised:
        execute_workflow(
            context,
            prompt="Embed the controlled batch",
            embedding_inputs={"documents": embedding_items()},
        )

    assert raised.value is error
    assert producer.calls == [embedding_items()]


def test_embedding_step_closes_unexpected_sync_awaitable_before_error() -> None:
    """A sync binding cannot leak an awaitable result after dispatch."""

    awaitable = _ClosableEmbeddingAwaitable()
    producer = _RecordingEmbeddingProducer(awaitable)
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="sync",
    )

    with pytest.raises(WorkflowExecutionError, match="embedding"):
        execute_workflow(
            context,
            prompt="Embed the controlled batch",
            embedding_inputs={"documents": embedding_items()},
        )

    assert producer.calls == [embedding_items()]
    assert awaitable.closed is True


def test_embedding_step_marks_batch_output_sensitive_in_external_trace() -> None:
    """The public trace summary never exposes embedding text or vectors."""

    producer = _RecordingEmbeddingProducer(embedding_result())
    sink = InMemoryTraceSink()
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="sync",
        trace_sink=sink,
    )

    execute_workflow(
        context,
        prompt="Embed the controlled batch",
        embedding_inputs={"documents": embedding_items()},
    )

    completed = next(
        event for event in sink.events if event.event_type == "node_completed"
    )
    assert completed.sensitive_fields == ("output",)
    summary = str(summarize_trace_events(sink.events))
    assert "private embedding text" not in summary
    assert "0.25" not in summary


def test_embedding_step_overlay_requires_host_execution_context() -> None:
    """A bare workflow cannot inject a host-owned embedding batch."""

    with pytest.raises(WorkflowExecutionError, match="embedding"):
        execute_workflow(
            embedding_step_workflow(),
            prompt="Embed the controlled batch",
            embedding_inputs={"documents": embedding_items()},
        )


def test_embedding_step_rejects_other_context_overlay_before_producer_dispatch() -> (
    None
):
    """Embedding inputs are the context's only permitted per-run overlay."""

    producer = _RecordingEmbeddingProducer(embedding_result())
    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=producer,
        embedding_producer_mode="sync",
    )

    with pytest.raises(WorkflowExecutionError, match="cannot be combined"):
        execute_workflow(
            context,
            prompt="Embed the controlled batch",
            embedding_inputs={"documents": embedding_items()},
            model_adapter=make_adapter([]),
        )

    assert producer.calls == []


def test_embedding_step_context_binding_is_immutable() -> None:
    """The host profile cannot be reassigned after execution context creation."""

    context = WorkflowExecutionContext(
        workflow=embedding_step_workflow(),
        embedding_profile_id="host-embedding",
        embedding_producer=_RecordingEmbeddingProducer(embedding_result()),
        embedding_producer_mode="sync",
    )

    with pytest.raises(AttributeError):
        context.embedding_profile_id = "other-profile"  # type: ignore[misc]


def test_embedding_step_copies_batch_before_async_producer_completion() -> None:
    """Mutating caller input after dispatch cannot change the selected batch."""

    async def invoke() -> tuple[
        object, _BlockingAsyncEmbeddingProducer, EmbeddingBatchResult
    ]:
        original = embedding_items()
        replacement = (EmbeddingInputItem(id="entry-2", text="replacement"),)
        inputs = {"documents": original}
        expected = embedding_result()
        producer = _BlockingAsyncEmbeddingProducer(expected)
        context = WorkflowExecutionContext(
            workflow=embedding_step_workflow(),
            embedding_profile_id="host-embedding",
            embedding_producer=producer,
            embedding_producer_mode="async",
        )
        task = asyncio.create_task(
            execute_workflow_async(
                context,
                prompt="Embed the controlled batch",
                embedding_inputs=inputs,
            )
        )
        await producer.started.wait()
        inputs["documents"] = replacement
        producer.release.set()
        return await task, producer, expected

    result, producer, expected = asyncio.run(invoke())

    assert result.final_result is expected
    assert producer.calls == [embedding_items()]


def test_local_embedding_tool_continues_model_loop_with_bounded_result() -> None:
    """One model-selected embedding call continues through the normal tool loop."""

    producer = _RecordingEmbeddingProducer(embedding_result())
    registry = InMemoryToolRegistry([create_local_embedding_tool(producer)])
    adapter = _ScriptedParityAdapter(
        [
            ModelResponse(
                content=None,
                tool_calls=(
                    ModelToolCall(
                        "embed-1",
                        "local_embedding_batch",
                        {
                            "items": [
                                {"id": "entry-1", "text": "private embedding text"}
                            ]
                        },
                    ),
                ),
            ),
            ModelResponse(content="embedded"),
        ]
    )

    result = asyncio.run(
        execute_workflow_async(
            loop_tool_workflow(
                tools=[{"id": "local_embedding_batch"}],
                available_tools=["local_embedding_batch"],
            ),
            prompt="Embed the controlled batch",
            tool_registry=registry,
            model_adapter=adapter,
        )
    )

    assert result.final_result == "embedded"
    assert producer.calls == [embedding_items()]
    assert len(adapter.requests) == 2
    tool_result = next(
        event
        for event in result.state.trace_events
        if event.event_type == "tool_result"
    )
    assert tool_result.payload["output"] == {"status": "embedding_result_redacted"}
    assert not any(
        event.event_type == "approval_requested" for event in result.state.trace_events
    )


def provider_compaction_workflow(
    *,
    fallback: str,
    retry_on_overflow: bool = False,
    prompt_hierarchy: dict[str, list[str]] | None = None,
) -> LoadedAgentWorkflow:
    auto: dict[str, object] = {
        "enabled": True,
        "threshold_ratio": 0.01,
        "implementation": "provider",
        "strategy": "provider_remote",
        "remote": {
            "provider_capability": "responses_compact",
            "fallback": fallback,
        },
    }
    if retry_on_overflow:
        auto["retry_on_overflow"] = True
    return workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "provider-context-compaction-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "prompt_hierarchy": prompt_hierarchy or {},
                        "context_compaction": {"auto": auto},
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


def test_compile_agent_workflow_preserves_base_workflow_and_executes_from_compiled() -> (
    None
):
    """Execution accepts compiled workflows while leaving the base workflow unchanged."""

    base_workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "compiled-execution-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "skills": [{"id": "base-skill", "instructions": "Base skill."}],
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Base {prompt}"},
                    "skill_refs": ["base-skill"],
                }
            ],
            "edges": [],
        }
    )

    compiled = compile_agent_workflow(
        base_workflow,
        runtime_overrides={
            "format_version": 1,
            "override_type": "dynamic_agent_runtime_overrides",
            "skills": {
                "added": [
                    {
                        "id": "added-skill",
                        "prompt_role": "developer",
                        "instructions": "Extra instructions.",
                    }
                ]
            },
            "nodes": {
                "answer": {
                    "prompt": {
                        "replace": {"user_template": "Compiled {prompt}"},
                    },
                    "skill_refs": {"add": ["added-skill"]},
                }
            },
        },
    )

    result = execute_workflow(
        compiled,
        prompt="request",
        model_adapter=make_adapter([{"id": "resp_1", "output_text": "done"}]),
    )

    assert result.final_result == "done"
    assert base_workflow.runtime_overrides is None
    request = result.state.node_inputs["answer"]
    message_texts = [message["content"] for message in request["input"]]
    assert "Extra instructions." in message_texts
    assert "Compiled request" in message_texts


def test_load_agent_package_workflow_returns_compiled_workflow(
    tmp_path,
) -> None:
    """Package-loading API returns compiled workflow form with optional overrides."""

    package_dir = tmp_path / "compiled-package"
    package_dir.mkdir()
    (package_dir / "agent-runtime.yaml").write_text(
        """
format_version: 1
package_type: dynamic_agent_design
package_id: compiled-package
entrypoint: answer
packaging:
  mode: hybrid_bundle
skills:
  - id: base-skill
    instructions: Base skill.
nodes:
  - id: answer
    kind: llm_step
    prompt:
      user_template: Base {prompt}
    skill_refs:
      - base-skill
edges: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "agent-graph.mmd").write_text("flowchart TD\n", encoding="utf-8")
    (package_dir / "agent-design.md").write_text(
        "Runtime manifest: `agent-runtime.yaml`\nMermaid graph: `agent-graph.mmd`\n",
        encoding="utf-8",
    )

    compiled = load_agent_package_workflow(
        str(package_dir),
        runtime_overrides={
            "format_version": 1,
            "override_type": "dynamic_agent_runtime_overrides",
            "skills": {
                "added": [
                    {
                        "id": "added-skill",
                        "prompt_role": "developer",
                        "instructions": "Extra instructions.",
                    }
                ]
            },
        },
    )

    assert compiled.base_workflow.package_root == str(package_dir)
    assert compiled.package_root == str(package_dir)
    assert compiled.runtime_overrides is not None
    assert compiled.runtime_overrides.added_skills[0].id == "added-skill"


def test_run_agent_workflow_accepts_package_directory() -> None:
    fixture = package_fixture_path()

    result = run_agent_workflow(
        package_directory=str(fixture),
        prompt="Say hello from package API.",
        model_adapter=make_adapter([{"id": "resp_pkg", "output_text": "package ok"}]),
    )

    assert result == "package ok"


def test_run_agent_workflow_accepts_model_adapter_coverage() -> None:
    fixture = package_fixture_path()

    result = run_agent_workflow(
        package_directory=str(fixture),
        prompt="Say hello from package API.",
        model_adapter=make_adapter(
            [{"id": "resp_coverage", "output_text": "coverage ok"}]
        ),
        model_adapter_coverage="augmented",
    )

    assert result == "coverage ok"


async def _run_agent_workflow_async_keeps_compatibility_artifact_inputs() -> None:
    fixture = package_fixture_path()

    result = await run_agent_workflow_async(
        runtime_manifest=str(fixture / "agent-runtime.yaml"),
        agent_design=str(fixture / "agent-design.md"),
        mermaid_graph=str(fixture / "agent-graph.mmd"),
        prompt="Say hello from compatibility inputs.",
        model_adapter=make_async_adapter(
            [{"id": "resp_compat", "output_text": "compat ok"}]
        ),
    )

    assert result == "compat ok"


def test_run_agent_workflow_async_keeps_compatibility_artifact_inputs() -> None:
    asyncio.run(_run_agent_workflow_async_keeps_compatibility_artifact_inputs())


async def _run_agent_workflow_async_accepts_model_adapter_coverage() -> None:
    fixture = package_fixture_path()

    result = await run_agent_workflow_async(
        runtime_manifest=str(fixture / "agent-runtime.yaml"),
        agent_design=str(fixture / "agent-design.md"),
        mermaid_graph=str(fixture / "agent-graph.mmd"),
        prompt="Say hello from compatibility inputs.",
        model_adapter=make_async_adapter(
            [{"id": "resp_coverage_async", "output_text": "coverage async ok"}]
        ),
        model_adapter_coverage="augmented",
    )

    assert result == "coverage async ok"


def test_run_agent_workflow_async_accepts_model_adapter_coverage() -> None:
    asyncio.run(_run_agent_workflow_async_accepts_model_adapter_coverage())


def test_prepare_execution_plan_resolves_node_indexes_and_defaults() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-default",
                    "max_steps": 8,
                    "tool_use_completion": {
                        "run_again": "required",
                        "stop_on_tool": "enabled",
                        "after_tool_result_tools": "disabled",
                        "final_output": "state_field",
                        "final_output_state_key": "lookup_summary",
                    },
                    "async_session": {
                        "mode": "create_or_resume",
                        "persist": "external_checkpoint",
                        "history": "summary",
                        "session_id_state_key": "session_id",
                        "session_messages_state_key": "session_messages",
                    },
                    "retry_policy": {"max_attempts": 2},
                    "token_budget": {"max_prompt_tokens": 100},
                }
            },
            "metadata": {
                "handoffs": [
                    {
                        "id": "handoff_to_reviewer",
                        "target": "reviewer",
                        "on_handoff": "switch_active_profile",
                        "nested_history": "preserve",
                    }
                ]
            },
            "extensions": {"future_optional": {"required": False, "config": {}}},
            "output_contracts": [
                {"id": "answer_contract", "required_fields": ["message"]}
            ],
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "model": "gpt-node",
                    "model_parameters": {"temperature": 0},
                    "tool_choice": "auto",
                    "response_format": {"type": "json_object"},
                    "prompt": {
                        "user_template": "Answer {prompt}",
                        "output_schema_ref": "answer_contract",
                    },
                    "available_tools": ["search_repo"],
                    "retry_policy": {"max_attempts": 3},
                    "token_budget_policy": {"max_prompt_tokens": 50},
                },
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "static"},
                    "inputs_from": {"extra": "answer"},
                    "outputs": {"state_key": "lookup_summary"},
                    "agent_as_tool": {
                        "skill_id": "search-specialist",
                        "task_boundary": "perform a bounded search subtask",
                        "output_mode": "tool_result",
                    },
                    "failure_behavior": "continue",
                    "retry_policy": {"max_attempts": 4},
                },
                {
                    "id": "route",
                    "kind": "decision_step",
                    "decision_subtype": "llm_route",
                    "route_from": "answer",
                    "decision_contract": {"allowed_paths": ["done"]},
                },
            ],
            "edges": [
                {"source": "answer", "target": "lookup", "edge_kind": "sequential"},
                {"source": "lookup", "target": "route", "edge_kind": "sequential"},
            ],
            "tools": [{"id": "search_repo"}],
        }
    )

    plan = prepare_execution_plan(workflow)

    assert plan.entrypoint_id == "answer"
    assert plan.max_steps == 8
    assert plan.tool_use_completion_policy is not None
    assert plan.tool_use_completion_policy.run_again == "required"
    assert plan.tool_use_completion_policy.stop_on_tool == "enabled"
    assert plan.tool_use_completion_policy.after_tool_result_tools == "disabled"
    assert plan.tool_use_completion_policy.final_output == "state_field"
    assert plan.tool_use_completion_policy.final_output_state_key == "lookup_summary"
    assert plan.async_session_policy is not None
    assert plan.async_session_policy.mode == "create_or_resume"
    assert plan.async_session_policy.persist == "external_checkpoint"
    assert plan.async_session_policy.history == "summary"
    assert plan.async_session_policy.session_id_state_key == "session_id"
    assert plan.async_session_policy.session_messages_state_key == "session_messages"
    assert len(plan.handoffs) == 1
    assert plan.handoffs[0].id == "handoff_to_reviewer"
    assert plan.handoffs[0].target == "reviewer"
    assert set(plan.nodes_by_id) == {"answer", "lookup", "route"}
    assert [edge.target for edge in plan.edges_by_source["answer"]] == ["lookup"]
    assert plan.unsupported_extensions == ("future_optional",)
    answer = plan.nodes_by_id["answer"]
    assert answer.model == "gpt-node"
    assert answer.model_parameters == {"temperature": 0}
    assert answer.tool_choice == "auto"
    assert answer.output_schema_ref == "answer_contract"
    assert answer.retry_policy == {"max_attempts": 3}
    assert answer.token_budget_policy == {"max_prompt_tokens": 50}
    lookup = plan.nodes_by_id["lookup"]
    assert lookup.agent_as_tool is not None
    assert lookup.agent_as_tool.skill_id == "search-specialist"
    assert lookup.agent_as_tool.task_boundary == "perform a bounded search subtask"
    assert lookup.agent_as_tool.output_mode == "tool_result"
    assert lookup.inputs == {"query": "static"}
    assert lookup.inputs_from == {"extra": "answer"}
    assert lookup.outputs == {"state_key": "lookup_summary"}
    assert lookup.failure_behavior == "continue"
    route = plan.nodes_by_id["route"]
    assert route.route_from == "answer"
    assert route.allowed_routes == frozenset({"done"})


def test_prepare_execution_plan_preserves_tool_choice_policy() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-choice-policy-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-default",
                    "tool_choice_policy": {
                        "initial": "required",
                        "after_tool_result": "auto",
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "available_tools": ["search_repo"],
                    "tool_choice_policy": {
                        "initial": "auto",
                        "after_tool_result": "required",
                    },
                },
                {
                    "id": "legacy",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Legacy {prompt}"},
                    "tool_choice": "required",
                },
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )

    plan = prepare_execution_plan(workflow)

    assert plan.tool_choice_policy is not None
    assert plan.tool_choice_policy.initial == "required"
    assert plan.tool_choice_policy.after_tool_result == "auto"
    answer = plan.nodes_by_id["answer"]
    assert answer.tool_choice_policy is not None
    assert answer.tool_choice_policy.initial == "auto"
    assert answer.tool_choice_policy.after_tool_result == "required"
    assert plan.nodes_by_id["legacy"].tool_choice == "required"


def test_prepare_execution_plan_keeps_base_workflow_unchanged_for_context_pipeline_nodes() -> (
    None
):
    """Eligible context-pipeline nodes should be prepared without mutating base workflow data."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "graph-mutation-base-immutability",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {prepared_context} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "prepared_context",
                    },
                }
            ],
            "edges": [],
        }
    )
    base_raw_before = deepcopy(workflow.runtime_manifest.nodes[0].raw)

    plan = prepare_execution_plan(workflow)

    assert workflow.runtime_manifest.nodes[0].raw == base_raw_before
    assert getattr(plan, "mutation_bundle", None) is not None


def test_prepare_execution_plan_derives_mutation_preparation_for_eligible_llm_step() -> (
    None
):
    """Eligible llm_step nodes should receive derived mutation preparation metadata."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "graph-mutation-derived-preparation",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {prepared_context} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "prepared_context",
                    },
                }
            ],
            "edges": [],
        }
    )

    plan = prepare_execution_plan(workflow)
    answer = plan.nodes_by_id["answer"]

    assert getattr(answer, "mutation_spec", None) is not None


def test_prepare_model_input_applies_context_pipeline_prepared_context_before_render() -> (
    None
):
    """Eligible llm_step nodes should receive prepared context before prompt rendering."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-context-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {prepared_context} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "prepared_context",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="What changed?",
        session_messages=(
            OpenAIMessage(role="user", content="Earlier question."),
            OpenAIMessage(role="assistant", content="Earlier answer."),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    user_prompt = prepared_input.named_parts["user_prompt"].content
    assert "Earlier question." in user_prompt
    assert "Earlier answer." in user_prompt
    assert "What changed?" in user_prompt


def test_prepare_model_input_respects_context_contract_output_slot_name() -> None:
    """Prepared-input mutation should fill the declared output slot, not a hard-coded key."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-context-output-slot-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {context_window} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "context_window",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Summarize the thread.",
        session_messages=(
            OpenAIMessage(role="user", content="First question."),
            OpenAIMessage(role="assistant", content="First answer."),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    user_prompt = prepared_input.named_parts["user_prompt"].content
    assert "First question." in user_prompt
    assert "First answer." in user_prompt
    assert "Summarize the thread." in user_prompt


def test_prepare_model_input_records_mutation_preparation_diagnostics() -> None:
    """Prepared-input metadata and traces should distinguish transformed inputs."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-context-diagnostics-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {prepared_context} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "prepared_context",
                    },
                },
                {
                    "id": "plain",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                },
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="What changed?",
        session_messages=(
            OpenAIMessage(role="user", content="Earlier question."),
            OpenAIMessage(role="assistant", content="Earlier answer."),
        ),
    )
    tracer = WorkflowTracer(events=state.trace_events, run_id="test-run")

    transformed_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        tracer=tracer,
    )
    unchanged_input = prepare_model_input(
        plan.nodes_by_id["plain"],
        plan,
        state,
        tracer=tracer,
    )

    assert transformed_input.preparation.mutation_applied is True
    assert transformed_input.preparation.mutation_id == "context-pruning-answer"
    assert transformed_input.preparation.mutation_output_slots == ("prepared_context",)
    assert unchanged_input.preparation.mutation_applied is False
    assert unchanged_input.preparation.mutation_id is None
    assert unchanged_input.preparation.mutation_output_slots == ()

    prepared_events = [
        event
        for event in state.trace_events
        if event.event_type == "model_input_prepared"
    ]
    prepared_payloads = {event.node_id: event.payload for event in prepared_events}

    assert prepared_payloads["answer"]["mutation_applied"] is True
    assert prepared_payloads["answer"]["mutation_id"] == "context-pruning-answer"
    assert prepared_payloads["answer"]["mutation_output_slots"] == ("prepared_context",)
    assert prepared_payloads["plain"]["mutation_applied"] is False
    assert prepared_payloads["plain"]["mutation_id"] is None
    assert prepared_payloads["plain"]["mutation_output_slots"] == ()


def test_pruning_context_injection_trace_reports_redacted_attachment() -> None:
    """Mutation traces should identify injection points without transcript text."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "pruning-context-injection-trace-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {prepared_context} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "prepared_context",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="What changed?",
        session_messages=(
            OpenAIMessage(role="user", content="secret earlier question"),
            OpenAIMessage(role="assistant", content="secret earlier answer"),
        ),
    )
    tracer = WorkflowTracer(events=state.trace_events, run_id="test-run")

    prepare_model_input(plan.nodes_by_id["answer"], plan, state, tracer=tracer)

    [prepared_event] = [
        event
        for event in state.trace_events
        if event.event_type == "model_input_prepared"
    ]
    payload = prepared_event.payload

    assert payload["mutation_attachment"] == {
        "type": "llm_step_interaction",
        "target_node_id": "answer",
    }
    assert "secret earlier question" not in repr(payload)
    assert "secret earlier answer" not in repr(payload)


def test_prepare_model_input_renders_messages_and_named_parts() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-input-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "skills": [
                {
                    "id": "style-guide",
                    "prompt_role": "developer",
                    "instructions": "Use concise style for {prompt}.",
                }
            ],
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "skill_refs": ["style-guide"],
                    "prompt": {
                        "system": "System {prompt}.",
                        "user_template": "Answer {prompt}.",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="question")

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert prepared_input.model == "gpt-test"
    assert prepared_input.part_names == (
        "system",
        "skill_instructions",
        "user_prompt",
    )
    assert [message.content for message in prepared_input.messages] == [
        "System question.",
        "Use concise style for question.",
        "Answer question.",
    ]
    assert prepared_input.named_parts["user_prompt"].content == "Answer question."


def test_prepare_model_input_applies_hierarchy_pruning_and_compaction() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "prepared-input-policy-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "prompt_hierarchy": {
                            "system": ["Global safety first."],
                            "developer": ["Workspace rules apply."],
                        },
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "strategy": "summary_message",
                            "summary_role": "developer",
                            "summary_prefix": "Earlier session:",
                            "max_chars_per_message": 18,
                        },
                    },
                }
            },
            "skills": [
                {
                    "id": "style-guide",
                    "prompt_role": "developer",
                    "instructions": "Use concise style for {prompt}.",
                }
            ],
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "skill_refs": ["style-guide"],
                    "prompt": {
                        "system": "System {prompt}.",
                        "user_template": "Answer {prompt}.",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="question",
        session_messages=(
            OpenAIMessage(role="user", content="First older user request."),
            OpenAIMessage(role="assistant", content="First older assistant reply."),
            OpenAIMessage(role="user", content="Most recent user request."),
            OpenAIMessage(role="assistant", content="Most recent assistant reply."),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert prepared_input.part_names == (
        "hierarchy_system_1",
        "system",
        "skill_instructions",
        "hierarchy_developer_1",
        "session_summary",
        "session_message_1",
        "session_message_2",
        "user_prompt",
    )
    assert [message.role for message in prepared_input.messages] == [
        "system",
        "system",
        "developer",
        "developer",
        "developer",
        "user",
        "assistant",
        "user",
    ]
    assert prepared_input.named_parts["session_summary"].content == (
        "Earlier session:\n- user: First older user …\n- assistant: First older assis…"
    )
    assert prepared_input.named_parts["session_message_1"].content == (
        "Most recent user request."
    )
    assert prepared_input.named_parts["session_message_2"].content == (
        "Most recent assistant reply."
    )
    assert prepared_input.preparation.hierarchy_applied is True
    assert prepared_input.preparation.session_messages_included == 2
    assert prepared_input.preparation.session_messages_pruned == 2
    assert prepared_input.preparation.context_compaction_applied is True


def test_pruning_context_injection_uses_bounded_session_messages() -> None:
    """Injected pruning context should use prepare-stage bounded session history."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "pruning-context-bounded-session-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "strategy": "summary_message",
                            "summary_role": "developer",
                            "summary_prefix": "Earlier session:",
                            "max_chars_per_message": 20,
                        },
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {prepared_context} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        },
                        {"kind": "latest_user_prompt", "source": "prompt"},
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "current_prompt_input": "prompt",
                        "output_slot": "prepared_context",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="What should I do next?",
        session_messages=(
            OpenAIMessage(role="user", content="pruned older secret request"),
            OpenAIMessage(role="assistant", content="pruned older secret answer"),
            OpenAIMessage(role="user", content="recent user request"),
            OpenAIMessage(role="assistant", content="recent assistant answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)
    user_prompt = prepared_input.named_parts["user_prompt"].content

    assert "recent user request" in user_prompt
    assert "recent assistant answer" in user_prompt
    assert "What should I do next?" in user_prompt
    assert "pruned older secret request" not in user_prompt
    assert "pruned older secret answer" not in user_prompt
    assert prepared_input.preparation.session_messages_included == 2
    assert prepared_input.preparation.session_messages_pruned == 2


def test_pruning_context_injection_reports_bounded_context_diagnostics() -> None:
    """Injected context diagnostics should report counts without transcript text."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "pruning-context-diagnostics-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 1},
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "Use {prepared_context} to answer {prompt}"
                    },
                    "context_pipeline": {
                        "enabled": True,
                        "strategy": "semantic_pruning",
                        "profile": "default",
                    },
                    "context_sources": [
                        {
                            "kind": "conversation_history",
                            "source": "state.chat_history",
                        }
                    ],
                    "context_contract": {
                        "history_input": "state.chat_history",
                        "output_slot": "prepared_context",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Continue.",
        session_messages=(
            OpenAIMessage(role="user", content="secret old content"),
            OpenAIMessage(role="user", content="visible recent content"),
        ),
    )
    tracer = WorkflowTracer(events=state.trace_events, run_id="test-run")

    prepare_model_input(plan.nodes_by_id["answer"], plan, state, tracer=tracer)

    [prepared_event] = [
        event
        for event in state.trace_events
        if event.event_type == "model_input_prepared"
    ]
    payload = prepared_event.payload

    assert payload["mutation_context"] == {
        "session_messages_included": 1,
        "session_messages_pruned": 1,
        "context_compaction_applied": False,
    }
    assert "secret old content" not in repr(payload)
    assert "visible recent content" not in repr(payload)


def test_prepare_model_input_groups_session_messages_into_turn_units() -> None:
    """prepare_model_input records stable turn/segment diagnostics for sessions."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "turn-grouping-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "context_compaction": {
                            "auto": {
                                "enabled": True,
                                "implementation": "metadata_only",
                                "strategy": "basic",
                            }
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish the work",
        session_messages=(
            OpenAIMessage(role="user", content="first request"),
            OpenAIMessage(role="assistant", content="calling search"),
            OpenAIMessage(role="tool", content="search result"),
            OpenAIMessage(role="assistant", content="first answer"),
            OpenAIMessage(role="user", content="second request"),
            OpenAIMessage(role="assistant", content="second answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert prepared_input.preparation.turn_count == 2
    assert prepared_input.preparation.segment_count == 6
    assert prepared_input.preparation.turns == (
        {
            "turn_id": "turn_1",
            "lane": "recent_turns",
            "message_count": 4,
            "roles": ("user", "assistant", "tool", "assistant"),
            "selection_status": "included",
        },
        {
            "turn_id": "turn_2",
            "lane": "current_turn",
            "message_count": 2,
            "roles": ("user", "assistant"),
            "selection_status": "included",
        },
    )
    assert prepared_input.preparation.segments[0]["segment_id"] == "turn_1_segment_1"
    assert prepared_input.preparation.segments[0]["role"] == "user"
    assert prepared_input.preparation.segments[2]["role"] == "tool"


def test_prepare_model_input_records_auto_compaction_threshold_metadata() -> None:
    """prepare_model_input normalizes auto-compaction threshold diagnostics."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "auto-compact-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "context_compaction": {
                            "auto": {
                                "enabled": True,
                                "threshold_ratio": 0.95,
                                "reserve_tokens": 200,
                                "scope": "current_run",
                                "implementation": "metadata_only",
                                "strategy": "basic",
                                "mode": "auto",
                                "trigger": "reserve_tokens",
                                "lifecycle_stages": ["validate", "segment", "report"],
                                "metrics": ["lane_utilization"],
                            }
                        },
                        "context_compression": {
                            "profile": "fast",
                            "lanes": {
                                "pinned_tokens": 100,
                                "current_turn_tokens": 200,
                            },
                            "selection": {
                                "strategy": "deterministic_overlap",
                                "max_selected_turns": 3,
                                "chronological_reassembly": True,
                            },
                        },
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "model": "gpt-test",
                    "prompt": {"user_template": "Answer {prompt}"},
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    adapter = make_named_adapter(
        [ModelResponse(content="ok")],
        models=["gpt-test"],
    )
    adapter.context_windows = {"gpt-test": 1000}
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="older"),
            OpenAIMessage(role="assistant", content="answer"),
        ),
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(adapter,),
    )

    assert prepared_input.preparation.context_threshold == {
        "enabled": True,
        "threshold_ratio": 0.9,
        "context_window": 1000,
        "threshold_tokens": 900,
        "reserve_tokens": 200,
        "trigger": "reserve_tokens",
        "scope": "current_run",
        "implementation": "metadata_only",
        "strategy": "basic",
        "mode": "auto",
        "status": "metadata_only",
    }
    assert prepared_input.preparation.compression_profile == "fast"
    assert prepared_input.preparation.lane_budgets == {
        "pinned_tokens": 100,
        "current_turn_tokens": 200,
    }
    assert prepared_input.preparation.selection_policy == {
        "strategy": "deterministic_overlap",
        "max_selected_turns": 3,
        "chronological_reassembly": True,
    }
    assert prepared_input.preparation.lifecycle_stages == (
        {"stage": "validate", "status": "complete"},
        {"stage": "segment", "status": "complete"},
        {"stage": "report", "status": "complete"},
    )
    assert prepared_input.preparation.metrics == ("lane_utilization",)


def test_prepare_model_input_basic_compaction_reports_deterministic_metadata() -> None:
    """Basic fallback compaction is deterministic and protects recent turns."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "basic-compaction-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "strategy": "basic",
                            "summary_prefix": "Basic compacted context:",
                            "max_chars_per_message": 12,
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(
                role="user",
                content="older request with many details " * 20,
            ),
            OpenAIMessage(
                role="assistant",
                content="older answer with many details " * 20,
            ),
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert prepared_input.part_names == (
        "session_summary",
        "session_message_1",
        "session_message_2",
        "user_prompt",
    )
    assert prepared_input.named_parts["session_summary"].content == (
        "Basic compacted context:\n- user: older reque…\n- assistant: older answe…"
    )
    assert prepared_input.named_parts["session_message_1"].content == "latest request"
    assert prepared_input.named_parts["session_message_2"].content == "latest answer"
    assert prepared_input.preparation.compaction["strategy"] == "basic"
    assert prepared_input.preparation.compaction["messages_before"] == 2
    assert prepared_input.preparation.compaction["messages_after"] == 1
    assert (
        prepared_input.preparation.compaction["tokens_before"]
        > (prepared_input.preparation.compaction["tokens_after"])
    )
    assert 0 < prepared_input.preparation.compaction["compression_ratio"] < 1


def test_prepare_model_input_basic_compaction_noops_when_under_target() -> None:
    """Basic fallback compaction does not run when no session history is pruned."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "basic-compaction-noop-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 4},
                        "context_compaction": {"strategy": "basic"},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert "session_summary" not in prepared_input.named_parts
    assert prepared_input.preparation.context_compaction_applied is False
    assert prepared_input.preparation.compaction == {}


def test_prepare_model_input_compaction_tool_pairs_preserves_latest_turn() -> None:
    """Whole-turn pruning must not split a latest tool-call/result turn."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-pair-compaction-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 1},
                        "context_compaction": {"strategy": "basic"},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="old request"),
            OpenAIMessage(role="assistant", content="old answer"),
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="calling lookup"),
            OpenAIMessage(role="tool", content="lookup result"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert [
        prepared_input.named_parts[name].content
        for name in prepared_input.part_names
        if name.startswith("session_message_")
    ] == [
        "latest request",
        "calling lookup",
        "lookup result",
        "latest answer",
    ]
    assert "old request" in prepared_input.named_parts["session_summary"].content
    assert prepared_input.preparation.session_messages_included == 4


def test_prepare_model_input_local_compaction_builds_rolling_summary() -> None:
    """Explicit rolling-summary compaction uses structured local preparation."""

    adapter = make_adapter([])
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "rolling-summary-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "strategy": "rolling_summary",
                            "rolling_summary": {
                                "enabled": True,
                                "prior_summary_slot": "rolling_summary",
                                "source_provenance_slot": "source_provenance",
                                "max_retained_turns": 1,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        node_outputs={
            "rolling_summary": "Earlier summary to fold forward.",
            "source_provenance": ["docs/guide.md", "README.md"],
        },
        session_messages=(
            OpenAIMessage(role="user", content="first old request"),
            OpenAIMessage(role="assistant", content="first old answer"),
            OpenAIMessage(role="user", content="second old request"),
            OpenAIMessage(role="assistant", content="second old answer"),
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(adapter,),
    )

    summary = prepared_input.named_parts["session_summary"].content
    assert "## Prior Summary\nEarlier summary to fold forward." in summary
    assert "## Retained Turns\n- user: second old request" in summary
    assert "- assistant: second old answer" in summary
    assert "first old request" not in summary
    assert "## Source Provenance\n- docs/guide.md\n- README.md" in summary
    assert prepared_input.part_names == (
        "session_summary",
        "session_message_1",
        "session_message_2",
        "user_prompt",
    )
    assert prepared_input.preparation.compaction["strategy"] == "rolling_summary"
    assert prepared_input.preparation.compaction["retained_turn_count"] == 1
    assert prepared_input.preparation.compaction["information_retention_proxy"] > 0
    assert adapter.client.responses.calls == []


def test_prepare_model_input_model_summary_uses_injected_summarizer() -> None:
    """Model-backed summaries use an explicit collaborator, not the main adapter."""

    adapter = make_adapter([])
    calls: list[dict[str, object]] = []

    def summarizer(messages, metadata):
        calls.append({"messages": messages, "metadata": metadata})
        return "Model-backed summary of older context."

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "model-summary-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "strategy": "model_summary",
                            "summary_role": "developer",
                            "model_summary": {
                                "enabled": True,
                                "max_summary_chars": 120,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="older request"),
            OpenAIMessage(role="assistant", content="older answer"),
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(adapter,),
        context_summarizer=summarizer,
    )

    assert prepared_input.named_parts["session_summary"].content == (
        "Model-backed summary of older context."
    )
    assert prepared_input.preparation.compaction["strategy"] == "model_summary"
    assert prepared_input.preparation.compaction["summary_chars"] == 38
    assert prepared_input.preparation.compaction["messages_before"] == 2
    assert calls[0]["messages"] == (
        OpenAIMessage(role="user", content="older request"),
        OpenAIMessage(role="assistant", content="older answer"),
    )
    assert calls[0]["metadata"]["strategy"] == "model_summary"
    assert adapter.client.responses.calls == []


def test_prepare_model_input_model_summary_fails_closed_without_summarizer() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "missing-model-summary-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 1},
                        "context_compaction": {
                            "strategy": "model_summary",
                            "model_summary": {"enabled": True},
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="old request"),
            OpenAIMessage(role="assistant", content="old answer"),
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    with pytest.raises(WorkflowExecutionError, match="requires context_summarizer"):
        prepare_model_input(plan.nodes_by_id["answer"], plan, state)


def test_prepare_model_input_local_compaction_skips_summary_without_eviction() -> None:
    """Rolling-summary compaction is a no-op when no history is evicted."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "rolling-summary-noop-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 4},
                        "context_compaction": {
                            "strategy": "rolling_summary",
                            "rolling_summary": {"enabled": True},
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert "session_summary" not in prepared_input.named_parts
    assert prepared_input.preparation.compaction == {}


def test_prepare_model_input_pre_turn_compaction_replaces_over_threshold_context() -> (
    None
):
    """Injected pre-turn compaction can replace over-threshold prepared input."""

    calls: list[tuple[OpenAIMessage, ...]] = []

    def fake_compactor(
        messages: tuple[OpenAIMessage, ...],
        metadata: Mapping[str, Any],
    ) -> tuple[OpenAIMessage, ...]:
        calls.append(messages)
        assert metadata["phase"] == "pre_turn"
        return (
            OpenAIMessage(role="developer", content="Compacted replacement history."),
            OpenAIMessage(role="user", content="Answer finish."),
        )

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "pre-turn-compaction-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "context_compaction": {
                            "auto": {
                                "enabled": True,
                                "threshold_ratio": 0.01,
                                "implementation": "injected",
                                "trigger": "token_threshold",
                            }
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="finish " * 80)
    adapter = make_adapter([])
    adapter.context_windows = {"gpt-test": 1000}
    tracer = WorkflowTracer(events=state.trace_events, run_id="test-run")

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(adapter,),
        tracer=tracer,
        context_compactor=fake_compactor,
    )

    assert len(calls) == 1
    assert prepared_input.part_names == (
        "pre_turn_compacted_1",
        "pre_turn_compacted_2",
    )
    assert prepared_input.messages[0].content == "Compacted replacement history."
    assert prepared_input.preparation.pre_turn_compaction["status"] == "complete"
    assert (
        prepared_input.preparation.pre_turn_compaction["implementation"] == "injected"
    )
    assert (
        prepared_input.preparation.pre_turn_compaction["tokens_before"]
        > (prepared_input.preparation.pre_turn_compaction["tokens_after"])
    )
    prepared_events = [
        event
        for event in state.trace_events
        if event.event_type == "model_input_prepared"
    ]
    assert prepared_events[0].payload["pre_turn_compaction"]["phase"] == "pre_turn"
    assert "finish finish" not in repr(
        prepared_events[0].payload["pre_turn_compaction"]
    )


def test_prepare_model_input_provider_compaction_replaces_over_threshold_context() -> (
    None
):
    from dynamic_agent_runner import (
        ProviderContextCompactionRequest,
        ProviderContextCompactionResult,
    )

    prompt = "finish " * 80

    class FakeProviderCompactor:
        capabilities = {"responses_compact": True}

        def __init__(self) -> None:
            self.requests: list[ProviderContextCompactionRequest] = []

        def compact(
            self, request: ProviderContextCompactionRequest
        ) -> ProviderContextCompactionResult:
            self.requests.append(request)
            return ProviderContextCompactionResult(
                messages=(
                    OpenAIMessage(role="developer", content="Compacted history."),
                    OpenAIMessage(role="user", content=f"Answer {prompt}"),
                ),
                provider_window_id="window-1",
                token_baseline=3,
            )

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "provider-pre-turn-compaction-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "context_compaction": {
                            "auto": {
                                "enabled": True,
                                "threshold_ratio": 0.01,
                                "implementation": "provider",
                                "strategy": "provider_remote",
                                "remote": {
                                    "provider_capability": "responses_compact",
                                    "fallback": "error",
                                },
                            }
                        }
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt=prompt)
    adapter = make_adapter([])
    adapter.context_windows = {"gpt-test": 1000}
    compactor = FakeProviderCompactor()
    tracer = WorkflowTracer(events=state.trace_events)

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(adapter,),
        provider_context_compactor=compactor,
        tracer=tracer,
    )

    assert compactor.requests[0].phase == "pre_turn"
    assert prepared_input.messages[0].content == "Compacted history."
    assert prepared_input.preparation.pre_turn_compaction["status"] == "complete"
    assert prepared_input.preparation.pre_turn_compaction["window_id"] != "window-1"
    prepared_event = next(
        event
        for event in state.trace_events
        if event.event_type == "model_input_prepared"
    )
    assert "Compacted history." not in repr(prepared_event.payload)
    assert "window-1" not in repr(prepared_event.payload)


def test_prepare_model_input_new_window_reset_does_not_count_as_compaction() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "new-window-reset-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "reset_behavior": "new_window",
                            "reset_reason": "user_requested",
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="finish",
        session_messages=(
            OpenAIMessage(role="user", content="old request"),
            OpenAIMessage(role="assistant", content="old answer"),
            OpenAIMessage(role="user", content="latest request"),
            OpenAIMessage(role="assistant", content="latest answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert "session_summary" not in prepared_input.named_parts
    assert prepared_input.preparation.context_compaction_applied is False
    assert prepared_input.preparation.context_reset == {
        "reset_behavior": "new_window",
        "reason": "user_requested",
        "session_messages_dropped": 2,
        "compaction_success": False,
    }


def test_execute_workflow_retries_once_after_context_overflow_with_compaction() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "overflow-retry-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "context_compaction": {
                            "auto": {
                                "enabled": True,
                                "implementation": "injected",
                                "retry_on_overflow": True,
                            }
                        },
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
    adapter = make_adapter(
        [
            RuntimeError("context_length_exceeded: too many tokens"),
            {"id": "resp_retry", "output_text": "compacted answer"},
        ]
    )

    def fake_compactor(
        _messages: tuple[OpenAIMessage, ...],
        metadata: Mapping[str, Any],
    ) -> tuple[OpenAIMessage, ...]:
        assert metadata["phase"] == "overflow_retry"
        return (OpenAIMessage(role="user", content="Compacted question."),)

    result = execute_workflow(
        workflow,
        prompt="finish " * 80,
        model_adapter=adapter,
        context_compactor=fake_compactor,
    )

    assert result.final_result == "compacted answer"
    assert len(adapter.client.responses.calls) == 2
    assert adapter.client.responses.calls[1]["input"] == [
        {"role": "user", "content": "Compacted question."}
    ]
    retry_events = [
        event
        for event in result.state.trace_events
        if event.event_type == "context_overflow_retry"
    ]
    assert retry_events[0].payload["status"] == "retrying"


def test_execute_workflow_retries_once_after_context_overflow_with_provider_compaction() -> (
    None
):
    from dynamic_agent_runner import (
        ProviderContextCompactionRequest,
        ProviderContextCompactionResult,
    )

    prompt = "finish " * 80

    class FakeProviderCompactor:
        capabilities = {"responses_compact": True}

        def compact(
            self, request: ProviderContextCompactionRequest
        ) -> ProviderContextCompactionResult:
            assert request.phase == "overflow_retry"
            return ProviderContextCompactionResult(
                messages=(OpenAIMessage(role="user", content=f"Answer {prompt}"),),
                provider_window_id="window-retry",
            )

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "provider-overflow-retry-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "context_compaction": {
                            "auto": {
                                "enabled": True,
                                "implementation": "provider",
                                "strategy": "provider_remote",
                                "retry_on_overflow": True,
                                "remote": {
                                    "provider_capability": "responses_compact",
                                    "fallback": "error",
                                },
                            }
                        }
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
    adapter = make_adapter(
        [
            RuntimeError("context_length_exceeded: too many tokens"),
            {"id": "resp_retry", "output_text": "compacted answer"},
        ]
    )

    result = execute_workflow(
        workflow,
        prompt=prompt,
        model_adapter=adapter,
        provider_context_compactor=FakeProviderCompactor(),
    )

    assert result.final_result == "compacted answer"
    retry_event = next(
        event
        for event in result.state.trace_events
        if event.event_type == "context_overflow_retry"
    )
    assert retry_event.payload["window_id"] != "window-retry"
    assert retry_event.payload["tokens_after"] > 0
    assert "window-retry" not in repr(retry_event.payload)
    assert prompt not in repr(retry_event.payload)


@pytest.mark.parametrize(
    ("capability", "fallback", "expected_status"),
    [
        (None, "basic", "fallback"),
        (False, "basic", "fallback"),
        (None, "error", None),
        (False, "error", None),
    ],
)
def test_prepare_model_input_provider_compaction_handles_missing_collaborator_or_capability(
    capability: bool | None,
    fallback: str,
    expected_status: str | None,
) -> None:
    workflow = provider_compaction_workflow(fallback=fallback)
    plan = prepare_execution_plan(workflow)
    adapter = make_adapter([])
    adapter.context_windows = {"gpt-test": 1000}
    state = WorkflowExecutionState(prompt="active prompt " * 80)

    class Compactor:
        capabilities = {"responses_compact": capability}

    kwargs = {} if capability is None else {"provider_context_compactor": Compactor()}
    if expected_status is None:
        with pytest.raises(WorkflowExecutionError, match="provider context compaction"):
            prepare_model_input(
                plan.nodes_by_id["answer"],
                plan,
                state,
                model_adapters=(adapter,),
                **kwargs,
            )
        return

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(adapter,),
        **kwargs,
    )

    assert prepared_input.preparation.pre_turn_compaction["status"] == expected_status
    assert prepared_input.messages[-1].content == "Answer " + "active prompt " * 80


@pytest.mark.parametrize(
    "replacement",
    [
        (OpenAIMessage(role="tool", content="unpaired tool history"),),
        (
            OpenAIMessage(role="developer", content="Pinned instruction."),
            OpenAIMessage(role="user", content="rewritten active prompt"),
        ),
        [OpenAIMessage(role="user", content="not a tuple")],
    ],
)
def test_prepare_model_input_provider_compaction_falls_back_for_invalid_replacement(
    replacement: object,
) -> None:
    from dynamic_agent_runner import ProviderContextCompactionResult

    class Compactor:
        capabilities = {"responses_compact": True}

        def compact(self, _request: object) -> ProviderContextCompactionResult:
            return ProviderContextCompactionResult(messages=replacement)  # type: ignore[arg-type]

    workflow = provider_compaction_workflow(
        fallback="basic",
        prompt_hierarchy={"developer": ["Pinned instruction."]},
    )
    plan = prepare_execution_plan(workflow)
    adapter = make_adapter([])
    adapter.context_windows = {"gpt-test": 1000}
    state = WorkflowExecutionState(prompt="active prompt " * 80)

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(adapter,),
        provider_context_compactor=Compactor(),
    )

    assert prepared_input.preparation.pre_turn_compaction["status"] == "fallback"
    assert prepared_input.messages[-1].content == "Answer " + "active prompt " * 80


def test_prepare_model_input_provider_compaction_redacts_invalid_token_baseline() -> (
    None
):
    from dynamic_agent_runner import ProviderContextCompactionResult

    prompt = "active prompt " * 80

    class Compactor:
        capabilities = {"responses_compact": True}

        def compact(self, _request: object) -> ProviderContextCompactionResult:
            return ProviderContextCompactionResult(
                messages=(OpenAIMessage(role="user", content=f"Answer {prompt}"),),
                token_baseline="raw-provider-baseline",  # type: ignore[arg-type]
            )

    workflow = provider_compaction_workflow(fallback="basic")
    plan = prepare_execution_plan(workflow)
    adapter = make_adapter([])
    adapter.context_windows = {"gpt-test": 1000}
    state = WorkflowExecutionState(prompt=prompt)
    tracer = WorkflowTracer(events=state.trace_events)

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(adapter,),
        provider_context_compactor=Compactor(),
        tracer=tracer,
    )

    assert prepared_input.preparation.pre_turn_compaction["status"] == "fallback"
    prepared_event = next(
        event
        for event in state.trace_events
        if event.event_type == "model_input_prepared"
    )
    assert "raw-provider-baseline" not in repr(prepared_event.payload)


@pytest.mark.parametrize(
    ("capability", "fallback", "should_retry"),
    [
        (None, "basic", True),
        (False, "basic", True),
        (None, "error", False),
        (False, "error", False),
    ],
)
def test_execute_workflow_handles_unavailable_provider_overflow_compaction(
    capability: bool | None,
    fallback: str,
    should_retry: bool,
) -> None:
    class Compactor:
        capabilities = {"responses_compact": capability}

    workflow = provider_compaction_workflow(fallback=fallback, retry_on_overflow=True)
    adapter = make_adapter(
        [
            RuntimeError("context_length_exceeded: too many tokens"),
            {"id": "resp_retry", "output_text": "fallback answer"},
        ]
    )

    kwargs = {} if capability is None else {"provider_context_compactor": Compactor()}
    if not should_retry:
        with pytest.raises(WorkflowExecutionError, match="provider context compaction"):
            execute_workflow(
                workflow,
                prompt="active prompt " * 80,
                model_adapter=adapter,
                **kwargs,
            )
        assert len(adapter.client.responses.calls) == 1
        return

    result = execute_workflow(
        workflow,
        prompt="active prompt " * 80,
        model_adapter=adapter,
        **kwargs,
    )

    assert result.final_result == "fallback answer"
    assert len(adapter.client.responses.calls) == 2
    retry_event = next(
        event
        for event in result.state.trace_events
        if event.event_type == "context_overflow_retry"
    )
    assert retry_event.payload["fallback"] == "basic"


def test_execute_workflow_rejects_provider_overflow_replacement_that_changes_active_turn() -> (
    None
):
    from dynamic_agent_runner import ProviderContextCompactionResult

    class Compactor:
        capabilities = {"responses_compact": True}

        def compact(self, _request: object) -> ProviderContextCompactionResult:
            return ProviderContextCompactionResult(
                messages=(
                    OpenAIMessage(role="user", content="rewritten active prompt"),
                )
            )

    workflow = provider_compaction_workflow(fallback="error", retry_on_overflow=True)
    adapter = make_adapter(
        [
            RuntimeError("context_length_exceeded: too many tokens"),
            {"id": "resp_retry", "output_text": "must not be used"},
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="provider context compaction"):
        execute_workflow(
            workflow,
            prompt="active prompt " * 80,
            model_adapter=adapter,
            provider_context_compactor=Compactor(),
        )

    assert len(adapter.client.responses.calls) == 1


def test_prepare_model_input_reports_context_lanes() -> None:
    """prepare_model_input reports ordered context lanes and utilization metadata."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "context-lanes-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "prompt_hierarchy": {
                            "system": ["Pinned system"],
                            "developer": ["Pinned developer"],
                        },
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {
                            "strategy": "summary_message",
                            "summary_prefix": "Earlier:",
                            "auto": {"enabled": True},
                        },
                        "context_compression": {
                            "profile": "balanced",
                            "lanes": {
                                "pinned_tokens": 200,
                                "current_turn_tokens": 400,
                                "recent_turn_tokens": 400,
                                "summary_tokens": 100,
                            },
                        },
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "system": "Base system",
                        "user_template": "Answer {prompt}",
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="now",
        session_messages=(
            OpenAIMessage(role="user", content="old"),
            OpenAIMessage(role="assistant", content="old answer"),
            OpenAIMessage(role="user", content="recent"),
            OpenAIMessage(role="assistant", content="recent answer"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert [lane["lane_id"] for lane in prepared_input.preparation.context_lanes] == [
        "pinned",
        "rolling_summary",
        "recent_turns",
        "current_turn",
    ]
    assert prepared_input.preparation.context_lanes[0]["part_count"] == 3
    assert prepared_input.preparation.context_lanes[0]["budget_tokens"] == 200
    assert prepared_input.preparation.context_lanes[1]["part_count"] == 1
    assert prepared_input.preparation.context_lanes[2]["part_count"] == 2
    assert prepared_input.preparation.context_lanes[3]["part_count"] == 1
    assert prepared_input.preparation.context_lanes[3]["budget_tokens"] == 400


def test_prepare_model_input_enforces_recent_turn_lane_budget() -> None:
    """Recent-turn lane budget trimming does not borrow from current-turn budget."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "lane-budget-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 4},
                        "context_compaction": {
                            "auto": {"enabled": True},
                        },
                        "context_compression": {
                            "profile": "fast",
                            "lanes": {
                                "recent_turn_tokens": 1,
                                "current_turn_tokens": 1000,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="protected current prompt",
        session_messages=(
            OpenAIMessage(role="user", content="recent user with many tokens"),
            OpenAIMessage(
                role="assistant", content="recent assistant with many tokens"
            ),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)
    lane_map = {
        lane["lane_id"]: lane for lane in prepared_input.preparation.context_lanes
    }

    assert "session_message_1" not in prepared_input.named_parts
    assert "session_message_2" not in prepared_input.named_parts
    assert prepared_input.named_parts["user_prompt"].content == (
        "Answer protected current prompt"
    )
    assert lane_map["recent_turns"]["trimmed_count"] == 2
    assert lane_map["recent_turns"]["omitted_count"] == 2
    assert lane_map["current_turn"]["part_count"] == 1


def test_prepare_model_input_older_turn_selection_selects_relevant_turns() -> None:
    """Deterministic older-turn selection reports scores and reasons."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "older-turn-selection-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {"auto": {"enabled": True}},
                        "context_compression": {
                            "profile": "balanced",
                            "lanes": {"selected_turn_tokens": 1000},
                            "selection": {
                                "strategy": "deterministic_overlap",
                                "max_selected_turns": 1,
                                "chronological_reassembly": True,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Explain the billing error in src/billing.py",
        session_messages=(
            OpenAIMessage(role="user", content="Discuss src/auth.py login"),
            OpenAIMessage(role="assistant", content="Auth summary"),
            OpenAIMessage(role="user", content="Investigate src/billing.py error"),
            OpenAIMessage(role="assistant", content="Billing stack trace"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert "selected_turn_1" in prepared_input.named_parts
    assert (
        "src/billing.py error" in prepared_input.named_parts["selected_turn_1"].content
    )
    assert prepared_input.preparation.selected_turns == (
        {
            "turn_id": "turn_2",
            "selection_status": "selected",
            "selection_reason": "deterministic_overlap",
            "relevance_score": 2,
        },
    )
    lane_map = {
        lane["lane_id"]: lane for lane in prepared_input.preparation.context_lanes
    }
    assert lane_map["selected_older_turns"]["part_count"] == 1


def test_prepare_model_input_exact_profile_preserves_identifier_matches() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "exact-profile-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compaction": {"auto": {"enabled": True}},
                        "context_compression": {
                            "profile": "exact",
                            "selection": {
                                "strategy": "hybrid_exact_semantic",
                                "max_selected_turns": 1,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Resolve BUG-1234 without losing the exact issue key",
        session_messages=(
            OpenAIMessage(role="user", content="BUG-1234 failed in auth_v2.py"),
            OpenAIMessage(role="assistant", content="Issue-key evidence"),
            OpenAIMessage(role="user", content="Unrelated billing issue"),
            OpenAIMessage(role="assistant", content="Other evidence"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert "BUG-1234 failed" in prepared_input.named_parts["selected_turn_1"].content
    assert prepared_input.preparation.selection_policy == {
        "profile": "exact",
        "strategy": "hybrid_exact_semantic",
        "max_selected_turns": 1,
    }
    assert prepared_input.preparation.selected_turns == (
        {
            "turn_id": "turn_1",
            "selection_status": "selected",
            "selection_reason": "hybrid_exact_semantic",
            "relevance_score": 1,
        },
    )


def test_prepare_model_input_injected_semantic_selector_selects_low_overlap_turn() -> (
    None
):
    seen_query: list[str] = []
    seen_candidates: list[tuple[ContextSelectionCandidate, ...]] = []
    seen_metadata: list[Mapping[str, object]] = []

    def selector(
        query: str,
        candidates: tuple[ContextSelectionCandidate, ...],
        metadata: Mapping[str, object],
    ) -> tuple[ContextSelection, ...]:
        seen_query.append(query)
        seen_candidates.append(candidates)
        seen_metadata.append(metadata)
        return (ContextSelection(turn_id="turn_1", score=0.91, reason="domain_hint"),)

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "semantic-selector-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compression": {
                            "profile": "semantic",
                            "selection": {
                                "strategy": "injected_semantic",
                                "max_selected_turns": 1,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="How should we recover the tenant audit ledger?",
        session_messages=(
            OpenAIMessage(role="user", content="The WAL shard is corrupt"),
            OpenAIMessage(role="assistant", content="Restore from replica delta"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        context_selector=selector,
    )

    assert seen_query == ["How should we recover the tenant audit ledger?"]
    assert len(seen_candidates) == 1
    assert len(seen_candidates[0]) == 1
    candidate = seen_candidates[0][0]
    assert candidate.turn_id == "turn_1"
    assert candidate.text == "The WAL shard is corrupt\nRestore from replica delta"
    assert candidate.roles == ("user", "assistant")
    assert candidate.exact_match_count == 0
    assert candidate.token_estimate > 0
    assert seen_metadata[0]["profile"] == "semantic"
    assert prepared_input.named_parts["selected_turn_1"].content.startswith(
        "Selected older turn turn_1:"
    )
    assert prepared_input.preparation.selection_policy == {
        "profile": "semantic",
        "strategy": "injected_semantic",
        "max_selected_turns": 1,
        "selector_status": "available",
    }
    assert prepared_input.preparation.selected_turns == (
        {
            "turn_id": "turn_1",
            "selection_status": "selected",
            "selection_reason": "domain_hint",
            "relevance_score": 0.91,
            "selector": "injected_semantic",
        },
    )


def test_prepare_model_input_injected_semantic_missing_selector_falls_back() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "missing-semantic-selector-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compression": {
                            "profile": "semantic",
                            "selection": {
                                "strategy": "injected_semantic",
                                "max_selected_turns": 1,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Explain billing retry behavior",
        session_messages=(
            OpenAIMessage(role="user", content="Billing retries fail"),
            OpenAIMessage(role="assistant", content="Retry evidence"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert (
        "Billing retries fail" in prepared_input.named_parts["selected_turn_1"].content
    )
    assert prepared_input.preparation.selection_policy == {
        "profile": "semantic",
        "strategy": "injected_semantic",
        "max_selected_turns": 1,
        "selector_status": "missing",
        "fallback_strategy": "deterministic_overlap",
    }
    assert prepared_input.preparation.selected_turns == (
        {
            "turn_id": "turn_1",
            "selection_status": "selected",
            "selection_reason": "deterministic_overlap",
            "relevance_score": 2,
        },
    )


def test_prepare_model_input_injected_semantic_protects_exact_identifier_matches() -> (
    None
):
    def selector(
        _query: str,
        _candidates: tuple[ContextSelectionCandidate, ...],
        _metadata: Mapping[str, object],
    ) -> tuple[ContextSelection, ...]:
        return (ContextSelection(turn_id="turn_2", score=0.99, reason="semantic"),)

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "semantic-exact-protection-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compression": {
                            "profile": "semantic",
                            "selection": {
                                "strategy": "injected_semantic",
                                "max_selected_turns": 1,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Resolve BUG-7777",
        session_messages=(
            OpenAIMessage(role="user", content="BUG-7777 blocks release"),
            OpenAIMessage(role="assistant", content="Exact issue evidence"),
            OpenAIMessage(role="user", content="Architecture cleanup notes"),
            OpenAIMessage(role="assistant", content="Broad semantic background"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        context_selector=selector,
    )

    assert (
        "BUG-7777 blocks release"
        in prepared_input.named_parts["selected_turn_1"].content
    )
    assert prepared_input.preparation.selected_turns == (
        {
            "turn_id": "turn_1",
            "selection_status": "selected",
            "selection_reason": "exact_identifier_match",
            "relevance_score": 1,
            "selector": "injected_semantic",
        },
    )
    assert prepared_input.preparation.omitted_turns == (
        {
            "turn_id": "turn_2",
            "selection_status": "omitted",
            "selection_reason": "max_selected_turns_exceeded",
            "relevance_score": 0.99,
            "selector": "injected_semantic",
        },
    )


def test_prepare_model_input_injected_semantic_excludes_retrieved_context_candidates() -> (
    None
):
    seen_candidates: list[tuple[ContextSelectionCandidate, ...]] = []

    def selector(
        _query: str,
        candidates: tuple[ContextSelectionCandidate, ...],
        _metadata: Mapping[str, object],
    ) -> tuple[ContextSelection, ...]:
        seen_candidates.append(candidates)
        return (ContextSelection(turn_id="turn_1", score=0.75),)

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "semantic-rag-boundary-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "retrieved_context": {"enabled": True},
                        "context_compression": {
                            "profile": "semantic",
                            "selection": {
                                "strategy": "injected_semantic",
                                "max_selected_turns": 1,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Explain retained memory",
        node_outputs={
            "retrieved_context": [
                {
                    "source_id": "rag-source",
                    "chunk_id": "rag-chunk",
                    "content": "RAG-only evidence must not be scored as a turn.",
                }
            ]
        },
        session_messages=(
            OpenAIMessage(role="user", content="Older session turn"),
            OpenAIMessage(role="assistant", content="Older response"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        context_selector=selector,
    )

    assert tuple(candidate.turn_id for candidate in seen_candidates[0]) == ("turn_1",)
    assert "RAG-only evidence" not in seen_candidates[0][0].text
    assert "retrieved_context_1" in prepared_input.named_parts
    assert (
        "RAG-only evidence" in prepared_input.named_parts["retrieved_context_1"].content
    )


def test_prepare_model_input_injected_semantic_rejects_invalid_selector_results() -> (
    None
):
    def selector(
        _query: str,
        _candidates: tuple[ContextSelectionCandidate, ...],
        _metadata: Mapping[str, object],
    ) -> tuple[object, ...]:
        return (
            object(),
            ContextSelection(turn_id="turn_99", score=0.42, reason="unknown"),
            ContextSelection(turn_id="turn_2", score="bad"),
            ContextSelection(turn_id="turn_1", score=0.6, reason="valid"),
        )

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "invalid-semantic-selector-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compression": {
                            "profile": "semantic",
                            "selection": {
                                "strategy": "injected_semantic",
                                "max_selected_turns": 1,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Choose the right recovery note",
        session_messages=(
            OpenAIMessage(role="user", content="First candidate fact"),
            OpenAIMessage(role="assistant", content="First candidate answer"),
            OpenAIMessage(role="user", content="Second candidate fact"),
            OpenAIMessage(role="assistant", content="Second candidate answer"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        context_selector=selector,
    )

    assert (
        "First candidate fact" in prepared_input.named_parts["selected_turn_1"].content
    )
    assert prepared_input.preparation.selected_turns == (
        {
            "turn_id": "turn_1",
            "selection_status": "selected",
            "selection_reason": "valid",
            "relevance_score": 0.6,
            "selector": "injected_semantic",
        },
    )
    assert prepared_input.preparation.rejected_turns == (
        {
            "selection_status": "rejected",
            "selection_reason": "invalid_selector_result",
            "selector": "injected_semantic",
        },
        {
            "turn_id": "turn_99",
            "selection_status": "rejected",
            "selection_reason": "unknown_selector_turn",
            "relevance_score": 0.42,
            "selector": "injected_semantic",
        },
        {
            "turn_id": "turn_2",
            "selection_status": "rejected",
            "selection_reason": "invalid_selector_score",
            "selector": "injected_semantic",
        },
        {
            "turn_id": "turn_2",
            "selection_status": "rejected",
            "selection_reason": "no_injected_semantic_score",
            "relevance_score": 0,
            "selector": "injected_semantic",
        },
    )


def test_prepare_model_input_injected_semantic_selector_error_records_rejection() -> (
    None
):
    def selector(
        _query: str,
        _candidates: tuple[ContextSelectionCandidate, ...],
        _metadata: Mapping[str, object],
    ) -> tuple[ContextSelection, ...]:
        raise RuntimeError("secret selector text should not leak")

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "semantic-selector-error-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compression": {
                            "profile": "semantic",
                            "selection": {
                                "strategy": "injected_semantic",
                                "max_selected_turns": 1,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="question",
        session_messages=(
            OpenAIMessage(role="user", content="Older candidate fact"),
            OpenAIMessage(role="assistant", content="Older candidate answer"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        context_selector=selector,
    )

    assert "selected_turn_1" not in prepared_input.named_parts
    assert prepared_input.preparation.selected_turns == ()
    assert prepared_input.preparation.rejected_turns == (
        {
            "selection_status": "rejected",
            "selection_reason": "selector_error",
            "error_type": "RuntimeError",
            "selector": "injected_semantic",
        },
        {
            "turn_id": "turn_1",
            "selection_status": "rejected",
            "selection_reason": "no_injected_semantic_score",
            "relevance_score": 0,
            "selector": "injected_semantic",
        },
    )
    assert "secret selector text should not leak" not in repr(
        prepared_input.preparation.rejected_turns
    )


def test_prepare_model_input_injected_semantic_trace_metadata_is_bounded() -> None:
    def selector(
        _query: str,
        _candidates: tuple[ContextSelectionCandidate, ...],
        _metadata: Mapping[str, object],
    ) -> tuple[ContextSelection, ...]:
        return (ContextSelection(turn_id="turn_1", score=0.7, reason="semantic"),)

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "semantic-selector-trace-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compression": {
                            "profile": "semantic",
                            "selection": {
                                "strategy": "injected_semantic",
                                "max_selected_turns": 1,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="question",
        session_messages=(
            OpenAIMessage(role="user", content="SENSITIVE-SELECTOR-CANDIDATE"),
            OpenAIMessage(role="assistant", content="Selected answer"),
            OpenAIMessage(role="user", content="Unscored older turn"),
            OpenAIMessage(role="assistant", content="Unscored answer"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )
    tracer = WorkflowTracer(events=state.trace_events, run_id="test-run")

    prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        tracer=tracer,
        context_selector=selector,
    )

    [prepared_event] = [
        event
        for event in state.trace_events
        if event.event_type == "model_input_prepared"
    ]
    payload = prepared_event.payload

    assert payload["selection_policy"] == {
        "profile": "semantic",
        "strategy": "injected_semantic",
        "max_selected_turns": 1,
        "selector_status": "available",
    }
    assert payload["selected_turns"] == (
        {
            "turn_id": "turn_1",
            "selection_status": "selected",
            "selection_reason": "semantic",
            "relevance_score": 0.7,
            "selector": "injected_semantic",
        },
    )
    assert payload["rejected_turns"] == (
        {
            "turn_id": "turn_2",
            "selection_status": "rejected",
            "selection_reason": "no_injected_semantic_score",
            "relevance_score": 0,
            "selector": "injected_semantic",
        },
    )
    assert "SENSITIVE-SELECTOR-CANDIDATE" not in repr(payload)


def test_execute_workflow_accepts_direct_context_selector_kwarg() -> None:
    def selector(
        _query: str,
        _candidates: tuple[ContextSelectionCandidate, ...],
        _metadata: Mapping[str, object],
    ) -> tuple[ContextSelection, ...]:
        return (ContextSelection(turn_id="turn_1", score=0.8),)

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "direct-context-selector-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compression": {
                            "profile": "semantic",
                            "selection": {
                                "strategy": "injected_semantic",
                                "max_selected_turns": 1,
                            },
                        },
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
    adapter = make_named_adapter(
        [{"id": "resp", "output_text": "ok"}], models=["gpt-test"]
    )

    result = execute_workflow(
        workflow,
        prompt="question",
        model_adapter=adapter,
        context_selector=selector,
        session_messages=(
            OpenAIMessage(role="user", content="Older selected session fact"),
            OpenAIMessage(role="assistant", content="Older selected answer"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )

    assert result.final_result == "ok"
    request_messages = adapter.client.responses.calls[0]["input"]
    assert any(
        "Older selected session fact" in message["content"]
        for message in request_messages
    )


def test_execute_workflow_accepts_context_selector_on_execution_context() -> None:
    def selector(
        _query: str,
        _candidates: tuple[ContextSelectionCandidate, ...],
        _metadata: Mapping[str, object],
    ) -> tuple[ContextSelection, ...]:
        return (ContextSelection(turn_id="turn_1", score=0.8),)

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "execution-context-selector-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 2},
                        "context_compression": {
                            "profile": "semantic",
                            "selection": {
                                "strategy": "injected_semantic",
                                "max_selected_turns": 1,
                            },
                        },
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
    adapter = make_named_adapter(
        [{"id": "resp", "output_text": "ok"}], models=["gpt-test"]
    )
    context = WorkflowExecutionContext(
        workflow=workflow,
        model_adapter=adapter,
        context_selector=selector,
    )

    result = execute_workflow(
        context,
        prompt="question",
        session_messages=(
            OpenAIMessage(role="user", content="Older context-selected fact"),
            OpenAIMessage(role="assistant", content="Older context-selected answer"),
            OpenAIMessage(role="user", content="Recent unrelated"),
            OpenAIMessage(role="assistant", content="Recent reply"),
        ),
    )

    assert result.final_result == "ok"
    request_messages = adapter.client.responses.calls[0]["input"]
    assert any(
        "Older context-selected fact" in message["content"]
        for message in request_messages
    )


def test_prepare_model_input_chronological_reassembly_orders_selected_turns() -> None:
    """Selected older turns render in original order even when scores differ."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "chronological-selection-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "session_pruning": {"max_messages": 0},
                        "context_compaction": {"auto": {"enabled": True}},
                        "context_compression": {
                            "profile": "balanced",
                            "selection": {
                                "strategy": "deterministic_overlap",
                                "max_selected_turns": 2,
                                "chronological_reassembly": True,
                            },
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="alpha beta beta",
        session_messages=(
            OpenAIMessage(role="user", content="alpha"),
            OpenAIMessage(role="assistant", content="first"),
            OpenAIMessage(role="user", content="beta beta"),
            OpenAIMessage(role="assistant", content="second"),
        ),
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    selected_names = [
        name for name in prepared_input.part_names if name.startswith("selected_turn_")
    ]
    assert selected_names == ["selected_turn_1", "selected_turn_2"]
    assert "alpha" in prepared_input.named_parts["selected_turn_1"].content
    assert "beta beta" in prepared_input.named_parts["selected_turn_2"].content


def test_prepare_model_input_retrieved_context_lane_packs_evidence() -> None:
    """Caller-provided retrieved evidence is packed into a bounded context lane."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "retrieved-context-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "retrieved_context": {
                            "enabled": True,
                            "source_slot": "retrieved_context",
                            "header": "Retrieved evidence:",
                        },
                        "context_compression": {
                            "lanes": {"retrieved_context_tokens": 8}
                        },
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Explain billing retries",
        node_outputs={
            "retrieved_context": [
                {
                    "source_id": "kb-billing",
                    "chunk_id": "chunk-required",
                    "citation_handle": "[1]",
                    "content": "Required billing retry rules.",
                    "required": True,
                    "token_estimate": 20,
                    "score": 0.98,
                    "freshness": {"as_of": "2026-06-16"},
                    "packing_hint": {"order": 1},
                },
                {
                    "source_id": "kb-billing",
                    "chunk_id": "chunk-optional",
                    "citation_handle": "[2]",
                    "content": "Optional retry example.",
                    "lane_hint": "optional",
                    "token_estimate": 4,
                    "score": 0.77,
                    "freshness": {"as_of": "2026-06-15"},
                    "packing_hint": {"order": 2},
                },
                {
                    "source_id": "kb-billing",
                    "chunk_id": "chunk-omitted",
                    "citation_handle": "[3]",
                    "content": "Sensitive omitted evidence body.",
                    "lane_hint": "optional",
                    "token_estimate": 6,
                    "score": 0.52,
                    "freshness": {"as_of": "2026-06-14"},
                    "packing_hint": {"order": 3},
                },
            ]
        },
    )

    prepared_input = prepare_model_input(plan.nodes_by_id["answer"], plan, state)

    assert "retrieved_context_1" in prepared_input.named_parts
    assert "retrieved_context_2" in prepared_input.named_parts
    assert "retrieved_context_3" not in prepared_input.named_parts
    assert (
        "Required billing retry rules."
        in prepared_input.named_parts["retrieved_context_1"].content
    )
    assert prepared_input.preparation.retrieved_context == (
        {
            "source_id": "kb-billing",
            "chunk_id": "chunk-required",
            "citation_handle": "[1]",
            "required": True,
            "token_estimate": 20,
            "score": 0.98,
            "freshness": {"as_of": "2026-06-16"},
            "packing_hint": {"order": 1},
            "selection_status": "included",
        },
        {
            "source_id": "kb-billing",
            "chunk_id": "chunk-optional",
            "citation_handle": "[2]",
            "required": False,
            "token_estimate": 4,
            "score": 0.77,
            "freshness": {"as_of": "2026-06-15"},
            "packing_hint": {"order": 2},
            "selection_status": "included",
        },
    )
    assert prepared_input.preparation.retrieved_context_omitted == (
        {
            "source_id": "kb-billing",
            "chunk_id": "chunk-omitted",
            "citation_handle": "[3]",
            "required": False,
            "token_estimate": 6,
            "score": 0.52,
            "freshness": {"as_of": "2026-06-14"},
            "packing_hint": {"order": 3},
            "selection_status": "omitted",
            "selection_reason": "retrieved_context_lane_budget_exceeded",
        },
    )
    lane_map = {
        lane["lane_id"]: lane for lane in prepared_input.preparation.context_lanes
    }
    assert lane_map["retrieved_context"]["part_count"] == 2
    assert lane_map["retrieved_context"]["budget_tokens"] == 8
    assert lane_map["retrieved_context"]["omitted_count"] == 1


def test_prepare_model_input_retrieved_context_lane_redacts_trace_content() -> None:
    """Retrieved-context trace metadata must not expose raw evidence content."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "retrieved-context-trace-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "prepare_model_input": {
                        "retrieved_context": {"enabled": True},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(
        prompt="Explain billing retries",
        node_outputs={
            "retrieved_context": [
                {
                    "source_id": "kb-billing",
                    "chunk_id": "chunk-sensitive",
                    "citation_handle": "[1]",
                    "content": "Do not leak this retrieved body in traces.",
                    "token_estimate": 5,
                }
            ]
        },
    )
    tracer = WorkflowTracer(events=state.trace_events, run_id="test-run")

    prepare_model_input(plan.nodes_by_id["answer"], plan, state, tracer=tracer)

    prepared_events = [
        event
        for event in state.trace_events
        if event.event_type == "model_input_prepared"
    ]
    assert len(prepared_events) == 1
    trace_payload = prepared_events[0].payload
    assert trace_payload["retrieved_context"] == (
        {
            "source_id": "kb-billing",
            "chunk_id": "chunk-sensitive",
            "citation_handle": "[1]",
            "required": False,
            "token_estimate": 5,
            "selection_status": "included",
        },
    )
    assert "Do not leak this retrieved body" not in repr(trace_payload)


def test_prepare_model_input_includes_bounded_file_context_with_provenance(
    tmp_path,
) -> None:
    """File-backed prompt context is opt-in, bounded, and source-tracked."""

    package_dir = tmp_path / "file-context-package"
    package_dir.mkdir()
    (package_dir / "README.md").write_text("Package overview\n", encoding="utf-8")
    docs_dir = package_dir / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("Guide details\n", encoding="utf-8")
    nested_dir = docs_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "ignored.md").write_text("Ignored nested file\n", encoding="utf-8")

    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "file-context-agent",
                "entrypoint": "answer",
                "packaging": {"mode": "hybrid_bundle"},
                "runtime": {
                    "execution_policy": {
                        "model": "gpt-test",
                        "prepare_model_input": {
                            "file_context": {
                                "enabled": True,
                                "roots": ["docs", "README.md"],
                                "max_depth": 1,
                                "max_files": 2,
                                "max_bytes": 4096,
                                "max_tokens": 400,
                                "prompt_role": "developer",
                                "header": "Project context:",
                            }
                        },
                    }
                },
                "nodes": [
                    {
                        "id": "answer",
                        "kind": "llm_step",
                        "prompt": {"user_template": "Answer {prompt}."},
                    }
                ],
                "edges": [],
            }
        ),
        package_root=str(package_dir),
    )
    plan = prepare_execution_plan(workflow)

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        WorkflowExecutionState(prompt="question"),
    )

    assert prepared_input.part_names == (
        "file_context_1",
        "file_context_2",
        "user_prompt",
    )
    assert prepared_input.preparation.file_context_applied is True
    assert prepared_input.preparation.file_context_sources == (
        "README.md",
        "docs/guide.md",
    )
    assert prepared_input.preparation.file_context_files_included == 2
    assert prepared_input.preparation.file_context_bytes > 0
    assert prepared_input.preparation.file_context_estimated_tokens > 0
    assert "Source: README.md" in prepared_input.named_parts["file_context_1"].content
    assert (
        "Source: docs/guide.md" in prepared_input.named_parts["file_context_2"].content
    )
    assert "ignored.md" not in prepared_input.named_parts["file_context_2"].content


def test_prepare_model_input_rejects_file_context_roots_outside_package(
    tmp_path,
) -> None:
    """File-backed prompt context rejects roots that escape the package root."""

    package_dir = tmp_path / "file-context-package"
    package_dir.mkdir()

    workflow = LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "file-context-agent",
                "entrypoint": "answer",
                "packaging": {"mode": "hybrid_bundle"},
                "runtime": {
                    "execution_policy": {
                        "model": "gpt-test",
                        "prepare_model_input": {
                            "file_context": {
                                "enabled": True,
                                "roots": ["../outside"],
                                "max_depth": 1,
                                "max_files": 1,
                                "max_bytes": 512,
                            }
                        },
                    }
                },
                "nodes": [
                    {
                        "id": "answer",
                        "kind": "llm_step",
                        "prompt": {"user_template": "Answer {prompt}."},
                    }
                ],
                "edges": [],
            }
        ),
        package_root=str(package_dir),
    )
    plan = prepare_execution_plan(workflow)

    with pytest.raises(WorkflowExecutionError) as exc_info:
        prepare_model_input(
            plan.nodes_by_id["answer"],
            plan,
            WorkflowExecutionState(prompt="question"),
        )

    assert "escapes package root" in str(exc_info.value)


def test_execute_workflow_async_runs_async_model_adapter() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "async-model-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
    adapter = make_async_adapter([{"id": "resp", "output_text": "async done"}])

    result = asyncio.run(
        execute_workflow_async(workflow, prompt="Hello", model_adapter=adapter)
    )

    assert result.final_result == "async done"
    assert adapter.client.responses.calls[0]["model"] == "gpt-test"


def test_execute_workflow_async_awaits_async_direct_tool() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "async-tool-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [make_async_tool("search_repo", output={"answer": "async 42"})]
    )

    result = asyncio.run(
        execute_workflow_async(workflow, prompt="Run", tool_registry=registry)
    )

    assert result.final_result == {"answer": "async 42"}
    assert result.state.tool_results["lookup"].output == {"answer": "async 42"}


def test_execute_workflow_async_awaits_async_lifecycle_hooks() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "async-hook-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
    observed: list[str] = []

    async def before_node(context: NodeHookContext) -> None:
        await asyncio.sleep(0)
        observed.append(f"before:{context.node_id}:{context.run_id}")

    async def after_node(context: NodeHookContext) -> None:
        await asyncio.sleep(0)
        observed.append(f"after:{context.node_id}:{context.output}:{context.run_id}")

    result = asyncio.run(
        execute_workflow_async(
            workflow,
            prompt="Hello",
            model_adapter=make_async_adapter([{"id": "resp", "output_text": "done"}]),
            lifecycle_hooks=WorkflowLifecycleHooks(
                before_node=before_node,
                after_node=after_node,
            ),
            run_id="async-run-1",
        )
    )

    assert result.final_result == "done"
    assert observed == ["before:answer:async-run-1", "after:answer:done:async-run-1"]


def test_execute_workflow_runs_llm_tool_and_final_llm_steps() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "executor-agent",
            "entrypoint": "analyze",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "analyze",
                    "kind": "llm_step",
                    "prompt": {
                        "system": "Analyze.",
                        "user_template": "Question: {prompt}",
                    },
                    "available_tools": ["search_repo"],
                },
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs_from": {"query": "analyze"},
                },
                {
                    "id": "final",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Use {lookup}"},
                },
            ],
            "edges": [
                {"source": "analyze", "target": "lookup", "edge_kind": "sequential"},
                {"source": "lookup", "target": "final", "edge_kind": "sequential"},
            ],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry([make_tool("search_repo", output={"answer": "42"})])
    adapter = make_adapter(
        [
            {"id": "resp_1", "output_text": "find agents"},
            {"id": "resp_2", "output_text": "final answer"},
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "final answer"
    assert [execution.node_id for execution in result.state.executions] == [
        "analyze",
        "lookup",
        "final",
    ]
    assert result.state.tool_results["lookup"].output == {"answer": "42"}
    first_call = adapter.client.responses.calls[0]
    assert first_call["tools"][0]["name"] == "search_repo"


def test_execute_workflow_preserves_tool_schema_without_descriptor_budget() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-budget-default-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "available_tools": ["search_repo", "read_file"],
                }
            ],
            "edges": [],
        }
    )
    registry = InMemoryToolRegistry([make_tool("search_repo"), make_tool("read_file")])
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "done"
    assert [tool["name"] for tool in adapter.client.responses.calls[0]["tools"]] == [
        "search_repo",
        "read_file",
    ]
    model_request = next(
        event
        for event in result.state.trace_events
        if event.event_type == "model_request"
    )
    assert "tool_descriptor_budget" not in model_request.payload


def test_execute_workflow_applies_descriptor_budget_to_model_tools() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-budget-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "tool_descriptor_budget": {
                        "enabled": True,
                        "max_tools": 1,
                        "required_tools": ["read_file"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "available_tools": ["search_repo", "read_file"],
                    "tool_descriptor_budget": {"required_tools": ["read_file"]},
                }
            ],
            "edges": [],
        }
    )
    registry = InMemoryToolRegistry([make_tool("search_repo"), make_tool("read_file")])
    captured_requests: list[object] = []
    adapter = OpenAIClientAdapter(
        FakeClient([{"id": "resp", "output_text": "done"}]),
        response_validator=lambda request, _response: captured_requests.append(request),
    )

    result = execute_workflow(
        workflow,
        prompt="Read pyproject.toml",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert [tool["name"] for tool in adapter.client.responses.calls[0]["tools"]] == [
        "read_file"
    ]
    model_request = next(
        event
        for event in result.state.trace_events
        if event.event_type == "model_request"
    )
    diagnostics = model_request.payload["tool_descriptor_budget"]
    assert diagnostics["selected_tool_ids"] == ["read_file"]
    assert diagnostics["omitted"][0]["tool_id"] == "search_repo"
    assert diagnostics["omitted"][0]["reason"] == "max_tools"
    assert "Read pyproject" not in repr(diagnostics)
    assert "parameters" not in repr(diagnostics)
    assert len(captured_requests) == 1
    context = captured_requests[0].adapter_context
    assert isinstance(context, ActiveAdapterToolContext)
    assert context.allowed_tool_ids == frozenset({"read_file"})
    assert [tool.id for tool in context.tools] == ["read_file"]
    assert model_request.payload["request"] == adapter.client.responses.calls[0]
    assert "adapter_context" not in model_request.payload["request"]
    assert not _contains_identity(
        model_request.payload,
        context,
        registry,
        result.state,
    )


def test_execute_workflow_fails_before_dispatch_when_required_tool_excluded() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-budget-required-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "tool_descriptor_budget": {
                        "enabled": True,
                        "required_tools": ["write_file"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "available_tools": ["read_file"],
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    with pytest.raises(WorkflowExecutionError, match="required tool 'write_file'"):
        execute_workflow(
            workflow,
            prompt="Write file",
            tool_registry=InMemoryToolRegistry([make_tool("read_file")]),
            model_adapter=adapter,
        )

    assert adapter.client.responses.calls == []


def test_execute_workflow_does_not_loop_model_tool_calls_without_policy() -> None:
    tool_invocations: list[object] = []

    def search_handler(args: object) -> object:
        tool_invocations.append(args)
        return {"answer": "42"}

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "single-call-tool-agent",
            "entrypoint": "analyze",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "analyze",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Question: {prompt}"},
                    "available_tools": ["search_repo"],
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {
                        "id": "search_repo",
                        "description_for_llm": "Search",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    }
                ),
                search_handler,
            )
        ]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            }
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result is None
    assert len(adapter.client.responses.calls) == 1
    assert tool_invocations == []
    assert result.state.node_outputs["analyze"].tool_calls[0].name == "search_repo"


def test_execute_workflow_loops_model_tool_call_with_policy() -> None:
    workflow = loop_tool_workflow()
    registry = InMemoryToolRegistry(
        [
            make_tool(
                "search_repo",
                output=ToolResult(
                    tool_id="search_repo",
                    success=True,
                    output={"raw": "secret raw"},
                    model_output={"summary": "agents found"},
                ),
            )
        ]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {"id": "resp_2", "output_text": "final answer"},
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "final answer"
    assert len(adapter.client.responses.calls) == 2
    second_input = adapter.client.responses.calls[1]["input"]
    assert second_input[-2]["role"] == "assistant"
    assert second_input[-2]["content"] == ""
    assert second_input[-2]["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "search_repo",
                "arguments": '{"query":"agents"}',
            },
        }
    ]
    assert second_input[-1] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "search_repo",
        "content": '{"summary": "agents found"}',
    }
    assert result.state.tool_results["analyze.call_1"].model_facing_output == {
        "summary": "agents found"
    }
    model_requests = [
        event
        for event in result.state.trace_events
        if event.event_type == "model_request"
    ]
    assert len(model_requests) == 2
    for trace_event, provider_call in zip(
        model_requests, adapter.client.responses.calls, strict=True
    ):
        assert trace_event.payload["request"] == provider_call
        assert "adapter_context" not in trace_event.payload["request"]
        assert not _contains_identity(trace_event.payload, registry, result.state)


def test_execute_workflow_runs_injected_mlx_tool_call_through_registry(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "mlx-model"
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (model_path / "tokenizer.model").write_text("", encoding="utf-8")
    (model_path / "weights.npz").write_bytes(b"")
    backend = FakeToolCapableMLXBackend()
    codec = FakeMLXToolCodec(
        MLXToolCodecResponse(
            tool_call=MLXToolCallCandidate(
                name="search_repo", arguments='{"query":"agents"}'
            )
        ),
        MLXToolCodecResponse(content="final answer"),
    )
    handler_calls: list[object] = []
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {
                        "id": "search_repo",
                        "description_for_llm": "Search the repository.",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    }
                ),
                lambda arguments: (
                    handler_calls.append(arguments)
                    or ToolResult(
                        tool_id="search_repo",
                        success=True,
                        output={"raw": "secret raw"},
                        model_output={"summary": "agents found"},
                    )
                ),
            )
        ]
    )
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(model_aliases=("mlx-local-chat",), model_path=model_path),
        backend=backend,
        tool_codec=codec,
        platform_system=lambda: "Darwin",
    )

    result = execute_workflow(
        loop_tool_workflow(execution_policy_extra={"model": "mlx-local-chat"}),
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "final answer"
    assert handler_calls == [{"query": "agents"}]
    assert backend.requests == []
    assert backend.rendered_prompts == ["<tool-aware-prompt>"] * 2
    assert len(codec.rendered_requests) == 2
    continuation = codec.rendered_requests[1].messages
    assistant_call, tool_result = continuation[-2:]
    assert assistant_call["role"] == "assistant"
    assert assistant_call["tool_calls"] == [
        {
            "id": assistant_call["call_id"],
            "type": "function",
            "function": {
                "name": "search_repo",
                "arguments": '{"query":"agents"}',
            },
        }
    ]
    assert tool_result == {
        "role": "tool",
        "tool_call_id": assistant_call["call_id"],
        "name": "search_repo",
        "content": '{"summary": "agents found"}',
        "_dar_transcript_type": "model_tool_result",
        "call_id": assistant_call["call_id"],
        "output": '{"summary": "agents found"}',
    }
    tool_loop_events = [
        event
        for event in result.state.trace_events
        if event.event_type == "model_tool_loop_tool_call"
    ]
    assert len(tool_loop_events) == 1
    assert tool_loop_events[0].payload["tool_id"] == "search_repo"


@pytest.mark.parametrize("asynchronous", [False, True])
def test_execute_workflow_runs_pinned_qwen3_tool_call_through_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    asynchronous: bool,
) -> None:
    from dynamic_agent_runner import (
        PINNED_QWEN3_MLX_MODEL_ID,
        create_qwen3_mlx_local_adapter,
        create_qwen3_mlx_local_async_adapter,
    )

    class Tokenizer:
        def __init__(self) -> None:
            self.conversations: list[list[dict[str, object]]] = []

        def apply_chat_template(
            self,
            conversation: list[dict[str, object]],
            *,
            tools: list[dict[str, object]] | None = None,
            add_generation_prompt: bool,
            tokenize: bool,
        ) -> str:
            assert tools is not None
            assert add_generation_prompt is True
            assert tokenize is False
            self.conversations.append(conversation)
            return "<native-qwen3-prompt>"

    model_path = tmp_path / "mlx-model"
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (model_path / "tokenizer.model").write_text("", encoding="utf-8")
    (model_path / "weights.npz").write_bytes(b"")
    generations = [
        '<tool_call>{"name":"search_repo","arguments":{"query":"agents"}}</tool_call>',
        "final answer",
    ]
    monkeypatch.setitem(
        sys.modules,
        "mlx_lm",
        SimpleNamespace(generate=lambda *_args, **_kwargs: generations.pop(0)),
    )
    tokenizer = Tokenizer()
    factory = (
        create_qwen3_mlx_local_async_adapter
        if asynchronous
        else create_qwen3_mlx_local_adapter
    )
    adapter = factory(
        MLXLocalModelConfig(
            model_aliases=("qwen3",),
            model_path=model_path,
            expected_model_id=PINNED_QWEN3_MLX_MODEL_ID,
        ),
        model=object(),
        tokenizer=tokenizer,
        platform_system=lambda: "Darwin",
    )
    handler_calls: list[object] = []
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {
                        "id": "search_repo",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    }
                ),
                lambda arguments: (
                    handler_calls.append(arguments)
                    or ToolResult(
                        tool_id="search_repo",
                        success=True,
                        output={"raw": "secret raw"},
                        model_output={"summary": "agents found"},
                    )
                ),
            )
        ]
    )
    workflow = loop_tool_workflow(execution_policy_extra={"model": "qwen3"})

    if asynchronous:
        result = asyncio.run(
            execute_workflow_async(
                workflow,
                prompt="How?",
                tool_registry=registry,
                model_adapter=adapter,
            )
        )
    else:
        result = execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=registry,
            model_adapter=adapter,
        )

    assert result.final_result == "final answer"
    assert handler_calls == [{"query": "agents"}]
    assistant_call, tool_result = tokenizer.conversations[1][-2:]
    assert assistant_call["role"] == "assistant"
    assert assistant_call["tool_calls"][0]["function"] == {
        "name": "search_repo",
        "arguments": '{"query":"agents"}',
    }
    assert tool_result["role"] == "tool"
    assert tool_result["name"] == "search_repo"
    assert tool_result["content"] == '{"summary": "agents found"}'


def test_execute_workflow_awaits_adapter_returning_awaitable_response() -> None:
    class AwaitableAdapter:
        models = ("gpt-test",)

        def create_response(self, _request: object) -> object:
            async def respond() -> ModelResponse:
                return ModelResponse(content="awaited response")

            return respond()

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "awaitable-model-adapter-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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

    result = execute_workflow(workflow, prompt="How?", model_adapter=AwaitableAdapter())

    assert result.final_result == "awaited response"


def test_execute_workflow_rejects_malformed_injected_mlx_tool_call_before_dispatch(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "mlx-model"
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (model_path / "tokenizer.model").write_text("", encoding="utf-8")
    (model_path / "weights.npz").write_bytes(b"")
    backend = FakeToolCapableMLXBackend()
    codec = FakeMLXToolCodec(
        MLXToolCodecResponse(
            tool_call=MLXToolCallCandidate(
                name="search_repo", arguments='{"query":"first","query":"second"}'
            )
        )
    )
    handler_calls: list[object] = []
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping({"id": "search_repo"}),
                lambda arguments: handler_calls.append(arguments) or {"ok": True},
            )
        ]
    )
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(model_aliases=("mlx-local-chat",), model_path=model_path),
        backend=backend,
        tool_codec=codec,
        platform_system=lambda: "Darwin",
    )
    sink = InMemoryTraceSink()

    with pytest.raises(ModelExecutionError, match="duplicate JSON keys"):
        execute_workflow(
            loop_tool_workflow(execution_policy_extra={"model": "mlx-local-chat"}),
            prompt="How?",
            tool_registry=registry,
            model_adapter=adapter,
            trace_sink=sink,
        )

    assert handler_calls == []
    assert backend.requests == []
    assert backend.rendered_prompts == ["<tool-aware-prompt>"]
    assert len(codec.rendered_requests) == 1
    assert not [
        event
        for event in sink.events
        if event.event_type == "model_tool_loop_tool_call"
    ]


def test_execute_workflow_rejects_initial_text_only_response_when_tool_required() -> (
    None
):
    tool_invocations: list[object] = []
    workflow = loop_tool_workflow()
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping({"id": "search_repo"}),
                lambda arguments: tool_invocations.append(arguments) or {"ok": True},
            )
        ]
    )
    adapter = make_adapter([{"id": "resp_1", "output_text": "I cannot do that."}])

    with pytest.raises(WorkflowExecutionError, match="required tool call"):
        execute_workflow(
            workflow,
            prompt="Search for DAR",
            tool_registry=registry,
            model_adapter=adapter,
        )

    assert len(adapter.client.responses.calls) == 1
    assert tool_invocations == []


def test_required_tool_loop_rejects_text_after_failed_provider_callback() -> None:
    plan = prepare_execution_plan(loop_tool_workflow())
    node = plan.nodes_by_id["analyze"]
    state = WorkflowExecutionState(prompt="Search for DAR", run_id="failed-callback")
    state.tool_results["analyze.apple-failed"] = ToolResult(
        tool_id="search_repo",
        success=False,
        error="external action unavailable",
    )
    tracer = WorkflowTracer(events=state.trace_events, run_id=state.run_id)

    with pytest.raises(WorkflowExecutionError, match="required tool call"):
        asyncio.run(
            _execute_model_tool_loop_async(
                node,
                plan,
                state,
                None,
                None,
                SimpleNamespace(),
                ModelResponse(content="I cannot do that."),
                (),
                None,
                tracer,
                None,
            )
        )


def test_execute_workflow_keeps_provider_tool_call_correlations_separate() -> None:
    """Provider-origin call ids must remain bound to their own results and traces."""

    calls: list[object] = []
    result = execute_workflow(
        loop_tool_workflow(),
        prompt="Run",
        tool_registry=InMemoryToolRegistry(
            [
                RegisteredTool(
                    ToolDefinition.from_mapping({"id": "search_repo"}),
                    lambda arguments: (
                        calls.append(arguments) or {"summary": arguments["query"]}
                    ),
                )
            ]
        ),
        model_adapter=make_adapter(
            [
                {
                    "id": "response-1",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "provider-call-a",
                            "name": "search_repo",
                            "arguments": '{"query":"first"}',
                        }
                    ],
                },
                {
                    "id": "response-2",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "provider-call-b",
                            "name": "search_repo",
                            "arguments": '{"query":"second"}',
                        }
                    ],
                },
                {"id": "response-3", "output_text": "done"},
            ]
        ),
        run_id="provider-run",
    )

    assert calls == [{"query": "first"}, {"query": "second"}]
    assert result.final_result == "done"
    assert result.state.tool_results["analyze.provider-call-a"].model_facing_output == {
        "summary": "first"
    }
    assert result.state.tool_results["analyze.provider-call-b"].model_facing_output == {
        "summary": "second"
    }
    for call_id, query in (
        ("provider-call-a", "first"),
        ("provider-call-b", "second"),
    ):
        loop_events = [
            event
            for event in result.state.trace_events
            if event.event_type == "model_tool_loop_tool_call"
            and event.payload.get("tool_call_id") == call_id
        ]
        correlated_events = [
            event
            for event in result.state.trace_events
            if event.event_type in {"tool_started", "tool_result", "tool_finished"}
            and event.payload.get("tool_call_id") == call_id
        ]
        assert len(loop_events) == 1
        assert loop_events[0].payload["tool_id"] == "search_repo"
        assert loop_events[0].payload["arguments"] == {"query": query}
        assert [event.event_type for event in correlated_events] == [
            "tool_started",
            "tool_result",
            "tool_finished",
        ]
        assert {event.run_id for event in correlated_events} == {"provider-run"}
        assert {event.node_id for event in correlated_events} == {"analyze"}
        assert {event.payload["tool_id"] for event in correlated_events} == {
            "search_repo"
        }
        result_event = next(
            event for event in correlated_events if event.event_type == "tool_result"
        )
        assert result_event.payload["output"] == {"summary": query}


def test_execute_workflow_renders_chatgpt_codex_tool_loop_follow_up_items() -> None:
    workflow = loop_tool_workflow()
    registry = InMemoryToolRegistry(
        [
            make_tool(
                "search_repo",
                output=ToolResult(
                    tool_id="search_repo",
                    success=True,
                    output={"raw": "secret raw"},
                    model_output={"summary": "agents found"},
                ),
            )
        ]
    )
    provider = FakeProvider(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {"id": "resp_2", "output_text": "final answer"},
        ],
        OpenAIProviderConfig(provider_name="chatgpt-codex"),
        models=FakeModels({"models": [{"slug": "gpt-test"}]}),
    )
    adapter = OpenAIClientAdapter(provider=provider)

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "final answer"
    second_input = adapter.client.responses.calls[1]["input"]
    assert second_input[-2:] == [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "search_repo",
            "arguments": '{"query":"agents"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"summary": "agents found"}',
        },
    ]


def test_execute_workflow_applies_runtime_tool_choice_policy_by_loop_phase() -> None:
    workflow = loop_tool_workflow(
        execution_policy_extra={
            "tool_choice_policy": {
                "initial": "required",
                "after_tool_result": "auto",
            }
        }
    )
    registry = InMemoryToolRegistry([make_tool("search_repo")])
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {"id": "resp_2", "output_text": "final answer"},
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "final answer"
    assert adapter.client.responses.calls[0]["tool_choice"] == "required"
    assert "tool_choice" not in adapter.client.responses.calls[1]


def test_execute_workflow_node_tool_choice_policy_overrides_runtime_policy() -> None:
    workflow = loop_tool_workflow(
        execution_policy_extra={
            "tool_choice_policy": {
                "initial": "auto",
                "after_tool_result": "required",
            }
        },
        node_extra={
            "tool_choice_policy": {
                "initial": "required",
                "after_tool_result": "auto",
            }
        },
    )
    registry = InMemoryToolRegistry([make_tool("search_repo")])
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {"id": "resp_2", "output_text": "final answer"},
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "final answer"
    assert adapter.client.responses.calls[0]["tool_choice"] == "required"
    assert "tool_choice" not in adapter.client.responses.calls[1]


def test_execute_workflow_preserves_legacy_tool_choice_without_policy() -> None:
    workflow = loop_tool_workflow(node_extra={"tool_choice": "required"})
    registry = InMemoryToolRegistry([make_tool("search_repo")])
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {"id": "resp_2", "output_text": "final answer"},
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "final answer"
    assert adapter.client.responses.calls[0]["tool_choice"] == "required"
    assert adapter.client.responses.calls[1]["tool_choice"] == "required"


@pytest.mark.parametrize("asynchronous", [False, True])
def test_execute_workflow_disables_tools_after_tool_result_when_requested(
    asynchronous: bool,
) -> None:
    workflow = loop_tool_workflow(
        execution_policy_extra={
            "tool_use_completion": {
                "run_again": "required",
                "stop_on_tool": "disabled",
                "final_output": "default",
                "after_tool_result_tools": "disabled",
            }
        },
        node_extra={"tool_choice": "required"},
    )
    registry = InMemoryToolRegistry([make_tool("search_repo")])
    responses = [
        {
            "id": "resp_1",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "search_repo",
                    "arguments": '{"query":"agents"}',
                }
            ],
        },
        {"id": "resp_2", "output_text": "final answer"},
    ]
    adapter = make_async_adapter(responses) if asynchronous else make_adapter(responses)

    result = (
        asyncio.run(
            execute_workflow_async(
                workflow,
                prompt="How?",
                tool_registry=registry,
                model_adapter=adapter,
            )
        )
        if asynchronous
        else execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=registry,
            model_adapter=adapter,
        )
    )

    assert result.final_result == "final answer"
    assert adapter.client.responses.calls[0]["tools"][0]["name"] == "search_repo"
    assert "tools" not in adapter.client.responses.calls[1]
    assert "tool_choice" not in adapter.client.responses.calls[1]


@pytest.mark.parametrize("asynchronous", [False, True])
def test_execute_workflow_rejects_tool_calls_after_tool_exposure_is_disabled(
    asynchronous: bool,
) -> None:
    workflow = loop_tool_workflow(
        execution_policy_extra={
            "tool_use_completion": {
                "run_again": "required",
                "stop_on_tool": "disabled",
                "final_output": "default",
                "after_tool_result_tools": "disabled",
            }
        }
    )
    calls: list[object] = []
    tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "search_repo",
                "description_for_llm": "Use search_repo",
                "input_schema": {"type": "object", "properties": {}},
            }
        ),
        lambda arguments: calls.append(arguments) or {"result": "first"},
    )
    responses = [
        {
            "id": "resp_1",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "search_repo",
                    "arguments": "{}",
                }
            ],
        },
        {
            "id": "resp_2",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_2",
                    "name": "search_repo",
                    "arguments": "{}",
                }
            ],
        },
    ]
    adapter = make_async_adapter(responses) if asynchronous else make_adapter(responses)

    if asynchronous:

        def invocation() -> object:
            return asyncio.run(
                execute_workflow_async(
                    workflow,
                    prompt="How?",
                    tool_registry=InMemoryToolRegistry([tool]),
                    model_adapter=adapter,
                )
            )
    else:

        def invocation() -> object:
            return execute_workflow(
                workflow,
                prompt="How?",
                tool_registry=InMemoryToolRegistry([tool]),
                model_adapter=adapter,
            )

    with pytest.raises(WorkflowExecutionError, match="tool exposure was disabled"):
        invocation()

    assert calls == [{}]
    assert "tools" not in adapter.client.responses.calls[1]


def test_execute_workflow_mid_turn_compaction_fails_without_compactor() -> None:
    workflow = loop_tool_workflow()
    workflow.runtime_manifest.execution_policy["prepare_model_input"] = {
        "context_compaction": {
            "auto": {
                "enabled": True,
                "threshold_tokens": 20,
                "implementation": "injected",
            }
        }
    }
    registry = InMemoryToolRegistry(
        [make_tool("search_repo", output={"summary": "agents found " * 20})]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="mid-turn context compaction"):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=registry,
            model_adapter=adapter,
        )


def test_execute_workflow_mid_turn_compaction_uses_injected_compactor() -> None:
    workflow = loop_tool_workflow()
    workflow.runtime_manifest.execution_policy["prepare_model_input"] = {
        "context_compaction": {
            "auto": {
                "enabled": True,
                "threshold_tokens": 20,
                "implementation": "injected",
            }
        }
    }
    registry = InMemoryToolRegistry(
        [make_tool("search_repo", output={"summary": "agents found " * 20})]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {"id": "resp_2", "output_text": "final answer"},
        ]
    )

    def fake_compactor(
        _messages: tuple[OpenAIMessage, ...],
        metadata: Mapping[str, Any],
    ) -> tuple[OpenAIMessage, ...]:
        assert metadata["phase"] == "pre_turn"
        return (
            OpenAIMessage(role="developer", content="Mid-turn compacted context."),
            OpenAIMessage(role="user", content="Continue."),
        )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
        context_compactor=fake_compactor,
    )

    assert result.final_result == "final answer"
    second_input = adapter.client.responses.calls[1]["input"]
    assert second_input == [
        {"role": "developer", "content": "Mid-turn compacted context."},
        {"role": "user", "content": "Continue."},
    ]
    compaction_events = [
        event
        for event in result.state.trace_events
        if event.event_type == "mid_turn_compaction"
    ]
    assert compaction_events[0].payload["status"] == "complete"
    assert compaction_events[0].payload["phase"] == "mid_turn"


def test_execute_workflow_traces_iterative_model_tool_loop() -> None:
    workflow = loop_tool_workflow()
    registry = InMemoryToolRegistry(
        [make_tool("search_repo", output={"summary": "agents found"})]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {"id": "resp_2", "output_text": "final answer"},
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=registry,
        model_adapter=adapter,
        run_id="loop-run-1",
    )

    loop_events = [
        event
        for event in result.state.trace_events
        if event.event_type.startswith("model_tool_loop")
    ]
    assert [event.event_type for event in loop_events] == [
        "model_tool_loop_started",
        "model_tool_loop_turn_started",
        "model_tool_loop_tool_call",
        "model_tool_loop_stopped",
        "model_tool_loop_final_output",
    ]
    assert {event.run_id for event in loop_events} == {"loop-run-1"}
    assert loop_events[0].payload == {
        "max_iterations": 8,
        "tool_count": 1,
    }
    assert loop_events[1].payload == {
        "iteration": 1,
        "tool_call_count": 1,
    }
    assert loop_events[2].payload == {
        "iteration": 1,
        "tool_call_id": "call_1",
        "tool_id": "search_repo",
        "arguments": {"query": "agents"},
    }
    assert "arguments" in loop_events[2].sensitive_fields
    assert loop_events[3].payload == {
        "iteration": 2,
        "stop_reason": "final_model_output",
    }
    assert loop_events[4].payload == {
        "final_output": "final answer",
        "final_output_policy": "default",
        "stop_reason": "final_model_output",
    }
    assert "final_output" in loop_events[4].sensitive_fields


def test_execute_workflow_rejects_unavailable_model_tool_call() -> None:
    workflow = loop_tool_workflow(available_tools=["search_repo"])
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "write_file",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            }
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="unavailable tool 'write_file'"):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=InMemoryToolRegistry([make_tool("search_repo")]),
            model_adapter=adapter,
        )


def test_execute_workflow_rejects_hidden_model_tool_call() -> None:
    workflow = loop_tool_workflow(
        available_tools=["hidden_search"],
        tools=[{"id": "hidden_search", "exposure": "hidden"}],
    )
    calls: list[object] = []
    hidden_tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "hidden_search",
                "exposure": "hidden",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ),
        lambda args: calls.append(args) or {"answer": "hidden"},
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "hidden_search",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            }
        ]
    )

    with pytest.raises(
        WorkflowExecutionError, match="unavailable tool 'hidden_search'"
    ):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=InMemoryToolRegistry([hidden_tool]),
            model_adapter=adapter,
        )

    assert calls == []


def test_execute_workflow_rejects_malformed_model_tool_arguments() -> None:
    workflow = loop_tool_workflow()
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": "not json",
                    }
                ],
            }
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="arguments must be JSON"):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=InMemoryToolRegistry([make_tool("search_repo")]),
            model_adapter=adapter,
        )


def test_execute_workflow_aborts_failed_model_tool_call() -> None:
    workflow = loop_tool_workflow()
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            }
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="search unavailable"):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=InMemoryToolRegistry(
                [make_flaky_tool("search_repo", [RuntimeError("search unavailable")])]
            ),
            model_adapter=adapter,
        )


def test_execute_workflow_stops_at_model_tool_loop_limit() -> None:
    workflow = loop_tool_workflow(max_steps=1)
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {
                "id": "resp_2",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_2",
                        "name": "search_repo",
                        "arguments": '{"query":"more"}',
                    }
                ],
            },
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="tool loop limit 1"):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=InMemoryToolRegistry([make_tool("search_repo")]),
            model_adapter=adapter,
        )


def test_execute_workflow_pauses_approval_required_model_tool_before_invocation() -> (
    None
):
    calls: list[object] = []
    workflow = loop_tool_workflow(
        tools=[
            {
                "id": "workspace_write",
                "approval_required": "yes",
                "side_effect": "write",
            }
        ],
        available_tools=["workspace_write"],
    )
    tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "workspace_write",
                "approval_required": "yes",
                "side_effect": "write",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ),
        lambda args: calls.append(args) or {"ok": True},
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "workspace_write",
                        "arguments": '{"query":"notes"}',
                    }
                ],
            }
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=InMemoryToolRegistry([tool]),
        model_adapter=adapter,
    )

    assert isinstance(result, WorkflowInterruptedResult)
    assert calls == []
    assert result.interruption.node_id == "analyze"
    assert result.interruption.tool_id == "workspace_write"
    assert result.interruption.action_id == "call_1"
    assert result.interruption.arguments == {"query": "notes"}
    assert result.state.tool_results == {}


def test_tool_from_function_pauses_approval_required_tool_before_invocation() -> None:
    calls: list[str] = []

    def workspace_write(query: str) -> dict[str, bool]:
        calls.append(query)
        return {"ok": True}

    workflow = loop_tool_workflow(
        tools=[
            {
                "id": "workspace_write",
                "approval_required": "yes",
                "side_effect": "write",
            }
        ],
        available_tools=["workspace_write"],
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "workspace_write",
                        "arguments": '{"query":"notes"}',
                    }
                ],
            }
        ]
    )

    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=InMemoryToolRegistry(
            [
                tool_from_function(
                    workspace_write,
                    metadata={
                        "id": "workspace_write",
                        "approval_required": "yes",
                        "side_effect": "write",
                    },
                )
            ]
        ),
        model_adapter=adapter,
    )

    assert isinstance(result, WorkflowInterruptedResult)
    assert calls == []
    assert result.interruption.tool_id == "workspace_write"
    assert result.interruption.action_id == "call_1"
    assert result.interruption.arguments == {"query": "notes"}
    assert result.state.tool_results == {}


@pytest.mark.parametrize(
    ("decision_state", "interrupted"),
    [
        (ProviderDecisionState.UNRESOLVED, True),
        (ProviderDecisionState.DENIED, False),
    ],
)
def test_provider_model_tool_decision_has_the_declared_executor_outcome(
    decision_state: ProviderDecisionState,
    interrupted: bool,
) -> None:
    calls: list[object] = []
    workflow = loop_tool_workflow(
        tools=[{"id": "workspace_write", "approval_required": "yes"}],
        available_tools=["workspace_write"],
    )
    plan = prepare_execution_plan(workflow)
    node = plan.nodes_by_id["analyze"]
    tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "workspace_write",
                "approval_required": "yes",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ),
        lambda arguments: calls.append(arguments) or {"ok": True},
    )
    registry = InMemoryToolRegistry([tool])
    tool = registry.get_tool("workspace_write")
    state = WorkflowExecutionState(prompt="How?", run_id="run-1")
    tracer = WorkflowTracer(events=state.trace_events, run_id=state.run_id)

    class Collaborator:
        def decide(self, request: ProviderDecisionRequest) -> ProviderToolDecision:
            return ProviderToolDecision(
                state=decision_state,
                invocation_id=request.invocation_id,
                fingerprint=request.fingerprint,
            )

    adapter_context = tool_context(
        plan=plan,
        node=node,
        tools=(tool,),
        registry=registry,
        state=state,
        tracer=tracer,
        lifecycle_hooks=None,
        retry_policy=RetryPolicy(),
        decision_collaborator=Collaborator(),
    )

    invocation = _invoke_model_tool_call_async(
        node,
        plan,
        ModelToolCall(
            id="call_1",
            name="workspace_write",
            arguments={"query": "notes"},
        ),
        "call_1",
        1,
        None,
        adapter_context,
        state,
        tracer,
        None,
    )

    if interrupted:
        result = asyncio.run(invocation)
        assert isinstance(result, WorkflowInterruptedResult)
        assert result.interruption.state is ApprovalInterruptionState.PENDING
    else:
        with pytest.raises(WorkflowExecutionError, match="provider tool decision"):
            asyncio.run(invocation)
    assert calls == []
    assert state.tool_results == {}
    assert state.errors == []
    assert state.retry_records == []


def test_executor_converts_provider_callback_interruption_to_workflow_result() -> None:
    workflow = loop_tool_workflow(available_tools=[])
    approval = ApprovalInterruption(
        interruption_id="approval-1",
        run_id="provider-run",
        workflow_id="loop-tool-agent",
        node_id="analyze",
        tool_id="send",
        action_id="apple-call-1",
        arguments={"message": "private"},
        policy={"approval_required": "yes"},
        reason="approval required",
    )

    class ProviderInterruptingAdapter(AsyncOpenAIClientAdapter):
        async def create_response(self, _request: object) -> ModelResponse:
            raise ProviderToolInterruption(approval, provider="apple_foundation_models")

    adapter = ProviderInterruptingAdapter(models=("gpt-test",))

    result = asyncio.run(
        execute_workflow_async(workflow, prompt="Send", model_adapter=adapter)
    )

    assert isinstance(result, WorkflowInterruptedResult)
    assert result.interruption is approval
    assert result.state.tool_results == {}


@pytest.mark.parametrize(
    "message",
    [
        "provider tool decision is denied",
        "tool input rejected by guardrail",
        "send delivery failed",
    ],
)
def test_executor_does_not_retry_provider_callback_terminal_failures(
    message: str,
) -> None:
    calls = 0
    workflow = loop_tool_workflow(
        available_tools=[],
        execution_policy_extra={"model_retry_policy": {"max_attempts": 2}},
    )

    class TerminalAdapter(AsyncOpenAIClientAdapter):
        async def create_response(self, _request: object) -> ModelResponse:
            nonlocal calls
            calls += 1
            raise ProviderToolTerminalError(message)

    with pytest.raises(WorkflowExecutionError, match=message):
        asyncio.run(
            execute_workflow_async(
                workflow,
                prompt="Send",
                model_adapter=TerminalAdapter(models=("gpt-test",)),
            )
        )

    assert calls == 1


def loop_tool_workflow(
    *,
    tools: list[dict[str, object]] | None = None,
    available_tools: list[str] | None = None,
    max_steps: int | None = None,
    execution_policy_extra: dict[str, object] | None = None,
    node_extra: dict[str, object] | None = None,
    guardrails: list[dict[str, object]] | None = None,
) -> LoadedAgentWorkflow:
    execution_policy: dict[str, object] = {
        "model": "gpt-test",
        "tool_use_completion": {
            "run_again": "required",
            "stop_on_tool": "disabled",
            "final_output": "default",
        },
    }
    execution_policy.update(execution_policy_extra or {})
    if max_steps is not None:
        execution_policy["max_steps"] = max_steps
    tool_entries = tools or [{"id": "search_repo"}]
    llm_node: dict[str, object] = {
        "id": "analyze",
        "kind": "llm_step",
        "prompt": {"user_template": "Question: {prompt}"},
        "available_tools": (
            available_tools if available_tools is not None else ["search_repo"]
        ),
    }
    llm_node.update(node_extra or {})
    manifest: dict[str, object] = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "loop-tool-agent",
        "entrypoint": "analyze",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": execution_policy},
        "nodes": [llm_node],
        "edges": [],
        "tools": tool_entries,
    }
    if guardrails is not None:
        manifest["extensions"] = {"guardrails": {"declarations": guardrails}}
    return workflow_from(manifest)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_model_interface_parity_s1_selects_only_create_record(
    asynchronous: bool,
    parity_io_blocker: None,
) -> None:
    registry, invocations, results = _parity_registry()
    result, _, record, error = _run_parity_loop(
        [
            ModelResponse(
                content=None,
                tool_calls=(
                    ModelToolCall(
                        "create-1",
                        "create_record",
                        {"title": "DAR", "body": "controlled"},
                    ),
                ),
            ),
            ModelResponse(content="created"),
        ],
        scenario="S1",
        asynchronous=asynchronous,
        registry=registry,
        invocations=invocations,
        results=results,
    )

    assert error is None
    assert result is not None
    assert result.final_result == "created"
    assert record.interface == "executor_fake_adapter"
    assert record.invocations == (
        ("create_record", {"title": "DAR", "body": "controlled"}),
    )
    assert record.invocation_results == (
        ("create_record", {"record_id": "record-created"}),
    )
    assert record.completion_class == "completed"


class _ScriptedParityAdapter:
    models = ("gpt-test",)

    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[OpenAIModelRequest] = []

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        self.requests.append(request)
        return self.responses.pop(0)


class _AsyncScriptedParityAdapter(_ScriptedParityAdapter):
    async def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        self.requests.append(request)
        await asyncio.sleep(0)
        return self.responses.pop(0)


@pytest.fixture
def parity_io_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    install_parity_io_blocker(monkeypatch)


def test_model_interface_parity_io_blocker_rejects_every_external_seam(
    parity_io_blocker: None,
) -> None:
    with pytest.raises(AssertionError, match="prohibit external I/O"):
        socket.create_connection(("example.invalid", 443))
    with (
        socket.socket() as client,
        pytest.raises(AssertionError, match="prohibit external I/O"),
    ):
        client.connect(("example.invalid", 443))
    with pytest.raises(AssertionError, match="prohibit external I/O"):
        subprocess.Popen(["false"])
    with pytest.raises(AssertionError, match="prohibit external I/O"):
        local_models.download_hub_file("repo", "file")
    with pytest.raises(AssertionError, match="prohibit external I/O"):
        local_models.download_hub_snapshot("repo")
    with pytest.raises(AssertionError, match="prohibit external I/O"):
        hugging_face_support.download_hub_file("repo", "file")
    with pytest.raises(AssertionError, match="prohibit external I/O"):
        hugging_face_support.download_hub_snapshot("repo")

    async def assert_async_interceptors() -> None:
        with pytest.raises(AssertionError, match="prohibit external I/O"):
            await asyncio.create_subprocess_exec("false")
        with pytest.raises(AssertionError, match="prohibit external I/O"):
            await asyncio.create_subprocess_shell("false")

    asyncio.run(assert_async_interceptors())


def _parity_tool_definitions() -> list[dict[str, object]]:
    return shared_parity_tool_definitions()


def _parity_registry() -> tuple[
    InMemoryToolRegistry,
    list[tuple[str, Mapping[str, object]]],
    list[tuple[str, object]],
]:
    return shared_parity_registry()


def _parity_record(
    *,
    scenario: str,
    asynchronous: bool,
    calls: tuple[ModelToolCall, ...],
    exposed_schemas: tuple[tuple[str, Mapping[str, object]], ...],
    invocations: list[tuple[str, Mapping[str, object]]],
    results: list[tuple[str, object]],
    result: object | None,
    error: WorkflowExecutionError | None,
    sink: InMemoryTraceSink,
) -> ParityRecord:
    events = result.state.trace_events if result is not None else sink.events
    record = ParityRecord(
        interface="executor_fake_adapter",
        scenario=scenario,
        asynchronous=asynchronous,
        exposed_schemas=exposed_schemas,
        normalized_calls=tuple((call.name, call.arguments) for call in calls),
        invocations=tuple(invocations),
        invocation_results=tuple(results),
        completion_class="error" if error is not None else "completed",
        error_class=type(error).__name__ if error is not None else None,
        trace_event_types=tuple(event.event_type for event in events),
        stop_reasons=tuple(
            str(event.payload["stop_reason"])
            for event in events
            if event.event_type == "model_tool_loop_stopped"
        ),
    )
    assert result is None or not isinstance(result, WorkflowInterruptedResult)
    assert not any("approval" in event_type for event_type in record.trace_event_types)
    assert_parity_semantic_projection(record)
    return record


def _parity_loop_workflow() -> LoadedAgentWorkflow:
    return shared_parity_loop_workflow()


def _run_parity_loop(
    responses: list[ModelResponse],
    *,
    scenario: str,
    asynchronous: bool,
    registry: InMemoryToolRegistry,
    invocations: list[tuple[str, Mapping[str, object]]],
    results: list[tuple[str, object]],
) -> tuple[
    object | None, _ScriptedParityAdapter, ParityRecord, WorkflowExecutionError | None
]:
    adapter = (
        _AsyncScriptedParityAdapter(responses)
        if asynchronous
        else _ScriptedParityAdapter(responses)
    )
    sink = InMemoryTraceSink()
    calls = tuple(call for response in responses for call in response.tool_calls)
    try:
        if asynchronous:
            result = asyncio.run(
                execute_workflow_async(
                    _parity_loop_workflow(),
                    prompt="controlled parity",
                    tool_registry=registry,
                    model_adapter=adapter,
                    trace_sink=sink,
                )
            )
        else:
            result = execute_workflow(
                _parity_loop_workflow(),
                prompt="controlled parity",
                tool_registry=registry,
                model_adapter=adapter,
                trace_sink=sink,
            )
    except WorkflowExecutionError as error:
        return (
            None,
            adapter,
            _parity_record(
                scenario=scenario,
                asynchronous=asynchronous,
                calls=calls,
                exposed_schemas=parity_exposed_schemas(adapter.requests[0].tools),
                invocations=invocations,
                results=results,
                result=None,
                error=error,
                sink=sink,
            ),
            error,
        )
    return (
        result,
        adapter,
        _parity_record(
            scenario=scenario,
            asynchronous=asynchronous,
            calls=calls,
            exposed_schemas=parity_exposed_schemas(adapter.requests[0].tools),
            invocations=invocations,
            results=results,
            result=result,
            error=None,
            sink=sink,
        ),
        None,
    )


def _run_parity_no_tool(*, asynchronous: bool) -> tuple[object, ParityRecord]:
    definitions = _parity_tool_definitions()
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "parity-no-tool",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "available_tools": [str(tool["id"]) for tool in definitions],
                }
            ],
            "edges": [],
            "tools": definitions,
        }
    )
    registry, invocations, results = _parity_registry()
    adapter = (
        _AsyncScriptedParityAdapter([ModelResponse(content="no tool")])
        if asynchronous
        else _ScriptedParityAdapter([ModelResponse(content="no tool")])
    )
    sink = InMemoryTraceSink()
    if asynchronous:
        result = asyncio.run(
            execute_workflow_async(
                workflow,
                prompt="answer",
                tool_registry=registry,
                model_adapter=adapter,
                trace_sink=sink,
            )
        )
    else:
        result = execute_workflow(
            workflow,
            prompt="answer",
            tool_registry=registry,
            model_adapter=adapter,
            trace_sink=sink,
        )
    return result, _parity_record(
        scenario="S5",
        asynchronous=asynchronous,
        calls=(),
        exposed_schemas=parity_exposed_schemas(adapter.requests[0].tools),
        invocations=invocations,
        results=results,
        result=result,
        error=None,
        sink=sink,
    )


def _parity_contract_projection(record: ParityRecord) -> tuple[object, ...]:
    return shared_parity_contract_projection(record)


@pytest.mark.parametrize(
    ("scenario", "responses"),
    [
        (
            "S1",
            [
                ModelResponse(
                    content=None,
                    tool_calls=(
                        ModelToolCall(
                            "create-1",
                            "create_record",
                            {"title": "DAR", "body": "controlled"},
                        ),
                    ),
                ),
                ModelResponse(content="created"),
            ],
        ),
        (
            "S2-valid",
            [
                ModelResponse(
                    content=None,
                    tool_calls=(
                        ModelToolCall(
                            "transform-1",
                            "transform_record",
                            {"record_id": "record-seed", "operation": "uppercase"},
                        ),
                    ),
                ),
                ModelResponse(content="transformed"),
            ],
        ),
        (
            "S2-invalid-enum",
            [
                ModelResponse(
                    content=None,
                    tool_calls=(
                        ModelToolCall(
                            "invalid",
                            "transform_record",
                            {"record_id": "record-seed", "operation": "lowercase"},
                        ),
                    ),
                )
            ],
        ),
        (
            "S3",
            [
                ModelResponse(
                    content=None,
                    tool_calls=(
                        ModelToolCall("lookup-1", "lookup_record", {"key": "seed"}),
                    ),
                ),
                ModelResponse(
                    content=None,
                    tool_calls=(
                        ModelToolCall(
                            "transform-1",
                            "transform_record",
                            {"record_id": "record-seed", "operation": "uppercase"},
                        ),
                    ),
                ),
                ModelResponse(content="SEED"),
            ],
        ),
        (
            "S4",
            [
                ModelResponse(
                    content=None,
                    tool_calls=(
                        ModelToolCall("fail-1", "fail_controlled", {"code": "planned"}),
                    ),
                )
            ],
        ),
        (
            "S6",
            [
                ModelResponse(
                    content=None,
                    tool_calls=(ModelToolCall("bad-1", "lookup_record", "not-json"),),
                )
            ],
        ),
    ],
)
def test_model_interface_parity_sync_and_async_records_match(
    scenario: str,
    responses: list[ModelResponse],
    parity_io_blocker: None,
) -> None:
    def run(asynchronous: bool) -> ParityRecord:
        registry, invocations, results = _parity_registry()
        _, _, record, _ = _run_parity_loop(
            responses,
            scenario=scenario,
            asynchronous=asynchronous,
            registry=registry,
            invocations=invocations,
            results=results,
        )
        return record

    assert _parity_contract_projection(run(False)) == _parity_contract_projection(
        run(True)
    )


def test_model_interface_parity_s5_sync_and_async_records_match(
    parity_io_blocker: None,
) -> None:
    _, sync_record = _run_parity_no_tool(asynchronous=False)
    _, async_record = _run_parity_no_tool(asynchronous=True)

    assert _parity_contract_projection(sync_record) == _parity_contract_projection(
        async_record
    )


@pytest.mark.parametrize("asynchronous", [False, True])
def test_model_interface_parity_s2_valid_and_invalid_arguments(
    asynchronous: bool, parity_io_blocker: None
) -> None:
    registry, invocations, results = _parity_registry()
    result, _, record, error = _run_parity_loop(
        [
            ModelResponse(
                content=None,
                tool_calls=(
                    ModelToolCall(
                        "transform-1",
                        "transform_record",
                        {"record_id": "record-seed", "operation": "uppercase"},
                    ),
                ),
            ),
            ModelResponse(content="transformed"),
        ],
        scenario="S2-valid",
        asynchronous=asynchronous,
        registry=registry,
        invocations=invocations,
        results=results,
    )
    assert error is None
    assert result is not None
    assert result.final_result == "transformed"
    assert invocations == [
        ("transform_record", {"record_id": "record-seed", "operation": "uppercase"})
    ]
    assert record.error_class is None
    for name, arguments in (
        ("missing", {"record_id": "record-seed"}),
        ("wrong-type", {"record_id": 1, "operation": "uppercase"}),
        ("invalid-enum", {"record_id": "record-seed", "operation": "lowercase"}),
        (
            "unknown",
            {"record_id": "record-seed", "operation": "uppercase", "unknown": True},
        ),
        ("malformed", "not-json"),
    ):
        registry, invocations, results = _parity_registry()
        _, _, invalid_record, invalid_error = _run_parity_loop(
            [
                ModelResponse(
                    content=None,
                    tool_calls=(
                        ModelToolCall("invalid", "transform_record", arguments),
                    ),
                )
            ],
            scenario=f"S2-{name}",
            asynchronous=asynchronous,
            registry=registry,
            invocations=invocations,
            results=results,
        )
        assert isinstance(invalid_error, WorkflowExecutionError)
        assert invalid_record.error_class == "WorkflowExecutionError"
        assert invocations == []


@pytest.mark.parametrize("asynchronous", [False, True])
def test_model_interface_parity_s3_continues_with_lookup_identifier(
    asynchronous: bool, parity_io_blocker: None
) -> None:
    registry, invocations, results = _parity_registry()
    result, adapter, record, error = _run_parity_loop(
        [
            ModelResponse(
                content=None,
                tool_calls=(
                    ModelToolCall("lookup-1", "lookup_record", {"key": "seed"}),
                ),
            ),
            ModelResponse(
                content=None,
                tool_calls=(
                    ModelToolCall(
                        "transform-1",
                        "transform_record",
                        {"record_id": "record-seed", "operation": "uppercase"},
                    ),
                ),
            ),
            ModelResponse(content="SEED"),
        ],
        scenario="S3",
        asynchronous=asynchronous,
        registry=registry,
        invocations=invocations,
        results=results,
    )
    assert error is None
    assert result is not None
    assert result.final_result == "SEED"
    assert invocations == [
        ("lookup_record", {"key": "seed"}),
        ("transform_record", {"record_id": "record-seed", "operation": "uppercase"}),
    ]
    assert record.invocation_results[-1] == (
        "transform_record",
        {"record_id": "record-seed", "body": "SEED"},
    )
    assert len(adapter.requests) == 3
    continuation = adapter.requests[1].messages
    assert continuation[-1]["_dar_transcript_type"] == "model_tool_result"
    assert continuation[-1]["name"] == "lookup_record"
    assert "record-seed" in str(continuation[-1]["content"])


@pytest.mark.parametrize("asynchronous", [False, True])
def test_model_interface_parity_s4_reports_controlled_failure(
    asynchronous: bool, parity_io_blocker: None
) -> None:
    registry, invocations, results = _parity_registry()
    result, adapter, record, error = _run_parity_loop(
        [
            ModelResponse(
                content=None,
                tool_calls=(
                    ModelToolCall("fail-1", "fail_controlled", {"code": "planned"}),
                ),
            )
        ],
        scenario="S4",
        asynchronous=asynchronous,
        registry=registry,
        invocations=invocations,
        results=results,
    )
    assert result is None
    assert isinstance(error, WorkflowExecutionError)
    assert "planned controlled failure" in str(error)
    assert invocations == [("fail_controlled", {"code": "planned"})]
    assert len(adapter.requests) == 1
    assert record.completion_class == "error"
    assert record.error_class == "WorkflowExecutionError"
    assert record.trace_event_types.count("model_tool_loop_tool_call") == 1
    assert record.stop_reasons == ("tool_failure",)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_model_interface_parity_s5_completes_without_a_tool(
    asynchronous: bool, parity_io_blocker: None
) -> None:
    result, record = _run_parity_no_tool(asynchronous=asynchronous)
    assert result.final_result == "no tool"
    assert record.invocations == ()
    assert record.invocation_results == ()
    assert "model_tool_result" not in record.trace_event_types


@pytest.mark.parametrize("asynchronous", [False, True])
def test_model_interface_parity_s6_rejects_malformed_normalized_call_before_dispatch(
    asynchronous: bool, parity_io_blocker: None
) -> None:
    registry, invocations, results = _parity_registry()
    result, adapter, record, error = _run_parity_loop(
        [
            ModelResponse(
                content=None,
                tool_calls=(ModelToolCall("bad-1", "lookup_record", "not-json"),),
            )
        ],
        scenario="S6",
        asynchronous=asynchronous,
        registry=registry,
        invocations=invocations,
        results=results,
    )
    assert result is None
    assert isinstance(error, WorkflowExecutionError)
    assert "arguments must be JSON" in str(error)
    assert record.error_class == "WorkflowExecutionError"
    assert invocations == []
    assert len(adapter.requests) == 1
    assert "model_tool_loop_tool_call" not in record.trace_event_types
    assert "tool_started" not in record.trace_event_types


def test_execute_workflow_uses_model_facing_tool_output_in_context_and_trace() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-facet-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                    "outputs": {"state_key": "search_summary"},
                },
                {
                    "id": "final",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Use {lookup} and {search_summary}"},
                },
            ],
            "edges": [
                {"source": "lookup", "target": "final", "edge_kind": "sequential"}
            ],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [
            make_tool(
                "search_repo",
                output=ToolResult(
                    tool_id="search_repo",
                    success=True,
                    output={"raw": "full raw result"},
                    model_output={"summary": "safe summary"},
                    raw_output={"raw": "full raw result"},
                    log_preview="safe summary",
                    event_payload={"record_count": 1},
                    sensitive_fields=("raw_output",),
                ),
            )
        ]
    )
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    result = execute_workflow(
        workflow,
        prompt="Run",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "done"
    assert result.state.node_outputs["lookup"].model_output == {
        "summary": "safe summary"
    }
    assert result.state.node_outputs["search_summary"] == {"summary": "safe summary"}
    assert adapter.client.responses.calls[0]["input"][-1]["content"] == (
        "Use {'summary': 'safe summary'} and {'summary': 'safe summary'}"
    )
    tool_result_events = [
        event
        for event in result.state.trace_events
        if event.event_type == "tool_result"
    ]
    assert tool_result_events[0].payload == {
        "tool_id": "search_repo",
        "success": True,
        "error": None,
        "output": {"summary": "safe summary"},
        "raw_output": {"raw": "full raw result"},
        "log_preview": "safe summary",
        "event_payload": {"record_count": 1},
    }
    assert set(tool_result_events[0].sensitive_fields) == {"output", "raw_output"}


def test_execute_workflow_formats_top_level_tool_results_as_model_facing_output() -> (
    None
):
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-results-context-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                },
                {
                    "id": "final",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Use {tool_results}"},
                },
            ],
            "edges": [
                {"source": "lookup", "target": "final", "edge_kind": "sequential"}
            ],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [
            make_tool(
                "search_repo",
                output=ToolResult(
                    tool_id="search_repo",
                    success=True,
                    output={"raw": "large raw result"},
                    model_output={"summary": "compact summary"},
                ),
            )
        ]
    )
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    result = execute_workflow(
        workflow,
        prompt="Run",
        tool_registry=registry,
        model_adapter=adapter,
    )

    assert result.final_result == "done"
    assert result.state.tool_results["lookup"].output == {"raw": "large raw result"}
    assert adapter.client.responses.calls[0]["input"][-1]["content"] == (
        "Use {'lookup': {'summary': 'compact summary'}}"
    )


def test_execute_workflow_accepts_execution_context() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "context-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])
    context = WorkflowExecutionContext(workflow=workflow, model_adapter=adapter)

    result = execute_workflow(context, prompt="Hello")

    assert result.final_result == "done"
    assert adapter.client.responses.calls[0]["model"] == "gpt-test"


def test_execute_workflow_rejects_context_with_runtime_kwargs() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "context-conflict-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
    context = WorkflowExecutionContext(workflow=workflow)

    with pytest.raises(WorkflowExecutionError, match="cannot be combined"):
        execute_workflow(
            context,
            prompt="Hello",
            model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
        )


def test_execute_workflow_routes_llm_decision_branch() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "branch-agent",
            "entrypoint": "choose",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "choose",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Route"},
                },
                {
                    "id": "route",
                    "kind": "decision_step",
                    "decision_subtype": "llm_route",
                    "route_from": "choose",
                },
                {"id": "left", "kind": "llm_step", "prompt": {"user_template": "Left"}},
                {
                    "id": "right",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Right"},
                },
            ],
            "edges": [
                {"source": "choose", "target": "route", "edge_kind": "sequential"},
                {
                    "source": "route",
                    "target": "left",
                    "edge_kind": "branch",
                    "condition": "left",
                },
                {
                    "source": "route",
                    "target": "right",
                    "edge_kind": "branch",
                    "condition": "right",
                },
            ],
        }
    )
    adapter = make_adapter(
        [
            {"id": "route", "output_text": '{"route":"right"}'},
            {"id": "final", "output_text": "right result"},
        ]
    )

    result = execute_workflow(workflow, prompt="Pick", model_adapter=adapter)

    assert result.final_result == "right result"
    assert [execution.node_id for execution in result.state.executions] == [
        "choose",
        "route",
        "right",
    ]


def test_execute_workflow_rejects_malformed_route_output() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "route-malformed-agent",
            "entrypoint": "choose",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "choose",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Route"},
                },
                {
                    "id": "route",
                    "kind": "decision_step",
                    "decision_subtype": "llm_route",
                    "route_from": "choose",
                    "decision_contract": {
                        "allowed_paths": [{"id": "left"}, {"id": "right"}]
                    },
                },
            ],
            "edges": [
                {"source": "choose", "target": "route", "edge_kind": "sequential"},
            ],
        }
    )
    adapter = make_adapter([{"id": "route", "output_text": '{"status":"lost"}'}])

    with pytest.raises(WorkflowExecutionError, match="produced no route"):
        execute_workflow(workflow, prompt="Pick", model_adapter=adapter)


def test_execute_workflow_rejects_route_outside_allowed_paths() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "route-unknown-agent",
            "entrypoint": "choose",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "choose",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Route"},
                },
                {
                    "id": "route",
                    "kind": "decision_step",
                    "decision_subtype": "llm_route",
                    "route_from": "choose",
                    "decision_contract": {"allowed_paths": ["left", "right"]},
                },
            ],
            "edges": [
                {"source": "choose", "target": "route", "edge_kind": "sequential"},
            ],
        }
    )
    adapter = make_adapter([{"id": "route", "output_text": '{"route":"middle"}'}])

    with pytest.raises(WorkflowExecutionError, match="outside allowed paths"):
        execute_workflow(workflow, prompt="Pick", model_adapter=adapter)


def test_execute_workflow_validates_llm_output_contract_fields() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "contract-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {
                        "user_template": "{prompt}",
                        "output_schema_ref": "answer_contract",
                    },
                }
            ],
            "edges": [],
            "output_contracts": [
                {
                    "id": "answer_contract",
                    "required_fields": ["message", "confidence"],
                }
            ],
        }
    )
    adapter = make_adapter(
        [
            {
                "id": "resp",
                "output_text": '{"message":"done","confidence":"high"}',
            }
        ]
    )

    result = execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert result.final_result == '{"message":"done","confidence":"high"}'


def test_execute_workflow_rejects_missing_output_contract_fields() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "contract-missing-field-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "output_schema_ref": "answer_contract",
                }
            ],
            "edges": [],
            "output_contracts": [
                {
                    "id": "answer_contract",
                    "required_fields": ["message", "confidence"],
                }
            ],
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": '{"message":"done"}'}])

    with pytest.raises(WorkflowExecutionError, match="missing required field"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)


def test_execute_workflow_rejects_unstructured_contract_output() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "contract-unstructured-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "output_schema_ref": "answer_contract",
                }
            ],
            "edges": [],
            "output_contracts": [
                {
                    "id": "answer_contract",
                    "required_fields": ["message", "confidence"],
                }
            ],
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": "plain answer"}])

    with pytest.raises(WorkflowExecutionError, match="requires structured output"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)


def test_execute_workflow_rejects_unknown_output_contract_ref() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "contract-unknown-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "output_schema_ref": "missing_contract",
                }
            ],
            "edges": [],
            "output_contracts": [],
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": "plain answer"}])

    with pytest.raises(WorkflowExecutionError, match="unknown output contract"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)


def test_execute_workflow_records_token_usage_when_budget_enabled() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "token-budget-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "token_budget": {
                        "model": "gpt-4o-mini",
                        "max_prompt_tokens": 1000,
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
            "edges": [],
        }
    )

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
    )

    assert result.final_result == "done"
    assert len(result.state.token_usage) == 1
    assert result.state.token_usage[0].node_id == "answer"
    assert result.state.token_usage[0].estimated_prompt_tokens > 0
    assert result.state.token_usage[0].exceeded is False


def test_execute_workflow_applies_prompt_and_skill_overrides() -> None:
    """Runtime overrides alter one LLM node without mutating loaded artifacts."""

    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "behavior-override-agent",
        "entrypoint": "draft",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": {"model": "gpt-test"}},
        "nodes": [
            {
                "id": "draft",
                "kind": "llm_step",
                "prompt": {
                    "system": "Base system.",
                    "developer": "Base developer.",
                    "user_template": "Base {prompt}",
                },
                "skill_refs": ["base-skill"],
            }
        ],
        "edges": [],
        "skills": [
            {
                "id": "base-skill",
                "prompt_role": "developer",
                "instructions": "Use base style.",
            }
        ],
    }
    overrides = {
        "format_version": 1,
        "override_type": "dynamic_agent_runtime_overrides",
        "skills": {
            "added": [
                {
                    "id": "concise-writer",
                    "prompt_role": "developer",
                    "instructions": "Write tersely for {prompt}.",
                }
            ]
        },
        "nodes": {
            "draft": {
                "prompt": {
                    "prepend": {"system": "Prepended. "},
                    "append": {"developer": " Appended."},
                    "replace": {"user_template": "Override {prompt}"},
                },
                "skill_refs": {"add": ["concise-writer"]},
            }
        },
    }
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    final_result = run_agent_workflow(
        runtime_manifest=manifest,
        runtime_overrides=overrides,
        prompt="Hello",
        model_adapter=adapter,
    )

    assert final_result == "done"
    call = adapter.client.responses.calls[0]
    assert call["input"] == [
        {"role": "system", "content": "Prepended. Base system."},
        {"role": "developer", "content": "Base developer. Appended."},
        {"role": "developer", "content": "Use base style."},
        {"role": "developer", "content": "Write tersely for Hello."},
        {"role": "user", "content": "Override Hello"},
    ]
    assert manifest["nodes"][0]["prompt"]["user_template"] == "Base {prompt}"


def test_prepare_model_input_routes_to_adapter_model_by_required_features() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "feature-routing-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "default_model": "remote-basic",
                    "model_map": {
                        "remote-basic": ["tool_calling"],
                        "local-structured": ["tool_calling", "structured_output"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "model_requirements": {
                        "required_capabilities": ["structured_output"]
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")
    remote = make_named_adapter(
        [{"id": "unused", "output_text": "remote"}], models=["remote-basic"]
    )
    local = make_named_adapter(
        [{"id": "unused-2", "output_text": "local"}],
        models=["local-structured"],
        is_local=True,
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=[remote, local],
    )

    assert prepared_input.model == "local-structured"
    assert prepared_input.adapter is local


def test_execute_workflow_fails_when_no_adapter_matches_required_features() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "fallback-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "default_model": "local-structured",
                    "model_map": {
                        "remote-basic": ["tool_calling"],
                        "local-structured": ["structured_output"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "model_requirements": {
                        "required_capabilities": ["structured_output"]
                    },
                }
            ],
            "edges": [],
        }
    )
    remote = make_named_adapter(
        [{"id": "remote", "output_text": "remote-result"}],
        models=["remote-basic"],
    )

    with pytest.raises(WorkflowExecutionError, match="requires capabilities"):
        execute_workflow(workflow, prompt="Hello", model_adapter=[remote])

    assert remote.client.responses.calls == []


def test_execute_workflow_strict_fails_with_no_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-empty-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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

    def fail_default_adapter(*args, **kwargs):
        raise AssertionError("strict coverage must not create a default adapter")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor.AsyncOpenAIClientAdapter",
        fail_default_adapter,
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=None,
            model_adapter_coverage="strict",
        )


def test_execute_workflow_strict_fails_with_empty_adapter_list() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-empty-list-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=[],
            model_adapter_coverage="strict",
        )


def test_execute_workflow_strict_fails_with_nonmatching_adapter() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-nonmatching-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    adapter = make_named_adapter(
        [{"id": "unused", "output_text": "wrong"}],
        models=["other-model"],
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=[adapter],
            model_adapter_coverage="strict",
        )

    assert adapter.client.responses.calls == []


def test_execute_workflow_strict_with_mlx_adapter_prevents_default_openai(
    tmp_path: Path,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-mlx-nonmatching-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    backend = FakeMLXBackend()
    adapter = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "mlx-model",
        ),
        backend=backend,
        platform_system=lambda: "Darwin",
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=[adapter],
            model_adapter_coverage="strict",
        )

    assert backend.requests == []


def test_execute_workflow_strict_selects_apple_adapter_without_default_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Session:
        async def respond(self, prompt: str, **kwargs: object) -> str:
            return "apple answer"

    monkeypatch.setattr(
        "dynamic_agent_runner.apple_foundation_models.sys.platform", "darwin"
    )
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-apple-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {"default_model": "apple-system-language-model"}
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
    adapter = create_apple_foundation_model_async_adapter(
        AppleFoundationModelConfig(
            availability_checker=lambda: (True, None),
            session_factory=lambda _instructions: Session(),
        )
    )

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=[adapter],
        model_adapter_coverage="strict",
    )

    assert result.final_result == "apple answer"


def test_execute_workflow_strict_fails_when_required_features_are_unavailable() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-feature-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "default_model": "structured-model",
                    "model_map": {
                        "basic-model": ["tool_calling"],
                        "structured-model": ["structured_output"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "model_requirements": {
                        "required_capabilities": ["structured_output"]
                    },
                }
            ],
            "edges": [],
        }
    )
    adapter = make_named_adapter(
        [{"id": "unused", "output_text": "basic"}],
        models=["basic-model"],
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=[adapter],
            model_adapter_coverage="strict",
        )

    assert adapter.client.responses.calls == []


def test_execute_workflow_augmented_uses_default_openai_for_missing_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "augmented-default-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    supplied = make_named_adapter(
        [{"id": "unused", "output_text": "wrong"}],
        models=["other-model"],
    )
    seen_adapters: list[object] = []
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")
    monkeypatch.setenv("HOME", str(tmp_path))

    async def fake_acompletion(**kwargs: object) -> object:
        return kwargs

    monkeypatch.setitem(
        sys.modules, "litellm", SimpleNamespace(acompletion=fake_acompletion)
    )

    async def fake_create_model_response(adapter, request):
        seen_adapters.append(adapter)
        _client = adapter.client
        return ModelResponse(response_id="resp-default", content="default ok")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._create_model_response_async",
        fake_create_model_response,
    )

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=[supplied],
        model_adapter_coverage="augmented",
    )

    assert result.final_result == "default ok"
    assert supplied.client.responses.calls == []
    assert isinstance(seen_adapters[0], AsyncOpenAIClientAdapter)
    assert seen_adapters[0].models == ("gpt-test",)
    assert seen_adapters[0]._provider.config.api_key == "ambient-key"


def test_execute_workflow_augmented_default_openai_uses_chatgpt_codex_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "augmented-chatgpt-default-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    supplied = make_named_adapter(
        [{"id": "unused", "output_text": "wrong"}],
        models=["other-model"],
    )
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        '{"auth_mode": "chatgpt", "tokens": {"access_token": "secret-token"}}',
        encoding="utf-8",
    )
    seen_adapters: list[object] = []
    created_kwargs: list[dict[str, object]] = []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    class FakeOfficialAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(dict(kwargs))

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(AsyncOpenAI=FakeOfficialAsyncOpenAI),
    )

    async def fake_create_model_response(adapter, request):
        seen_adapters.append(adapter)
        _client = adapter.client
        return ModelResponse(response_id="resp-default", content="default ok")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._create_model_response_async",
        fake_create_model_response,
    )

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=[supplied],
        model_adapter_coverage="augmented",
    )

    assert result.final_result == "default ok"
    assert supplied.client.responses.calls == []
    assert isinstance(seen_adapters[0], AsyncOpenAIClientAdapter)
    assert created_kwargs == [
        {
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": "secret-token",
        }
    ]


def test_execute_workflow_augmented_with_mlx_adapter_uses_default_openai(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "augmented-mlx-default-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    backend = FakeMLXBackend("wrong")
    supplied = create_mlx_local_adapter(
        MLXLocalModelConfig(
            model_aliases=("mlx-local-chat",),
            model_path=tmp_path / "mlx-model",
        ),
        backend=backend,
        platform_system=lambda: "Darwin",
    )
    seen_adapters: list[object] = []

    async def fake_create_model_response(adapter, request):
        seen_adapters.append(adapter)
        return ModelResponse(response_id="resp-default", content="default ok")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._create_model_response_async",
        fake_create_model_response,
    )

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=[supplied],
        model_adapter_coverage="augmented",
    )

    assert result.final_result == "default ok"
    assert backend.requests == []
    assert isinstance(seen_adapters[0], AsyncOpenAIClientAdapter)
    assert seen_adapters[0].models == ("gpt-test",)


def test_execute_workflow_strict_with_llama_cpp_adapter_prevents_default_openai(
    tmp_path: Path,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "strict-llama-cpp-nonmatching-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")
    backend = FakeLlamaCppBackend()
    adapter = create_llama_cpp_local_adapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
        backend=backend,
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=[adapter],
            model_adapter_coverage="strict",
        )

    assert backend.calls == []


def test_execute_workflow_augmented_with_llama_cpp_adapter_uses_default_openai(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "augmented-llama-cpp-default-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    model_path = tmp_path / "model.gguf"
    model_path.write_text("fake gguf", encoding="utf-8")
    backend = FakeLlamaCppBackend("wrong")
    supplied = create_llama_cpp_local_adapter(
        LlamaCppLocalModelConfig(
            model_aliases=("llama-local-chat",),
            model_path=model_path,
        ),
        backend=backend,
    )
    seen_adapters: list[object] = []

    async def fake_create_model_response(adapter, request):
        seen_adapters.append(adapter)
        return ModelResponse(response_id="resp-default", content="default ok")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._create_model_response_async",
        fake_create_model_response,
    )

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=[supplied],
        model_adapter_coverage="augmented",
    )

    assert result.final_result == "default ok"
    assert backend.calls == []
    assert isinstance(seen_adapters[0], AsyncOpenAIClientAdapter)
    assert seen_adapters[0].models == ("gpt-test",)


def test_execute_workflow_omitted_coverage_defaults_to_augmented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "augmented-default-omitted-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    supplied = make_named_adapter(
        [{"id": "unused", "output_text": "wrong"}],
        models=["other-model"],
    )
    seen_adapters: list[object] = []

    async def fake_create_model_response(adapter, request):
        seen_adapters.append(adapter)
        return ModelResponse(response_id="resp-default", content="default ok")

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._create_model_response_async",
        fake_create_model_response,
    )

    result = execute_workflow(workflow, prompt="Hello", model_adapter=[supplied])

    assert result.final_result == "default ok"
    assert supplied.client.responses.calls == []
    assert isinstance(seen_adapters[0], AsyncOpenAIClientAdapter)


def test_execute_workflow_rejects_unknown_model_adapter_coverage() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "invalid-coverage-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage"):
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter_coverage="best_effort",
        )


def test_execution_context_applies_model_adapter_coverage() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "context-strict-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-test"}},
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
    context = WorkflowExecutionContext(
        workflow=workflow,
        model_adapter=[],
        model_adapter_coverage="strict",
    )

    with pytest.raises(WorkflowExecutionError, match="model_adapter_coverage.*strict"):
        execute_workflow(context, prompt="Hello")


def test_prepare_model_input_uses_openai_model_registry_for_native_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "registry-routing-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-4o-mini"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "model_requirements": {
                        "required_capabilities": ["structured_output"]
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")
    remote = make_named_adapter(
        [{"id": "unused", "output_text": "remote"}],
        models=["custom-remote"],
    )
    local = make_named_adapter(
        [{"id": "unused-2", "output_text": "local"}],
        models=["gpt-4o-mini"],
        is_local=True,
    )

    class FakeCapabilities:
        supports_structured = True
        supports_functions = True
        supports_vision = False
        supports_web_search = False
        context_window = 128000
        input_modalities = ["text"]

    monkeypatch.setattr(
        "dynamic_agent_runner.executor._get_openai_model_capabilities",
        lambda model_name: FakeCapabilities() if model_name == "gpt-4o-mini" else None,
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=[remote, local],
    )

    assert prepared_input.model == "gpt-4o-mini"
    assert prepared_input.adapter is local


def test_prepare_model_input_does_not_route_by_local_only_metadata() -> None:
    from dynamic_agent_runner.local_models import (
        LocalOpenAIEndpointConfig,
        create_local_openai_adapter,
    )

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "local-only-metadata-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "default_model": "qwen-local",
                    "model_map": {
                        "qwen-local": ["structured_output"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "Answer {prompt}"},
                    "model_requirements": {
                        "operational_preferences": {"data_boundary": "local_only"},
                        "required_capabilities": ["structured_output"],
                    },
                }
            ],
            "edges": [],
        }
    )
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")
    remote = make_named_adapter(
        [{"id": "unused", "output_text": "remote"}],
        models=["qwen-local"],
    )
    local = create_local_openai_adapter(
        LocalOpenAIEndpointConfig(
            base_url="http://localhost:11434/v1",
            api_key="local-key",
            model_aliases=["qwen-local", "chat-default"],
            provider_name="llama.cpp",
            expected_model_id="Qwen/Qwen3-4B-Instruct-2507",
        )
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=[remote, local],
    )

    assert prepared_input.model == "qwen-local"
    assert prepared_input.adapter is remote
    assert local.is_local is True
    assert local.models == ("qwen-local", "chat-default")


def test_prepare_model_input_uses_default_openai_adapter_without_capability_routing() -> (
    None
):
    """Without provided adapters or model-map requirements, the default OpenAI adapter is used."""

    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "default-openai-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"default_model": "gpt-4o-mini"}},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(),
    )

    assert prepared_input.model == "gpt-4o-mini"
    assert isinstance(prepared_input.adapter, AsyncOpenAIClientAdapter)
    assert prepared_input.adapter.models == ("gpt-4o-mini",)


def test_prepare_model_input_uses_lowest_supported_model_when_workflow_omits_model() -> (
    None
):
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "missing-model-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")
    models = FakeModels(
        {
            "data": [
                {"id": "gpt-5.5"},
                {"id": "gpt-5.4"},
                {"id": "codex-auto-review"},
            ]
        }
    )
    adapter = OpenAIClientAdapter(FakeClient([{"id": "unused"}], models=models))

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=[adapter],
    )

    assert prepared_input.model == "gpt-5.4"
    assert prepared_input.adapter is adapter
    assert models.calls == [{}]


def test_prepare_model_input_auto_creates_default_adapter_when_workflow_omits_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "missing-model-default-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
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
    plan = prepare_execution_plan(workflow)
    state = WorkflowExecutionState(prompt="Hi")

    class FakeDefaultOpenAIClientAdapter:
        def default_model(self) -> str:
            return "gpt-5.4"

    monkeypatch.setattr(
        "dynamic_agent_runner.executor.OpenAIClientAdapter",
        FakeDefaultOpenAIClientAdapter,
    )

    prepared_input = prepare_model_input(
        plan.nodes_by_id["answer"],
        plan,
        state,
        model_adapters=(),
    )

    assert prepared_input.model == "gpt-5.4"
    assert isinstance(prepared_input.adapter, AsyncOpenAIClientAdapter)
    assert prepared_input.adapter.models == ("gpt-5.4",)


def test_execute_workflow_applies_skill_only_remove_and_node_isolation() -> None:
    """Per-node skill binding overrides stay scoped to their target node."""

    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "skill-scope-agent",
        "entrypoint": "first",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": {"model": "gpt-test"}},
        "nodes": [
            {
                "id": "first",
                "kind": "llm_step",
                "prompt": {"user_template": "First {prompt}"},
                "skill_refs": ["base", "extra"],
            },
            {
                "id": "second",
                "kind": "llm_step",
                "prompt": {"user_template": "Second {first}"},
                "skill_refs": ["extra"],
            },
        ],
        "edges": [{"source": "first", "target": "second", "edge_kind": "sequential"}],
        "skills": [
            {"id": "base", "prompt_role": "developer", "instructions": "Base."},
            {"id": "extra", "prompt_role": "developer", "instructions": "Extra."},
            {"id": "only", "prompt_role": "developer", "instructions": "Only."},
        ],
    }
    overrides = {
        "format_version": 1,
        "override_type": "dynamic_agent_runtime_overrides",
        "nodes": {"first": {"skill_refs": {"only": ["only"], "remove": ["base"]}}},
    }
    adapter = make_adapter(
        [
            {"id": "first", "output_text": "first output"},
            {"id": "second", "output_text": "second output"},
        ]
    )

    result = run_agent_workflow(
        runtime_manifest=manifest,
        runtime_overrides=overrides,
        prompt="Hello",
        model_adapter=adapter,
    )

    assert result == "second output"
    first_messages = adapter.client.responses.calls[0]["input"]
    second_messages = adapter.client.responses.calls[1]["input"]
    assert {message["content"] for message in first_messages} == {
        "Only.",
        "First Hello",
    }
    assert {message["content"] for message in second_messages} == {
        "Extra.",
        "Second first output",
    }


def test_execute_workflow_uses_overridden_output_schema_ref() -> None:
    """Prompt replacement of output_schema_ref participates in validation."""

    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "schema-override-agent",
        "entrypoint": "answer",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": {"model": "gpt-test"}},
        "nodes": [
            {
                "id": "answer",
                "kind": "llm_step",
                "prompt": {"user_template": "Answer {prompt}"},
            }
        ],
        "edges": [],
        "output_contracts": [
            {"id": "strict_answer", "required_fields": ["message", "confidence"]}
        ],
    }
    overrides = {
        "format_version": 1,
        "override_type": "dynamic_agent_runtime_overrides",
        "nodes": {
            "answer": {"prompt": {"replace": {"output_schema_ref": "strict_answer"}}}
        },
    }
    adapter = make_adapter([{"id": "resp", "output_text": '{"message":"done"}'}])

    with pytest.raises(WorkflowExecutionError, match="missing required field"):
        run_agent_workflow(
            runtime_manifest=manifest,
            runtime_overrides=overrides,
            prompt="Hello",
            model_adapter=adapter,
        )


def test_execute_workflow_fails_when_prompt_exceeds_token_budget() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "token-budget-failure-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                    "token_budget": {
                        "model": "gpt-4o-mini",
                        "max_prompt_tokens": 1,
                    },
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    with pytest.raises(WorkflowExecutionError, match="exceeds budget"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert adapter.client.responses.calls == []


def test_execute_workflow_skips_token_usage_when_budget_disabled() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "token-budget-disabled-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
            "edges": [],
        }
    )

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
    )

    assert result.state.token_usage == []


def test_execute_workflow_errors_on_tool_failure_by_default() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-failure-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {},
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry([make_tool("search_repo")])

    with pytest.raises(WorkflowExecutionError, match="missing required input"):
        execute_workflow(workflow, prompt="Run", tool_registry=registry)


def test_execute_workflow_pauses_approval_required_tool_before_invocation() -> None:
    calls: list[object] = []
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "approval-pause-agent",
            "entrypoint": "write",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "write",
                    "kind": "tool_use_step",
                    "tool_id": "workspace_write",
                    "inputs": {"path": "notes.txt", "content": "hello"},
                }
            ],
            "edges": [],
            "tools": [
                {
                    "id": "workspace_write",
                    "approval_required": "yes",
                    "side_effect": "write",
                    "sandbox": "workspace",
                }
            ],
        }
    )
    tool = RegisteredTool(
        ToolDefinition.from_mapping(
            {
                "id": "workspace_write",
                "approval_required": "yes",
                "side_effect": "write",
                "sandbox": "workspace",
            }
        ),
        lambda args: calls.append(args) or {"ok": True},
    )
    registry = InMemoryToolRegistry([tool])

    result = execute_workflow(workflow, prompt="Run", tool_registry=registry)

    assert isinstance(result, WorkflowInterruptedResult)
    assert calls == []
    assert result.final_result is None
    assert result.interruption.run_id == result.state.run_id
    assert result.interruption.workflow_id == "approval-pause-agent"
    assert result.interruption.node_id == "write"
    assert result.interruption.tool_id == "workspace_write"
    assert result.interruption.arguments == {"path": "notes.txt", "content": "hello"}
    assert result.interruption.policy["approval_required"] == "yes"
    assert result.state.tool_results == {}
    assert result.state.executions == []


def input_guardrail_workflow() -> LoadedAgentWorkflow:
    return workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "input-guardrail-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "extensions": {
                "guardrails": {
                    "declarations": [
                        {
                            "id": "no_secrets",
                            "phase": "input",
                            "behavior_on_tripwire": "abort",
                        }
                    ]
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


def test_execute_workflow_fails_closed_for_missing_input_guardrail_adapter() -> None:
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])

    with pytest.raises(GuardrailExecutionError, match="no_secrets"):
        execute_workflow(
            input_guardrail_workflow(),
            prompt="hello",
            model_adapter=adapter,
        )

    assert adapter.client.responses.calls == []


def test_execute_workflow_aborts_on_input_guardrail_tripwire() -> None:
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])
    guardrails = InMemoryGuardrailRegistry(
        {
            "no_secrets": lambda _subject: GuardrailResult(
                guardrail_id="no_secrets",
                decision=GuardrailDecision.ABORT,
                reason_code="secret_detected",
                message="Secret content is not allowed.",
            )
        }
    )

    with pytest.raises(GuardrailExecutionError, match="secret_detected"):
        execute_workflow(
            input_guardrail_workflow(),
            prompt="secret",
            model_adapter=adapter,
            guardrail_registry=guardrails,
        )

    assert adapter.client.responses.calls == []


def tool_input_guardrail_workflow(
    *,
    approval_required: bool = False,
    declarations: list[dict[str, object]] | None = None,
) -> LoadedAgentWorkflow:
    tool: dict[str, object] = {"id": "search_repo"}
    if approval_required:
        tool["approval_required"] = "yes"
    return workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-input-guardrail-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "extensions": {
                "guardrails": {
                    "declarations": declarations
                    or [{"id": "safe_tool_args", "phase": "tool_input"}]
                }
            },
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": {"terms": ["agents"]}},
                }
            ],
            "edges": [],
            "tools": [tool],
        }
    )


def test_execute_workflow_runs_tool_input_guardrail_after_validation() -> None:
    observed_subjects: list[object] = []
    observed_handler_arguments: list[object] = []
    invocation_order: list[str] = []

    def guardrail(subject: object) -> GuardrailResult:
        observed_subjects.append(deepcopy(subject))
        assert isinstance(subject, dict)
        subject["arguments"]["query"]["terms"].append("mutated")
        return GuardrailResult(guardrail_id="safe_tool_args", phase="tool_input")

    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping({"id": "search_repo"}),
                lambda arguments: (
                    observed_handler_arguments.append(arguments)
                    or invocation_order.append("handler")
                    or {"ok": True}
                ),
            )
        ]
    )

    result = execute_workflow(
        tool_input_guardrail_workflow(),
        prompt="Run",
        tool_registry=registry,
        guardrail_registry=InMemoryGuardrailRegistry({"safe_tool_args": guardrail}),
        lifecycle_hooks=WorkflowLifecycleHooks(
            before_tool=lambda _context: invocation_order.append("before_tool"),
            after_tool=lambda _context: invocation_order.append("after_tool"),
        ),
        run_id="direct-tool-run",
    )

    assert observed_subjects == [
        {
            "phase": "tool_input",
            "tool_id": "search_repo",
            "node_id": "lookup",
            "arguments": {"query": {"terms": ["agents"]}},
        }
    ]
    assert observed_handler_arguments == [{"query": {"terms": ["agents"]}}]
    assert invocation_order == ["before_tool", "handler", "after_tool"]
    assert result.final_result == {"ok": True}
    assert result.state.tool_results["lookup"].model_facing_output == {"ok": True}
    assert result.state.node_outputs["lookup"].model_facing_output == {"ok": True}
    assert [event.event_type for event in result.state.trace_events] == [
        "workflow_started",
        "node_started",
        "guardrail_started",
        "guardrail_passed",
        "tool_started",
        "tool_invocation",
        "retry_recorded",
        "tool_result",
        "tool_finished",
        "node_completed",
        "workflow_completed",
    ]
    direct_tool_events = [
        event
        for event in result.state.trace_events
        if event.event_type
        in {"tool_started", "tool_invocation", "tool_result", "tool_finished"}
    ]
    assert {event.run_id for event in direct_tool_events} == {"direct-tool-run"}
    assert all("tool_call_id" not in event.payload for event in direct_tool_events)


def test_execute_workflow_aborts_tool_input_guardrail_before_approval_or_tool_hooks() -> (
    None
):
    calls: list[object] = []
    hooks: list[str] = []
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {"id": "search_repo", "approval_required": "yes"}
                ),
                lambda arguments: calls.append(arguments) or {"ok": True},
            )
        ]
    )
    guardrails = InMemoryGuardrailRegistry(
        {
            "safe_tool_args": lambda _subject: GuardrailResult(
                guardrail_id="safe_tool_args",
                phase="tool_input",
                decision=GuardrailDecision.ABORT,
                reason_code="unsafe_arguments",
            )
        }
    )

    with pytest.raises(GuardrailExecutionError, match="unsafe_arguments"):
        execute_workflow(
            tool_input_guardrail_workflow(approval_required=True),
            prompt="Run",
            tool_registry=registry,
            guardrail_registry=guardrails,
            lifecycle_hooks=WorkflowLifecycleHooks(
                before_tool=lambda _context: hooks.append("before_tool"),
                after_tool=lambda _context: hooks.append("after_tool"),
            ),
        )

    assert calls == []
    assert hooks == []


def test_execute_workflow_fails_closed_for_missing_tool_input_guardrail_adapter() -> (
    None
):
    calls: list[object] = []
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping({"id": "search_repo"}),
                lambda arguments: calls.append(arguments) or {"ok": True},
            )
        ]
    )

    with pytest.raises(GuardrailExecutionError, match="missing_adapter"):
        execute_workflow(
            tool_input_guardrail_workflow(),
            prompt="Run",
            tool_registry=registry,
        )

    assert calls == []


def test_execute_workflow_runs_tool_input_guardrails_in_manifest_order() -> None:
    observed: list[str] = []
    calls: list[object] = []
    guardrails = InMemoryGuardrailRegistry(
        {
            "first": lambda _subject: (
                observed.append("first")
                or GuardrailResult(guardrail_id="first", phase="tool_input")
            ),
            "second": lambda _subject: (
                observed.append("second")
                or GuardrailResult(
                    guardrail_id="second",
                    phase="tool_input",
                    decision=GuardrailDecision.ABORT,
                    reason_code="second_blocks",
                )
            ),
        }
    )

    with pytest.raises(GuardrailExecutionError, match="second_blocks"):
        execute_workflow(
            tool_input_guardrail_workflow(
                declarations=[
                    {"id": "first", "phase": "tool_input"},
                    {"id": "second", "phase": "tool_input"},
                ]
            ),
            prompt="Run",
            tool_registry=InMemoryToolRegistry(
                [
                    RegisteredTool(
                        ToolDefinition.from_mapping({"id": "search_repo"}),
                        lambda arguments: calls.append(arguments) or {"ok": True},
                    )
                ]
            ),
            guardrail_registry=guardrails,
        )

    assert observed == ["first", "second"]
    assert calls == []


def test_execute_workflow_fails_closed_for_invalid_tool_input_guardrail_result() -> (
    None
):
    secret = "do-not-trace-this"
    registry = InMemoryToolRegistry([make_tool("search_repo", output={"ok": True})])
    guardrails = InMemoryGuardrailRegistry(
        {"safe_tool_args": lambda _subject: object()}  # type: ignore[dict-item]
    )
    sink = InMemoryTraceSink()

    with pytest.raises(GuardrailExecutionError, match="malformed_result"):
        execute_workflow(
            tool_input_guardrail_workflow(),
            prompt=secret,
            tool_registry=registry,
            guardrail_registry=guardrails,
            trace_sink=sink,
        )

    error_event = next(
        event for event in sink.events if event.event_type == "guardrail_errored"
    )
    assert error_event.payload == {
        "guardrail_id": "safe_tool_args",
        "phase": "tool_input",
        "tool_id": "search_repo",
        "node_id": "lookup",
        "reason": "malformed_result",
    }
    assert secret not in repr(error_event.payload)


def test_execute_workflow_aborts_guarded_model_tool_call_before_dispatch() -> None:
    observed_subjects: list[object] = []
    tool_calls: list[object] = []
    workflow = loop_tool_workflow(
        guardrails=[{"id": "safe_tool_args", "phase": "tool_input"}]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            }
        ]
    )
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping({"id": "search_repo"}),
                lambda arguments: tool_calls.append(arguments) or {"ok": True},
            )
        ]
    )
    guardrails = InMemoryGuardrailRegistry(
        {
            "safe_tool_args": lambda subject: (
                observed_subjects.append(subject)
                or GuardrailResult(
                    guardrail_id="safe_tool_args",
                    phase="tool_input",
                    decision=GuardrailDecision.ABORT,
                    reason_code="unsafe_arguments",
                )
            )
        }
    )

    with pytest.raises(GuardrailExecutionError, match="unsafe_arguments"):
        execute_workflow(
            workflow,
            prompt="How?",
            tool_registry=registry,
            model_adapter=adapter,
            guardrail_registry=guardrails,
        )

    assert observed_subjects == [
        {
            "phase": "tool_input",
            "tool_id": "search_repo",
            "node_id": "analyze",
            "tool_call_id": "call_1",
            "arguments": {"query": "agents"},
        }
    ]
    assert tool_calls == []
    assert len(adapter.client.responses.calls) == 1


def test_execute_workflow_runs_passing_guardrail_for_model_tool_call() -> None:
    subjects: list[object] = []
    workflow = loop_tool_workflow(
        guardrails=[{"id": "safe_tool_args", "phase": "tool_input"}]
    )
    adapter = make_adapter(
        [
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_repo",
                        "arguments": '{"query":"agents"}',
                    }
                ],
            },
            {"id": "resp_2", "output_text": "final answer"},
        ]
    )
    result = execute_workflow(
        workflow,
        prompt="How?",
        tool_registry=InMemoryToolRegistry(
            [make_tool("search_repo", output={"answer": "42"})]
        ),
        model_adapter=adapter,
        guardrail_registry=InMemoryGuardrailRegistry(
            {
                "safe_tool_args": lambda subject: (
                    subjects.append(subject)
                    or GuardrailResult(
                        guardrail_id="safe_tool_args", phase="tool_input"
                    )
                )
            }
        ),
    )

    assert result.final_result == "final answer"
    assert subjects[0]["tool_call_id"] == "call_1"
    assert result.state.tool_results["analyze.call_1"].success


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (
            lambda _subject: GuardrailResult(
                guardrail_id="wrong_id", phase="tool_input"
            ),
            "result_identity_mismatch",
        ),
        (
            lambda _subject: GuardrailResult(
                guardrail_id="safe_tool_args", phase="input"
            ),
            "result_phase_mismatch",
        ),
        (
            lambda _subject: (_ for _ in ()).throw(RuntimeError("adapter failed")),
            "handler_error",
        ),
    ],
)
def test_execute_workflow_fails_closed_for_tool_input_guardrail_errors(
    handler: object,
    reason: str,
) -> None:
    sink = InMemoryTraceSink()
    with pytest.raises(GuardrailExecutionError, match=reason):
        execute_workflow(
            tool_input_guardrail_workflow(),
            prompt="Run",
            tool_registry=InMemoryToolRegistry([make_tool("search_repo")]),
            guardrail_registry=InMemoryGuardrailRegistry(
                {"safe_tool_args": handler}  # type: ignore[dict-item]
            ),
            trace_sink=sink,
        )

    guardrail_events = [
        event
        for event in sink.events
        if event.event_type
        in {"guardrail_started", "guardrail_errored", "workflow_error"}
    ]
    assert [event.event_type for event in guardrail_events] == [
        "guardrail_started",
        "guardrail_errored",
        "workflow_error",
    ]
    assert guardrail_events[1].payload["reason"] == reason


def test_run_agent_workflow_returns_final_result() -> None:
    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "api-agent",
        "entrypoint": "answer",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": {"model": "gpt-test"}},
        "nodes": [
            {
                "id": "answer",
                "kind": "llm_step",
                "prompt": {"user_template": "{prompt}"},
            }
        ],
        "edges": [],
    }

    final_result = run_agent_workflow(
        runtime_manifest=manifest,
        prompt="Hello",
        model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
    )

    assert final_result == "done"


def approval_required_tool_manifest() -> dict[str, object]:
    return {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "approval-api-agent",
        "entrypoint": "write",
        "packaging": {"mode": "hybrid_bundle"},
        "nodes": [
            {
                "id": "write",
                "kind": "tool_use_step",
                "tool_id": "workspace_write",
                "inputs": {"path": "notes.txt", "content": "hello"},
            }
        ],
        "edges": [],
        "tools": [{"id": "workspace_write", "approval_required": "yes"}],
    }


def approval_required_tool_registry() -> InMemoryToolRegistry:
    return InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {"id": "workspace_write", "approval_required": "yes"}
                ),
                lambda _args: {"ok": True},
            )
        ]
    )


def test_run_agent_workflow_errors_when_workflow_is_interrupted() -> None:
    with pytest.raises(WorkflowExecutionError, match="interrupted for approval"):
        run_agent_workflow(
            prompt="Run",
            runtime_manifest=approval_required_tool_manifest(),
            tool_registry=approval_required_tool_registry(),
        )


async def _run_agent_workflow_async_errors_when_workflow_is_interrupted() -> None:
    with pytest.raises(WorkflowExecutionError, match="interrupted for approval"):
        await run_agent_workflow_async(
            prompt="Run",
            runtime_manifest=approval_required_tool_manifest(),
            tool_registry=approval_required_tool_registry(),
        )


def test_run_agent_workflow_async_errors_when_workflow_is_interrupted() -> None:
    asyncio.run(_run_agent_workflow_async_errors_when_workflow_is_interrupted())


def test_run_agent_workflow_async_returns_final_result() -> None:
    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "async-api-agent",
        "entrypoint": "answer",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": {"model": "gpt-test"}},
        "nodes": [
            {
                "id": "answer",
                "kind": "llm_step",
                "prompt": {"user_template": "{prompt}"},
            }
        ],
        "edges": [],
    }

    final_result = asyncio.run(
        run_agent_workflow_async(
            runtime_manifest=manifest,
            prompt="Hello",
            model_adapter=make_async_adapter(
                [{"id": "resp", "output_text": "async done"}]
            ),
        )
    )

    assert final_result == "async done"


def test_execute_workflow_sync_wrapper_accepts_async_model_adapter() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "sync-wrapper-async-adapter-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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

    result = execute_workflow(
        workflow,
        prompt="Hello",
        model_adapter=make_async_adapter([{"id": "resp", "output_text": "done"}]),
    )

    assert result.final_result == "done"


def test_execute_workflow_sync_wrapper_rejects_running_event_loop() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "sync-wrapper-loop-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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

    async def call_sync_wrapper() -> None:
        execute_workflow(
            workflow,
            prompt="Hello",
            model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
        )

    with pytest.raises(WorkflowExecutionError, match="event loop"):
        asyncio.run(call_sync_wrapper())


def test_run_agent_workflow_sync_wrapper_rejects_running_event_loop() -> None:
    manifest = {
        "format_version": 1,
        "package_type": "dynamic_agent_design",
        "package_id": "api-sync-wrapper-loop-agent",
        "entrypoint": "answer",
        "packaging": {"mode": "hybrid_bundle"},
        "runtime": {"execution_policy": {"model": "gpt-test"}},
        "nodes": [
            {
                "id": "answer",
                "kind": "llm_step",
                "prompt": {"user_template": "{prompt}"},
            }
        ],
        "edges": [],
    }

    async def call_sync_wrapper() -> None:
        run_agent_workflow(
            runtime_manifest=manifest,
            prompt="Hello",
            model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
        )

    with pytest.raises(WorkflowExecutionError, match="event loop"):
        asyncio.run(call_sync_wrapper())


def test_run_agent_workflow_accepts_execution_context() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "api-context-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
    adapter = make_adapter([{"id": "resp", "output_text": "done"}])
    context = WorkflowExecutionContext(workflow=workflow, model_adapter=adapter)

    final_result = run_agent_workflow(prompt="Hello", execution_context=context)

    assert final_result == "done"


def test_run_agent_workflow_rejects_context_with_artifact_kwargs() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "api-context-conflict-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
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
    context = WorkflowExecutionContext(workflow=workflow)

    with pytest.raises(TypeError, match="cannot be combined"):
        run_agent_workflow(
            prompt="Hello",
            execution_context=context,
            model_adapter=make_adapter([{"id": "resp", "output_text": "done"}]),
        )


def test_execute_workflow_fails_on_step_limit() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "loop-agent",
            "entrypoint": "one",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {"id": "one", "kind": "llm_step", "prompt": {"user_template": "Loop"}}
            ],
            "edges": [
                {"source": "one", "target": "one", "edge_kind": "sequential"},
            ],
        }
    )
    adapter = make_adapter([{"id": "resp", "output_text": "again"}] * 3)

    with pytest.raises(WorkflowExecutionError, match="exceeded maximum step count"):
        execute_workflow(workflow, prompt="Loop", model_adapter=adapter, max_steps=2)


def test_execute_workflow_retries_retryable_model_failures() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "model-retry-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "model_retry_policy": {
                        "max_attempts": 3,
                        "retry_on": ["model_error"],
                    },
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter(
        [RuntimeError("temporary outage"), {"id": "resp", "output_text": "done"}]
    )

    result = execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert result.final_result == "done"
    assert len(adapter.client.responses.calls) == 2
    assert result.state.retry_records[-1].attempts == 2
    assert result.state.retry_records[-1].outcome == "success"


def test_execute_workflow_does_not_retry_model_by_default() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "model-no-retry-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {"execution_policy": {"model": "gpt-test"}},
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter(
        [RuntimeError("temporary outage"), {"id": "resp", "output_text": "done"}]
    )

    with pytest.raises(ModelExecutionError, match="temporary outage"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert len(adapter.client.responses.calls) == 1


def test_execute_workflow_does_not_retry_non_retryable_model_failures() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "model-non-retry-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "retry_policy": {"max_attempts": 3, "retry_on": ["tool_failure"]},
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter(
        [RuntimeError("non-retryable outage"), {"id": "resp", "output_text": "done"}]
    )

    with pytest.raises(ModelExecutionError, match="non-retryable outage"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert len(adapter.client.responses.calls) == 1


def test_execute_workflow_records_model_retry_exhaustion() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "model-retry-exhaustion-agent",
            "entrypoint": "answer",
            "packaging": {"mode": "hybrid_bundle"},
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "retry_policy": {"max_attempts": 2, "retry_on": ["exception"]},
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
            "edges": [],
        }
    )
    adapter = make_adapter([RuntimeError("outage 1"), RuntimeError("outage 2")])

    with pytest.raises(ModelExecutionError, match="outage 2"):
        execute_workflow(workflow, prompt="Hello", model_adapter=adapter)

    assert len(adapter.client.responses.calls) == 2


def test_execute_workflow_retries_tool_failures_from_registry_metadata() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-retry-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [
            make_flaky_tool(
                "search_repo",
                [RuntimeError("temporary tool failure"), {"answer": "42"}],
                raw={"retry_policy": {"max_attempts": 3, "retry_on": ["failure"]}},
            )
        ]
    )

    result = execute_workflow(workflow, prompt="Run", tool_registry=registry)

    assert result.state.tool_results["lookup"].output == {"answer": "42"}
    assert result.state.retry_records[-1].operation == "tool"
    assert result.state.retry_records[-1].attempts == 2
    assert result.state.retry_records[-1].outcome == "success"


def test_execute_workflow_exhausts_retryable_tool_failures() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-retry-exhaustion-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                    "retry_policy": {"max_attempts": 2, "retry_on": ["tool_failure"]},
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [
            make_flaky_tool(
                "search_repo",
                [RuntimeError("temporary 1"), RuntimeError("temporary 2")],
            )
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="temporary 2"):
        execute_workflow(workflow, prompt="Run", tool_registry=registry)


def test_execute_workflow_does_not_retry_non_retryable_tool_failures() -> None:
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "tool-non-retry-agent",
            "entrypoint": "lookup",
            "packaging": {"mode": "hybrid_bundle"},
            "nodes": [
                {
                    "id": "lookup",
                    "kind": "tool_use_step",
                    "tool_id": "search_repo",
                    "inputs": {"query": "agents"},
                    "retry_policy": {"max_attempts": 3, "retry_on": ["exception"]},
                }
            ],
            "edges": [],
            "tools": [{"id": "search_repo"}],
        }
    )
    registry = InMemoryToolRegistry(
        [
            make_flaky_tool(
                "search_repo",
                [RuntimeError("non-retryable tool failure"), {"answer": "42"}],
            )
        ]
    )

    with pytest.raises(WorkflowExecutionError, match="non-retryable tool failure"):
        execute_workflow(workflow, prompt="Run", tool_registry=registry)
