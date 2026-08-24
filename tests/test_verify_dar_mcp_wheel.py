"""Tests for the local DAR-wheel MCP verification script."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import zipfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPOSITORY_ROOT / "scripts" / "verify_dar_mcp_wheel.py"


def _write_wheel(path: Path, *, version: str = "9.8.7") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"dynamic_agent_runner-{version}.dist-info/METADATA",
            f"Name: dynamic-agent-runner\nVersion: {version}\n",
        )


def _write_fake_uvx(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            from pathlib import Path
            import sys

            Path(os.environ["FAKE_UVX_CAPTURE"]).write_text(
                json.dumps(
                    {
                        "argv": sys.argv[1:],
                        "cwd": os.getcwd(),
                        "uv_cache_dir": os.environ.get("UV_CACHE_DIR"),
                        "uv_tool_dir": os.environ.get("UV_TOOL_DIR"),
                    }
                )
            )
            for line in sys.stdin:
                request = json.loads(line)
                if request.get("id") == 1:
                    response = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "protocolVersion": "2025-06-18",
                            "serverInfo": {
                                "name": "Dynamic Agent Runner",
                                "version": "9.8.7",
                            },
                        },
                    }
                elif request.get("id") == 2:
                    response = {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {"tools": []},
                    }
                else:
                    continue
                print(json.dumps(response), flush=True)
            """
        )
    )
    path.chmod(0o755)


def test_verifier_runs_local_wheel_with_isolated_uvx_environment(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "dynamic_agent_runner-9.8.7-py3-none-any.whl"
    fake_uvx = tmp_path / "uvx"
    capture = tmp_path / "uvx-invocation.json"
    _write_wheel(wheel)
    _write_fake_uvx(fake_uvx)

    result = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--wheel",
            str(wheel),
            "--uvx",
            str(fake_uvx),
        ],
        cwd=tmp_path,
        env={**os.environ, "FAKE_UVX_CAPTURE": str(capture)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "server_name": "Dynamic Agent Runner",
        "tools": [],
        "version": "9.8.7",
        "wheel": str(wheel.resolve()),
    }
    invocation = json.loads(capture.read_text())
    assert invocation["argv"] == [
        "--from",
        str(wheel.resolve()),
        "dynamic-agent-runner-mcp",
        "--stdio",
    ]
    invocation_directory = Path(invocation["cwd"])
    assert invocation_directory.name.startswith("dar-mcp-wheel-")
    cache_directory = Path(invocation["uv_cache_dir"])
    tool_directory = Path(invocation["uv_tool_dir"])
    assert cache_directory.name == "uv-cache"
    assert tool_directory.name == "uv-tools"
    assert cache_directory.parent.name == invocation_directory.name
    assert tool_directory.parent.name == invocation_directory.name
