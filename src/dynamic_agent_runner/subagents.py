"""Opt-in subagent tool pack for bounded child delegation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from dynamic_agent_runner.errors import ToolRegistryError
from dynamic_agent_runner.models import (
    ToolDefinition,
    ToolOriginKind,
    ToolSource,
    ToolSourceKind,
)
from dynamic_agent_runner.registry import InMemoryToolRegistry, RegisteredTool


class SubagentRunner(Protocol):
    """Runner interface used by the subagent tool pack."""

    def run_subagent(self, *, preset: "SubagentPreset", prompt: str) -> Any:
        """Run one bounded child prompt."""


@dataclass(frozen=True)
class SubagentPreset:
    """Configuration for one callable child specialist."""

    id: str
    label: str | None = None
    tool_ids: tuple[str, ...] = ()
    max_iterations: int | None = None
    timeout_seconds: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ToolRegistryError("subagent preset requires id")
        object.__setattr__(self, "tool_ids", tuple(self.tool_ids))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class SubagentToolPolicy:
    """Limits for subagent tool execution."""

    max_children: int = 5
    max_parallel: int = 1
    require_approval: bool = False
    allow_recursive_spawn: bool = False


@dataclass(frozen=True)
class SubagentResult:
    """Bounded child result returned to the parent model."""

    child_id: str
    preset_id: str
    status: str
    summary: str
    error: str | None = None
    elapsed_ms: int | None = None
    citations: tuple[Any, ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        """Return a JSON-compatible bounded result mapping."""

        payload: dict[str, Any] = {
            "child_id": self.child_id,
            "preset_id": self.preset_id,
            "status": self.status,
            "summary": self.summary,
        }
        if self.error is not None:
            payload["error"] = self.error
        if self.elapsed_ms is not None:
            payload["elapsed_ms"] = self.elapsed_ms
        if self.citations:
            payload["citations"] = list(self.citations)
        return payload


def create_subagent_registry(
    *,
    runner: SubagentRunner | None = None,
    presets: Mapping[str, SubagentPreset] | None = None,
    policy: SubagentToolPolicy | None = None,
) -> InMemoryToolRegistry:
    """Create the opt-in subagent built-in tool pack."""

    if runner is None:
        raise ToolRegistryError("subagent tool pack requires runner")
    guard = _SubagentToolGuard(
        runner=runner,
        presets=dict(presets or {}),
        policy=policy or SubagentToolPolicy(),
    )
    return InMemoryToolRegistry(
        [
            _subagent_tool(
                "run_subagent",
                "Run subagent",
                "Run one bounded child specialist prompt.",
                {
                    "preset_id": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                ("preset_id", "prompt"),
                guard.run_one,
            ),
            _subagent_tool(
                "run_subagents",
                "Run subagents",
                "Run a bounded list of child specialist prompts.",
                {
                    "children": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "preset_id": {"type": "string"},
                                "prompt": {"type": "string"},
                            },
                            "required": ["preset_id", "prompt"],
                        },
                    }
                },
                ("children",),
                guard.run_many,
            ),
        ]
    )


class _SubagentToolGuard:
    def __init__(
        self,
        *,
        runner: SubagentRunner,
        presets: Mapping[str, SubagentPreset],
        policy: SubagentToolPolicy,
    ) -> None:
        self.runner = runner
        self.presets = dict(presets)
        self.policy = policy

    def run_one(self, args: Mapping[str, Any]) -> dict[str, Any]:
        child = {
            "preset_id": str(args["preset_id"]),
            "prompt": str(args["prompt"]),
        }
        return self.run_many({"children": [child]})

    def run_many(self, args: Mapping[str, Any]) -> dict[str, Any]:
        children = args.get("children")
        if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
            raise ToolRegistryError("run_subagents requires a children sequence")
        if len(children) > self.policy.max_children:
            raise ToolRegistryError(
                f"run_subagents accepts at most {self.policy.max_children} children"
            )
        results = [self._run_child(child) for child in children]
        status = (
            "completed"
            if all(r.get("status") == "completed" for r in results)
            else "partial"
        )
        return {"status": status, "children": results}

    def _run_child(self, child: Any) -> dict[str, Any]:
        if not isinstance(child, Mapping):
            raise ToolRegistryError("subagent child request must be a mapping")
        preset_id = str(child.get("preset_id") or "")
        prompt = str(child.get("prompt") or "")
        try:
            preset = self.presets[preset_id]
        except KeyError as exc:
            raise ToolRegistryError(f"unknown subagent preset {preset_id!r}") from exc
        raw_result = self.runner.run_subagent(preset=preset, prompt=prompt)
        return _subagent_result_mapping(raw_result, preset_id=preset_id)


def _subagent_result_mapping(raw_result: Any, *, preset_id: str) -> dict[str, Any]:
    if isinstance(raw_result, SubagentResult):
        return raw_result.to_mapping()
    if isinstance(raw_result, Mapping):
        result = dict(raw_result)
        result.setdefault("preset_id", preset_id)
        result.setdefault("status", "completed")
        result.setdefault("summary", "")
        return result
    return {
        "child_id": preset_id,
        "preset_id": preset_id,
        "status": "completed",
        "summary": str(raw_result),
    }


def _subagent_tool(
    tool_id: str,
    label: str,
    description: str,
    properties: Mapping[str, Any],
    required: Sequence[str],
    handler: Any,
) -> RegisteredTool:
    raw = {
        "id": tool_id,
        "label": label,
        "description_for_llm": description,
        "tool_type": "agent_tool",
        "input_schema": {
            "type": "object",
            "properties": dict(properties),
            "required": list(required),
        },
        "side_effect": "read",
        "approval_required": "no",
        "timeout": "runtime_default",
        "retry_policy": "none",
        "failure_behavior": "error",
    }
    definition = ToolDefinition.from_mapping(raw)
    definition = replace_tool_source(definition, tool_id)
    return RegisteredTool(definition, handler)


def replace_tool_source(definition: ToolDefinition, tool_id: str) -> ToolDefinition:
    """Return a tool definition with subagent built-in provenance."""

    from dataclasses import replace

    return replace(
        definition,
        source=ToolSource(
            kind=ToolSourceKind.BUILT_IN,
            origin=ToolOriginKind.BUILT_IN,
            source_id="subagent",
            detail=tool_id,
        ),
    )


__all__ = [
    "SubagentPreset",
    "SubagentResult",
    "SubagentRunner",
    "SubagentToolPolicy",
    "create_subagent_registry",
]
