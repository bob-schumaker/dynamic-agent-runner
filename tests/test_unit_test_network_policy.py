"""Regression checks for the no-live-provider unit-test policy."""

from __future__ import annotations

import ast
import socket
import tempfile
from pathlib import Path

import pytest

from conftest import UnitTestNetworkAccessError


TEST_ROOT = Path(__file__).parent
FORBIDDEN_UNIT_TEST_IMPORTS = frozenset(
    {
        "aiohttp",
        "httpx",
        "huggingface_hub",
        "litellm",
        "openai",
        "requests",
        "urllib.request",
        "websockets",
    }
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_unit_tests_block_socket_connections() -> None:
    with pytest.raises(UnitTestNetworkAccessError, match="network access is blocked"):
        socket.create_connection(("api.openai.com", 443))

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        with pytest.raises(
            UnitTestNetworkAccessError, match="network access is blocked"
        ):
            client.connect(("api.openai.com", 443))


def test_unit_test_network_policy_preserves_unix_domain_ipc() -> None:
    with tempfile.TemporaryDirectory(dir="/private/tmp", prefix="dar-test-") as root:
        socket_path = Path(root) / "local.sock"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(socket_path))
            server.listen(1)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(str(socket_path))
                peer, _ = server.accept()
                peer.close()


def test_ordinary_tests_do_not_import_live_provider_transports() -> None:
    violations: dict[str, list[str]] = {}
    for path in TEST_ROOT.glob("test_*.py"):
        if path.name.startswith("test_live_"):
            continue
        imported = _imports(path)
        forbidden = sorted(imported & FORBIDDEN_UNIT_TEST_IMPORTS)
        if forbidden:
            violations[path.name] = forbidden

    assert not violations, f"ordinary unit tests import live transports: {violations}"


def test_live_test_modules_have_an_explicit_opt_in() -> None:
    missing_opt_in: list[str] = []
    for path in TEST_ROOT.glob("test_live_*.py"):
        source = path.read_text(encoding="utf-8")
        has_skip_gate = "pytest.skip" in source or "pytest.mark.skipif" in source
        if "DAR_RUN_LIVE_" not in source or not has_skip_gate:
            missing_opt_in.append(path.name)

    assert not missing_opt_in, (
        f"live tests need an explicit DAR_RUN_LIVE opt-in: {missing_opt_in}"
    )
