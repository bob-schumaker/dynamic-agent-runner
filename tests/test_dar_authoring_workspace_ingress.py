"""Tests for trusted workspace file ingress into opaque artifacts."""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.state import PrivateStateStore  # noqa: E402
from dar_workflow_server.workspace_ingress import (  # noqa: E402
    WorkspaceIngressError,
    WorkspaceIngressPolicy,
    WorkspaceIngressService,
)


NOW = datetime(2026, 8, 24, tzinfo=UTC)


def _service(tmp_path: Path) -> WorkspaceIngressService:
    return WorkspaceIngressService(
        input_root=tmp_path / "input",
        private_workspace_parent=tmp_path / "private-workspaces",
        store=PrivateStateStore(tmp_path / "state"),
        owner="local-os-user-v1:501:ada",
        max_file_bytes=1024,
        artifact_ttl=timedelta(minutes=5),
    )


def _policy() -> WorkspaceIngressPolicy:
    return WorkspaceIngressPolicy(
        workflow_id="document-helper",
        registration_digest="a" * 64,
        accepted_roles=("document",),
        accepted_media_types=("text/plain",),
    )


def test_ingress_copies_selected_file_to_a_registration_bound_artifact(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input" / "document.txt"
    source.parent.mkdir()
    body = b"document body\n"
    source.write_bytes(body)
    private_parent = tmp_path / "private-workspaces"
    private_parent.mkdir(mode=0o700)
    service = _service(tmp_path)

    artifact = service.ingress(
        source_path=source,
        role="document",
        media_type="text/plain",
        policy=_policy(),
        now=NOW,
    )

    assert artifact.artifact_id.startswith("v1.")
    assert artifact.byte_count == len(body)
    assert artifact.content_hash == f"sha256:{hashlib.sha256(body).hexdigest()}"
    assert artifact.expires_at == NOW + timedelta(minutes=5)
    assert str(source) not in repr(artifact)
    loaded = service.load(
        artifact.artifact_id,
        workflow_id="document-helper",
        registration_digest="a" * 64,
        now=NOW,
    )
    assert loaded.content_path.read_bytes() == body
    assert loaded.role == "document"
    assert loaded.media_type == "text/plain"


@pytest.mark.parametrize(
    ("role", "media_type"),
    [("body", "text/plain"), ("document", "text/html")],
)
def test_ingress_rejects_artifacts_outside_the_registered_contract(
    tmp_path: Path, role: str, media_type: str
) -> None:
    source = tmp_path / "input" / "document.txt"
    source.parent.mkdir()
    source.write_text("body", encoding="utf-8")
    (tmp_path / "private-workspaces").mkdir(mode=0o700)

    with pytest.raises(WorkspaceIngressError, match="accepted"):
        _service(tmp_path).ingress(
            source_path=source,
            role=role,
            media_type=media_type,
            policy=_policy(),
            now=NOW,
        )


def test_ingress_rejects_outside_and_symlinked_sources_without_an_artifact(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    os.symlink(outside, input_root / "linked.txt")
    (tmp_path / "private-workspaces").mkdir(mode=0o700)
    service = _service(tmp_path)

    for source in (outside, input_root / "linked.txt"):
        with pytest.raises(WorkspaceIngressError):
            service.ingress(
                source_path=source,
                role="document",
                media_type="text/plain",
                policy=_policy(),
                now=NOW,
            )


def test_artifact_load_rejects_a_different_workflow_registration_or_expiry(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input" / "document.txt"
    source.parent.mkdir()
    source.write_text("body", encoding="utf-8")
    (tmp_path / "private-workspaces").mkdir(mode=0o700)
    service = _service(tmp_path)
    artifact = service.ingress(
        source_path=source,
        role="document",
        media_type="text/plain",
        policy=_policy(),
        now=NOW,
    )

    with pytest.raises(WorkspaceIngressError, match="registration"):
        service.load(
            artifact.artifact_id,
            workflow_id="other-workflow",
            registration_digest="a" * 64,
            now=NOW,
        )
    with pytest.raises(WorkspaceIngressError, match="unavailable"):
        service.load(
            artifact.artifact_id,
            workflow_id="document-helper",
            registration_digest="a" * 64,
            now=NOW + timedelta(minutes=5),
        )
