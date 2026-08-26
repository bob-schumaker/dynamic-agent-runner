"""Global fixtures for DAR's unit-test suite."""

from __future__ import annotations

import socket

import pytest


class UnitTestNetworkAccessError(RuntimeError):
    """Raised when a unit test attempts to open a network connection."""


def _blocked_network_access(*_args: object, **_kwargs: object) -> None:
    raise UnitTestNetworkAccessError("network access is blocked in unit tests")


_ORIGINAL_SOCKET_CONNECT = socket.socket.connect
_ORIGINAL_SOCKET_CONNECT_EX = socket.socket.connect_ex


def _connect_unix_or_block(connection: socket.socket, address: object) -> None:
    if connection.family == socket.AF_UNIX:
        _ORIGINAL_SOCKET_CONNECT(connection, address)
        return
    _blocked_network_access(connection, address)


def _connect_ex_unix_or_block(connection: socket.socket, address: object) -> int:
    if connection.family == socket.AF_UNIX:
        return _ORIGINAL_SOCKET_CONNECT_EX(connection, address)
    _blocked_network_access(connection, address)
    raise AssertionError("unreachable")


@pytest.fixture(autouse=True)
def block_unit_test_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Require unit tests to use injected fakes instead of live transports."""

    monkeypatch.setattr(socket, "create_connection", _blocked_network_access)
    monkeypatch.setattr(socket.socket, "connect", _connect_unix_or_block)
    monkeypatch.setattr(socket.socket, "connect_ex", _connect_ex_unix_or_block)
