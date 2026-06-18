"""Tests for persistent agent session state and stores."""

from __future__ import annotations

import asyncio

import pytest

from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.errors import (
    AgentSessionError,
    GuardrailExecutionError,
    ModelExecutionError,
)
from dynamic_agent_runner.executor import WorkflowInterruptedResult
from dynamic_agent_runner.guardrails import (
    GuardrailDecision,
    GuardrailResult,
    InMemoryGuardrailRegistry,
)
from dynamic_agent_runner.models import LoadedAgentWorkflow, ToolDefinition
from dynamic_agent_runner.openai_client import OpenAIClientAdapter, OpenAIMessage
from dynamic_agent_runner.registry import InMemoryToolRegistry, RegisteredTool
from dynamic_agent_runner.sessions import (
    AGENT_SESSION_STATE_SCHEMA_VERSION,
    AgentSession,
    AgentSessionState,
    InMemorySessionStore,
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
    def __init__(self, responses: list[object]):
        self.responses = FakeResponses(responses)


def make_adapter(responses: list[object]) -> OpenAIClientAdapter:
    return OpenAIClientAdapter(FakeClient(responses))


def workflow_from(data: dict[str, object]) -> LoadedAgentWorkflow:
    return LoadedAgentWorkflow(runtime_manifest=load_runtime_manifest(data))


def make_execution_context(
    package_id: str = "session-agent",
    *,
    model_adapter: OpenAIClientAdapter | None = None,
    guardrail_registry: InMemoryGuardrailRegistry | None = None,
) -> WorkflowExecutionContext:
    manifest = load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": package_id,
            "name": "Session Agent",
            "entrypoint": "answer",
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
        }
    )
    return WorkflowExecutionContext(
        workflow=LoadedAgentWorkflow(manifest),
        model_adapter=model_adapter,
        guardrail_registry=guardrail_registry,
    )


def make_policy_execution_context(
    *,
    history: str,
    model_adapter: OpenAIClientAdapter,
    user_template: str = "Use {prepared_context} to answer {prompt}",
) -> WorkflowExecutionContext:
    async_session: dict[str, object] = {
        "mode": "create_or_resume",
        "persist": "in_memory",
        "history": history,
        "session_id_state_key": "session_id",
    }
    if history != "none":
        async_session["session_messages_state_key"] = "session_messages"
    manifest = load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": f"session-{history}-agent",
            "name": "Session Policy Agent",
            "entrypoint": "answer",
            "runtime": {
                "execution_policy": {
                    "model": "gpt-test",
                    "async_session": async_session,
                }
            },
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": user_template},
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
        }
    )
    return WorkflowExecutionContext(
        workflow=LoadedAgentWorkflow(manifest),
        model_adapter=model_adapter,
    )


def test_create_session_with_explicit_id_returns_empty_state() -> None:
    store = InMemorySessionStore()

    session = AgentSession.create(
        execution_context=make_execution_context(),
        session_store=store,
        session_id="thread-123",
    )

    state = session.current_state()
    assert state.session_id == "thread-123"
    assert state.schema_version == AGENT_SESSION_STATE_SCHEMA_VERSION
    assert state.messages == ()
    assert state.turn_count == 0
    assert state.last_run_id is None
    assert state.last_result is None
    assert store.load("thread-123") == state


def test_create_session_generates_session_id_when_absent() -> None:
    session = AgentSession.create(
        execution_context=make_execution_context(),
        session_store=InMemorySessionStore(),
    )

    assert session.session_id
    assert session.current_state().session_id == session.session_id


def test_store_returns_copy_safe_session_state() -> None:
    store = InMemorySessionStore()
    state = AgentSessionState(
        session_id="thread-123",
        workflow_identity="session-agent:answer",
        messages=(OpenAIMessage(role="user", content="hello"),),
        turn_count=1,
        metadata={"nested": {"value": "original"}},
    )
    store.save(state)

    loaded = store.load("thread-123")
    mapping = loaded.to_mapping()
    mapping["metadata"]["nested"]["value"] = "changed"
    mapping["messages"].append({"role": "assistant", "content": "mutated"})

    reloaded = store.load("thread-123")
    assert reloaded.metadata == {"nested": {"value": "original"}}
    assert reloaded.messages == (OpenAIMessage(role="user", content="hello"),)


def test_store_isolates_session_ids() -> None:
    store = InMemorySessionStore()
    first = AgentSessionState(
        session_id="first",
        workflow_identity="session-agent:answer",
        metadata={"owner": "first"},
    )
    second = AgentSessionState(
        session_id="second",
        workflow_identity="session-agent:answer",
        metadata={"owner": "second"},
    )

    store.save(first)
    store.save(second)

    assert store.load("first").metadata == {"owner": "first"}
    assert store.load("second").metadata == {"owner": "second"}


def test_store_fails_clearly_for_missing_session() -> None:
    store = InMemorySessionStore()

    with pytest.raises(AgentSessionError, match="session 'missing' was not found"):
        store.load("missing")


def test_session_state_rejects_malformed_snapshots() -> None:
    with pytest.raises(AgentSessionError, match="session snapshot requires session_id"):
        AgentSessionState.from_mapping({"schema_version": 1})

    with pytest.raises(AgentSessionError, match="unsupported session snapshot schema"):
        AgentSessionState.from_mapping(
            {
                "schema_version": AGENT_SESSION_STATE_SCHEMA_VERSION + 1,
                "session_id": "thread-123",
                "workflow_identity": "session-agent:answer",
                "messages": [],
            }
        )


async def _accept_passes_prior_messages_to_next_bounded_run() -> None:
    adapter = make_adapter(
        [
            {"id": "first", "output_text": "first answer"},
            {"id": "second", "output_text": "second answer"},
        ]
    )
    session = AgentSession.create(
        execution_context=make_execution_context(model_adapter=adapter),
        session_store=InMemorySessionStore(),
        session_id="thread-123",
    )

    first = await session.accept("first prompt")
    second = await session.accept("second prompt")

    assert first.final_result == "first answer"
    assert second.final_result == "second answer"
    second_input = adapter.client.responses.calls[1]["input"]
    second_content = "\n".join(str(message["content"]) for message in second_input)
    assert "first prompt" in second_content
    assert "first answer" in second_content
    state = session.current_state()
    assert state.messages == (
        OpenAIMessage(role="user", content="first prompt"),
        OpenAIMessage(role="assistant", content="first answer"),
        OpenAIMessage(role="user", content="second prompt"),
        OpenAIMessage(role="assistant", content="second answer"),
    )
    assert state.turn_count == 2
    assert state.last_run_id is not None
    assert state.last_result == "second answer"


def test_accept_passes_prior_messages_to_next_bounded_run() -> None:
    asyncio.run(_accept_passes_prior_messages_to_next_bounded_run())


async def _accept_does_not_append_assistant_turn_after_failure() -> None:
    adapter = make_adapter([RuntimeError("model down")])
    session = AgentSession.create(
        execution_context=make_execution_context(model_adapter=adapter),
        session_store=InMemorySessionStore(),
        session_id="thread-123",
    )

    with pytest.raises(ModelExecutionError, match="model down"):
        await session.accept("first prompt")

    assert session.current_state().messages == ()
    assert session.current_state().turn_count == 0


def test_accept_does_not_append_assistant_turn_after_failure() -> None:
    asyncio.run(_accept_does_not_append_assistant_turn_after_failure())


async def _accept_exposes_interruption_without_appending_assistant_turn() -> None:
    registry = InMemoryToolRegistry(
        [
            RegisteredTool(
                ToolDefinition.from_mapping(
                    {"id": "workspace_write", "approval_required": "yes"}
                ),
                lambda _args: {"ok": True},
            )
        ]
    )
    context = WorkflowExecutionContext(
        workflow=workflow_from(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "approval-session-agent",
                "entrypoint": "write",
                "nodes": [
                    {
                        "id": "write",
                        "kind": "tool_use_step",
                        "tool_id": "workspace_write",
                        "inputs": {"path": "notes.txt"},
                    }
                ],
                "tools": [{"id": "workspace_write", "approval_required": "yes"}],
            }
        ),
        tool_registry=registry,
    )
    session = AgentSession.create(
        execution_context=context,
        session_store=InMemorySessionStore(),
        session_id="thread-123",
    )

    result = await session.accept("write file")

    assert isinstance(result.workflow_result, WorkflowInterruptedResult)
    assert result.final_result is None
    assert session.current_state().messages == ()


def test_accept_exposes_interruption_without_appending_assistant_turn() -> None:
    asyncio.run(_accept_exposes_interruption_without_appending_assistant_turn())


async def _accept_preserves_input_guardrail_behavior() -> None:
    adapter = make_adapter([{"id": "unused", "output_text": "done"}])
    guardrails = InMemoryGuardrailRegistry(
        {
            "no_secrets": lambda _subject: GuardrailResult(
                guardrail_id="no_secrets",
                decision=GuardrailDecision.ABORT,
                reason_code="secret_detected",
            )
        }
    )
    workflow = workflow_from(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": "guardrail-session-agent",
            "entrypoint": "answer",
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
        }
    )
    session = AgentSession.create(
        execution_context=WorkflowExecutionContext(
            workflow=workflow,
            model_adapter=adapter,
            guardrail_registry=guardrails,
        ),
        session_store=InMemorySessionStore(),
        session_id="thread-123",
    )

    with pytest.raises(GuardrailExecutionError, match="secret_detected"):
        await session.accept("secret")

    assert adapter.client.responses.calls == []
    assert session.current_state().messages == ()


def test_accept_preserves_input_guardrail_behavior() -> None:
    asyncio.run(_accept_preserves_input_guardrail_behavior())


async def _history_none_stores_but_does_not_replay_messages() -> None:
    adapter = make_adapter(
        [
            {"id": "first", "output_text": "first answer"},
            {"id": "second", "output_text": "second answer"},
        ]
    )
    session = AgentSession.create(
        execution_context=make_policy_execution_context(
            history="none",
            model_adapter=adapter,
        ),
        session_store=InMemorySessionStore(),
        session_id="thread-123",
    )

    await session.accept("first prompt")
    await session.accept("second prompt")

    second_content = "\n".join(
        str(message["content"])
        for message in adapter.client.responses.calls[1]["input"]
    )
    assert "first prompt" not in second_content
    assert "first answer" not in second_content
    assert len(session.current_state().messages) == 4


def test_history_none_stores_but_does_not_replay_messages() -> None:
    asyncio.run(_history_none_stores_but_does_not_replay_messages())


async def _history_last_turn_replays_only_previous_pair() -> None:
    adapter = make_adapter(
        [
            {"id": "first", "output_text": "first answer"},
            {"id": "second", "output_text": "second answer"},
            {"id": "third", "output_text": "third answer"},
        ]
    )
    session = AgentSession.create(
        execution_context=make_policy_execution_context(
            history="last_turn",
            model_adapter=adapter,
        ),
        session_store=InMemorySessionStore(),
        session_id="thread-123",
    )

    await session.accept("first prompt")
    await session.accept("second prompt")
    await session.accept("third prompt")

    third_content = "\n".join(
        str(message["content"])
        for message in adapter.client.responses.calls[2]["input"]
    )
    assert "first prompt" not in third_content
    assert "first answer" not in third_content
    assert "second prompt" in third_content
    assert "second answer" in third_content


def test_history_last_turn_replays_only_previous_pair() -> None:
    asyncio.run(_history_last_turn_replays_only_previous_pair())


async def _history_full_replays_all_messages() -> None:
    adapter = make_adapter(
        [
            {"id": "first", "output_text": "first answer"},
            {"id": "second", "output_text": "second answer"},
            {"id": "third", "output_text": "third answer"},
        ]
    )
    session = AgentSession.create(
        execution_context=make_policy_execution_context(
            history="full",
            model_adapter=adapter,
        ),
        session_store=InMemorySessionStore(),
        session_id="thread-123",
    )

    await session.accept("first prompt")
    await session.accept("second prompt")
    await session.accept("third prompt")

    third_content = "\n".join(
        str(message["content"])
        for message in adapter.client.responses.calls[2]["input"]
    )
    assert "first prompt" in third_content
    assert "first answer" in third_content
    assert "second prompt" in third_content
    assert "second answer" in third_content


def test_history_full_replays_all_messages() -> None:
    asyncio.run(_history_full_replays_all_messages())


async def _history_summary_preserves_metadata_without_summary_generation() -> None:
    adapter = make_adapter(
        [
            {"id": "first", "output_text": "first answer"},
            {"id": "second", "output_text": "second answer"},
        ]
    )
    store = InMemorySessionStore()
    session = AgentSession.create(
        execution_context=make_policy_execution_context(
            history="summary",
            model_adapter=adapter,
        ),
        session_store=store,
        session_id="thread-123",
    )
    store.save(
        AgentSessionState(
            session_id="thread-123",
            workflow_identity=session.current_state().workflow_identity,
            metadata={"summary": "caller supplied"},
        )
    )

    await session.accept("first prompt")
    await session.accept("second prompt")

    second_content = "\n".join(
        str(message["content"])
        for message in adapter.client.responses.calls[1]["input"]
    )
    assert "first prompt" not in second_content
    assert session.current_state().metadata == {"summary": "caller supplied"}
    assert len(adapter.client.responses.calls) == 2


def test_history_summary_preserves_metadata_without_summary_generation() -> None:
    asyncio.run(_history_summary_preserves_metadata_without_summary_generation())


async def _session_id_state_key_is_available_to_run_state() -> None:
    adapter = make_adapter([{"id": "first", "output_text": "ok"}])
    session = AgentSession.create(
        execution_context=make_policy_execution_context(
            history="none",
            model_adapter=adapter,
            user_template="Session {session_id}: {prompt}",
        ),
        session_store=InMemorySessionStore(),
        session_id="thread-123",
    )

    await session.accept("hello")

    first_content = "\n".join(
        str(message["content"])
        for message in adapter.client.responses.calls[0]["input"]
    )
    assert "Session thread-123: hello" in first_content


def test_session_id_state_key_is_available_to_run_state() -> None:
    asyncio.run(_session_id_state_key_is_available_to_run_state())


async def _session_restarts_from_snapshot_with_restored_messages() -> None:
    adapter = make_adapter([{"id": "next", "output_text": "next answer"}])
    snapshot = AgentSessionState(
        session_id="thread-123",
        workflow_identity="session-agent:answer",
        messages=(
            OpenAIMessage(role="user", content="saved prompt"),
            OpenAIMessage(role="assistant", content="saved answer"),
        ),
        turn_count=1,
    ).to_mapping()

    session = AgentSession.from_snapshot(
        snapshot,
        execution_context=make_execution_context(model_adapter=adapter),
        session_store=InMemorySessionStore(),
    )
    await session.accept("next prompt")

    content = "\n".join(
        str(message["content"])
        for message in adapter.client.responses.calls[0]["input"]
    )
    assert "saved prompt" in content
    assert "saved answer" in content
    assert session.current_state().turn_count == 2


def test_session_restarts_from_snapshot_with_restored_messages() -> None:
    asyncio.run(_session_restarts_from_snapshot_with_restored_messages())


def test_session_restart_rejects_incompatible_workflow_identity() -> None:
    snapshot = AgentSessionState(
        session_id="thread-123",
        workflow_identity="other-agent:answer",
    ).to_mapping()

    with pytest.raises(AgentSessionError, match="does not match workflow"):
        AgentSession.from_snapshot(
            snapshot,
            execution_context=make_execution_context(),
            session_store=InMemorySessionStore(),
        )
