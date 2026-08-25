"""Tests for the DAR authoring local workflow CLI façade."""

from __future__ import annotations

import json
import shutil
import base64
import hashlib
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


from dynamic_agent_runner.workflow_host import cli  # noqa: E402
from dynamic_agent_runner.workflow_host.cli import main, run_main  # noqa: E402


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "templates"


def _invoke(args: list[str]) -> tuple[int, dict[str, object]]:
    output: list[str] = []
    result = main(args, write=output.append)
    return result, json.loads(output[0])


def _human_material_manifest(
    tmp_path: Path, content: str = "private design example"
) -> Path:
    source = tmp_path / "selected-material.txt"
    source.write_text(content, encoding="utf-8")
    manifest = tmp_path / "materials.json"
    manifest.write_text(
        json.dumps(
            {
                "format_version": 1,
                "members": [
                    {
                        "disposition": "reference_only",
                        "path": str(source),
                        "role": "example",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_cli_invokes_a_human_selected_no_tool_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Host:
        def __init__(self) -> None:
            self.calls: list[tuple[object, ...]] = []

        def select_package(self, path: Path, *, now: object) -> str:
            self.calls.append(("select", path, now))
            return "source-handle"

        def register(
            self,
            *,
            workflow_id: str,
            package_source_handle: str,
            now: object,
            mcp_binding_id: str | None = None,
        ) -> SimpleNamespace:
            self.calls.append(
                ("register", workflow_id, package_source_handle, mcp_binding_id, now)
            )
            return SimpleNamespace(workflow_id=workflow_id)

        def prepare(
            self, *, workflow_id: str, prompt: str, now: object
        ) -> SimpleNamespace:
            self.calls.append(("prepare", workflow_id, prompt, now))
            return SimpleNamespace(prepared_input_id="prepared-input")

        def run(
            self,
            *,
            workflow_id: str,
            prepared_input_id: str,
            now: object,
            approval_broker: object | None = None,
        ) -> SimpleNamespace:
            assert approval_broker is None
            self.calls.append(("run", workflow_id, prepared_input_id, now))
            return SimpleNamespace(
                status="completed", run_id="run-1", output={"message": "done"}
            )

    host = Host()
    monkeypatch.setattr(cli.LocalWorkflowHost, "open", lambda _root: host)
    output: list[str] = []

    assert (
        main(
            [
                "--state-root",
                "/private/state",
                "invoke",
                "--path",
                "/private/packages/document-helper",
                "--workflow-id",
                "document-helper",
                "--prompt",
                "Answer the document question.",
            ],
            write=output.append,
        )
        == 0
    )

    assert [call[0] for call in host.calls] == [
        "select",
        "register",
        "prepare",
        "run",
    ]
    assert json.loads(output[0]) == {
        "message": "done",
        "run_id": "run-1",
        "status": "completed",
        "workflow_id": "document-helper",
    }


def test_cli_dry_runs_a_human_selected_package_with_a_reviewed_mcp_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Host:
        def __init__(self) -> None:
            self.calls: list[tuple[object, ...]] = []

        def select_package(self, path: Path, *, now: object) -> str:
            self.calls.append(("select", path, now))
            return "source-handle"

        def register(
            self,
            *,
            workflow_id: str,
            package_source_handle: str,
            now: object,
            mcp_binding_id: str | None = None,
        ) -> SimpleNamespace:
            self.calls.append(
                ("register", workflow_id, package_source_handle, mcp_binding_id, now)
            )
            return SimpleNamespace(workflow_id=workflow_id)

        def prepare(
            self, *, workflow_id: str, prompt: str, now: object
        ) -> SimpleNamespace:
            self.calls.append(("prepare", workflow_id, prompt, now))
            return SimpleNamespace(prepared_input_id="prepared-input")

        def dry_run(
            self, *, workflow_id: str, prepared_input_id: str, now: object
        ) -> SimpleNamespace:
            self.calls.append(("dry_run", workflow_id, prepared_input_id, now))
            return SimpleNamespace(status="ready", workflow_id=workflow_id)

        def run(self, **_kwargs: object) -> None:
            raise AssertionError("dry run must not execute a workflow")

    host = Host()
    monkeypatch.setattr(cli.LocalWorkflowHost, "open", lambda _root: host)
    output: list[str] = []

    assert (
        main(
            [
                "--state-root",
                "/private/state",
                "invoke",
                "--path",
                "/private/packages/mail-reader",
                "--workflow-id",
                "mail-reader",
                "--prompt",
                "List unread mail.",
                "--mcp-binding-id",
                "binding-opaque-id",
                "--dry-run",
            ],
            write=output.append,
        )
        == 0
    )

    assert [call[0] for call in host.calls] == [
        "select",
        "register",
        "prepare",
        "dry_run",
    ]
    assert host.calls[1][3] == "binding-opaque-id"
    assert json.loads(output[0]) == {
        "status": "ready",
        "workflow_id": "mail-reader",
    }


def test_cli_invokes_with_an_unambiguous_workspace_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Host:
        def select_package(self, path: Path, *, now: object) -> str:
            return "source-handle"

        def register(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(workflow_id="document-helper")

        def ingress_default_file(
            self, *, workflow_id: str, path: Path, now: object
        ) -> SimpleNamespace:
            assert workflow_id == "document-helper"
            assert path == Path("/private/input/document.txt")
            return SimpleNamespace(artifact_id="workspace-artifact")

        def prepare(
            self,
            *,
            workflow_id: str,
            prompt: str,
            workspace_artifact_ids: tuple[str, ...],
            now: object,
        ) -> SimpleNamespace:
            assert workflow_id == "document-helper"
            assert prompt == "Answer the document question."
            assert workspace_artifact_ids == ("workspace-artifact",)
            return SimpleNamespace(prepared_input_id="prepared-input")

        def run(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                status="completed", run_id="run-1", output={"message": "done"}
            )

    monkeypatch.setattr(cli.LocalWorkflowHost, "open", lambda _root: Host())
    output: list[str] = []

    assert (
        main(
            [
                "--state-root",
                "/private/state",
                "invoke",
                "--path",
                "/private/packages/document-helper",
                "--workflow-id",
                "document-helper",
                "--prompt",
                "Answer the document question.",
                "--workspace-file",
                "/private/input/document.txt",
            ],
            write=output.append,
        )
        == 0
    )

    assert json.loads(output[0])["status"] == "completed"


def test_cli_dry_run_rejects_workspace_files_before_ingress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Host:
        def select_package(self, **_kwargs: object) -> None:
            raise AssertionError("dry run with a file must not select or ingress")

    monkeypatch.setattr(cli.LocalWorkflowHost, "open", lambda _root: Host())

    assert (
        main(
            [
                "--state-root",
                "/private/state",
                "invoke",
                "--path",
                "/private/packages/document-helper",
                "--workflow-id",
                "document-helper",
                "--prompt",
                "Answer the document question.",
                "--workspace-file",
                "/private/input/document.txt",
                "--dry-run",
            ]
        )
        == 2
    )


def test_cli_projects_selected_authoring_material_only_after_host_issuance(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    package_root = tmp_path / "packages"
    state_args = ["--state-root", str(state_root)]
    status, _ = _invoke(
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
    assert package_root.is_dir()

    manifest = _human_material_manifest(tmp_path)
    issued_output: list[str] = []
    assert (
        main(
            [
                *state_args,
                "issue-authoring-materials",
                "--materials-manifest",
                str(manifest),
            ],
            write=issued_output.append,
        )
        == 0
    )
    receipt = json.loads(issued_output[0])
    assert "content" not in issued_output[0]

    status, projection = _invoke(
        [
            *state_args,
            "project-authoring-materials",
            "--material-set-id",
            receipt["material_set_id"],
        ]
    )

    assert status == 0
    assert projection["members"] == [
        {
            "artifact_id": receipt["members"][0]["artifact_id"],
            "content": "private design example",
            "digest": receipt["members"][0]["digest"],
            "disposition": "reference_only",
            "role": "example",
        }
    ]


def test_cli_issues_authoring_materials_from_a_human_manifest_only(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    package_root = tmp_path / "packages"
    selected = tmp_path / "selected-example.txt"
    unselected = tmp_path / "unselected-example.txt"
    selected.write_text("private selected example", encoding="utf-8")
    unselected.write_text("unselected source text", encoding="utf-8")
    manifest = tmp_path / "materials.json"
    manifest.write_text(
        json.dumps(
            {
                "format_version": 1,
                "members": [
                    {
                        "disposition": "reference_only",
                        "path": str(selected),
                        "role": "example",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    state_args = ["--state-root", str(state_root)]
    assert (
        _invoke(
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
        )[0]
        == 0
    )
    issued_output: list[str] = []

    assert (
        main(
            [
                *state_args,
                "issue-authoring-materials",
                "--materials-manifest",
                str(manifest),
            ],
            write=issued_output.append,
        )
        == 0
    )
    receipt = json.loads(issued_output[0])
    assert "private selected example" not in issued_output[0]
    assert "unselected source text" not in issued_output[0]

    status, projection = _invoke(
        [
            *state_args,
            "project-authoring-materials",
            "--material-set-id",
            receipt["material_set_id"],
        ]
    )
    assert status == 0
    assert projection["members"][0]["content"] == "private selected example"
    assert "unselected source text" not in json.dumps(projection)


@pytest.mark.parametrize(
    "manifest_value",
    [
        {
            "format_version": 1,
            "members": [
                {"content": "raw", "role": "example", "disposition": "reference_only"}
            ],
        },
        {
            "format_version": 1,
            "members": [
                {
                    "path": "relative.txt",
                    "role": "example",
                    "disposition": "reference_only",
                }
            ],
        },
    ],
)
def test_cli_rejects_raw_or_relative_material_manifest_members(
    tmp_path: Path, manifest_value: dict[str, object]
) -> None:
    manifest = tmp_path / "materials.json"
    manifest.write_text(json.dumps(manifest_value), encoding="utf-8")
    output: list[str] = []

    assert (
        main(
            [
                "--state-root",
                str(tmp_path / "state"),
                "issue-authoring-materials",
                "--materials-manifest",
                str(manifest),
            ],
            write=output.append,
        )
        == 2
    )
    assert output == []


def test_cli_finalizes_a_host_selected_authored_package(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    package_root = tmp_path / "packages"
    package = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, package)
    state_args = ["--state-root", str(state_root)]
    status, _ = _invoke(
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
    manifest = _human_material_manifest(tmp_path)
    issued_output: list[str] = []
    assert (
        main(
            [
                *state_args,
                "issue-authoring-materials",
                "--materials-manifest",
                str(manifest),
            ],
            write=issued_output.append,
        )
        == 0
    )
    receipt = json.loads(issued_output[0])

    status, finalized = _invoke(
        [
            *state_args,
            "finalize-authored-package",
            "--path",
            str(package),
            "--material-set-id",
            receipt["material_set_id"],
        ]
    )

    assert status == 0
    assert finalized["package_id"] == "dar-authoring-no-tool-template"
    assert len(finalized["package_digest"]) == 64
    assert (package / "package-manifest.json").is_file()


def test_cli_builds_and_finalizes_a_host_owned_authored_package(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    package_root = tmp_path / "packages"
    package_root.mkdir()
    state_args = ["--state-root", str(state_root)]
    status, _ = _invoke(
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

    manifest = _human_material_manifest(tmp_path)
    issued_output: list[str] = []
    assert (
        main(
            [
                *state_args,
                "issue-authoring-materials",
                "--materials-manifest",
                str(manifest),
            ],
            write=issued_output.append,
        )
        == 0
    )
    material_set_id = json.loads(issued_output[0])["material_set_id"]
    status, output = _invoke(
        [*state_args, "create-authored-package", "--package-name", "document-helper"]
    )
    assert status == 0

    for source in sorted(TEMPLATE_ROOT.iterdir()):
        written: list[str] = []
        assert (
            main(
                [
                    *state_args,
                    "write-authored-package-file",
                    "--authoring-output-id",
                    output["authoring_output_id"],
                    "--relative-path",
                    source.name,
                    "--content-stdin",
                ],
                write=written.append,
                read_stdin=lambda source=source: source.read_text(encoding="utf-8"),
            )
            == 0
        )
        assert json.loads(written[0])["byte_count"] == source.stat().st_size

    status, finalized = _invoke(
        [
            *state_args,
            "finalize-authored-package",
            "--authoring-output-id",
            output["authoring_output_id"],
            "--material-set-id",
            material_set_id,
        ]
    )

    assert status == 0
    assert finalized["status"] == "finalized"
    assert (package_root / "document-helper" / "package-manifest.json").is_file()


def test_cli_dry_runs_a_host_owned_package_by_name(tmp_path: Path) -> None:
    root = tmp_path / "state"
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    state_args = ["--state-root", str(root)]
    status, _ = _invoke(
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

    status, result = _invoke(
        [
            *state_args,
            "invoke",
            "--package-name",
            "document-helper",
            "--workflow-id",
            "document-helper",
            "--prompt",
            "Answer the document question.",
            "--dry-run",
        ]
    )

    assert status == 0
    assert result == {"status": "ready", "workflow_id": "document-helper"}


def _signed_archive(
    source: Path, *, key_id: str, private_key: Ed25519PrivateKey
) -> Path:
    digest = hashlib.sha256()
    files = []
    for path in sorted(source.iterdir()):
        body = path.read_bytes()
        file_digest = hashlib.sha256(body).hexdigest()
        digest.update(f"{path.name}\0{file_digest}\0{len(body)}\n".encode("utf-8"))
        files.append(
            {"byte_count": len(body), "path": path.name, "sha256": file_digest}
        )
    manifest = json.dumps(
        {
            "content_digest": digest.hexdigest(),
            "dar_runtime": {
                "distribution": "dynamic-agent-runner",
                "required_version": "0.1.16",
            },
            "descriptor_format_version": 1,
            "files": files,
            "format_version": 2,
            "package_id": "dar-authoring-no-tool-template",
            "runtime_format_version": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    (source / "package-manifest.json").write_bytes(manifest)
    signature = private_key.sign(manifest)
    (source / "package-signature.json").write_text(
        json.dumps(
            {
                "algorithm": "ed25519",
                "format_version": 1,
                "key_id": key_id,
                "signature": base64.b64encode(signature).decode("ascii"),
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    archive = source.parent / "document-helper.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for path in sorted(source.iterdir()):
            package.write(path, path.name)
    return archive


def test_cli_manages_human_trusted_publisher_keys(tmp_path: Path) -> None:
    state_args = ["--state-root", str(tmp_path / "state")]
    key_id = "publisher.example.v1"
    public_key = base64.b64encode(
        Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    ).decode("ascii")

    status, added = _invoke(
        [
            *state_args,
            "trust-publisher",
            "--key-id",
            key_id,
            "--public-key-base64",
            public_key,
        ]
    )
    assert status == 0
    assert added["key_id"] == key_id
    status, listed = _invoke([*state_args, "list-trusted-publishers"])
    assert status == 0
    assert listed["publishers"][0]["key_id"] == key_id
    status, revoked = _invoke(
        [*state_args, "revoke-trusted-publisher", "--key-id", key_id]
    )
    assert status == 0
    assert revoked == {"key_id": key_id, "status": "revoked"}


def test_cli_exports_a_signed_package_with_key_material_only_on_stdin(
    tmp_path: Path,
) -> None:
    root = tmp_path / "state"
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    state_args = ["--state-root", str(root)]
    key_id = "publisher.example.v1"
    private_key = Ed25519PrivateKey.generate()

    status, _ = _invoke(
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
    status, selected = _invoke([*state_args, "select-package", "--path", str(source)])
    assert status == 0
    status, previewed = _invoke(
        [
            *state_args,
            "preview-package",
            "--package-source-handle",
            selected["package_source_handle"],
        ]
    )
    assert status == 0
    assert previewed["status"] == "previewed"
    output: list[str] = []
    private_key_base64 = base64.b64encode(private_key.private_bytes_raw()).decode(
        "ascii"
    )
    archive = package_root / "document-helper-signed.zip"

    status = main(
        [
            *state_args,
            "export-signed-package",
            "--package-source-handle",
            selected["package_source_handle"],
            "--destination",
            str(archive),
            "--key-id",
            key_id,
            "--expected-content-digest",
            previewed["content_digest"],
            "--private-key-stdin",
        ],
        write=output.append,
        read_stdin=lambda: private_key_base64,
    )

    assert status == 0
    exported = json.loads(output[0])
    assert exported["status"] == "exported"
    assert exported["byte_count"] == archive.stat().st_size
    assert len(exported["content_digest"]) == 64
    assert exported["publisher_key_id"] == key_id
    assert private_key_base64 not in output[0]


def test_cli_does_not_read_a_signing_key_without_digest_confirmation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "state"
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    state_args = ["--state-root", str(root)]

    status, _ = _invoke(
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
    status, selected = _invoke([*state_args, "select-package", "--path", str(source)])
    assert status == 0

    key_was_read = False

    def read_key() -> str:
        nonlocal key_was_read
        key_was_read = True
        return "not-used"

    assert (
        main(
            [
                *state_args,
                "export-signed-package",
                "--package-source-handle",
                selected["package_source_handle"],
                "--destination",
                str(package_root / "signed.zip"),
                "--key-id",
                "publisher.example.v1",
                "--expected-content-digest",
                "wrong",
                "--private-key-stdin",
            ],
            read_stdin=read_key,
        )
        == 2
    )
    assert not key_was_read


def test_cli_registers_a_trusted_publisher_signed_zip(tmp_path: Path) -> None:
    root = tmp_path / "state"
    package_root = tmp_path / "packages"
    source = package_root / "document-helper"
    shutil.copytree(TEMPLATE_ROOT, source)
    key_id = "publisher.example.v1"
    private_key = Ed25519PrivateKey.generate()
    archive = _signed_archive(source, key_id=key_id, private_key=private_key)
    state_args = ["--state-root", str(root)]

    status, _ = _invoke(
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
    status, _ = _invoke(
        [
            *state_args,
            "trust-publisher",
            "--key-id",
            key_id,
            "--public-key-base64",
            base64.b64encode(private_key.public_key().public_bytes_raw()).decode(
                "ascii"
            ),
        ]
    )
    assert status == 0
    status, selected = _invoke(
        [
            *state_args,
            "select-package",
            "--path",
            str(archive),
            "--publisher-signed",
        ]
    )
    assert status == 0
    status, _ = _invoke(
        [
            *state_args,
            "register",
            "--workflow-id",
            "publisher-package",
            "--package-source-handle",
            selected["package_source_handle"],
        ]
    )

    assert status == 0
    catalog = json.loads((root / "catalog" / "packages.json").read_text())
    revisions = catalog["packages"]["dar-authoring-no-tool-template"]
    assert len(revisions) == 1
    revision = next(iter(revisions.values()))
    assert revision["trust"] == "publisher_signature"
    assert revision["publisher_key_id"] == key_id


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
                "--ask",
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
    assert "document body" not in json.dumps(artifact)

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
    assert "document body" not in json.dumps(prepared)


def test_run_cli_passes_ask_as_a_host_only_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class Host:
        def run(self, **kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(
                status="completed", run_id="run-1", output={"message": "done"}
            )

    monkeypatch.setattr(cli.LocalWorkflowHost, "open", lambda root: Host())
    output: list[str] = []

    assert (
        run_main(
            [
                "--state-root",
                "/tmp/dar-authoring-test",
                "--workflow-id",
                "mail-reader",
                "--prepared-input-id",
                "v1.input.signature",
                "--ask",
            ],
            write=output.append,
        )
        == 0
    )

    assert len(calls) == 1
    assert calls[0]["workflow_id"] == "mail-reader"
    assert calls[0]["prepared_input_id"] == "v1.input.signature"
    assert calls[0]["approval_broker"] is not None
    assert output == ['{"message":"done","run_id":"run-1","status":"completed"}']


def test_cli_configures_generic_mcp_connection_without_exposing_api_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def create(**kwargs: object) -> SimpleNamespace:
        calls.append(("create", kwargs))
        return SimpleNamespace(connection_id="v1.connection")

    def configure_token(**kwargs: object) -> SimpleNamespace:
        calls.append(("token", kwargs))
        return SimpleNamespace(authentication_id="v1.authentication")

    def attach(**kwargs: object) -> SimpleNamespace:
        calls.append(("attach", kwargs))
        return SimpleNamespace()

    monkeypatch.setattr(cli, "create_mcp_connection", create)
    monkeypatch.setattr(cli, "configure_mcp_api_token", configure_token)
    monkeypatch.setattr(cli, "attach_mcp_client", attach)
    state_args = ["--state-root", "/tmp/dar-authoring-test"]

    status, connection = _invoke(
        [
            *state_args,
            "create-mcp-connection",
            "--endpoint",
            "https://mcp.example.test/v1",
            "--scope",
            "mail.read",
            "--authentication-method",
            "api_token",
        ]
    )
    assert status == 0
    assert connection == {"connection_id": "v1.connection", "status": "created"}

    output: list[str] = []
    status = main(
        [
            *state_args,
            "configure-mcp-api-token",
            "--connection-id",
            "v1.connection",
            "--token-stdin",
        ],
        write=output.append,
        read_stdin=lambda: "secret-token\n",
    )
    assert status == 0
    assert json.loads(output[0]) == {
        "authentication_id": "v1.authentication",
        "status": "authenticated",
    }
    assert "secret-token" not in output[0]

    status, attached = _invoke(
        [
            *state_args,
            "attach-mcp-client",
            "--connection-id",
            "v1.connection",
            "--authentication-id",
            "v1.authentication",
            "--peer-certificate-sha256",
            "a" * 64,
        ]
    )
    assert status == 0
    assert attached == {"status": "attached"}
    assert calls == [
        (
            "create",
            {
                "root": Path("/tmp/dar-authoring-test"),
                "endpoint": "https://mcp.example.test/v1",
                "scopes": ["mail.read"],
                "authentication_method": "api_token",
            },
        ),
        (
            "token",
            {
                "root": Path("/tmp/dar-authoring-test"),
                "connection_id": "v1.connection",
                "token": "secret-token",
            },
        ),
        (
            "attach",
            {
                "root": Path("/tmp/dar-authoring-test"),
                "connection_id": "v1.connection",
                "authentication_id": "v1.authentication",
                "peer_certificate_sha256": "a" * 64,
                "timeout_seconds": 10,
                "max_response_bytes": 32_768,
            },
        ),
    ]


def test_cli_authorizes_generic_mcp_oauth_through_human_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def authorize(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(authentication_id="v1.authentication")

    monkeypatch.setattr(cli, "authorize_mcp_oauth", authorize)
    output: list[str] = []

    assert (
        main(
            [
                "--state-root",
                "/tmp/dar-authoring-test",
                "authorize-mcp-oauth",
                "--connection-id",
                "v1.connection",
                "--authorization-endpoint",
                "https://login.example.test/authorize",
                "--token-endpoint",
                "https://login.example.test/token",
                "--client-id",
                "public-client",
            ],
            write=output.append,
        )
        == 0
    )
    assert json.loads(output[0]) == {
        "authentication_id": "v1.authentication",
        "status": "authenticated",
    }
    assert calls == [
        {
            "root": Path("/tmp/dar-authoring-test"),
            "connection_id": "v1.connection",
            "authorization_endpoint": "https://login.example.test/authorize",
            "token_endpoint": "https://login.example.test/token",
            "client_id": "public-client",
        }
    ]


def test_cli_inspects_reviews_binds_and_registers_mcp_workflows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class Host:
        def discover_mcp_tools(self) -> tuple[SimpleNamespace, ...]:
            return (
                SimpleNamespace(name="list_unread", input_schema={"type": "object"}),
            )

        def review_mcp_surface(self, **kwargs: object) -> SimpleNamespace:
            calls.append(("review", kwargs))
            return SimpleNamespace(snapshot_id="v1.snapshot")

        def bind_mcp_package(self, **kwargs: object) -> SimpleNamespace:
            calls.append(("bind", kwargs))
            return SimpleNamespace(binding_id="v1.binding")

        def register(self, **kwargs: object) -> SimpleNamespace:
            calls.append(("register", kwargs))
            return SimpleNamespace(
                workflow_id="mail-reader",
                registration_digest="a" * 64,
                profile_id="v1.profile",
            )

    monkeypatch.setattr(cli.LocalWorkflowHost, "open", lambda root: Host())
    state_args = ["--state-root", "/tmp/dar-authoring-test"]

    status, tools = _invoke([*state_args, "inspect-mcp-tools"])
    assert status == 0
    assert tools == {
        "tools": [{"input_schema": {"type": "object"}, "name": "list_unread"}]
    }

    status, snapshot = _invoke(
        [
            *state_args,
            "review-mcp-surface",
            "--approve-read-tool",
            "list_unread",
        ]
    )
    assert status == 0
    assert snapshot == {"snapshot_id": "v1.snapshot", "status": "reviewed"}

    status, binding = _invoke(
        [
            *state_args,
            "bind-mcp-package",
            "--package-source-handle",
            "v1.source",
            "--snapshot-id",
            "v1.snapshot",
        ]
    )
    assert status == 0
    assert binding == {"binding_id": "v1.binding", "status": "bound"}

    status, registration = _invoke(
        [
            *state_args,
            "register",
            "--workflow-id",
            "mail-reader",
            "--package-source-handle",
            "v1.source",
            "--mcp-binding-id",
            "v1.binding",
        ]
    )
    assert status == 0
    assert registration["workflow_id"] == "mail-reader"
    assert calls[0] == (
        "review",
        {
            "approved_read_only_tool_names": ["list_unread"],
            "approved_tool_side_effects": {},
        },
    )
    assert calls[1][0] == "bind"
    assert calls[1][1]["package_source_handle"] == "v1.source"
    assert calls[1][1]["snapshot_id"] == "v1.snapshot"
    assert calls[2][0] == "register"
    assert calls[2][1]["mcp_binding_id"] == "v1.binding"
