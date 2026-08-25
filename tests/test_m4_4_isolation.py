"""Tests for the fail-closed M4.4 clean-actor isolation adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.m4_4_isolation import (  # noqa: E402
    M44IsolationError,
    M44IsolationRequest,
    MacOSSeatbeltIsolation,
)


def _request(tmp_path: Path) -> M44IsolationRequest:
    read_only = tmp_path / "read-only"
    writable = tmp_path / "writable"
    read_only.mkdir()
    writable.mkdir()
    return M44IsolationRequest(
        command=("/usr/bin/true",),
        read_only_roots=(read_only,),
        writable_root=writable,
        working_directory=writable,
        environment={"PATH": "/usr/bin:/bin"},
    )


def test_seatbelt_profile_grants_only_declared_roots_and_denies_network(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)

    profile = MacOSSeatbeltIsolation().profile(request)

    assert "(deny default)" in profile
    assert "(allow network-outbound" not in profile
    assert f'(subpath "{request.read_only_roots[0]}")' in profile
    assert f'(subpath "{request.writable_root}")' in profile
    assert "(allow file-write*" in profile


def test_isolation_request_rejects_an_overlapping_or_symlinked_mount(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    linked = tmp_path / "linked"
    linked.symlink_to(request.writable_root, target_is_directory=True)

    with pytest.raises(M44IsolationError, match="overlap"):
        M44IsolationRequest(
            command=("/usr/bin/true",),
            read_only_roots=(request.writable_root,),
            writable_root=request.writable_root,
            working_directory=request.writable_root,
            environment={"PATH": "/usr/bin:/bin"},
        )
    with pytest.raises(M44IsolationError, match="symlink"):
        M44IsolationRequest(
            command=("/usr/bin/true",),
            read_only_roots=(linked,),
            writable_root=request.writable_root,
            working_directory=request.writable_root,
            environment={"PATH": "/usr/bin:/bin"},
        )


def test_isolation_request_rejects_ambient_execution_environment(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)

    with pytest.raises(M44IsolationError, match="environment"):
        M44IsolationRequest(
            command=request.command,
            read_only_roots=request.read_only_roots,
            writable_root=request.writable_root,
            working_directory=request.working_directory,
            environment={"HOME": "/Users/operator"},
        )


def test_seatbelt_run_fails_closed_when_the_runtime_probe_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolation = MacOSSeatbeltIsolation()
    monkeypatch.setattr(isolation, "available", lambda: False)

    with pytest.raises(M44IsolationError, match="unavailable"):
        isolation.run(_request(tmp_path))
