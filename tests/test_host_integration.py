"""Tests for host-facing workflow integration helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from dynamic_agent_runner.capabilities import (
    CapabilityState,
    CapabilityStatusItem,
    CapabilityStatusReport,
)
from dynamic_agent_runner.errors import ToolRegistryError
from dynamic_agent_runner.host_integration import (
    HostToolBinding,
    ResolvedModelSelection,
    create_host_tool_registry,
    summarize_capability_report,
    summarize_trace_events,
)
from dynamic_agent_runner.tracing import TraceEvent


@dataclass
class FakeHostTool:
    canonical_id: str
    model_id: str

    def invoke(self, args: object) -> object:
        return {"canonical_id": self.canonical_id, "args": args}


def test_create_host_tool_registry_maps_model_ids_to_canonical_host_tools() -> None:
    host_tool = FakeHostTool("project.tools.search-docs", "search_docs")
    registry = create_host_tool_registry(
        [
            HostToolBinding(
                canonical_id=host_tool.canonical_id,
                model_id=host_tool.model_id,
                label="Search docs",
                description="Search host project documents.",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                handler=host_tool.invoke,
                aliases=("find_docs",),
            )
        ]
    )

    schema = registry.to_openai_tools(["search_docs"])[0]
    result = registry.invoke_tool("search_docs", {"query": "agent"})

    assert schema["name"] == "search_docs"
    assert result.success is True
    assert result.output == {
        "canonical_id": "project.tools.search-docs",
        "args": {"query": "agent"},
    }
    assert registry.get_tool("find_docs").id == "find_docs"
    assert registry.invoke_tool("find_docs", {"query": "alias"}).output == {
        "canonical_id": "project.tools.search-docs",
        "args": {"query": "alias"},
    }
    assert registry.get_tool("search_docs").definition.raw["host_canonical_id"] == (
        "project.tools.search-docs"
    )


def test_create_host_tool_registry_rejects_model_id_and_alias_collisions() -> None:
    with pytest.raises(ToolRegistryError, match="host tool id collision"):
        create_host_tool_registry(
            [
                HostToolBinding(
                    canonical_id="one",
                    model_id="same",
                    description="first",
                    handler=lambda _args: None,
                ),
                HostToolBinding(
                    canonical_id="two",
                    model_id="other",
                    aliases=("same",),
                    description="second",
                    handler=lambda _args: None,
                ),
            ]
        )


def test_summarize_trace_events_bounds_and_redacts_payloads() -> None:
    events = [
        TraceEvent(
            sequence=1,
            event_type="model_called",
            node_id="draft",
            run_id="run-1",
            payload={
                "prompt": "secret prompt",
                "count": 3,
                "items": [1, 2, 3, 4, 5],
                "nested": {"alpha": 1, "beta": 2, "gamma": 3},
            },
            sensitive_fields=("prompt",),
        )
    ]

    summary = summarize_trace_events(events, max_items=1, max_sequence_items=2)

    assert summary == [
        {
            "sequence": 1,
            "event_type": "model_called",
            "run_id": "run-1",
            "node_id": "draft",
            "payload": {
                "prompt": "[REDACTED]",
                "count": 3,
                "items": {"type": "list", "length": 5, "items": [1, 2]},
                "nested": {
                    "type": "dict",
                    "keys": ["alpha", "beta", "gamma"],
                    "length": 3,
                },
            },
        }
    ]


def test_summarize_capability_report_returns_bounded_status_payload() -> None:
    report = CapabilityStatusReport.from_items(
        package_id="host-agent",
        items=[
            CapabilityStatusItem(
                id="tool.host.search",
                label="Host search",
                state=CapabilityState.LIVE,
                category="tool",
                summary="Host search is live.",
                details={
                    "host_canonical_id": "project.tools.search-docs",
                    "raw": {"large": ["x"] * 20},
                },
            )
        ],
    )

    assert summarize_capability_report(report) == {
        "package_id": "host-agent",
        "valid": True,
        "validation_error": None,
        "summary": {"total": 1, "counts_by_state": {"live": 1}},
        "items": [
            {
                "id": "tool.host.search",
                "label": "Host search",
                "state": "live",
                "category": "tool",
                "summary": "Host search is live.",
                "owner": None,
                "required_collaborator": None,
                "details": {
                    "host_canonical_id": "project.tools.search-docs",
                    "raw": {"type": "dict", "keys": ["large"], "length": 1},
                },
            }
        ],
    }


def test_resolved_model_selection_exposes_execution_kwargs_without_secrets() -> None:
    first_adapter = object()
    second_adapter = object()
    selection = ResolvedModelSelection(
        model="gpt-test",
        adapters=(first_adapter, second_adapter),
        coverage="strict",
        unavailable_reason="missing token",
        diagnostics={"api_key": "secret", "provider": "fake"},
    )

    assert selection.to_execution_kwargs() == {
        "model_adapter": (first_adapter, second_adapter),
        "model_adapter_coverage": "strict",
    }
    assert selection.to_diagnostic_payload() == {
        "model": "gpt-test",
        "coverage": "strict",
        "available": False,
        "unavailable_reason": "missing token",
        "diagnostics": {"api_key": "[REDACTED]", "provider": "fake"},
    }
