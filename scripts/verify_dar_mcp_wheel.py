#!/usr/bin/env python3
"""Verify that a local DAR wheel serves the MCP endpoint through ``uvx``."""

from __future__ import annotations

import argparse
from email.parser import BytesParser
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import zipfile


class VerificationError(Exception):
    """The local wheel did not satisfy the MCP smoke-check contract."""


def _wheel_version(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        metadata_paths = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise VerificationError(
                "wheel must contain exactly one dist-info METADATA file"
            )
        metadata = BytesParser().parsebytes(archive.read(metadata_paths[0]))
    if metadata["Name"] != "dynamic-agent-runner" or not metadata["Version"]:
        raise VerificationError(
            "wheel must identify dynamic-agent-runner and a version"
        )
    return metadata["Version"]


def _response_by_id(output: str, request_id: int) -> dict[str, Any]:
    for line in output.splitlines():
        try:
            response = json.loads(line)
        except json.JSONDecodeError as error:
            raise VerificationError(
                f"MCP server emitted non-JSON output: {line!r}"
            ) from error
        if response.get("id") == request_id:
            return response
    raise VerificationError(f"MCP server did not respond to request {request_id}")


def _verify_responses(output: str, expected_version: str) -> list[dict[str, Any]]:
    initialized = _response_by_id(output, 1)
    server_info = initialized.get("result", {}).get("serverInfo")
    expected_info = {"name": "Dynamic Agent Runner", "version": expected_version}
    if server_info != expected_info:
        raise VerificationError(
            f"unexpected MCP server identity: expected {expected_info!r}, got {server_info!r}"
        )
    tools_response = _response_by_id(output, 2)
    tools = tools_response.get("result", {}).get("tools")
    if not isinstance(tools, list):
        raise VerificationError("MCP tools/list response must contain a tools array")
    return tools


def verify_local_wheel(*, wheel: Path, uvx: str, timeout: float) -> dict[str, Any]:
    """Run the MCP server from ``wheel`` in a clean temporary environment."""
    resolved_wheel = wheel.resolve()
    if not resolved_wheel.is_file():
        raise VerificationError(f"wheel does not exist: {resolved_wheel}")
    expected_version = _wheel_version(resolved_wheel)
    requests = (
        "\n".join(
            json.dumps(request)
            for request in (
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            )
        )
        + "\n"
    )
    with tempfile.TemporaryDirectory(prefix="dar-mcp-wheel-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["UV_CACHE_DIR"] = str(temporary_path / "uv-cache")
        environment["UV_TOOL_DIR"] = str(temporary_path / "uv-tools")
        try:
            result = subprocess.run(
                [
                    uvx,
                    "--from",
                    str(resolved_wheel),
                    "dynamic-agent-runner-mcp",
                    "--stdio",
                ],
                cwd=temporary_path,
                env=environment,
                input=requests,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except OSError as error:
            raise VerificationError(f"could not start uvx: {error}") from error
        except subprocess.TimeoutExpired as error:
            raise VerificationError(
                f"MCP server did not exit within {timeout} seconds"
            ) from error
    if result.returncode:
        raise VerificationError(
            f"MCP server exited {result.returncode}: {result.stderr.strip()}"
        )
    tools = _verify_responses(result.stdout, expected_version)
    return {
        "server_name": "Dynamic Agent Runner",
        "tools": tools,
        "version": expected_version,
        "wheel": str(resolved_wheel),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--uvx", default="uvx")
    parser.add_argument("--timeout", default=30.0, type=float)
    arguments = parser.parse_args()
    try:
        print(json.dumps(verify_local_wheel(**vars(arguments)), sort_keys=True))
    except VerificationError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
