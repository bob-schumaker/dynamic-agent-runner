"""Tests for the generic Dynamic Agent Runner stdio MCP entry point."""

from __future__ import annotations

import json
from io import StringIO
from importlib.metadata import version
from pathlib import Path
import tomllib

from dynamic_agent_runner.mcp_server import main


def test_project_declares_the_generic_stdio_mcp_entry_point() -> None:
    project = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )

    assert project["project"]["scripts"]["dynamic-agent-runner-mcp"] == (
        "dynamic_agent_runner.mcp_server:console_main"
    )


def test_stdio_server_hides_execution_tools_without_a_configured_host() -> None:
    stdin = StringIO(
        "\n".join(
            (
                '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}',
                '{"jsonrpc":"2.0","method":"notifications/initialized"}',
                '{"jsonrpc":"2.0","id":2,"method":"tools/list"}',
            )
        )
        + "\n"
    )
    stdout = StringIO()

    assert main(["--stdio"], stdin=stdin, stdout=stdout, stderr=StringIO()) == 0

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["result"]["serverInfo"] == {
        "name": "Dynamic Agent Runner",
        "version": version("dynamic-agent-runner"),
    }
    assert responses[1]["result"]["tools"] == []


def test_stdio_server_advertises_one_bound_workflow_tool_when_configured() -> None:
    from dynamic_agent_runner.workflow_host.server import _Session

    session = _Session(host_opener=lambda _root: object())
    session.handle('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    session.handle('{"jsonrpc":"2.0","method":"notifications/initialized"}')

    response = session.handle('{"jsonrpc":"2.0","id":2,"method":"tools/list"}')

    assert response is not None
    assert response["result"]["tools"] == [
        {
            "name": "run_dar_workflow",
            "description": "Run one registered local DAR workflow.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["format_version", "workflow_id", "prompt"],
                "properties": {
                    "format_version": {"const": 1},
                    "workflow_id": {"type": "string", "minLength": 1},
                    "prompt": {"type": "string", "minLength": 1},
                },
            },
        }
    ]


def test_stdio_server_seals_input_before_running_a_registered_workflow() -> None:
    from datetime import UTC, datetime, timedelta

    from dynamic_agent_runner.workflow_host.preparation import PreparedWorkflowInput
    from dynamic_agent_runner.workflow_host.runner import RunDarWorkflowResult
    from dynamic_agent_runner.workflow_host.server import _Session

    class Host:
        def prepare(self, *, workflow_id: str, prompt: str, now: object):
            assert workflow_id == "document-helper"
            assert prompt == "Answer this document question."
            assert isinstance(now, datetime)
            return PreparedWorkflowInput(
                prepared_input_id="v1.sealed.signature",
                workflow_id=workflow_id,
                registration_digest="registration-digest",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )

        def run(self, *, workflow_id: str, prepared_input_id: str, now: object):
            assert workflow_id == "document-helper"
            assert prepared_input_id == "v1.sealed.signature"
            assert isinstance(now, datetime)
            return RunDarWorkflowResult(
                status="completed", run_id="run-1", output={"message": "done"}
            )

    session = _Session(host_opener=lambda _root: Host())
    session.handle('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    session.handle('{"jsonrpc":"2.0","method":"notifications/initialized"}')

    response = session.handle(
        """{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"run_dar_workflow","arguments":{"format_version":1,"workflow_id":"document-helper","prompt":"Answer this document question."}}}"""
    )

    assert response is not None
    assert response["result"]["structuredContent"] == {
        "status": "completed",
        "workflow_id": "document-helper",
        "run_id": "run-1",
        "message": "done",
    }


def test_stdio_server_rejects_a_caller_supplied_prepared_input() -> None:
    from dynamic_agent_runner.workflow_host.runner import RunDarWorkflowResult
    from dynamic_agent_runner.workflow_host.server import _Session

    class Host:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def prepare(self, *, workflow_id: str, prompt: str, now: object):
            raise AssertionError("caller-supplied prepared input must be rejected")

        def run(self, *, workflow_id: str, prepared_input_id: str, now: object):
            self.calls.append(
                {
                    "workflow_id": workflow_id,
                    "prepared_input_id": prepared_input_id,
                }
            )
            return RunDarWorkflowResult(
                status="completed", run_id="run-1", output={"message": "done"}
            )

    host = Host()
    session = _Session(host_opener=lambda _root: host)
    session.handle('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    session.handle('{"jsonrpc":"2.0","method":"notifications/initialized"}')

    response = session.handle(
        """{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"run_dar_workflow","arguments":{"format_version":1,"workflow_id":"document-helper","prepared_input_id":"v1.sealed.signature"}}}"""
    )

    assert host.calls == []
    assert response is not None
    assert response["error"] == {
        "code": -32000,
        "message": "Workflow run failed",
    }


def test_stdio_server_rejects_unsealed_hybrid_fields() -> None:
    from dynamic_agent_runner.workflow_host.server import _Session

    class Host:
        def prepare(self, **_kwargs: object):
            raise AssertionError("unsealed fields must be rejected before preparation")

    session = _Session(host_opener=lambda _root: Host())
    session.handle('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    session.handle('{"jsonrpc":"2.0","method":"notifications/initialized"}')

    response = session.handle(
        """{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"run_dar_workflow","arguments":{"format_version":1,"workflow_id":"document-helper","prompt":"Answer this document question.","additional_context":"not accepted"}}}"""
    )

    assert response is not None
    assert response["error"] == {
        "code": -32000,
        "message": "Workflow run failed",
    }


def test_authoring_stdio_server_exposes_only_one_session_broker_surface() -> None:
    from dynamic_agent_runner.workflow_host.server import _AuthoringSession

    session = _AuthoringSession(
        material_set_id="v1.material-set.signature", host_opener=lambda _root: object()
    )
    session.handle('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    session.handle('{"jsonrpc":"2.0","method":"notifications/initialized"}')

    response = session.handle('{"jsonrpc":"2.0","id":2,"method":"tools/list"}')

    assert response is not None
    assert [tool["name"] for tool in response["result"]["tools"]] == [
        "project_authoring_materials",
        "create_authored_package",
        "write_authored_package_file",
        "finalize_authored_package",
    ]


def test_authoring_stdio_server_binds_one_material_set_and_output() -> None:
    from datetime import UTC, datetime, timedelta

    from dynamic_agent_runner.workflow_host.authoring_materials import (
        AuthoringMaterialProjectionMember,
        AuthoringMaterialSetProjection,
    )
    from dynamic_agent_runner.workflow_host.authoring_output import (
        AuthoredPackageValidation,
    )
    from dynamic_agent_runner.workflow_host.authoring_outputs import (
        AuthoredFileReceipt,
        AuthoringOutputReceipt,
    )
    from dynamic_agent_runner.workflow_host.server import _AuthoringSession

    class Host:
        def project_authoring_materials(self, material_set_id: str, *, now: object):
            assert material_set_id == "v1.material-set.signature"
            assert isinstance(now, datetime)
            return AuthoringMaterialSetProjection(
                material_set_id=material_set_id,
                members=(
                    AuthoringMaterialProjectionMember(
                        artifact_id="v1.material.example",
                        digest="a" * 64,
                        role="example",
                        disposition="include",
                        content="approved example",
                    ),
                ),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )

        def create_authored_package(self, *, package_name: str, now: object):
            assert package_name == "document-summary"
            assert isinstance(now, datetime)
            return AuthoringOutputReceipt(
                output_id="v1.output.signature",
                package_name=package_name,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )

        def write_authored_package_file(self, **kwargs: object):
            assert kwargs["output_id"] == "v1.output.signature"
            assert kwargs["relative_path"] == "agent-design.md"
            assert kwargs["content"] == "design"
            return AuthoredFileReceipt("agent-design.md", "b" * 64, 6)

        def finalize_authored_output(self, **kwargs: object):
            assert kwargs["output_id"] == "v1.output.signature"
            assert kwargs["material_set_id"] == "v1.material-set.signature"
            return AuthoredPackageValidation("document-summary", "c" * 64, "d" * 64, 4)

    session = _AuthoringSession(
        material_set_id="v1.material-set.signature", host_opener=lambda _root: Host()
    )
    session.handle('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    session.handle('{"jsonrpc":"2.0","method":"notifications/initialized"}')

    projected = session.handle(
        '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"project_authoring_materials","arguments":{"format_version":1}}}'
    )
    created = session.handle(
        '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"create_authored_package","arguments":{"format_version":1,"package_name":"document-summary"}}}'
    )
    written = session.handle(
        '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"write_authored_package_file","arguments":{"format_version":1,"authoring_output_id":"v1.output.signature","relative_path":"agent-design.md","content":"design"}}}'
    )
    finalized = session.handle(
        '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"finalize_authored_package","arguments":{"format_version":1,"authoring_output_id":"v1.output.signature"}}}'
    )
    replayed = session.handle(
        '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"finalize_authored_package","arguments":{"format_version":1,"authoring_output_id":"v1.output.signature"}}}'
    )

    assert (
        projected["result"]["structuredContent"]["members"][0]["content"]
        == "approved example"
    )
    assert (
        created["result"]["structuredContent"]["authoring_output_id"]
        == "v1.output.signature"
    )
    assert written["result"]["structuredContent"]["content_hash"] == "b" * 64
    assert finalized["result"]["structuredContent"]["package_digest"] == "c" * 64
    assert replayed["error"]["message"] == "Authoring request failed"
