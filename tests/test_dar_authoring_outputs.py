"""Tests for host-owned authored-package output directories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.authoring_outputs import (  # noqa: E402
    AuthoringOutputError,
    AuthoringOutputService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 24, tzinfo=UTC)


def _service(tmp_path: Path) -> tuple[AuthoringOutputService, Path]:
    output_root = tmp_path / "packages"
    output_root.mkdir()
    return (
        AuthoringOutputService(
            store=PrivateStateStore(tmp_path / "state"),
            owner="local-user",
            output_root=output_root,
            max_file_bytes=1024,
            output_ttl=timedelta(hours=1),
        ),
        output_root,
    )


def test_creates_an_opaque_output_and_atomically_writes_only_relative_files(
    tmp_path: Path,
) -> None:
    service, output_root = _service(tmp_path)
    output = service.create(package_name="document-helper", now=NOW)

    written = service.write_file(
        output_id=output.output_id,
        relative_path="skill-bundle/answer.md",
        content="answer the document",
        now=NOW,
    )

    assert output.output_id.startswith("v1.")
    assert output.package_name == "document-helper"
    assert written.relative_path == "skill-bundle/answer.md"
    assert written.byte_count == len("answer the document")
    assert len(written.content_hash) == 64
    assert (output_root / "document-helper" / "skill-bundle" / "answer.md").read_text(
        encoding="utf-8"
    ) == "answer the document"


@pytest.mark.parametrize("relative_path", ("../escape.txt", "/escape.txt", ".hidden"))
def test_rejects_paths_outside_the_owned_output_directory(
    tmp_path: Path, relative_path: str
) -> None:
    service, output_root = _service(tmp_path)
    output = service.create(package_name="document-helper", now=NOW)

    with pytest.raises(AuthoringOutputError, match="output path is invalid"):
        service.write_file(
            output_id=output.output_id,
            relative_path=relative_path,
            content="escape",
            now=NOW,
        )

    assert not (output_root.parent / "escape.txt").exists()


def test_rejects_symlinked_output_directories(tmp_path: Path) -> None:
    service, output_root = _service(tmp_path)
    output = service.create(package_name="document-helper", now=NOW)
    package = output_root / "document-helper"
    package.rmdir()
    package.symlink_to(tmp_path)

    with pytest.raises(AuthoringOutputError, match="authoring output is unavailable"):
        service.write_file(
            output_id=output.output_id,
            relative_path="agent-design.md",
            content="escape",
            now=NOW,
        )
