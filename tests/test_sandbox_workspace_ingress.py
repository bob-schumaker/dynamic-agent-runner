"""Tests for the descriptor-relative sandbox file-ingress primitive."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

import dynamic_agent_runner.sandbox_workspace as sandbox_workspace
from dynamic_agent_runner.sandbox_workspace import (
    SandboxWorkspaceError,
    copy_regular_file_no_follow,
    create_private_workspace,
)


def test_copy_regular_file_no_follow_copies_the_opened_source_atomically(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "input"
    source = source_root / "nested" / "message.txt"
    source.parent.mkdir(parents=True)
    body = b"hello from the selected file\n"
    source.write_bytes(body)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    copied = copy_regular_file_no_follow(
        source_root=source_root,
        source_relative_path="nested/message.txt",
        workspace_root=workspace,
        destination_name="input.txt",
        max_bytes=len(body),
    )

    assert copied.relative_path == "input.txt"
    assert copied.byte_count == len(body)
    assert copied.content_hash == f"sha256:{hashlib.sha256(body).hexdigest()}"
    assert (workspace / "input.txt").read_bytes() == body
    assert not list(workspace.glob(".dar-ingress-*"))


@pytest.mark.parametrize(
    "relative_path", ["../outside.txt", "nested/../message.txt", "/tmp/x"]
)
def test_copy_regular_file_no_follow_rejects_noncanonical_source_paths(
    tmp_path: Path, relative_path: str
) -> None:
    source_root = tmp_path / "input"
    source_root.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(SandboxWorkspaceError, match="relative"):
        copy_regular_file_no_follow(
            source_root=source_root,
            source_relative_path=relative_path,
            workspace_root=workspace,
            destination_name="input.txt",
            max_bytes=100,
        )


def test_copy_regular_file_no_follow_rejects_symlinked_source_component(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "input"
    source_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "message.txt").write_text("secret", encoding="utf-8")
    os.symlink(outside, source_root / "linked")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(SandboxWorkspaceError, match="symlink"):
        copy_regular_file_no_follow(
            source_root=source_root,
            source_relative_path="linked/message.txt",
            workspace_root=workspace,
            destination_name="input.txt",
            max_bytes=100,
        )


def test_copy_regular_file_no_follow_keeps_the_opened_parent_during_a_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "input"
    source = source_root / "nested" / "message.txt"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"trusted body")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "message.txt").write_bytes(b"attacker body")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    original_open = os.open
    swapped = False

    def swap_parent(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == "message.txt" and not swapped:
            swapped = True
            source.parent.rename(source_root / "parked")
            os.symlink(replacement, source.parent)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", swap_parent)
    monkeypatch.setattr(
        sandbox_workspace, "_require_posix_no_follow_support", lambda: None
    )

    copied = copy_regular_file_no_follow(
        source_root=source_root,
        source_relative_path="nested/message.txt",
        workspace_root=workspace,
        destination_name="input.txt",
        max_bytes=100,
    )

    assert swapped
    assert copied.byte_count == len(b"trusted body")
    assert (workspace / "input.txt").read_bytes() == b"trusted body"


def test_copy_regular_file_no_follow_rejects_nonregular_and_oversize_sources(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "input"
    source_root.mkdir()
    (source_root / "directory").mkdir()
    os.mkfifo(source_root / "pipe")
    (source_root / "large.txt").write_bytes(b"0123456789")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(SandboxWorkspaceError, match="regular"):
        copy_regular_file_no_follow(
            source_root=source_root,
            source_relative_path="directory",
            workspace_root=workspace,
            destination_name="directory.txt",
            max_bytes=100,
        )
    with pytest.raises(SandboxWorkspaceError, match="regular"):
        copy_regular_file_no_follow(
            source_root=source_root,
            source_relative_path="pipe",
            workspace_root=workspace,
            destination_name="pipe.txt",
            max_bytes=100,
        )
    with pytest.raises(SandboxWorkspaceError, match="maximum"):
        copy_regular_file_no_follow(
            source_root=source_root,
            source_relative_path="large.txt",
            workspace_root=workspace,
            destination_name="large.txt",
            max_bytes=9,
        )

    assert not list(workspace.iterdir())


def test_copy_regular_file_no_follow_does_not_replace_a_workspace_entry(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "input"
    source_root.mkdir()
    (source_root / "message.txt").write_text("new", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "input.txt").write_text("existing", encoding="utf-8")

    with pytest.raises(SandboxWorkspaceError, match="already exists"):
        copy_regular_file_no_follow(
            source_root=source_root,
            source_relative_path="message.txt",
            workspace_root=workspace,
            destination_name="input.txt",
            max_bytes=100,
        )

    assert (workspace / "input.txt").read_text(encoding="utf-8") == "existing"


def test_create_private_workspace_creates_an_owner_only_fresh_directory(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "workspaces"
    parent.mkdir()

    first = create_private_workspace(parent)
    second = create_private_workspace(parent)

    assert first.relative_path != second.relative_path
    assert first.root.parent == parent
    assert second.root.parent == parent
    assert stat.S_IMODE(first.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(second.root.stat().st_mode) == 0o700
