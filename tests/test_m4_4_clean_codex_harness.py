"""Tests for the M4.4 clean-process Codex launch contract."""

from __future__ import annotations

import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from dynamic_agent_runner.workflow_host.m4_4_clean_codex import (  # noqa: E402
    M44CleanCodexError,
    build_clean_codex_environment,
    build_clean_codex_run_environment,
    create_marketplace,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "scripts" / "run_m4_4_clean_codex.py"
SCENARIO = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "dar-authoring"
    / "m4-4"
    / "document-summary.json"
)


class _ModelHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
        body = json.dumps(
            {
                "id": "m44-local-response",
                "model": "openai/local-test-model",
                "object": "response",
                "output_text": "summary",
                "status": "completed",
                "choices": [{"message": {"content": "summary"}}],
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "summary"}],
                    }
                ],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_arguments: object) -> None:
        return


def _fake_codex_actor(tmp_path: Path) -> Path:
    template = REPO_ROOT / "dar-authoring" / "templates"
    files = {}
    for path in template.rglob("*"):
        if not path.is_file():
            continue
        content = path.read_bytes()
        if path.name == "agent-runtime.yaml":
            content = content.replace(b"local-model", b"openai/local-test-model")
        files[path.relative_to(template).as_posix()] = base64.b64encode(
            content
        ).decode()
    actor = tmp_path / "fake-codex"
    actor.write_text(
        "\n".join(
            (
                f"#!{sys.executable}",
                "import base64, json, os, socket, sys",
                f"FILES = {files!r}",
                "def request(connection, value):",
                "    connection.sendall((json.dumps(value) + '\\n').encode())",
                "    return json.loads(connection.makefile('r', encoding='utf-8').readline())",
                "def connect():",
                "    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)",
                "    connection.connect(os.environ['DAR_AUTHORING_BROKER_SOCKET'])",
                "    request(connection, {'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})",
                '    connection.sendall(b\'{\\"jsonrpc\\":\\"2.0\\",\\"method\\":\\"notifications/initialized\\"}\\n\')',
                "    return connection",
                "if sys.argv[1:] == ['--version']:",
                "    print('codex-cli test')",
                "elif 'exec' in sys.argv and os.environ.get('DAR_AUTHORING_MCP_MODE') == 'authoring':",
                "    connection = connect()",
                "    created = request(connection, {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'create_authored_package','arguments':{'format_version':1}}})",
                "    output_id = created['result']['structuredContent']['authoring_output_id']",
                "    for number, (path, encoded) in enumerate(FILES.items(), start=3):",
                "        request(connection, {'jsonrpc':'2.0','id':number,'method':'tools/call','params':{'name':'write_authored_package_file','arguments':{'format_version':1,'authoring_output_id':output_id,'relative_path':path,'content':base64.b64decode(encoded).decode()}}})",
                "    request(connection, {'jsonrpc':'2.0','id':99,'method':'tools/call','params':{'name':'finalize_authored_package','arguments':{'format_version':1,'authoring_output_id':output_id}}})",
                "    connection.close()",
                "elif 'exec' in sys.argv and os.environ.get('DAR_AUTHORING_MCP_MODE') == 'run':",
                "    connection = connect()",
                "    response = request(connection, {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'run_dar_workflow','arguments':{'format_version':1,'workflow_id':'document-summary','prompt':'Summarize this document.'}}})",
                "    connection.close()",
                "    raise SystemExit(0 if 'result' in response else 1)",
                "raise SystemExit(0)",
            )
        ),
        encoding="utf-8",
    )
    actor.chmod(0o755)
    return actor


def test_clean_codex_environment_keeps_only_declared_launch_values(
    tmp_path: Path,
) -> None:
    environment = build_clean_codex_environment(
        codex_home=tmp_path / "codex-home",
        working_directory=tmp_path / "workspace",
        wheel=tmp_path / "dynamic_agent_runner.whl",
        broker_socket=tmp_path / "broker.sock",
        inherited={
            "HOME": "/Users/operator",
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": "/source",
            "VIRTUAL_ENV": "/venv",
            "OPENAI_API_KEY": "operator-secret",
        },
    )

    assert environment == {
        "CODEX_HOME": str(tmp_path / "codex-home"),
        "DAR_AUTHORING_BROKER_SOCKET": str(tmp_path / "broker.sock"),
        "DAR_AUTHORING_DAR_WHEEL": str(tmp_path / "dynamic_agent_runner.whl"),
        "DAR_AUTHORING_MCP_MODE": "authoring",
        "HOME": str(tmp_path / "workspace"),
        "LANG": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }


def test_clean_codex_run_environment_exposes_only_a_controller_broker(
    tmp_path: Path,
) -> None:
    environment = build_clean_codex_run_environment(
        codex_home=tmp_path / "codex-home",
        working_directory=tmp_path / "workspace",
        wheel=tmp_path / "dynamic_agent_runner.whl",
        broker_socket=tmp_path / "broker.sock",
        inherited={"PATH": "/usr/bin:/bin", "OPENAI_API_KEY": "operator-secret"},
    )

    assert environment == {
        "CODEX_HOME": str(tmp_path / "codex-home"),
        "DAR_AUTHORING_DAR_WHEEL": str(tmp_path / "dynamic_agent_runner.whl"),
        "DAR_AUTHORING_BROKER_SOCKET": str(tmp_path / "broker.sock"),
        "DAR_AUTHORING_MCP_MODE": "run",
        "HOME": str(tmp_path / "workspace"),
        "LANG": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }


def test_clean_codex_environment_rejects_unsafe_or_missing_launch_paths(
    tmp_path: Path,
) -> None:
    with pytest.raises(M44CleanCodexError):
        build_clean_codex_environment(
            codex_home=Path("relative"),
            working_directory=tmp_path / "workspace",
            wheel=tmp_path / "dynamic_agent_runner.whl",
            broker_socket=tmp_path / "broker.sock",
            inherited={"PATH": "/usr/bin:/bin"},
        )


def test_marketplace_contains_only_the_copied_plugin(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    destination = tmp_path / "marketplace"

    marketplace = create_marketplace(plugin_root=plugin, destination=destination)

    assert marketplace == destination / ".agents" / "plugins" / "marketplace.json"
    assert (
        destination / "plugins" / "dar-authoring" / ".codex-plugin" / "plugin.json"
    ).is_file()
    assert marketplace.read_text(encoding="utf-8") == (
        '{"name":"m44-clean-codex","plugins":[{"category":"Productivity",'
        '"name":"dar-authoring","policy":{"authentication":"ON_INSTALL",'
        '"installation":"AVAILABLE"},"source":{"path":"./plugins/dar-authoring",'
        '"source":"local"}}]}'
    )


def test_marketplace_rejects_a_plugin_symlink(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (plugin / "escape").symlink_to(tmp_path / "outside")

    with pytest.raises(M44CleanCodexError, match="symbolic link"):
        create_marketplace(plugin_root=plugin, destination=tmp_path / "marketplace")


def test_external_harness_requires_a_pre_authenticated_test_profile(
    tmp_path: Path,
) -> None:
    materials = tmp_path / "materials.json"
    materials.write_text(
        '[{"content":"Build a document helper.","disposition":"reference_only",'
        '"role":"goal"}]',
        encoding="utf-8",
    )
    wheel = tmp_path / "dynamic_agent_runner.whl"
    wheel.write_bytes(b"wheel")
    completed = subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "--scenario",
            str(SCENARIO),
            "--codex-home",
            str(tmp_path / "no-auth"),
            "--plugin-root",
            str(REPO_ROOT / "dar-authoring"),
            "--wheel",
            str(wheel),
            "--materials",
            str(materials),
            "--package-name",
            "document-summary",
            "--workflow-id",
            "document-summary",
            "--author-prompt",
            "Build a document helper.",
            "--run-prompt",
            "Summarize this document.",
            "--model-id",
            "local-test-model",
            "--base-url",
            "http://127.0.0.1:11434/v1",
            "--evidence",
            str(tmp_path / "evidence" / "author-then-run.json"),
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
    )

    assert completed.returncode == 2
    assert "pre-authenticated test profile" in completed.stdout


def test_external_harness_records_a_redacted_authoring_failure(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    materials = tmp_path / "materials.json"
    materials.write_text(
        '[{"content":"private document content","disposition":"reference_only",'
        '"role":"goal"}]',
        encoding="utf-8",
    )
    wheel = tmp_path / "dynamic_agent_runner.whl"
    wheel.write_bytes(b"wheel")
    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text(
        "\n".join(
            (
                f"#!{sys.executable}",
                "import os, socket, sys",
                "if sys.argv[1:] == ['--version']:",
                "    print('codex-cli test')",
                "elif 'exec' in sys.argv:",
                "    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)",
                "    connection.connect(os.environ['DAR_AUTHORING_BROKER_SOCKET'])",
                '    connection.sendall(b\'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\\n\')',
                "    connection.recv(4096)",
                "    connection.close()",
                "    raise SystemExit(1)",
                "else:",
                "    raise SystemExit(0)",
            )
        ),
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    evidence = tmp_path / "evidence" / "author-then-run.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "--scenario",
            str(SCENARIO),
            "--codex-home",
            str(codex_home),
            "--plugin-root",
            str(REPO_ROOT / "dar-authoring"),
            "--wheel",
            str(wheel),
            "--materials",
            str(materials),
            "--package-name",
            "document-summary",
            "--workflow-id",
            "document-summary",
            "--author-prompt",
            "Build a document helper.",
            "--run-prompt",
            "Summarize this document.",
            "--model-id",
            "local-test-model",
            "--base-url",
            "http://127.0.0.1:11434/v1",
            "--evidence",
            str(evidence),
            "--codex-executable",
            str(fake_codex),
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
    )

    assert completed.returncode == 0, completed.stdout
    recorded = evidence.read_text(encoding="utf-8")
    assert json.loads(recorded)["observed_status"] == "harness_failure"
    assert json.loads(recorded)["terminal_phase"] == "authoring_validation"
    assert "private document content" not in recorded


def test_external_harness_requires_authoring_finalization_before_registration(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    materials = tmp_path / "materials.json"
    materials.write_text(
        '[{"content":"Build a document helper.","disposition":"reference_only",'
        '"role":"goal"}]',
        encoding="utf-8",
    )
    wheel = tmp_path / "dynamic_agent_runner.whl"
    wheel.write_bytes(b"wheel")
    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text(
        "\n".join(
            (
                f"#!{sys.executable}",
                "import sys",
                "if sys.argv[1:] == ['--version']:",
                "    print('codex-cli test')",
                "raise SystemExit(0)",
            )
        ),
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    evidence = tmp_path / "evidence" / "author-then-run.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "--scenario",
            str(SCENARIO),
            "--codex-home",
            str(codex_home),
            "--plugin-root",
            str(REPO_ROOT / "dar-authoring"),
            "--wheel",
            str(wheel),
            "--materials",
            str(materials),
            "--package-name",
            "document-summary",
            "--workflow-id",
            "document-summary",
            "--author-prompt",
            "Build a document helper.",
            "--run-prompt",
            "Summarize this document.",
            "--model-id",
            "local-test-model",
            "--base-url",
            "http://127.0.0.1:11434/v1",
            "--evidence",
            str(evidence),
            "--codex-executable",
            str(fake_codex),
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
    )

    assert completed.returncode == 0, completed.stdout
    assert json.loads(evidence.read_text(encoding="utf-8"))["terminal_phase"] == (
        "authoring_validation"
    )


def test_external_harness_records_a_completed_author_then_run_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-key")
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    materials = tmp_path / "materials.json"
    materials.write_text(
        '[{"content":"Build a document helper.","disposition":"reference_only",'
        '"role":"goal"}]',
        encoding="utf-8",
    )
    wheel = tmp_path / "dynamic_agent_runner.whl"
    wheel.write_bytes(b"wheel")
    evidence = tmp_path / "evidence" / "author-then-run.json"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(HARNESS),
                "--scenario",
                str(SCENARIO),
                "--codex-home",
                str(codex_home),
                "--plugin-root",
                str(REPO_ROOT / "dar-authoring"),
                "--wheel",
                str(wheel),
                "--materials",
                str(materials),
                "--package-name",
                "document-summary",
                "--workflow-id",
                "document-summary",
                "--author-prompt",
                "Build a document helper.",
                "--run-prompt",
                "Summarize this document.",
                "--model-id",
                "openai/local-test-model",
                "--base-url",
                f"http://127.0.0.1:{server.server_port}/v1",
                "--evidence",
                str(evidence),
                "--codex-executable",
                str(_fake_codex_actor(tmp_path)),
            ],
            capture_output=True,
            check=False,
            encoding="utf-8",
        )
    finally:
        server.shutdown()
        thread.join()

    assert completed.returncode == 0, completed.stdout
    recorded = json.loads(evidence.read_text(encoding="utf-8"))
    assert recorded["observed_status"] == "pending_human_review"
    assert recorded["terminal_phase"] == "invocation"
    assert recorded["action_trace_digest"]
    assert recorded["dispatch_count"] == 0
    assert recorded["final_package_digest"] == recorded["catalog_revision_digest"]
