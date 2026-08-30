"""Shared, no-side-effect contract data for model-interface parity checks.

Both the deterministic pytest matrix and the manually enabled live runner use
this catalog.  It deliberately contains only harmless in-memory tool behavior;
the live runner never exposes an external tool or a credential-bearing action.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dynamic_agent_runner.artifacts import load_runtime_manifest
from dynamic_agent_runner.models import LoadedAgentWorkflow, ToolDefinition
from dynamic_agent_runner.registry import (
    InMemoryToolRegistry,
    RegisteredTool,
    ToolResult,
)


@dataclass(frozen=True)
class ControlledToolScenario:
    """One adapter-independent controlled-tool scenario."""

    id: str
    prompt: str
    expected_calls: tuple[tuple[str, Mapping[str, object]], ...]
    expected_error: str | None = None
    after_tool_result_tool_choice: str = "auto"


def controlled_tool_definitions() -> tuple[Mapping[str, object], ...]:
    """Return the single schema set exposed by every parity-matrix target."""

    return (
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
    )


def controlled_tool_scenarios() -> tuple[ControlledToolScenario, ...]:
    """Return the common S1--S6 scenario catalog, including invalid variants."""

    return (
        ControlledToolScenario(
            "S1",
            "Call create_record with title DAR and body controlled, then give a brief final answer.",
            (("create_record", {"title": "DAR", "body": "controlled"}),),
        ),
        ControlledToolScenario(
            "S2",
            "Call transform_record with record_id record-seed and operation uppercase, then give a brief final answer.",
            (
                (
                    "transform_record",
                    {"record_id": "record-seed", "operation": "uppercase"},
                ),
            ),
        ),
        ControlledToolScenario(
            "S2-invalid",
            "Call transform_record with only record_id record-seed. Do not repair the arguments.",
            (("transform_record", {"record_id": "record-seed"}),),
            "validation_error",
        ),
        ControlledToolScenario(
            "S2-wrong-type",
            "Call transform_record with record_id 1 and operation uppercase. Do not repair the arguments.",
            (("transform_record", {"record_id": 1, "operation": "uppercase"}),),
            "validation_error",
        ),
        ControlledToolScenario(
            "S2-invalid-enum",
            "Call transform_record with record_id record-seed and operation lowercase. Do not repair the arguments.",
            (
                (
                    "transform_record",
                    {"record_id": "record-seed", "operation": "lowercase"},
                ),
            ),
            "validation_error",
        ),
        ControlledToolScenario(
            "S2-unknown",
            "Call transform_record with record_id record-seed, operation uppercase, and unknown true. Do not repair the arguments.",
            (
                (
                    "transform_record",
                    {
                        "record_id": "record-seed",
                        "operation": "uppercase",
                        "unknown": True,
                    },
                ),
            ),
            "validation_error",
        ),
        ControlledToolScenario(
            "S2-malformed",
            "Call transform_record with deliberately malformed, non-JSON arguments. Do not repair the arguments.",
            (),
            "normalization_error",
        ),
        ControlledToolScenario(
            "S3",
            "First call lookup_record with key seed. Then call transform_record with record_id from that result and operation uppercase. Give a brief final answer.",
            (
                ("lookup_record", {"key": "seed"}),
                (
                    "transform_record",
                    {"record_id": "record-seed", "operation": "uppercase"},
                ),
            ),
            after_tool_result_tool_choice="required",
        ),
        ControlledToolScenario(
            "S4",
            "Call fail_controlled with code planned, then stop without another tool call.",
            (("fail_controlled", {"code": "planned"}),),
            "tool_failure",
        ),
        ControlledToolScenario(
            "S5",
            "Return exactly one JSON object with string field status equal to ok and string field value equal to DAR_STRUCTURED_PARITY_OK. Do not call a tool or add markdown.",
            (),
        ),
        ControlledToolScenario(
            "S6",
            "Call lookup_record with deliberately malformed, non-JSON arguments. Do not repair the arguments.",
            (),
            "normalization_error",
        ),
    )


def controlled_tool_workflow(
    scenario: ControlledToolScenario,
    *,
    model: str = "gpt-test",
    include_tool_choice_policy: bool = True,
) -> LoadedAgentWorkflow:
    """Build the same harmless workflow shape for one scenario."""

    definitions = controlled_tool_definitions()
    policy: dict[str, object] = {"model": model}
    if scenario.id != "S5":
        policy["tool_use_completion"] = {
            "run_again": "required",
            "stop_on_tool": "disabled",
            "final_output": "default",
        }
        if include_tool_choice_policy:
            policy["tool_choice_policy"] = {
                "initial": "required",
                "after_tool_result": scenario.after_tool_result_tool_choice,
            }
    return LoadedAgentWorkflow(
        runtime_manifest=load_runtime_manifest(
            {
                "format_version": 1,
                "package_type": "dynamic_agent_design",
                "package_id": "controlled-tool-matrix",
                "entrypoint": "answer",
                "packaging": {"mode": "hybrid_bundle"},
                "runtime": {"execution_policy": policy},
                "nodes": [
                    {
                        "id": "answer",
                        "kind": "llm_step",
                        "prompt": {"user_template": "{prompt}"},
                        "available_tools": [str(tool["id"]) for tool in definitions],
                    }
                ],
                "edges": [],
                "tools": list(definitions),
            }
        )
    )


def controlled_tool_registry() -> tuple[
    InMemoryToolRegistry,
    list[tuple[str, Mapping[str, object]]],
    list[tuple[str, object]],
]:
    """Return harmless handlers and observable invocation/result records."""

    invocations: list[tuple[str, Mapping[str, object]]] = []
    results: list[tuple[str, object]] = []
    outputs: Mapping[str, object] = {
        "lookup_record": {"record_id": "record-seed", "body": "seed"},
        "create_record": {"record_id": "record-created"},
        "transform_record": {"record_id": "record-seed", "body": "SEED"},
        "fail_controlled": ToolResult(
            tool_id="fail_controlled", success=False, error="planned controlled failure"
        ),
    }

    def handler(tool_id: str):
        def run(arguments: Mapping[str, object]) -> object:
            invocations.append((tool_id, dict(arguments)))
            output = outputs[tool_id]
            results.append((tool_id, output))
            return output

        return run

    tools = tuple(
        RegisteredTool(
            ToolDefinition.from_mapping(definition), handler(str(definition["id"]))
        )
        for definition in controlled_tool_definitions()
    )
    return InMemoryToolRegistry(tools), invocations, results
