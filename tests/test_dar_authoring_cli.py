"""Tests for the DAR authoring local workflow CLI façade."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.cli import main, run_main  # noqa: E402


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


def _invoke(args: list[str]) -> tuple[int, dict[str, object]]:
    output: list[str] = []
    result = main(args, write=output.append)
    return result, json.loads(output[0])


def test_cli_configures_selects_registers_prepares_and_dry_runs(tmp_path: Path) -> None:
    root = tmp_path / "state"
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    state_args = ["--state-root", str(root)]

    status, configured = _invoke(
        [
            *state_args,
            "configure-local-model",
            "--package-root",
            str(package_root),
            "--model-id",
            "local-model-v1",
            "--base-url",
            "http://127.0.0.1:11434/v1",
        ]
    )
    assert status == 0
    assert configured["status"] == "configured"

    status, selected = _invoke([*state_args, "select-package", "--path", str(source)])
    assert status == 0
    status, registration = _invoke(
        [
            *state_args,
            "register",
            "--workflow-id",
            "document-helper",
            "--package-source-handle",
            selected["package_source_handle"],
        ]
    )
    assert status == 0
    assert registration["workflow_id"] == "document-helper"

    status, prepared = _invoke(
        [
            *state_args,
            "prepare",
            "--workflow-id",
            "document-helper",
            "--prompt",
            "Answer me.",
        ]
    )
    assert status == 0
    status, result = _invoke(
        [
            *state_args,
            "run",
            "--workflow-id",
            "document-helper",
            "--prepared-input-id",
            prepared["prepared_input_id"],
            "--dry-run",
        ]
    )
    assert status == 0
    assert result == {"status": "ready", "workflow_id": "document-helper"}

    output: list[str] = []
    assert (
        run_main(
            [
                *state_args,
                "--workflow-id",
                "document-helper",
                "--prepared-input-id",
                prepared["prepared_input_id"],
                "--dry-run",
            ],
            write=output.append,
        )
        == 0
    )


def test_cli_ingresses_a_registered_workspace_file_without_returning_its_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "state"
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
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
    state_args = ["--state-root", str(root)]

    status, _ = _invoke(
        [
            *state_args,
            "configure-local-model",
            "--package-root",
            str(package_root),
            "--workspace-input-root",
            str(input_root),
            "--model-id",
            "local-model-v1",
            "--base-url",
            "http://127.0.0.1:11434/v1",
        ]
    )
    assert status == 0
    status, selected = _invoke([*state_args, "select-package", "--path", str(source)])
    assert status == 0
    status, registration = _invoke(
        [
            *state_args,
            "register",
            "--workflow-id",
            "document-helper",
            "--package-source-handle",
            selected["package_source_handle"],
        ]
    )
    assert status == 0

    status, artifact = _invoke(
        [
            *state_args,
            "ingress-file",
            "--workflow-id",
            registration["workflow_id"],
            "--path",
            str(document),
            "--role",
            "document",
            "--media-type",
            "text/plain",
        ]
    )

    assert status == 0
    assert set(artifact) == {
        "artifact_id",
        "byte_count",
        "content_hash",
        "expires_at",
    }
    assert str(document) not in json.dumps(artifact)

    status, prepared = _invoke(
        [
            *state_args,
            "prepare",
            "--workflow-id",
            registration["workflow_id"],
            "--prompt",
            "Answer the request.",
            "--artifact-id",
            artifact["artifact_id"],
        ]
    )

    assert status == 0
    assert str(document) not in json.dumps(prepared)
