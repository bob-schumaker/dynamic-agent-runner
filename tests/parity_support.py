"""Test-only controlled-tool fixtures for model-interface parity coverage."""

from __future__ import annotations

import asyncio
import socket
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

import dynamic_agent_runner.hugging_face_support as hugging_face_support
import dynamic_agent_runner.local_models as local_models
from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.models import LoadedAgentWorkflow, ToolDefinition
from dynamic_agent_runner.registry import (
    InMemoryToolRegistry,
    RegisteredTool,
    ToolResult,
)
from dynamic_agent_runner.tracing import InMemoryTraceSink


@dataclass(frozen=True)
class ParityRecord:
    """Deterministic comparison projection for one controlled scenario."""

    interface: str
    scenario: str
    asynchronous: bool
    exposed_schemas: tuple[tuple[str, Mapping[str, object]], ...]
    normalized_calls: tuple[tuple[str, object], ...]
    invocations: tuple[tuple[str, Mapping[str, object]], ...]
    invocation_results: tuple[tuple[str, object], ...]
    completion_class: str
    error_class: str | None
    trace_event_types: tuple[str, ...]
    stop_reasons: tuple[str, ...]


def install_parity_io_blocker(monkeypatch: object) -> None:
    """Fail network, process, and model-download seams in parity tests."""

    def blocked(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("parity tests prohibit external I/O")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", blocked)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", blocked)
    monkeypatch.setattr(local_models, "download_hub_file", blocked)
    monkeypatch.setattr(local_models, "download_hub_snapshot", blocked)
    monkeypatch.setattr(hugging_face_support, "download_hub_file", blocked)
    monkeypatch.setattr(hugging_face_support, "download_hub_snapshot", blocked)


def parity_tool_definitions() -> list[dict[str, object]]:
    return [
        {
            "id": "lookup_record",
            "approval_required": "no",
            "input_schema": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
                "additionalProperties": False,
            },
        },
        {
            "id": "create_record",
            "approval_required": "no",
            "input_schema": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title", "body"],
                "additionalProperties": False,
            },
        },
        {
            "id": "transform_record",
            "approval_required": "no",
            "input_schema": {
                "type": "object",
                "properties": {
                    "record_id": {"type": "string"},
                    "operation": {"enum": ["uppercase"]},
                },
                "required": ["record_id", "operation"],
                "additionalProperties": False,
            },
        },
        {
            "id": "fail_controlled",
            "approval_required": "no",
            "input_schema": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
                "additionalProperties": False,
            },
        },
    ]


def parity_registry() -> tuple[
    InMemoryToolRegistry,
    list[tuple[str, Mapping[str, object]]],
    list[tuple[str, object]],
]:
    invocations: list[tuple[str, Mapping[str, object]]] = []
    results: list[tuple[str, object]] = []

    def handler(tool_id: str, output: object):
        def run(arguments: Mapping[str, object]) -> object:
            invocations.append((tool_id, dict(arguments)))
            results.append((tool_id, output))
            return output

        return run

    definitions = parity_tool_definitions()
    outputs = (
        {"record_id": "record-seed", "body": "seed"},
        {"record_id": "record-created"},
        {"record_id": "record-seed", "body": "SEED"},
        ToolResult(
            tool_id="fail_controlled", success=False, error="planned controlled failure"
        ),
    )
    tools = [
        RegisteredTool(
            ToolDefinition.from_mapping(definition),
            handler(str(definition["id"]), output),
        )
        for definition, output in zip(definitions, outputs, strict=True)
    ]
    return InMemoryToolRegistry(tools), invocations, results


def parity_loop_workflow() -> LoadedAgentWorkflow:
    definitions = parity_tool_definitions()
    return LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "loop-tool-agent",
                "entrypoint": "analyze",
                "packaging": {"mode": "hybrid_bundle"},
                "runtime": {
                    "execution_policy": {
                        "model": "gpt-test",
                        "tool_use_completion": {
                            "run_again": "required",
                            "stop_on_tool": "disabled",
                            "final_output": "default",
                        },
                        "tool_choice_policy": {
                            "initial": "required",
                            "after_tool_result": "auto",
                        },
                    }
                },
                "nodes": [
                    {
                        "id": "analyze",
                        "kind": "llm_step",
                        "prompt": {"user_template": "Question: {prompt}"},
                        "available_tools": [str(tool["id"]) for tool in definitions],
                    }
                ],
                "edges": [],
                "tools": definitions,
            }
        )
    )


def parity_no_tool_workflow() -> LoadedAgentWorkflow:
    """Return the S5 no-loop workflow with the same exposed tools."""

    definitions = parity_tool_definitions()
    return LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
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
    )


def parity_contract_projection(record: ParityRecord) -> tuple[object, ...]:
    return (
        record.interface,
        record.exposed_schemas,
        record.normalized_calls,
        record.invocations,
        record.invocation_results,
        record.completion_class,
        record.error_class,
        record.trace_event_types,
        record.stop_reasons,
    )


def parity_record(
    *,
    interface: str,
    scenario: str,
    asynchronous: bool,
    normalized_calls: tuple[tuple[str, object], ...],
    invocations: list[tuple[str, Mapping[str, object]]],
    results: list[tuple[str, object]],
    result: object | None,
    error: Exception | None,
    sink: InMemoryTraceSink,
) -> ParityRecord:
    """Build one comparison record from observed adapter output and execution."""

    events = result.state.trace_events if result is not None else sink.events
    assert result is None or type(result).__name__ != "WorkflowInterruptedResult"
    record = ParityRecord(
        interface=interface,
        scenario=scenario,
        asynchronous=asynchronous,
        exposed_schemas=tuple(
            (str(definition["id"]), definition["input_schema"])
            for definition in parity_tool_definitions()
        ),
        normalized_calls=normalized_calls,
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
    assert not any("approval" in event_type for event_type in record.trace_event_types)
    return record
