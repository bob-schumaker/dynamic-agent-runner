"""Narrow discovery surface for the DAR package control plane."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from importlib.metadata import version
from typing import TextIO


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the non-mutating v1 DAR package discovery command."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    if arguments != ["version", "--json"]:
        _write(stderr, _error("usage"))
        return 2
    try:
        distribution_version = _distribution_version()
    except Exception:  # noqa: BLE001 - receipt intentionally hides host details.
        _write(stderr, _error("internal"))
        return 1
    _write(
        stdout,
        {
            "format_version": 1,
            "status": "ok",
            "distribution": "dynamic-agent-runner",
            "version": distribution_version,
        },
    )
    return 0


def _distribution_version() -> str:
    return version("dynamic-agent-runner")


def _error(error_code: str) -> dict[str, object]:
    return {"format_version": 1, "status": "error", "error_code": error_code}


def _write(stream: TextIO, value: dict[str, object]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")), file=stream)


def console_main() -> None:
    """Console-script entry point."""

    raise SystemExit(main())
