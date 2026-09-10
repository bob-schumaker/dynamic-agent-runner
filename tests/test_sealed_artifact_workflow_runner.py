"""Contract tests for concrete sealed-artifact receiver composition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from dynamic_agent_runner.workflow_host.capabilities import CapabilityRequirements
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactHandleService,
    SealedArtifactOutputHandleService,
    parse_sealed_artifact_runner_descriptor,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_workflow_runner import (
    SealedArtifactInvocation,
    SealedArtifactWorkflowRunner,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


NOW = datetime(2026, 9, 10, tzinfo=UTC)
_OWNER = "local-os-user-v1:501:tester"
_REVISION = "a" * 64
_PROFILE = "b" * 64


@dataclass(frozen=True)
class _Registration:
    workflow_id: str = "example"
    package_id: str = "example"
    revision_digest: str = _REVISION
    profile_digest: str = _PROFILE
    policy_digest: str = "c" * 64


@dataclass(frozen=True)
class _Revision:
    package_root: Path
    trust: str = "human_selected_local"


@dataclass(frozen=True)
class _Identity:
    principal: str = _OWNER


def _package(root: Path) -> tuple[bytes, CapabilityRequirements]:
    asset = (
        b"def run(context):\n"
        b"    context.write_output('result', 'application/octet-stream', context.read_input('snapshot'))\n"
    )
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "runner.py").write_bytes(asset)
    requirements = CapabilityRequirements()
    descriptor = {
        "asset": {
            "abi_version": 1,
            "entrypoint": "run",
            "path": "assets/runner.py",
            "sha256": hashlib.sha256(asset).hexdigest(),
        },
        "callbacks": [],
        "capability_requirements_digest": requirements.digest,
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
            "max_runtime_milliseconds": 100,
        },
        "outputs": [
            {
                "max_bytes": 12,
                "media_type": "application/octet-stream",
                "role": "result",
                "schema_digest": None,
            }
        ],
        "profile_digest": _PROFILE,
        "schemas": [],
    }
    descriptor["artifact_runner_digest"] = hashlib.sha256(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    data = json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()
    (root / "sealed-artifact-runner.json").write_bytes(data)
    return data, requirements


def test_concrete_runner_reserves_consumes_and_publishes_atomically(
    tmp_path: Path, monkeypatch
) -> None:
    import dynamic_agent_runner.workflow_host.sealed_artifact_workflow_runner as module

    root = tmp_path / "package"
    descriptor_bytes, requirements = _package(root)
    descriptor = parse_sealed_artifact_runner_descriptor(descriptor_bytes)
    store = PrivateStateStore(tmp_path / "state")
    inputs = SealedArtifactHandleService(store=store, owner=_OWNER)
    input_handle = inputs.prepare(
        descriptor=descriptor,
        receiver_id=_OWNER,
        revision_digest=_REVISION,
        invocation_id="invocation",
        role="snapshot",
        media_type="application/octet-stream",
        schema_digest=None,
        content=b"snapshot",
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )

    class Registrations:
        def resolve(self, workflow_id: str) -> _Registration:
            assert workflow_id == "example"
            return _Registration()

    class Catalog:
        def revision(self, package_id: str, revision_digest: str) -> _Revision:
            assert (package_id, revision_digest) == ("example", _REVISION)
            return _Revision(root)

    class Callbacks:
        def revalidate(self, _callback) -> None:
            return None

        def invoke(self, _name: str, _request: bytes) -> bytes:
            raise AssertionError("no callback is declared")

    class CallbackResolver:
        def resolve(self, _descriptor, _policy) -> Callbacks:
            return Callbacks()

    monkeypatch.setattr(
        module,
        "compile_workflow_policy",
        lambda _revision, capability_catalog=None: SimpleNamespace(
            policy_digest="c" * 64,
            capability_requirements=requirements,
        ),
    )
    runner = SealedArtifactWorkflowRunner(
        registrations=Registrations(),
        catalog=Catalog(),
        handles=inputs,
        outputs=SealedArtifactOutputHandleService(store=store, owner=_OWNER),
        callback_resolver=CallbackResolver(),
        identity=_Identity(),
        output_ttl=timedelta(minutes=1),
    )

    result = runner.run(
        SealedArtifactInvocation(
            workflow_id="example",
            invocation_id="invocation",
            input_handles={"snapshot": input_handle.handle_id},
        ),
        now=NOW,
    )

    assert [handle.role for handle in result.outputs] == ["result"]
    assert result.receipt["status"] == "completed"
