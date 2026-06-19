"""Tests for collaborative parent/child agent session management."""

from __future__ import annotations

import asyncio

from dynamic_agent_runner.collaboration import (
    CollaborativeAgentPreset,
    CollaborativeAgentSessionManager,
)


class FakeChildSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.prompts: list[str] = []

    async def accept(self, prompt: str) -> object:
        self.prompts.append(prompt)
        return {"final_result": f"{self.session_id}: {prompt}"}

    def current_state(self) -> object:
        return {
            "session_id": self.session_id,
            "messages": list(self.prompts),
        }


def test_collaborative_manager_spawns_lists_and_snapshots_child_agents() -> None:
    created: list[FakeChildSession] = []

    def factory(agent_id: str, _preset: CollaborativeAgentPreset) -> FakeChildSession:
        session = FakeChildSession(agent_id)
        created.append(session)
        return session

    manager = CollaborativeAgentSessionManager(
        parent_session_id="parent-1",
        presets={
            "research": CollaborativeAgentPreset(
                id="research",
                role="Evidence collector",
                tool_ids=("web_search",),
            )
        },
        session_factory=factory,
    )

    child = manager.spawn_agent(
        preset_id="research",
        name="source-research",
        prompt="Find sources.",
    )

    assert child.status == "idle"
    assert child.role == "Evidence collector"
    assert created[0].prompts == []
    assert [agent.agent_id for agent in manager.list_agents()] == [child.agent_id]
    assert manager.get_agent_state(child.agent_id).name == "source-research"
    assert manager.current_state().to_mapping()["children"][0]["preset_id"] == (
        "research"
    )


async def _collaborative_manager_routes_prompts_and_restores_snapshot() -> None:
    sessions: dict[str, FakeChildSession] = {}

    def factory(agent_id: str, _preset: CollaborativeAgentPreset) -> FakeChildSession:
        return sessions.setdefault(agent_id, FakeChildSession(agent_id))

    manager = CollaborativeAgentSessionManager(
        parent_session_id="parent-1",
        presets={"review": CollaborativeAgentPreset(id="review")},
        session_factory=factory,
    )
    child = manager.spawn_agent(preset_id="review", name="reviewer")

    result = await manager.send_input(child.agent_id, "Check this.")
    snapshot = manager.current_state().to_mapping()
    restored = CollaborativeAgentSessionManager.from_snapshot(
        snapshot,
        presets={"review": CollaborativeAgentPreset(id="review")},
        session_factory=factory,
    )

    assert result == {"final_result": f"{child.agent_id}: Check this."}
    assert manager.get_agent_state(child.agent_id).status == "idle"
    assert sessions[child.agent_id].prompts == ["Check this."]
    assert restored.get_agent_state(child.agent_id).agent_id == child.agent_id
    assert restored.get_agent_state(child.agent_id).status == "idle"


def test_collaborative_manager_routes_prompts_and_restores_snapshot() -> None:
    asyncio.run(_collaborative_manager_routes_prompts_and_restores_snapshot())


def test_collaborative_manager_rejects_unknown_preset_and_closed_child() -> None:
    manager = CollaborativeAgentSessionManager(
        parent_session_id="parent-1",
        presets={"review": CollaborativeAgentPreset(id="review")},
        session_factory=lambda agent_id, _preset: FakeChildSession(agent_id),
    )

    missing = manager.spawn_agent(preset_id="missing", name="missing")
    child = manager.spawn_agent(preset_id="review", name="reviewer")
    manager.close_agent(child.agent_id)

    assert missing.status == "not_found"
    assert manager.get_agent_state(child.agent_id).status == "closed"
