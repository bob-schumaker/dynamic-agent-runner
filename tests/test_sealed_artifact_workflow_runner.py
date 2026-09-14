"""Contract tests for concrete sealed-artifact receiver composition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityCatalog,
    CapabilityContract,
    CapabilityProvider,
    CapabilityRequirement,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorAbi,
    ExecutionDescriptorValidatorRegistry,
)
from dynamic_agent_runner.workflow_host.locked_inference import (
    InferenceLimits,
    InferenceRole,
    InferenceRoles,
    LockedInferenceBinding,
    SealedAsset,
)
from dynamic_agent_runner.workflow_host.locked_inference_execution import (
    LockedInferenceHostLimits,
    LockedInferenceProvider,
)
from dynamic_agent_runner.workflow_host.locked_inference_provider_registry import (
    LockedInferenceProviderBinding,
    LockedInferenceProviderRegistry,
)
from dynamic_agent_runner.workflow_host.locked_inference_sealed_artifact_callback import (
    LockedInferenceExecutionFactory,
    LockedInferenceSealedArtifactCallbackResolver,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactHandleService,
    SealedArtifactOutputHandleService,
    SealedArtifactRunnerAdmissionError,
    parse_sealed_artifact_runner_descriptor,
    verify_sealed_artifact_runner_files,
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
    selected_capability_provider_ids: tuple[str, ...] = ()
    owner: str = _OWNER


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
                "required": False,
                "role": "prior",
                "schema_digest": None,
            },
            {
                "max_bytes": 12,
                "media_type": "application/octet-stream",
                "required": True,
                "role": "snapshot",
                "schema_digest": None,
            },
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
    prior_handle = inputs.prepare(
        descriptor=descriptor,
        receiver_id=_OWNER,
        revision_digest=_REVISION,
        invocation_id="invocation",
        role="prior",
        media_type="application/octet-stream",
        schema_digest=None,
        content=b"prior",
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
        def __init__(self) -> None:
            self.validated: list[tuple[object, object, object]] = []

        def revalidate(self, _callback) -> None:
            return None

        def invoke(self, _name: str, _request: bytes) -> bytes:
            raise AssertionError("no callback is declared")

        def validate_sealed_outputs(
            self, sealed, input_digests, input_contents
        ) -> None:
            self.validated.append((sealed, input_digests, input_contents))

    class CallbackResolver:
        callbacks = Callbacks()

        def resolve(self, _descriptor, _policy, _revision) -> Callbacks:
            return self.callbacks

    observed: list[object] = []

    class Validator:
        identity = ExecutionDescriptorAbi("test-abi", "1", "d" * 64)

        def validate(self, _descriptor) -> None:
            return None

    validators = ExecutionDescriptorValidatorRegistry((Validator(),))

    def policy(_revision, capability_catalog=None, descriptor_validators=None):
        observed.append(descriptor_validators)
        return SimpleNamespace(
            policy_digest="c" * 64,
            capability_requirements=requirements,
        )

    monkeypatch.setattr(module, "compile_workflow_policy", policy)
    resolver = CallbackResolver()
    runner = SealedArtifactWorkflowRunner(
        registrations=Registrations(),
        catalog=Catalog(),
        handles=inputs,
        outputs=SealedArtifactOutputHandleService(store=store, owner=_OWNER),
        callback_resolver=resolver,
        identity=_Identity(),
        output_ttl=timedelta(minutes=1),
        descriptor_validators=validators,
    )

    result = runner.run(
        SealedArtifactInvocation(
            workflow_id="example",
            invocation_id="invocation",
            input_handles={
                "prior": prior_handle.handle_id,
                "snapshot": input_handle.handle_id,
            },
        ),
        now=NOW,
    )

    assert [handle.role for handle in result.outputs] == ["result"]
    assert result.receipt["status"] == "completed"
    assert observed == [validators]
    assert len(resolver.callbacks.validated) == 1
    assert resolver.callbacks.validated[0][1] == {
        "prior": hashlib.sha256(b"prior").hexdigest(),
        "snapshot": hashlib.sha256(b"snapshot").hexdigest(),
    }
    assert resolver.callbacks.validated[0][2] == {
        "prior": b"prior",
        "snapshot": b"snapshot",
    }


def test_tampered_asset_stops_before_handle_or_provider_or_egress(
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
    (root / "assets" / "runner.py").write_bytes(b"tampered")

    class Registrations:
        def resolve(self, _workflow_id: str) -> _Registration:
            return _Registration()

    class Catalog:
        def revision(self, _package_id: str, _revision_digest: str) -> _Revision:
            return _Revision(root)

    class CallbackResolver:
        calls = 0

        def resolve(self, _descriptor, _policy, _revision):
            self.calls += 1
            raise AssertionError("provider resolution must not happen")

    resolver = CallbackResolver()
    monkeypatch.setattr(
        module,
        "compile_workflow_policy",
        lambda _revision, capability_catalog=None, descriptor_validators=None: (
            SimpleNamespace(
                policy_digest="c" * 64,
                capability_requirements=requirements,
            )
        ),
    )
    runner = SealedArtifactWorkflowRunner(
        registrations=Registrations(),
        catalog=Catalog(),
        handles=inputs,
        outputs=SealedArtifactOutputHandleService(store=store, owner=_OWNER),
        callback_resolver=resolver,
        identity=_Identity(),
        output_ttl=timedelta(minutes=1),
    )

    with pytest.raises(SealedArtifactRunnerAdmissionError, match="unavailable"):
        runner.run(
            SealedArtifactInvocation(
                "example", "invocation", {"snapshot": input_handle.handle_id}
            ),
            now=NOW,
        )

    assert resolver.calls == 0
    inputs.reserve(
        input_handle.handle_id,
        receiver_id=_OWNER,
        revision_digest=_REVISION,
        invocation_id="invocation",
        role="snapshot",
        media_type="application/octet-stream",
        schema_digest=None,
        now=NOW,
    )
    assert not store.active_records(
        kind="sealed_artifact_output_set", owner=_OWNER, now=NOW
    )


def test_changed_selected_provider_stops_before_descriptor_or_callback(
    tmp_path: Path, monkeypatch
) -> None:
    import dynamic_agent_runner.workflow_host.sealed_artifact_workflow_runner as module

    root = tmp_path / "package"
    descriptor_bytes, requirements = _package(root)
    descriptor = parse_sealed_artifact_runner_descriptor(descriptor_bytes)
    store = PrivateStateStore(tmp_path / "state")
    handles = SealedArtifactHandleService(store=store, owner=_OWNER)
    input_handle = handles.prepare(
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
        def resolve(self, _workflow_id: str) -> _Registration:
            return _Registration(selected_capability_provider_ids=("selected",))

    class Catalog:
        def revision(self, _package_id: str, _revision_digest: str) -> _Revision:
            return _Revision(root)

    class Resolver:
        calls = 0

        def resolve(self, _descriptor, _policy, _revision):
            self.calls += 1
            raise AssertionError("callback resolution must not happen")

    resolver = Resolver()
    monkeypatch.setattr(
        module,
        "compile_workflow_policy",
        lambda _revision, capability_catalog=None, descriptor_validators=None: (
            SimpleNamespace(
                policy_digest="c" * 64,
                capability_requirements=requirements,
                selected_capability_provider_ids=("replacement",),
            )
        ),
    )
    monkeypatch.setattr(
        module,
        "verify_sealed_artifact_runner_files",
        lambda *_args: pytest.fail("descriptor verification must not happen"),
    )
    runner = SealedArtifactWorkflowRunner(
        registrations=Registrations(),
        catalog=Catalog(),
        handles=handles,
        outputs=SealedArtifactOutputHandleService(store=store, owner=_OWNER),
        callback_resolver=resolver,
        identity=_Identity(),
        output_ttl=timedelta(minutes=1),
    )

    with pytest.raises(SealedArtifactRunnerAdmissionError, match="unavailable"):
        runner.run(
            SealedArtifactInvocation(
                "example", "invocation", {"snapshot": input_handle.handle_id}
            ),
            now=NOW,
        )

    assert resolver.calls == 0


def test_foreign_registration_owner_stops_before_catalog_or_callback(
    tmp_path: Path,
) -> None:
    root = tmp_path / "package"
    descriptor_bytes, _requirements = _package(root)
    descriptor = parse_sealed_artifact_runner_descriptor(descriptor_bytes)
    store = PrivateStateStore(tmp_path / "state")
    handles = SealedArtifactHandleService(store=store, owner=_OWNER)
    input_handle = handles.prepare(
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
    events: list[str] = []

    class Registrations:
        def resolve(self, _workflow_id: str) -> _Registration:
            events.append("registration")
            return _Registration(owner="other-owner")

    class Catalog:
        def revision(self, _package_id: str, _revision_digest: str) -> _Revision:
            events.append("catalog_revision")
            raise AssertionError("foreign registration must stop before ZIP access")

    class CallbackResolver:
        def resolve(self, _descriptor, _policy, _revision) -> object:
            events.append("callback_provider_resolution")
            raise AssertionError("foreign registration must stop before callback")

    runner = SealedArtifactWorkflowRunner(
        registrations=Registrations(),
        catalog=Catalog(),
        handles=handles,
        outputs=SealedArtifactOutputHandleService(store=store, owner=_OWNER),
        callback_resolver=CallbackResolver(),
        identity=_Identity(),
        output_ttl=timedelta(minutes=1),
    )

    with pytest.raises(SealedArtifactRunnerAdmissionError, match="unavailable"):
        runner.run(
            SealedArtifactInvocation(
                "example", "invocation", {"snapshot": input_handle.handle_id}
            ),
            now=NOW,
        )

    assert events == ["registration"]


def test_locked_inference_callback_runs_only_through_sealed_asset_context(
    tmp_path: Path, monkeypatch
) -> None:
    import dynamic_agent_runner.workflow_host.sealed_artifact_workflow_runner as module

    request_schema = json.dumps(
        {
            "max_depth": 2,
            "max_items": 1,
            "properties": {"value": {"max_string_bytes": 16, "type": "string"}},
            "required": ["value"],
            "type": "object",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    root = tmp_path / "package"
    asset = (
        b"def run(context):\n"
        b"    request = context.read_input('request')\n"
        b"    response = context.invoke_callback('suggest', request)\n"
        b"    context.write_output('result', 'application/json', response)\n"
    )
    child = json.dumps(
        {
            "body": {},
            "callback_name": "suggest",
            "capability_requirement": "model.generate.v1",
            "format_version": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    schema_digest = hashlib.sha256(request_schema).hexdigest()
    child_digest = hashlib.sha256(child).hexdigest()
    asset_digest = hashlib.sha256(asset).hexdigest()
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "runner.py").write_bytes(asset)
    (root / "schemas").mkdir()
    (root / "schemas" / "value.json").write_bytes(request_schema)
    instruction = b"sealed instruction"
    (root / "assets" / "instruction.txt").write_bytes(instruction)
    (root / "schemas" / "request.json").write_bytes(request_schema)
    (root / "schemas" / "response.json").write_bytes(request_schema)
    (root / "contracts").mkdir()
    (root / "contracts" / "suggest.json").write_bytes(child)
    generation = CapabilityRequirement(
        "model.generate.v1", "1", "d" * 64, ("structured",)
    )
    requirements = CapabilityRequirements((generation,), {})
    descriptor_value = {
        "asset": {
            "abi_version": 1,
            "entrypoint": "run",
            "path": "assets/runner.py",
            "sha256": asset_digest,
        },
        "callbacks": [
            {
                "child_contract_digest": child_digest,
                "max_calls": 1,
                "max_concurrency": 1,
                "max_request_bytes": 100,
                "max_response_bytes": 100,
                "max_total_request_bytes": 100,
                "max_total_response_bytes": 100,
                "name": "suggest",
                "requirement": "model.generate.v1",
                "timeout_milliseconds": 100,
            }
        ],
        "capability_requirements_digest": requirements.digest,
        "child_contract_digests": [child_digest],
        "format_version": 1,
        "inputs": [
            {
                "max_bytes": 100,
                "media_type": "application/json",
                "required": True,
                "role": "request",
                "schema_digest": schema_digest,
            }
        ],
        "limits": {
            "max_concurrency": 1,
            "max_cpu_milliseconds": 1,
            "max_io_bytes": 1000,
            "max_memory_bytes": 1,
            "max_runtime_milliseconds": 100,
        },
        "outputs": [
            {
                "max_bytes": 100,
                "media_type": "application/json",
                "role": "result",
                "schema_digest": schema_digest,
            }
        ],
        "profile_digest": _PROFILE,
        "schemas": [
            {
                "dialect": "json-schema-draft-2020-12",
                "path": "schemas/value.json",
                "sha256": schema_digest,
            }
        ],
    }
    descriptor_value["artifact_runner_digest"] = hashlib.sha256(
        json.dumps(descriptor_value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    descriptor_bytes = json.dumps(
        descriptor_value, sort_keys=True, separators=(",", ":")
    ).encode()
    (root / "sealed-artifact-runner.json").write_bytes(descriptor_bytes)
    descriptor = verify_sealed_artifact_runner_files(root, descriptor_bytes)
    roles = InferenceRoles(
        (
            InferenceRole(
                role="suggest",
                material_role="suggest",
                capability_id="model.generate.v1",
                instruction_asset=SealedAsset(
                    "assets/instruction.txt", hashlib.sha256(instruction).hexdigest()
                ),
                request_schema_asset=SealedAsset(
                    "schemas/request.json", hashlib.sha256(request_schema).hexdigest()
                ),
                response_schema_asset=SealedAsset(
                    "schemas/response.json", hashlib.sha256(request_schema).hexdigest()
                ),
                authorized_asset_digests=(asset_digest,),
                limits=InferenceLimits(1, 100, 100, 100, 1),
            ),
        )
    )

    class Provider(LockedInferenceProvider):
        calls = 0

        def generate(self, **_kwargs: object) -> bytes:
            self.calls += 1
            return b'{"value":"ok"}'

    provider = Provider()
    contract = CapabilityContract("model.generate.v1", "1", "d" * 64, ("structured",))
    capability_catalog = CapabilityCatalog(
        (contract,),
        (CapabilityProvider("receiver-generate", contract, conformance_passed=True),),
    )
    execution_factory = LockedInferenceExecutionFactory(
        capability_catalog=capability_catalog,
        provider_registry=LockedInferenceProviderRegistry(
            (LockedInferenceProviderBinding("receiver-generate", contract, provider),)
        ),
        host_limits=LockedInferenceHostLimits(1, 100, 100, 100, 1),
    )
    store = PrivateStateStore(tmp_path / "state")
    inputs = SealedArtifactHandleService(store=store, owner=_OWNER)
    input_handle = inputs.prepare(
        descriptor=descriptor,
        receiver_id=_OWNER,
        revision_digest=_REVISION,
        invocation_id="invocation",
        role="request",
        media_type="application/json",
        schema_digest=schema_digest,
        content=b'{"value":"request"}',
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )

    class Registrations:
        def resolve(self, _workflow_id: str) -> _Registration:
            return _Registration(
                selected_capability_provider_ids=("receiver-generate",)
            )

    class Catalog:
        def revision(self, _package_id: str, _revision_digest: str) -> _Revision:
            return _Revision(root)

    monkeypatch.setattr(
        module,
        "compile_workflow_policy",
        lambda _revision, capability_catalog=None, descriptor_validators=None: (
            SimpleNamespace(
                policy_digest="c" * 64,
                capability_requirements=requirements,
                inference_roles=roles,
                locked_inference_bindings=(
                    LockedInferenceBinding(
                        "suggest",
                        "suggest",
                        SimpleNamespace(material_lock_digest="e" * 64),
                        "1",
                        "d" * 64,
                    ),
                ),
                model_material_sets=SimpleNamespace(
                    for_role=lambda _role: SimpleNamespace(digest="e" * 64)
                ),
                selected_capability_provider_ids=("receiver-generate",),
            )
        ),
    )
    runner = SealedArtifactWorkflowRunner(
        registrations=Registrations(),
        catalog=Catalog(),
        handles=inputs,
        outputs=SealedArtifactOutputHandleService(store=store, owner=_OWNER),
        callback_resolver=LockedInferenceSealedArtifactCallbackResolver(
            execution_factory=execution_factory
        ),
        capability_catalog=capability_catalog,
        identity=_Identity(),
        output_ttl=timedelta(minutes=1),
    )

    result = runner.run(
        SealedArtifactInvocation(
            workflow_id="example",
            invocation_id="invocation",
            input_handles={"request": input_handle.handle_id},
        ),
        now=NOW,
    )

    assert [handle.role for handle in result.outputs] == ["result"]
    assert result.receipt["status"] == "completed"
    assert provider.calls == 1
