# Power-Marimo Host Integration Sketch with Current API

## Goal

Show a concrete, honest host-managed multi-call continuity pattern using the
current `dynamic-agent-runner` API surface.

## Core integration idea

`power-marimo` owns continuity across turns. The runner executes one bounded
workflow per call.

## Host-managed state

The host should persist a session record such as:

```python
from dataclasses import dataclass, field


@dataclass
class PowerMarimoSession:
    session_id: str
    notebook_id: str | None = None
    selected_room: str | None = None
    last_user_goal: str | None = None
    notebook_summary: str | None = None
    latest_analysis_summary: str | None = None
    recent_turns: list[dict[str, str]] = field(default_factory=list)
    artifacts: dict[str, object] = field(default_factory=dict)
```

Recommended contents:

- stable session id
- notebook identity / server identity
- selected room or experiment inputs
- compact notebook summary
- compact analysis summary
- a short recent-turn window for user-visible continuity
- any host-owned artifacts that should not be recomputed every turn

## One-time runner setup

Compile once and reuse the execution context:

```python
from dynamic_agent_runner import load_agent_package_workflow
from dynamic_agent_runner.context import WorkflowExecutionContext


compiled = load_agent_package_workflow(
    package_directory="/path/to/power-marimo-package",
    tool_registry=tool_registry,
)

execution_context = WorkflowExecutionContext(
    workflow=compiled,
    tool_registry=tool_registry,
    model_adapter=model_adapter,
    trace_sink=trace_sink,
    lifecycle_hooks=lifecycle_hooks,
    max_steps=12,
    prompt_cache=True,
)
```

## Per-turn prompt assembly

The host assembles the next prompt from current state plus the latest user turn.

```python
def build_turn_prompt(session: PowerMarimoSession, user_message: str) -> str:
    sections: list[str] = []
    sections.append(f"Session ID: {session.session_id}")
    if session.selected_room:
        sections.append(f"Selected room: {session.selected_room}")
    if session.notebook_summary:
        sections.append("Notebook summary:\n" + session.notebook_summary)
    if session.latest_analysis_summary:
        sections.append("Latest analysis summary:\n" + session.latest_analysis_summary)
    if session.recent_turns:
        transcript = "\n".join(
            f"{turn['role']}: {turn['content']}" for turn in session.recent_turns[-4:]
        )
        sections.append("Recent turns:\n" + transcript)
    sections.append("Current user message:\n" + user_message)
    return "\n\n".join(sections)
```

This keeps continuity explicit without requiring runner-owned session memory.

## Per-turn runner invocation

```python
from dynamic_agent_runner import run_agent_workflow_async


async def handle_user_turn(
    session: PowerMarimoSession,
    user_message: str,
) -> object:
    prompt = build_turn_prompt(session, user_message)
    result = await run_agent_workflow_async(
        prompt=prompt,
        execution_context=execution_context,
        run_id=f"{session.session_id}:{len(session.recent_turns)}",
    )
    session.recent_turns.append({"role": "user", "content": user_message})
    session.recent_turns.append({"role": "assistant", "content": str(result)})
    return result
```

## Post-run host update pattern

After each call, the host should update its durable session state from trusted
tool outputs or explicit application state, not just from free-form model text.

Example update flow:

1. extract changed notebook metadata from host-observed tool results
2. refresh `notebook_summary`
3. refresh `latest_analysis_summary`
4. trim or summarize `recent_turns`
5. persist the updated session record

## Recommended continuity policy for v1

For first-customer `power-marimo`, prefer:

- bounded recent-turn carry-forward
- host-generated notebook summary
- host-generated analysis summary
- stable session id per notebook/analysis thread

Avoid in v1:

- raw full-history replay on every turn
- model-generated durable memory without host review
- runner-owned persistence contracts

## Why this matches current runner reality

- `WorkflowExecutionContext` is intentionally reusable across runs.
- prompts are already per-run inputs.
- no runner-owned session abstraction needs to be invented to get a useful
  multi-turn workflow.

## Relationship to OA8

If OA8 is implemented later, this host pattern can evolve by mapping:

- `session.session_id` -> `session_id_state_key`
- host transcript policy -> `history`
- host summary field -> `summary_state_key`

That means this v1 host integration does not fight the future OA8 seam.
