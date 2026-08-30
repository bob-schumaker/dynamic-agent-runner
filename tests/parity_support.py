"""Test-only controlled-tool fixtures for model-interface parity coverage."""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
from collections.abc import Mapping, Sequence
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
                    "operation": {"type": "string", "enum": ["uppercase"]},
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


def parity_loop_workflow(
    *,
    include_tool_choice_policy: bool = True,
) -> LoadedAgentWorkflow:
    definitions = parity_tool_definitions()
    execution_policy: dict[str, object] = {
        "model": "gpt-test",
        "tool_use_completion": {
            "run_again": "required",
            "stop_on_tool": "disabled",
            "final_output": "default",
        },
    }
    if include_tool_choice_policy:
        execution_policy["tool_choice_policy"] = {
            "initial": "required",
            "after_tool_result": "auto",
        }
    return LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "loop-tool-agent",
                "entrypoint": "analyze",
                "packaging": {"mode": "hybrid_bundle"},
                "runtime": {"execution_policy": execution_policy},
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


def parity_exposed_schemas(
    tools: Sequence[Mapping[str, object]],
) -> tuple[tuple[str, Mapping[str, object]], ...]:
    """Normalize the tool definitions observed at one adapter-facing seam."""

    schemas: list[tuple[str, Mapping[str, object]]] = []
    for tool in tools:
        function = tool.get("function")
        definition = function if isinstance(function, Mapping) else tool
        name = definition.get("name")
        parameters = definition.get("parameters")
        assert isinstance(name, str)
        assert isinstance(parameters, Mapping)
        schemas.append((name, parameters))
    return tuple(schemas)


def assert_parity_semantic_projection(record: ParityRecord) -> None:
    """Require one native record to match its cross-interface scenario contract."""

    actual = parity_semantic_projection(record)
    expected = _parity_semantic_baseline(record.scenario)
    assert actual == expected, (record.interface, record.scenario, actual, expected)


def parity_semantic_projection(record: ParityRecord) -> tuple[object, ...]:
    """Project one record without provider formatting or trace mechanics."""

    scenario = _parity_scenario_name(record.scenario)
    error_category = _parity_error_category(record)
    normalized_calls = (
        ()
        if error_category == "normalization_error"
        else _canonical_parity_value(record.normalized_calls)
    )
    return (
        scenario,
        _canonical_parity_value(record.exposed_schemas),
        normalized_calls,
        _canonical_parity_value(record.invocations),
        _canonical_parity_value(record.invocation_results),
        record.completion_class,
        error_category,
    )


def _parity_semantic_baseline(scenario: str) -> tuple[object, ...]:
    scenario = _parity_scenario_name(scenario)
    schemas = tuple(
        (str(definition["id"]), definition["input_schema"])
        for definition in parity_tool_definitions()
    )
    calls: tuple[tuple[str, object], ...] = ()
    invocations: tuple[tuple[str, object], ...] = ()
    results: tuple[tuple[str, object], ...] = ()
    completion = "completed"
    error_category = "none"
    if scenario == "S1":
        calls = (("create_record", {"title": "DAR", "body": "controlled"}),)
        invocations = calls
        results = (("create_record", {"record_id": "record-created"}),)
    elif scenario == "S2":
        calls = (
            (
                "transform_record",
                {"record_id": "record-seed", "operation": "uppercase"},
            ),
        )
        invocations = calls
        results = (("transform_record", {"record_id": "record-seed", "body": "SEED"}),)
    elif scenario in {"S2-invalid", "S2-wrong-type", "S2-invalid-enum", "S2-unknown"}:
        calls = _parity_invalid_calls(scenario)
        completion = "error"
        error_category = "validation_error"
    elif scenario in {"S2-malformed", "S6"}:
        completion = "error"
        error_category = "normalization_error"
    elif scenario == "S3":
        calls = (
            ("lookup_record", {"key": "seed"}),
            (
                "transform_record",
                {"record_id": "record-seed", "operation": "uppercase"},
            ),
        )
        invocations = calls
        results = (
            ("lookup_record", {"record_id": "record-seed", "body": "seed"}),
            ("transform_record", {"record_id": "record-seed", "body": "SEED"}),
        )
    elif scenario == "S4":
        calls = (("fail_controlled", {"code": "planned"}),)
        invocations = calls
        results = (
            (
                "fail_controlled",
                ToolResult(
                    tool_id="fail_controlled",
                    success=False,
                    error="planned controlled failure",
                ),
            ),
        )
        completion = "error"
        error_category = "tool_failure"
    elif scenario != "S5":
        raise AssertionError(f"unknown parity scenario {scenario!r}")
    return (
        scenario,
        _canonical_parity_value(schemas),
        _canonical_parity_value(calls),
        _canonical_parity_value(invocations),
        _canonical_parity_value(results),
        completion,
        error_category,
    )


def _parity_scenario_name(scenario: str) -> str:
    aliases = {"S2-valid": "S2", "S2-missing": "S2-invalid"}
    return aliases.get(scenario, scenario)


def _parity_error_category(record: ParityRecord) -> str:
    scenario = _parity_scenario_name(record.scenario)
    if record.error_class is None:
        assert scenario in {"S1", "S2", "S3", "S5"}
        return "none"
    if scenario in {"S2-invalid", "S2-wrong-type", "S2-invalid-enum", "S2-unknown"}:
        assert record.error_class == "WorkflowExecutionError"
        return "validation_error"
    if scenario in {"S2-malformed", "S6"}:
        assert record.error_class in {"ModelExecutionError", "WorkflowExecutionError"}
        return "normalization_error"
    if scenario == "S4":
        assert record.error_class == "WorkflowExecutionError"
        return "tool_failure"
    raise AssertionError(f"unexpected parity error for {scenario!r}")


def _parity_invalid_calls(scenario: str) -> tuple[tuple[str, object], ...]:
    arguments = {
        "S2-invalid": {"record_id": "record-seed"},
        "S2-wrong-type": {"record_id": 1, "operation": "uppercase"},
        "S2-invalid-enum": {"record_id": "record-seed", "operation": "lowercase"},
        "S2-unknown": {
            "record_id": "record-seed",
            "operation": "uppercase",
            "unknown": True,
        },
    }
    return (("transform_record", arguments[scenario]),)


def _canonical_parity_value(value: object) -> object:
    if isinstance(value, str):
        try:
            return _canonical_parity_value(json.loads(value))
        except json.JSONDecodeError:
            return value
    if isinstance(value, ToolResult):
        return (
            "ToolResult",
            value.tool_id,
            value.success,
            _canonical_parity_value(value.output),
            value.error,
        )
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _canonical_parity_value(item))
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        )
    if isinstance(value, tuple | list):
        return tuple(_canonical_parity_value(item) for item in value)
    return value


def parity_record(
    *,
    interface: str,
    scenario: str,
    asynchronous: bool,
    normalized_calls: tuple[tuple[str, object], ...],
    exposed_schemas: tuple[tuple[str, Mapping[str, object]], ...],
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
        exposed_schemas=exposed_schemas,
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
    assert_parity_semantic_projection(record)
    return record
