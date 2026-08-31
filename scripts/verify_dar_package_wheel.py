"""Verify the ``dar-package`` entry point from one local DAR wheel."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import zipfile

from verify_dar_mcp_wheel import (
    VerificationError,
    _verify_wheel_record,
    _wheel_version,
)


def _verify_dar_package_entry_point(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        paths = [
            name
            for name in archive.namelist()
            if name.endswith(".dist-info/entry_points.txt")
        ]
        if len(paths) != 1:
            raise VerificationError("wheel must contain exactly one entry_points.txt")
        entry_points = archive.read(paths[0]).decode("utf-8")
    expected = "dar-package=dynamic_agent_runner.dar_package_cli:console_main"
    if expected not in entry_points.splitlines():
        raise VerificationError("wheel does not declare the dar-package entry point")


def verify_local_wheel(*, wheel: Path, uv: str, timeout: float) -> dict[str, Any]:
    """Run ``dar-package version --json`` from ``wheel`` in an isolated cwd."""

    resolved_wheel = wheel.resolve()
    if not resolved_wheel.is_file():
        raise VerificationError(f"wheel does not exist: {resolved_wheel}")
    _verify_wheel_record(resolved_wheel)
    _verify_dar_package_entry_point(resolved_wheel)
    expected_version = _wheel_version(resolved_wheel)
    with tempfile.TemporaryDirectory(
        prefix="dar-package-wheel-"
    ) as temporary_directory:
        temporary_path = Path(temporary_directory)
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["UV_CACHE_DIR"] = str(temporary_path / "uv-cache")
        try:
            result = subprocess.run(
                [
                    uv,
                    "run",
                    "--no-project",
                    "--python",
                    "3.14",
                    "--with",
                    str(resolved_wheel),
                    "dar-package",
                    "version",
                    "--json",
                ],
                cwd=temporary_path,
                env=environment,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except OSError as error:
            raise VerificationError(f"could not start uv: {error}") from error
        except subprocess.TimeoutExpired as error:
            raise VerificationError(
                f"dar-package did not exit within {timeout} seconds"
            ) from error
    if result.returncode:
        raise VerificationError(
            f"dar-package exited {result.returncode}: {result.stderr.strip()}"
        )
    try:
        receipt = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise VerificationError("dar-package emitted invalid JSON") from error
    if receipt != {
        "distribution": "dynamic-agent-runner",
        "format_version": 1,
        "status": "ok",
        "version": expected_version,
    }:
        raise VerificationError("dar-package receipt does not match wheel metadata")
    return {**receipt, "wheel": str(resolved_wheel)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--timeout", default=60.0, type=float)
    arguments = parser.parse_args()
    try:
        print(json.dumps(verify_local_wheel(**vars(arguments)), sort_keys=True))
    except VerificationError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
