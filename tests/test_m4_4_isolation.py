"""Tests for the fail-closed M4.4 clean-actor isolation adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.m4_4_isolation import (  # noqa: E402
    DockerContainerIsolation,
    M44ContainerIsolationRequest,
    M44ContainerMount,
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


def test_container_isolation_uses_virtual_paths_and_no_network(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    wheel = tmp_path / "runner.whl"
    writable = tmp_path / "writable"
    plugin.mkdir()
    wheel.write_bytes(b"wheel")
    writable.mkdir()
    request = M44ContainerIsolationRequest(
        image="m44-codex:test",
        command=("codex", "exec", "--help"),
        read_only_mounts=(
            M44ContainerMount(plugin, "/inputs/plugin"),
            M44ContainerMount(wheel, "/inputs/dynamic-agent-runner.whl"),
        ),
        writable_root=writable,
        environment={"PATH": "/usr/local/bin:/usr/bin:/bin"},
    )

    command = DockerContainerIsolation().command(request)

    assert command[:5] == ("docker", "run", "--rm", "--network", "none")
    assert "--read-only" in command
    assert "src=/inputs/plugin" not in " ".join(command)
    assert any("dst=/inputs/plugin,readonly" in item for item in command)
    assert any("dst=/workspace" in item for item in command)
    assert str(plugin) in " ".join(command)


def test_container_isolation_rejects_host_paths_as_virtual_targets(
    tmp_path: Path,
) -> None:
    plugin = tmp_path / "plugin"
    writable = tmp_path / "writable"
    plugin.mkdir()
    writable.mkdir()

    with pytest.raises(M44IsolationError, match="virtual mount"):
        M44ContainerMount(plugin, str(plugin))
