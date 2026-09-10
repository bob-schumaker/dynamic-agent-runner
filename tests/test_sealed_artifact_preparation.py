"""Contract tests for registered sealed-artifact input preparation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.sealed_artifact_preparation import (
    SealedArtifactInputPreparationService,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactHandleError,
    SealedArtifactHandleService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


NOW = datetime(2026, 9, 10, tzinfo=UTC)
_OWNER = "local-os-user-v1:501:tester"
_REVISION = "a" * 64
_PROFILE = "b" * 64


class _CountingStore(PrivateStateStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.issue_calls = 0

    def issue(self, **kwargs):  # type: ignore[no-untyped-def]
        self.issue_calls += 1
        return super().issue(**kwargs)


@dataclass(frozen=True)
class _Registration:
    package_id: str = "example"
    revision_digest: str = _REVISION
    profile_digest: str = _PROFILE


@dataclass(frozen=True)
class _Revision:
    package_root: Path


class _Registrations:
    def resolve(self, workflow_id: str) -> _Registration:
        assert workflow_id == "example"
        return _Registration()


class _Catalog:
    def __init__(self, root: Path) -> None:
        self._revision = _Revision(root)

    def revision(self, package_id: str, revision_digest: str) -> _Revision:
        assert (package_id, revision_digest) == ("example", _REVISION)
        return self._revision


@dataclass(frozen=True)
class _Identity:
    principal: str = _OWNER


def _package(root: Path, *, profile_digest: str = _PROFILE) -> None:
    asset = b"def run(context):\n    return None\n"
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "runner.py").write_bytes(asset)
    descriptor = {
        "asset": {
            "abi_version": 1,
            "entrypoint": "run",
            "path": "assets/runner.py",
            "sha256": hashlib.sha256(asset).hexdigest(),
        },
        "callbacks": [],
        "capability_requirements_digest": "c" * 64,
        "child_contract_digests": [],
        "format_version": 1,
        "inputs": [
            {
                "max_bytes": 12,
                "media_type": "application/octet-stream",
                "required": True,
                "role": "snapshot",
                "schema_digest": None,
            }
        ],
        "limits": {
            "max_concurrency": 1,
            "max_cpu_milliseconds": 1,
            "max_io_bytes": 100,
            "max_memory_bytes": 1,
            "max_runtime_milliseconds": 1,
        },
        "outputs": [
            {
                "max_bytes": 1,
                "media_type": "application/octet-stream",
                "role": "result",
                "schema_digest": None,
            }
        ],
        "profile_digest": profile_digest,
        "schemas": [],
    }
    descriptor["artifact_runner_digest"] = hashlib.sha256(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (root / "sealed-artifact-runner.json").write_bytes(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()
    )


def _service(tmp_path: Path, *, profile_digest: str = _PROFILE):
    root = tmp_path / "package"
    _package(root, profile_digest=profile_digest)
    store = _CountingStore(tmp_path / "state")
    handles = SealedArtifactHandleService(store=store, owner=_OWNER)
    return (
        SealedArtifactInputPreparationService(
            registrations=_Registrations(),
            catalog=_Catalog(root),
            handles=handles,
            identity=_Identity(),
        ),
        store,
    )


@pytest.mark.parametrize(
    ("receiver_id", "profile_digest"),
    [("other", _PROFILE), (_OWNER, "d" * 64)],
)
def test_preparation_rejects_before_copying_bytes(
    tmp_path: Path, receiver_id: str, profile_digest: str
) -> None:
    service, store = _service(tmp_path, profile_digest=profile_digest)

    with pytest.raises(SealedArtifactHandleError, match="invalid"):
        service.prepare(
            workflow_id="example",
            receiver_id=receiver_id,
            invocation_id="invocation",
            role="snapshot",
            media_type="application/octet-stream",
            schema_digest=None,
            content=b"sealed bytes",
            expires_at=NOW + timedelta(minutes=1),
            now=NOW,
        )

    assert store.issue_calls == 0


def test_preparation_binds_the_registered_revision_before_copying_bytes(
    tmp_path: Path,
) -> None:
    service, store = _service(tmp_path)

    handle = service.prepare(
        workflow_id="example",
        receiver_id=_OWNER,
        invocation_id="invocation",
        role="snapshot",
        media_type="application/octet-stream",
        schema_digest=None,
        content=b"sealed bytes",
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )

    assert handle.handle_id
    assert store.issue_calls == 1
