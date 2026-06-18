"""Tests for persistent agent session state and stores."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.context import WorkflowExecutionContext
from dynamic_agent_runner.errors import AgentSessionError
from dynamic_agent_runner.models import LoadedAgentWorkflow
from dynamic_agent_runner.openai_client import OpenAIMessage
from dynamic_agent_runner.sessions import (
    AGENT_SESSION_STATE_SCHEMA_VERSION,
    AgentSession,
    AgentSessionState,
    InMemorySessionStore,
)


def make_execution_context(
    package_id: str = "session-agent",
) -> WorkflowExecutionContext:
    manifest = load_runtime_manifest(
        {
            "format_version": 1,
            "package_type": "dynamic_agent_design",
            "package_id": package_id,
            "name": "Session Agent",
            "entrypoint": "answer",
            "nodes": [
                {
                    "id": "answer",
                    "kind": "llm_step",
                    "prompt": {"user_template": "{prompt}"},
                }
            ],
        }
    )
    return WorkflowExecutionContext(workflow=LoadedAgentWorkflow(manifest))


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
