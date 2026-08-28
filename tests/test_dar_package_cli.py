"""Tests for the non-mutating DAR package CLI discovery command."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
import shutil
import tomllib

import pytest

from dynamic_agent_runner import dar_package_cli
from dynamic_agent_runner.openai_client import ModelResponse, OpenAIClientAdapter
from dynamic_agent_runner.workflow_host.host import (
    LocalWorkflowHost,
    configure_local_host,
)
from dynamic_agent_runner.workflow_host.cli import main as workflow_host_main


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


class _Responses:
    def create(self, **_kwargs: object) -> ModelResponse:
        return ModelResponse(content="completed locally")


class _Client:
    responses = _Responses()


def test_project_declares_the_console_entry_point() -> None:
    project = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )

    assert project["project"]["scripts"]["dar-package"] == (
        "dynamic_agent_runner.dar_package_cli:console_main"
    )


def test_console_entry_point_emits_the_discovery_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        dar_package_cli.sys, "argv", ["dar-package", "version", "--json"]
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dar_package_cli, "_distribution_version", lambda: "0.2.1")

    with pytest.raises(SystemExit) as raised:
        dar_package_cli.console_main()

    captured = capsys.readouterr()
    assert raised.value.code == 0
    assert json.loads(captured.out) == {
        "distribution": "dynamic-agent-runner",
        "format_version": 1,
        "status": "ok",
        "version": "0.2.1",
    }
    assert captured.err == ""
    assert str(tmp_path) not in captured.out
    assert str(tmp_path) not in captured.err


def test_version_json_emits_the_exact_discovery_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = StringIO()
    stderr = StringIO()
    monkeypatch.setattr(dar_package_cli, "_distribution_version", lambda: "0.2.1")

    assert (
        dar_package_cli.main(["version", "--json"], stdout=stdout, stderr=stderr) == 0
    )
    assert json.loads(stdout.getvalue()) == {
        "distribution": "dynamic-agent-runner",
        "format_version": 1,
        "status": "ok",
        "version": "0.2.1",
    }
    assert stderr.getvalue() == ""


@pytest.mark.parametrize(
    "argv",
    [[], ["version"], ["version", "--text"], ["unknown", "--json"]],
)
def test_version_json_rejects_invalid_usage(argv: list[str]) -> None:
    stdout = StringIO()
    stderr = StringIO()

    assert dar_package_cli.main(argv, stdout=stdout, stderr=stderr) == 2
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error_code": "usage",
        "format_version": 1,
        "status": "error",
    }


def test_version_json_redacts_an_internal_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = StringIO()
    stderr = StringIO()

    def fail() -> str:
        raise RuntimeError("/private/state must not escape")

    monkeypatch.setattr(dar_package_cli, "_distribution_version", fail)

    assert (
        dar_package_cli.main(["version", "--json"], stdout=stdout, stderr=stderr) == 1
    )
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error_code": "internal",
        "format_version": 1,
        "status": "error",
    }
    assert "/private/state" not in stderr.getvalue()


def test_select_package_returns_only_an_opaque_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_path = Path("/private/packages/custom-email.zip")

    class Host:
        def select_package(self, path: Path, *, now: object) -> str:
            assert path == selected_path
            return "v1.package-source.selection"

    monkeypatch.setattr(dar_package_cli.LocalWorkflowHost, "open", lambda _root: Host())
    stdout = StringIO()
    stderr = StringIO()

    assert (
        dar_package_cli.main(
            ["select-package", "--path", str(selected_path), "--json"],
            stdout=stdout,
            stderr=stderr,
        )
        == 0
    )

    assert json.loads(stdout.getvalue()) == {
        "format_version": 1,
        "package_source_handle": "v1.package-source.selection",
        "status": "selected",
    }
    assert str(selected_path) not in stdout.getvalue()
    assert stderr.getvalue() == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["select-package", "--json"],
        ["select-package", "--path", "/private/packages/custom-email.zip"],
    ],
)
def test_select_package_requires_a_human_path_and_json_receipt(
    argv: list[str],
) -> None:
    stdout = StringIO()
    stderr = StringIO()

    assert dar_package_cli.main(argv, stdout=stdout, stderr=stderr) == 2
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error_code": "usage",
        "format_version": 1,
        "status": "error",
    }


def test_select_package_redacts_a_selection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_root: Path) -> object:
        raise dar_package_cli.LocalWorkflowHostError("/private/state is unavailable")

    monkeypatch.setattr(dar_package_cli.LocalWorkflowHost, "open", unavailable)
    stdout = StringIO()
    stderr = StringIO()

    assert (
        dar_package_cli.main(
            [
                "select-package",
                "--path",
                "/private/packages/custom-email.zip",
                "--json",
            ],
            stdout=stdout,
            stderr=stderr,
        )
        == 2
    )
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error_code": "usage",
        "format_version": 1,
        "status": "error",
    }
    assert "/private/state" not in stderr.getvalue()


def test_authoring_commands_use_only_opaque_host_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Host:
        def project_authoring_materials(
            self, material_set_id: str, *, now: object
        ) -> object:
            assert material_set_id == "materials-1"
            return type(
                "Projection",
                (),
                {
                    "expires_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "material_set_id": material_set_id,
                    "members": (
                        type(
                            "Member",
                            (),
                            {
                                "artifact_id": "artifact-1",
                                "content": "approved input",
                                "digest": "d" * 64,
                                "disposition": "distributable",
                                "role": "example",
                            },
                        )(),
                    ),
                },
            )()

        def create_authored_package(self, *, package_name: str, now: object) -> object:
            assert package_name == "document-summary"
            return type(
                "Output",
                (),
                {
                    "output_id": "output-1",
                    "expires_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "package_name": package_name,
                },
            )()

        def write_authored_package_file(self, **kwargs: object) -> object:
            assert kwargs["output_id"] == "output-1"
            assert kwargs["relative_path"] == "agent-design.md"
            assert kwargs["content"] == "# Design\n"
            return type(
                "Written",
                (),
                {
                    "byte_count": 9,
                    "content_hash": "a" * 64,
                    "relative_path": "agent-design.md",
                },
            )()

        def finalize_authored_output(self, **kwargs: object) -> object:
            assert kwargs["output_id"] == "output-1"
            assert kwargs["material_set_id"] == "materials-1"
            return type(
                "Finalized",
                (),
                {
                    "descriptor_digest": "b" * 64,
                    "file_count": 4,
                    "package_digest": "c" * 64,
                    "package_id": "package-1",
                },
            )()

    monkeypatch.setattr(dar_package_cli.LocalWorkflowHost, "open", lambda _root: Host())

    def run(argv: list[str], content: str = "") -> dict[str, object]:
        stdout = StringIO()
        stderr = StringIO()
        assert (
            dar_package_cli.main(
                argv, stdin=StringIO(content), stdout=stdout, stderr=stderr
            )
            == 0
        )
        assert stderr.getvalue() == ""
        return json.loads(stdout.getvalue())

    assert run(["project-authoring-materials", "--material-set-id", "materials-1"])[
        "members"
    ] == [
        {
            "artifact_id": "artifact-1",
            "content": "approved input",
            "digest": "d" * 64,
            "disposition": "distributable",
            "role": "example",
        }
    ]
    assert (
        run(["create-authored-package", "--package-name", "document-summary"])[
            "authoring_output_id"
        ]
        == "output-1"
    )
    assert (
        run(
            [
                "write-authored-package-file",
                "--authoring-output-id",
                "output-1",
                "--relative-path",
                "agent-design.md",
                "--content-stdin",
            ],
            "# Design\n",
        )["content_hash"]
        == "a" * 64
    )
    assert run(
        [
            "finalize-authored-package",
            "--authoring-output-id",
            "output-1",
            "--material-set-id",
            "materials-1",
        ]
    ) == {
        "descriptor_digest": "b" * 64,
        "file_count": 4,
        "format_version": 1,
        "package_digest": "c" * 64,
        "package_id": "package-1",
        "status": "finalized",
    }


@pytest.mark.parametrize(
    ("argv", "content"),
    [
        (["issue-authoring-materials", "--materials-json-stdin"], "[]"),
        (
            [
                "issue-authoring-materials",
                "--materials-manifest",
                "/private/materials.json",
            ],
            "",
        ),
        (["project-authoring-materials"], ""),
        (["create-authored-package"], ""),
        (["write-authored-package-file", "--authoring-output-id", "output-1"], ""),
        (["finalize-authored-package", "--path", "/private/package"], ""),
    ],
)
def test_authoring_commands_reject_incomplete_or_human_only_arguments(
    argv: list[str], content: str
) -> None:
    stdout = StringIO()
    stderr = StringIO()

    assert (
        dar_package_cli.main(
            argv, stdin=StringIO(content), stdout=stdout, stderr=stderr
        )
        == 2
    )
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error_code": "usage",
        "format_version": 1,
        "status": "error",
    }


def test_invoke_uses_a_saved_package_and_prompt_stdin_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Host:
        def __init__(self) -> None:
            self.calls: list[tuple[object, ...]] = []

        def invoke_saved(
            self,
            *,
            package_name: str,
            prompt: str,
            workspace_files: tuple[Path, ...],
            dry_run: bool,
            approval_broker: object | None,
            now: object,
        ) -> object:
            assert approval_broker is None
            assert workspace_files == ()
            assert not dry_run
            self.calls.append(("invoke", package_name, prompt, now))
            return type(
                "Result",
                (),
                {
                    "status": "completed",
                    "run_id": "run-1",
                    "output": {"summary": "done"},
                },
            )()

    host = Host()
    monkeypatch.setattr(dar_package_cli.LocalWorkflowHost, "open", lambda _root: host)
    stdout = StringIO()
    stderr = StringIO()

    status = dar_package_cli.main(
        ["invoke", "--package-name", "document-summary", "--prompt-stdin"],
        stdin=StringIO("Summarize this document."),
        stdout=stdout,
        stderr=stderr,
    )
    assert status == 0, stderr.getvalue()

    assert [call[0] for call in host.calls] == ["invoke"]
    assert host.calls[0][1:3] == (
        "document-summary",
        "Summarize this document.",
    )
    assert json.loads(stdout.getvalue()) == {
        "format_version": 1,
        "output": {"summary": "done"},
        "run_id": "run-1",
        "status": "completed",
        "workflow_id": "document-summary",
    }
    assert stderr.getvalue() == ""


def test_invoke_runs_an_already_registered_saved_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_root = tmp_path / "state"
    package_root = tmp_path / "packages"
    source = package_root / "document-summary"
    shutil.copytree(TEMPLATE_ROOT, source)
    descriptor = source / "workflow-descriptor.yaml"
    descriptor.write_text(
        descriptor.read_text(encoding="utf-8").replace(
            "allowed_artifact_roles: []", "allowed_artifact_roles: [document]"
        ),
        encoding="utf-8",
    )
    input_root = tmp_path / "input"
    input_root.mkdir()
    document = input_root / "document.txt"
    document.write_text("document body", encoding="utf-8")
    monkeypatch.setenv("DAR_AUTHORING_STATE_ROOT", str(state_root))
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(),
            models=[profile.model_id],
            is_local=True,
            execution_profile_adapter_id=profile.adapter_id,
        ),
    )
    configure_local_host(
        root=state_root,
        package_root=package_root,
        workspace_input_root=input_root,
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    host = LocalWorkflowHost.open(state_root)
    now = datetime.now(UTC)
    source_handle = host.select_package(source, now=now)
    host.register(
        workflow_id="document-summary",
        package_source_handle=source_handle,
        now=now,
    )
    assert dar_package_cli._default_state_root() == state_root
    stdout = StringIO()
    stderr = StringIO()

    status = dar_package_cli.main(
        [
            "invoke",
            "--package-name",
            "document-summary",
            "--prompt-stdin",
            "--workspace-file",
            str(document),
        ],
        stdin=StringIO("Summarize this document."),
        stdout=stdout,
        stderr=stderr,
    )
    assert status == 0, stderr.getvalue()

    receipt = json.loads(stdout.getvalue())
    assert receipt == {
        "format_version": 1,
        "output": {"message": "completed locally"},
        "run_id": receipt["run_id"],
        "status": "completed",
        "workflow_id": "document-summary",
    }
    assert isinstance(receipt["run_id"], str) and receipt["run_id"]
    assert stderr.getvalue() == ""


def test_authoring_cli_finalizes_a_package_that_a_human_can_register_and_invoke(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_root = tmp_path / "state"
    package_root = tmp_path / "packages"
    monkeypatch.setenv("DAR_AUTHORING_STATE_ROOT", str(state_root))
    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.host.create_local_adapter",
        lambda profile: OpenAIClientAdapter(
            _Client(),
            models=[profile.model_id],
            is_local=True,
            execution_profile_adapter_id=profile.adapter_id,
        ),
    )
    configure_local_host(
        root=state_root,
        package_root=package_root,
        model_id="local-model",
        base_url="http://127.0.0.1:11434/v1",
    )

    def command(argv: list[str], content: str = "") -> dict[str, object]:
        stdout = StringIO()
        stderr = StringIO()
        assert (
            dar_package_cli.main(
                argv,
                stdin=StringIO(content),
                stdout=stdout,
                stderr=stderr,
            )
            == 0
        ), stderr.getvalue()
        return json.loads(stdout.getvalue())

    material = tmp_path / "example.txt"
    material.write_text("approved input", encoding="utf-8")
    manifest = tmp_path / "materials.json"
    manifest.write_text(
        json.dumps(
            {
                "format_version": 1,
                "members": [
                    {
                        "disposition": "reference_only",
                        "path": str(material),
                        "role": "example",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    issued_output: list[str] = []
    assert (
        workflow_host_main(
            [
                "--state-root",
                str(state_root),
                "issue-authoring-materials",
                "--materials-manifest",
                str(manifest),
            ],
            write=issued_output.append,
        )
        == 0
    )
    materials = json.loads(issued_output[0])
    output = command(["create-authored-package", "--package-name", "document-summary"])
    for source in TEMPLATE_ROOT.iterdir():
        command(
            [
                "write-authored-package-file",
                "--authoring-output-id",
                str(output["authoring_output_id"]),
                "--relative-path",
                source.name,
                "--content-stdin",
            ],
            source.read_text(encoding="utf-8"),
        )
    finalized = command(
        [
            "finalize-authored-package",
            "--authoring-output-id",
            str(output["authoring_output_id"]),
            "--material-set-id",
            str(materials["material_set_id"]),
        ]
    )
    assert finalized["status"] == "finalized"

    host = LocalWorkflowHost.open(state_root)
    now = datetime.now(UTC)
    source_handle = host.select_authored_package("document-summary", now=now)
    host.register(
        workflow_id="document-summary",
        package_source_handle=source_handle,
        now=now,
    )
    invoked = command(
        ["invoke", "--package-name", "document-summary", "--prompt-stdin"],
        "Summarize this document.",
    )
    assert invoked["status"] == "completed"
    assert invoked["output"] == {"message": "completed locally"}


@pytest.mark.parametrize(
    "argv",
    [
        ["invoke", "--path", "/private/package", "--prompt-stdin"],
        ["invoke", "--package-name", "document-summary", "--prompt", "raw"],
        [
            "invoke",
            "--package-name",
            "document-summary",
            "--prompt-stdin",
            "--workflow-id",
            "forbidden",
        ],
        [
            "invoke",
            "--package-name",
            "document-summary",
            "--prompt-stdin",
            "--mcp-binding-id",
            "forbidden",
        ],
    ],
)
def test_invoke_rejects_legacy_or_provisioning_arguments(argv: list[str]) -> None:
    stdout = StringIO()
    stderr = StringIO()

    assert dar_package_cli.main(argv, stdout=stdout, stderr=stderr) == 2
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error_code": "usage",
        "format_version": 1,
        "status": "error",
    }


def test_invoke_dry_run_never_passes_a_workspace_file_to_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Host:
        def invoke_saved(self, **_kwargs: object) -> None:
            raise AssertionError("dry run with a workspace file must stop before host")

    monkeypatch.setattr(dar_package_cli.LocalWorkflowHost, "open", lambda _root: Host())
    stdout = StringIO()
    stderr = StringIO()

    assert (
        dar_package_cli.main(
            [
                "invoke",
                "--package-name",
                "document-summary",
                "--prompt-stdin",
                "--workspace-file",
                "/private/input/document.txt",
                "--dry-run",
            ],
            stdin=StringIO("Summarize this document."),
            stdout=stdout,
            stderr=stderr,
        )
        == 2
    )

    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error_code": "usage",
        "format_version": 1,
        "status": "error",
    }


def test_invoke_dry_run_returns_a_resolved_registration_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Host:
        def invoke_saved(self, **kwargs: object) -> object:
            assert kwargs["dry_run"] is True
            return type(
                "Result",
                (),
                {
                    "workflow_id": "internal-document-summary",
                    "registration_digest": "r" * 64,
                    "package_id": "document-summary-package",
                    "profile_id": "profile-v1",
                    "revision_digest": "d" * 64,
                },
            )()

    monkeypatch.setattr(dar_package_cli.LocalWorkflowHost, "open", lambda _root: Host())
    stdout = StringIO()
    stderr = StringIO()

    assert (
        dar_package_cli.main(
            [
                "invoke",
                "--package-name",
                "document-summary",
                "--prompt-stdin",
                "--dry-run",
            ],
            stdin=StringIO("Summarize this document."),
            stdout=stdout,
            stderr=stderr,
        )
        == 0
    )

    assert json.loads(stdout.getvalue()) == {
        "configuration": {
            "package_id": "document-summary-package",
            "profile_id": "profile-v1",
            "registration_digest": "r" * 64,
            "revision_digest": "d" * 64,
            "workflow_id": "internal-document-summary",
        },
        "format_version": 1,
        "mode": "dry_run",
        "status": "completed",
    }
    assert stderr.getvalue() == ""


def test_invoke_passes_workspace_files_only_to_saved_host_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Host:
        def invoke_saved(
            self,
            *,
            workspace_files: tuple[Path, ...],
            **_kwargs: object,
        ) -> object:
            assert workspace_files == (Path("/private/input/document.txt"),)
            return type(
                "Result",
                (),
                {
                    "status": "completed",
                    "run_id": "run-1",
                    "output": {"summary": "done"},
                },
            )()

    monkeypatch.setattr(dar_package_cli.LocalWorkflowHost, "open", lambda _root: Host())
    stdout = StringIO()
    stderr = StringIO()

    assert (
        dar_package_cli.main(
            [
                "invoke",
                "--package-name",
                "document-summary",
                "--prompt-stdin",
                "--workspace-file",
                "/private/input/document.txt",
            ],
            stdin=StringIO("Summarize this document."),
            stdout=stdout,
            stderr=stderr,
        )
        == 0
    )

    assert json.loads(stdout.getvalue())["status"] == "completed"
    assert stderr.getvalue() == ""


def test_invoke_passes_ask_as_a_local_host_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Host:
        def invoke_saved(
            self, *, approval_broker: object | None, **_kwargs: object
        ) -> object:
            assert isinstance(approval_broker, dar_package_cli.TerminalApprovalBroker)
            return type(
                "Result",
                (),
                {
                    "status": "completed",
                    "run_id": "run-1",
                    "output": {"summary": "done"},
                },
            )()

    monkeypatch.setattr(dar_package_cli.LocalWorkflowHost, "open", lambda _root: Host())

    assert (
        dar_package_cli.main(
            [
                "invoke",
                "--package-name",
                "document-summary",
                "--prompt-stdin",
                "--ask",
            ],
            stdin=StringIO("Summarize this document."),
            stdout=StringIO(),
            stderr=StringIO(),
        )
        == 0
    )


def test_invoke_redacts_a_saved_package_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_root: Path) -> object:
        raise dar_package_cli.LocalWorkflowHostError("/private/state is unavailable")

    monkeypatch.setattr(dar_package_cli.LocalWorkflowHost, "open", unavailable)
    stdout = StringIO()
    stderr = StringIO()

    assert (
        dar_package_cli.main(
            ["invoke", "--package-name", "document-summary", "--prompt-stdin"],
            stdin=StringIO("Summarize this document."),
            stdout=stdout,
            stderr=stderr,
        )
        == 1
    )

    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error_code": "capability_unavailable",
        "format_version": 1,
        "status": "capability_unavailable",
    }
    assert "/private/state" not in stderr.getvalue()


def test_invoke_returns_a_redacted_failed_result_for_a_runner_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Host:
        def invoke_saved(self, **_kwargs: object) -> None:
            raise dar_package_cli.RunDarWorkflowError("/private/state must not escape")

    monkeypatch.setattr(dar_package_cli.LocalWorkflowHost, "open", lambda _root: Host())
    stdout = StringIO()
    stderr = StringIO()

    assert (
        dar_package_cli.main(
            ["invoke", "--package-name", "document-summary", "--prompt-stdin"],
            stdin=StringIO("Summarize this document."),
            stdout=stdout,
            stderr=stderr,
        )
        == 1
    )

    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error_code": "failed",
        "format_version": 1,
        "status": "failed",
    }
    assert "/private/state" not in stderr.getvalue()
