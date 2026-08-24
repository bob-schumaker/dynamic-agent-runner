"""Tests for the DAR authoring no-tool workflow descriptor boundary."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from dynamic_agent_runner.models import RuntimeNode


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.descriptor import (  # noqa: E402
    WorkflowDescriptor,
    WorkflowDescriptorError,
    validate_no_tool_runtime_nodes,
)


def _descriptor() -> dict[str, object]:
    return {
        "format_version": 1,
        "package_id": "document-helper",
        "purpose": "Answer questions about supplied documents.",
        "dar_runtime": {
            "distribution": "dynamic-agent-runner",
            "required_version": "0.1.15",
        },
        "model": {"profile_requirement": "local-general-model"},
        "skills": [],
        "tools": [],
        "input_contract": {
            "mode": "hybrid",
            "structured_input_schema": None,
            "additional_context_max_bytes": 8192,
            "field_precedence": "original_prompt",
        },
        "task_invocation": {
            "entrypoint": "answer_document_question",
            "allowed_tool_ids": [],
            "max_total_tool_calls": 0,
            "allowed_structured_input_fields": [],
            "allowed_artifact_roles": ["document"],
            "terminal_output_schema_ref": "document-answer-v1",
        },
        "output": {"schema_ref": "document-answer-v1"},
        "limits": {"max_steps": 8},
    }


def test_valid_no_tool_descriptor_compiles() -> None:
    descriptor = WorkflowDescriptor.from_mapping(_descriptor())

    assert descriptor.package_id == "document-helper"
    assert descriptor.task_invocation.max_total_tool_calls == 0
    assert descriptor.limits.max_steps == 8
    validate_no_tool_runtime_nodes(
        descriptor, (RuntimeNode(id="answer", kind="llm_step"),)
    )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda value: value.update({"tools": ["send_email"]}), "tools"),
        (
            lambda value: value["task_invocation"].update(  # type: ignore[index,union-attr]
                {"allowed_tool_ids": ["send_email"], "max_total_tool_calls": 1}
            ),
            "allowed_tool_ids",
        ),
        (
            lambda value: value["limits"].update({"max_steps": 0}),  # type: ignore[index,union-attr]
            "max_steps",
        ),
        (
            lambda value: value["task_invocation"].pop("terminal_output_schema_ref"),  # type: ignore[index,union-attr]
            "terminal_output_schema_ref",
        ),
    ],
)
def test_no_tool_descriptor_rejects_missing_or_unavailable_capabilities(
    mutation: object, match: str
) -> None:
    value = _descriptor()
    mutation(value)  # type: ignore[operator]

    with pytest.raises(WorkflowDescriptorError, match=match):
        WorkflowDescriptor.from_mapping(value)


def test_no_tool_descriptor_rejects_runtime_tool_console() -> None:
    descriptor = WorkflowDescriptor.from_mapping(_descriptor())
    nodes = (
        RuntimeNode(id="answer", kind="llm_step"),
        RuntimeNode(
            id="console",
            kind="llm_step",
            available_tools=("send_email",),
        ),
    )

    with pytest.raises(WorkflowDescriptorError, match="undeclared tool"):
        validate_no_tool_runtime_nodes(descriptor, nodes)
