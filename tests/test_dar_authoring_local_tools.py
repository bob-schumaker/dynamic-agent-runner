"""Tests for declared deterministic workflow-local tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.local_tools import (
    DockerSandboxConfiguration,
    DockerSandboxExecutor,
    execute_macos_sandbox_exec,
    create_local_tool_binding,
    LocalToolDefinition,
    LocalToolSandbox,
    LocalToolSandboxError,
    macos_sandbox_profile,
)


def test_docker_sandbox_executor_has_no_ambient_capabilities(tmp_path: Path) -> None:
    asset = tmp_path / "package" / "tools" / "validate"
    asset.parent.mkdir(parents=True)
    asset.write_text("placeholder", encoding="utf-8")
    observed: dict[str, object] = {}

    def execute(command: tuple[str, ...], **kwargs: object) -> object:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return type("Result", (), {"stdout": b'{"valid":true}'})()

    executor = DockerSandboxExecutor(
        DockerSandboxConfiguration(
            image="example.invalid/dar/converter@sha256:" + "a" * 64,
            docker_executable=Path("/usr/local/bin/docker"),
            docker_host="unix:///private/tmp/dar-docker.sock",
            memory_bytes=64 * 1024 * 1024,
            max_processes=1,
            scratch_bytes=1024 * 1024,
            max_output_bytes=4096,
        ),
        execute=execute,
    )

    assert executor((str(asset),), b"sealed", 5) == b'{"valid":true}'

    command = observed["command"]
    assert isinstance(command, tuple)
    assert command[:3] == ("/usr/local/bin/docker", "run", "--rm")
    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges:true" in command
    assert "--pids-limit=1" in command
    assert "--memory=67108864" in command
    assert "--tmpfs=/dar/scratch:rw,noexec,nosuid,size=1048576,mode=1777" in command
    assert f"--mount=type=bind,src={asset},dst=/dar/asset,readonly" in command
    assert "--entrypoint=/dar/asset" in command
    assert command[-1:] == ("example.invalid/dar/converter@sha256:" + "a" * 64,)
    kwargs = observed["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["input"] == b"sealed"
    assert kwargs["env"] == {
        "DOCKER_HOST": "unix:///private/tmp/dar-docker.sock",
        "HOME": "/nonexistent",
        "PATH": "/usr/bin:/bin",
    }


def test_docker_sandbox_executor_rejects_unbounded_output(tmp_path: Path) -> None:
    asset = tmp_path / "package" / "tools" / "validate"
    asset.parent.mkdir(parents=True)
    asset.write_text("placeholder", encoding="utf-8")
    executor = DockerSandboxExecutor(
        DockerSandboxConfiguration(
            image="example.invalid/dar/converter@sha256:" + "a" * 64,
            docker_executable=Path("/usr/local/bin/docker"),
            docker_host="unix:///private/tmp/dar-docker.sock",
            memory_bytes=64 * 1024 * 1024,
            max_processes=1,
            scratch_bytes=1024 * 1024,
            max_output_bytes=4,
        ),
        execute=lambda _command, **_kwargs: type(
            "Result", (), {"stdout": b"overflow"}
        )(),
    )

    with pytest.raises(LocalToolSandboxError, match="output"):
        executor((str(asset),), b"sealed", 5)


def test_local_tool_sandbox_runs_only_a_declared_asset_with_bounded_io(
    tmp_path: Path,
) -> None:
    asset = tmp_path / "tools" / "summarize.sh"
    asset.parent.mkdir()
    asset.write_text("placeholder", encoding="utf-8")
    definition = LocalToolDefinition(
        tool_id="summarize",
        asset_path=asset,
        accepted_artifact_role="source_image",
        max_input_bytes=1024,
        max_output_bytes=512,
        timeout_seconds=1,
    )
    sandbox = LocalToolSandbox(
        package_root=tmp_path,
        execute=lambda command, input_bytes, timeout_seconds: (
            b'{"evidence":"bounded result"}'
        ),
    )

    result = sandbox.run(
        definition,
        artifact_role="source_image",
        artifact_bytes=b"sealed input",
    )

    assert result == {"evidence": "bounded result"}


def test_trusted_fixture_builds_macos_sandbox_exec_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = tmp_path / "tools" / "inspect"
    asset.parent.mkdir()
    asset.write_text(
        '#!/bin/sh\ninput=$(cat)\nprintf \'{"byte_count":%s}\\n\' "${#input}"\n',
        encoding="utf-8",
    )
    asset.chmod(0o700)
    definition = LocalToolDefinition(
        "inspect", asset, "opaque_binary_artifact", 1024, 512, 1
    )
    sandbox = LocalToolSandbox(
        package_root=tmp_path,
        execute=execute_macos_sandbox_exec,
    )
    observed: dict[str, object] = {}

    def execute(command: tuple[str, ...], **kwargs: object) -> object:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return type("Result", (), {"stdout": b'{"byte_count":6}'})()

    monkeypatch.setattr(
        "dynamic_agent_runner.workflow_host.local_tools.subprocess.run", execute
    )

    result = sandbox.run(
        definition,
        artifact_role="opaque_binary_artifact",
        artifact_bytes=b"sealed",
    )

    assert result == {"byte_count": 6}
    assert observed["command"] == (
        "sandbox-exec",
        "-p",
        "(version 1) (allow default)",
        str(asset),
    )


def test_local_tool_sandbox_requires_bounded_json_evidence(tmp_path: Path) -> None:
    asset = tmp_path / "tools" / "validate"
    asset.parent.mkdir()
    asset.write_text("placeholder", encoding="utf-8")
    definition = LocalToolDefinition(
        tool_id="validate",
        asset_path=asset,
        accepted_artifact_role="source_image",
        max_input_bytes=1024,
        max_output_bytes=512,
        timeout_seconds=1,
    )
    sandbox = LocalToolSandbox(
        package_root=tmp_path,
        execute=lambda _command, _input, _timeout: b"not-json",
    )

    with pytest.raises(LocalToolSandboxError, match="evidence"):
        sandbox.run(definition, artifact_role="source_image", artifact_bytes=b"x")


def test_local_tool_binding_exposes_only_its_declared_sealed_evidence(
    tmp_path: Path,
) -> None:
    asset = tmp_path / "tools" / "validate"
    asset.parent.mkdir()
    asset.write_text("placeholder", encoding="utf-8")
    definition = LocalToolDefinition("validate", asset, "source_image", 1024, 512, 1)
    binding = create_local_tool_binding(
        sandbox=LocalToolSandbox(
            package_root=tmp_path,
            execute=lambda _command, _input, _timeout: b'{"valid":true}',
        ),
        definition=definition,
        artifact_role="source_image",
        artifact_bytes=b"sealed input",
    )

    assert binding.model_id == "validate"
    assert binding.handler({}) == {"valid": True}


@pytest.mark.parametrize(
    ("asset_path", "role", "body"),
    [
        (Path("/bin/sh"), "source_image", b"sealed input"),
        (Path("tools/summarize.sh"), "other", b"sealed input"),
        (Path("tools/summarize.sh"), "source_image", b"x" * 1025),
    ],
)
def test_local_tool_sandbox_rejects_undeclared_access_and_oversized_input(
    tmp_path: Path, asset_path: Path, role: str, body: bytes
) -> None:
    package_root = tmp_path / "package"
    (package_root / "tools").mkdir(parents=True)
    (package_root / "tools" / "summarize.sh").write_text("placeholder")
    definition = LocalToolDefinition(
        tool_id="summarize",
        asset_path=asset_path,
        accepted_artifact_role="source_image",
        max_input_bytes=1024,
        max_output_bytes=512,
        timeout_seconds=1,
    )
    sandbox = LocalToolSandbox(
        package_root=package_root,
        execute=lambda command, input_bytes, timeout_seconds: b"bounded result",
    )

    with pytest.raises(LocalToolSandboxError):
        sandbox.run(definition, artifact_role=role, artifact_bytes=body)


def test_local_tool_sandbox_rejects_a_package_internal_symlink(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    tools = package_root / "tools"
    tools.mkdir(parents=True)
    target = tools / "target"
    target.write_text("placeholder", encoding="utf-8")
    asset = tools / "validate"
    asset.symlink_to(target)
    definition = LocalToolDefinition("validate", asset, "source_image", 1024, 512, 1)
    sandbox = LocalToolSandbox(
        package_root=package_root,
        execute=lambda _command, _input, _timeout: b"{}",
    )

    with pytest.raises(LocalToolSandboxError, match="asset"):
        sandbox.run(definition, artifact_role="source_image", artifact_bytes=b"x")


def test_macos_sandbox_profile_denies_network_and_allows_only_declared_paths(
    tmp_path: Path,
) -> None:
    profile = macos_sandbox_profile(
        asset_path=tmp_path / "package" / "tools" / "validate_svg",
        input_path=tmp_path / "run" / "input",
        output_path=tmp_path / "run" / "output",
    )

    assert "(deny default)" in profile
    assert "(deny network*)" in profile
    assert f'(literal "{tmp_path / "package" / "tools" / "validate_svg"}")' in profile
    assert f'(literal "{tmp_path / "run" / "input"}")' in profile
    assert f'(literal "{tmp_path / "run" / "output"}")' in profile
