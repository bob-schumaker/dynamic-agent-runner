"""Tests for the local DAR-package wheel verification script."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import zipfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPOSITORY_ROOT / "scripts" / "verify_dar_package_wheel.py"


def _record_digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode(
        "ascii"
    ).rstrip("=")


def _write_wheel(
    path: Path, *, version: str = "9.8.7", corrupt_record: bool = False
) -> None:
    metadata_name = f"dynamic_agent_runner-{version}.dist-info/METADATA"
    entry_points_name = f"dynamic_agent_runner-{version}.dist-info/entry_points.txt"
    package_name = "dynamic_agent_runner/dar_package_cli.py"
    record_name = f"dynamic_agent_runner-{version}.dist-info/RECORD"
    metadata = f"Name: dynamic-agent-runner\nVersion: {version}\n".encode()
    entry_points = b"[console_scripts]\ndar-package=dynamic_agent_runner.dar_package_cli:console_main\n"
    package = b'"""test package"""\n'
    recorded_package = b"corrupted package\n" if corrupt_record else package
    entries = {
        metadata_name: metadata,
        entry_points_name: entry_points,
        package_name: package,
    }
    record = "\n".join(
        [
            f"{name},{_record_digest(recorded_package if name == package_name else data)},{len(data)}"
            for name, data in entries.items()
        ]
        + [f"{record_name},,"]
    )
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        archive.writestr(record_name, record)


def _write_fake_uv(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            from pathlib import Path
            import sys

            Path(os.environ["FAKE_UV_CAPTURE"]).write_text(
                json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()})
            )
            print(json.dumps({
                "distribution": "dynamic-agent-runner",
                "format_version": 1,
                "status": "ok",
                "version": os.environ["FAKE_UV_VERSION"],
            }))
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_verifier_runs_dar_package_from_an_isolated_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "dynamic_agent_runner-9.8.7-py3-none-any.whl"
    fake_uv = tmp_path / "uv"
    capture = tmp_path / "uv-invocation.json"
    _write_wheel(wheel)
    _write_fake_uv(fake_uv)

    result = subprocess.run(
        [sys.executable, str(VERIFIER), "--wheel", str(wheel), "--uv", str(fake_uv)],
        cwd=tmp_path,
        env={
            **os.environ,
            "FAKE_UV_CAPTURE": str(capture),
            "FAKE_UV_VERSION": "9.8.7",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "distribution": "dynamic-agent-runner",
        "format_version": 1,
        "status": "ok",
        "version": "9.8.7",
        "wheel": str(wheel.resolve()),
    }
    invocation = json.loads(capture.read_text(encoding="utf-8"))
    assert invocation["argv"] == [
        "run",
        "--no-project",
        "--python",
        "3.14",
        "--with",
        str(wheel.resolve()),
        "dar-package",
        "version",
        "--json",
    ]
    assert Path(invocation["cwd"]).name.startswith("dar-package-wheel-")


def test_verifier_rejects_a_wheel_with_a_corrupted_record_hash(tmp_path: Path) -> None:
    wheel = tmp_path / "dynamic_agent_runner-9.8.7-py3-none-any.whl"
    fake_uv = tmp_path / "uv"
    capture = tmp_path / "uv-invocation.json"
    _write_wheel(wheel, corrupt_record=True)
    _write_fake_uv(fake_uv)

    result = subprocess.run(
        [sys.executable, str(VERIFIER), "--wheel", str(wheel), "--uv", str(fake_uv)],
        cwd=tmp_path,
        env={
            **os.environ,
            "FAKE_UV_CAPTURE": str(capture),
            "FAKE_UV_VERSION": "9.8.7",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "wheel RECORD hash is invalid" in result.stderr
    assert not capture.exists()
