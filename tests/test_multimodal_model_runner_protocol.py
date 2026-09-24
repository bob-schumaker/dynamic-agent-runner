"""Contract tests for the multimodal model-runner protocol."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from dynamic_agent_runner.multimodal_model_runner import (
    DARGenerationRequestContext,
    MultimodalRunnerAdmissionError,
    MultimodalRunnerBinding,
    MultimodalRunnerDescriptor,
    MultimodalRunnerHealth,
    MultimodalRunnerLimits,
    MultimodalRunnerProtocolError,
    MultimodalRunnerResult,
    SealedMultimodalInputMaterializer,
    SealedMultimodalHandle,
    SealedMultimodalRequest,
    admit_multimodal_runner,
)
from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.workflow_host.local_model_runners import (
    LocalModelRunnerCatalog,
)
from dynamic_agent_runner.workflow_host.host import LocalWorkflowHost
from dynamic_agent_runner.workflow_host.sealed_artifact_output_handler import (
    SealedArtifactOutputHandler,
    SealedArtifactOutputStageRequest,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactOutput,
    SealedArtifactOutputHandleService,
    SealedArtifactPrivateOutputSet,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationDeadline,
)
from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerLauncher,
)


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


_PUBLICATION_NOW = datetime(2026, 9, 24, tzinfo=UTC)
_PUBLICATION_DESCRIPTOR = _digest("publication-descriptor")


def _limits() -> MultimodalRunnerLimits:
    return MultimodalRunnerLimits(
        max_input_bytes=8_000_000,
        max_output_bytes=64_000,
        max_runtime_milliseconds=60_000,
        max_memory_bytes=2_000_000_000,
    )


def _descriptor() -> MultimodalRunnerDescriptor:
    return MultimodalRunnerDescriptor(
        runner_id="transformers-peft-v1",
        provider_runtime_id="transformers-peft",
        material_lock_digest=_digest("material"),
        execution_abi_digest=_digest("abi"),
        input_modalities=("image", "text"),
        output_modalities=("text",),
        converter_digest=_digest("converter"),
        output_contract_digest=_digest("output"),
        resource_limits=_limits(),
    )


def _request() -> SealedMultimodalRequest:
    descriptor = _descriptor()
    return _request_for_descriptor(descriptor)


def _request_for_descriptor(
    descriptor: MultimodalRunnerDescriptor,
) -> SealedMultimodalRequest:
    return SealedMultimodalRequest(
        package_id="floorplan-from-image",
        package_revision_digest=_digest("revision"),
        invocation_id="invocation-1",
        descriptor=descriptor,
        handles=(
            SealedMultimodalHandle(
                value="sealed:image:one",
                role="image",
                package_id="floorplan-from-image",
                package_revision_digest=_digest("revision"),
                invocation_id="invocation-1",
                material_lock_digest=descriptor.material_lock_digest,
                converter_digest=descriptor.converter_digest,
            ),
        ),
    )


def _context() -> DARGenerationRequestContext:
    return DARGenerationRequestContext(
        invocation_id="invocation-1",
        invocation_digest=_digest("invocation"),
        execution_device="mps",
        generation_budget={
            "max_new_tokens_per_fragment": 32,
            "max_continuations": 0,
            "max_total_generated_tokens": 32,
            "max_total_output_bytes": 4_096,
            "max_effective_context_tokens": 4_096,
            "max_runtime_milliseconds": 60_000,
            "max_memory_bytes": 2_000_000_000,
        },
        cancellation_supported=False,
        worker_protocol="generation-worker-v1",
    )


def _publication_descriptor() -> MultimodalRunnerDescriptor:
    return MultimodalRunnerDescriptor(
        **{
            **_descriptor().to_mapping(),
            "runner_id": "multimodal-publication-test",
            "output_modalities": ("image",),
            "contract_digest": "",
        }
    )


def _publication_request() -> SealedMultimodalRequest:
    return _request_for_descriptor(_publication_descriptor())


def _publication_result() -> MultimodalRunnerResult:
    request = _publication_request()
    return MultimodalRunnerResult(
        status="completed",
        text=None,
        output_handles=(
            SealedMultimodalHandle(
                value="sealed:output-one",
                role="result",
                package_id=request.package_id,
                package_revision_digest=request.package_revision_digest,
                invocation_id=request.invocation_id,
                material_lock_digest=request.descriptor.material_lock_digest,
                converter_digest=request.descriptor.converter_digest,
            ),
        ),
        generated_tokens=1,
        output_bytes=3,
        coverage={"image": 1},
        worker_reaped=True,
        package_id=request.package_id,
        package_revision_digest=request.package_revision_digest,
        material_lock_digest=request.descriptor.material_lock_digest,
        converter_digest=request.descriptor.converter_digest,
        contract_digest=request.descriptor.contract_digest,
    )


def _publication_handler(tmp_path):
    return SealedArtifactOutputHandler(
        service=SealedArtifactOutputHandleService(
            store=PrivateStateStore(tmp_path / "state"), owner="host"
        ),
        declaration_resolver=lambda workflow_id, package_id, digest: (
            (SealedArtifactOutput("result", "image/png", 16, None),)
            if (workflow_id, package_id, digest)
            == ("floorplan", "floorplan-from-image", _PUBLICATION_DESCRIPTOR)
            else None
        ),
    )


def _recording_publication_handler(
    tmp_path, events: list[str], *, fail_promote: bool = False
) -> SealedArtifactOutputHandler:
    return _RecordingOutputHandler(
        service=SealedArtifactOutputHandleService(
            store=PrivateStateStore(tmp_path / "state"), owner="host"
        ),
        declaration_resolver=lambda workflow_id, package_id, digest: (
            (SealedArtifactOutput("result", "image/png", 16, None),)
            if (workflow_id, package_id, digest)
            == ("floorplan", "floorplan-from-image", _PUBLICATION_DESCRIPTOR)
            else None
        ),
        events=events,
        fail_promote=fail_promote,
    )


class _PublicationMaterializer:
    def __init__(self, content: bytes = b"png", events: list[str] | None = None) -> None:
        self.content = content
        self.events = events
        self.calls: list[SealedMultimodalHandle] = []

    def resolve(
        self,
        handle: SealedMultimodalHandle,
        *,
        package_id: str,
        package_revision_digest: str,
        invocation_id: str,
        descriptor_digest: str,
        expires_at: datetime,
        now: datetime,
    ) -> tuple[str, str, bytes]:
        if self.events is not None:
            self.events.append("materialize")
        self.calls.append(handle)
        assert handle.package_id == package_id
        assert handle.package_revision_digest == package_revision_digest
        assert handle.invocation_id == invocation_id
        assert descriptor_digest == _PUBLICATION_DESCRIPTOR
        assert now < expires_at
        return handle.role, "image/png", self.content


class _RecordingOutputHandler(SealedArtifactOutputHandler):
    def __init__(self, *args, events: list[str], fail_promote: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = events
        self.fail_promote = fail_promote

    def stage_declared(
        self, request: SealedArtifactOutputStageRequest, *, now: datetime
    ) -> SealedArtifactPrivateOutputSet:
        self.events.append("stage")
        return super().stage_declared(request, now=now)

    def promote(
        self, private: SealedArtifactPrivateOutputSet, *, now: datetime
    ):
        self.events.append("promote")
        if self.fail_promote:
            raise RuntimeError("private promotion failure")
        return super().promote(private, now=now)

    def discard(
        self, private: SealedArtifactPrivateOutputSet, *, now: datetime
    ) -> None:
        self.events.append("discard")
        super().discard(private, now=now)


def test_descriptor_uses_closed_canonical_json_and_sha256_digest() -> None:
    descriptor = _descriptor()
    payload = json.loads(descriptor.canonical_bytes)
    assert "contract_digest" not in payload
    assert (
        descriptor.contract_digest
        == hashlib.sha256(descriptor.canonical_bytes).hexdigest()
    )
    assert descriptor.contract_digest == descriptor.digest
    assert descriptor.protocol_id == "dar.multimodal-runner.v1"
    assert descriptor.protocol_version == "1.0"


def test_descriptor_rejects_changed_declared_digest() -> None:
    descriptor = _descriptor()
    with pytest.raises(MultimodalRunnerProtocolError):
        MultimodalRunnerDescriptor(
            **{
                **descriptor.to_mapping(),
                "contract_digest": _digest("wrong"),
            }
        )


def test_health_is_bounded_and_redacted() -> None:
    assert MultimodalRunnerHealth("ready").to_mapping() == {
        "status": "ready",
        "reason": None,
    }
    with pytest.raises(MultimodalRunnerProtocolError):
        MultimodalRunnerHealth("ready", reason="/private/model/path")


def test_request_binds_opaque_handle_to_package_revision_and_invocation() -> None:
    request = _request()
    assert request.identity_tuple[-1] == request.invocation_id
    assert request.to_mapping()["handles"][0]["value"] == "sealed:image:one"
    with pytest.raises(MultimodalRunnerProtocolError):
        SealedMultimodalRequest(
            package_id=request.package_id,
            package_revision_digest=request.package_revision_digest,
            invocation_id=request.invocation_id,
            descriptor=request.descriptor,
            handles=(
                SealedMultimodalHandle(
                    value="/private/model/path",
                    role="image",
                    package_id=request.package_id,
                    package_revision_digest=request.package_revision_digest,
                    invocation_id=request.invocation_id,
                    material_lock_digest=request.descriptor.material_lock_digest,
                    converter_digest=request.descriptor.converter_digest,
                ),
            ),
        )
    with pytest.raises(MultimodalRunnerProtocolError):
        SealedMultimodalHandle(
            value="sealed:image:one",
            role="image",
            package_id=request.package_id,
            package_revision_digest=request.package_revision_digest,
            invocation_id="/private/model/path",
            material_lock_digest=request.descriptor.material_lock_digest,
            converter_digest=request.descriptor.converter_digest,
        )


def test_context_requires_the_canonical_seven_budget_fields() -> None:
    budget = {
        "max_new_tokens_per_fragment": 32,
        "max_continuations": 0,
        "max_total_generated_tokens": 32,
        "max_total_output_bytes": 4_096,
        "max_effective_context_tokens": 4_096,
        "max_runtime_milliseconds": 60_000,
        "max_memory_bytes": 2_000_000_000,
    }
    context = DARGenerationRequestContext(
        invocation_id="invocation-1",
        invocation_digest=_digest("invocation"),
        execution_device="mps",
        generation_budget=budget,
        cancellation_supported=False,
        worker_protocol="generation-worker-v1",
    )
    assert context.to_mapping()["generation_budget"] == budget
    with pytest.raises(MultimodalRunnerProtocolError):
        DARGenerationRequestContext(
            invocation_id="invocation-1",
            invocation_digest=_digest("invocation"),
            execution_device="mps",
            generation_budget={"max_runtime_milliseconds": 1},
            cancellation_supported=False,
            worker_protocol="generation-worker-v1",
        )


def test_result_requires_reaped_attestation_and_identity_bound_output() -> None:
    request = _request()
    result = MultimodalRunnerResult(
        status="completed",
        text="<svg />",
        output_handles=(),
        generated_tokens=4,
        output_bytes=7,
        coverage={"image": 1},
        worker_reaped=True,
        package_id=request.package_id,
        package_revision_digest=request.package_revision_digest,
        material_lock_digest=request.descriptor.material_lock_digest,
        converter_digest=request.descriptor.converter_digest,
        contract_digest=request.descriptor.contract_digest,
    )
    assert result.to_mapping()["worker_reaped"] is True
    with pytest.raises(MultimodalRunnerProtocolError):
        MultimodalRunnerResult(
            **{
                **result.to_mapping(),
                "worker_reaped": False,
            }
        )


class _FakeRunner:
    def __init__(self, descriptor: MultimodalRunnerDescriptor) -> None:
        self._descriptor = descriptor
        self.run_calls = 0

    @property
    def runner_id(self) -> str:
        return self._descriptor.runner_id

    def describe(self) -> MultimodalRunnerDescriptor:
        return self._descriptor

    def health(self) -> MultimodalRunnerHealth:
        return MultimodalRunnerHealth("ready")

    def run(
        self,
        request: SealedMultimodalRequest,
        *,
        context: DARGenerationRequestContext,
    ) -> MultimodalRunnerResult:
        self.run_calls += 1
        return MultimodalRunnerResult(
            status="completed",
            text="ok",
            output_handles=(),
            generated_tokens=1,
            output_bytes=2,
            coverage={},
            worker_reaped=True,
            package_id=request.package_id,
            package_revision_digest=request.package_revision_digest,
            material_lock_digest=request.descriptor.material_lock_digest,
            converter_digest=request.descriptor.converter_digest,
            contract_digest=request.descriptor.contract_digest,
        )


def test_admission_binds_one_exact_runner_without_dispatch() -> None:
    runner = _FakeRunner(_descriptor())
    binding = admit_multimodal_runner(runner, expected_descriptor=_descriptor())
    assert isinstance(binding, MultimodalRunnerBinding)
    assert binding.health().status == "ready"
    assert runner.run_calls == 0


def test_admission_rejects_descriptor_drift_and_unavailable_health() -> None:
    runner = _FakeRunner(_descriptor())
    changed = MultimodalRunnerDescriptor(
        **{
            **_descriptor().to_mapping(),
            "runner_id": "different-runner",
            "contract_digest": "",
        }
    )
    with pytest.raises(MultimodalRunnerAdmissionError):
        admit_multimodal_runner(runner, expected_descriptor=changed)

    class UnavailableRunner(_FakeRunner):
        def health(self) -> MultimodalRunnerHealth:
            return MultimodalRunnerHealth("unavailable", reason="runtime_unavailable")

    with pytest.raises(MultimodalRunnerAdmissionError):
        admit_multimodal_runner(
            UnavailableRunner(_descriptor()), expected_descriptor=_descriptor()
        )


def test_catalog_registers_and_resolves_one_multimodal_runner_without_dispatch() -> (
    None
):
    descriptor = MultimodalRunnerDescriptor(
        **{
            **_descriptor().to_mapping(),
            "runner_id": "multimodal-test",
            "contract_digest": "",
        }
    )
    runner = _FakeRunner(descriptor)
    catalog = LocalModelRunnerCatalog(())

    catalog.register_multimodal_runner(runner, expected_descriptor=descriptor)

    assert (
        catalog.resolve_multimodal_runner(
            descriptor.runner_id, expected_descriptor=descriptor
        ).runner
        is runner
    )
    assert runner.run_calls == 0


def test_catalog_rejects_duplicate_reserved_and_drifted_multimodal_runners() -> None:
    descriptor = MultimodalRunnerDescriptor(
        **{
            **_descriptor().to_mapping(),
            "runner_id": "multimodal-test",
            "contract_digest": "",
        }
    )
    runner = _FakeRunner(descriptor)
    catalog = LocalModelRunnerCatalog(())
    catalog.register_multimodal_runner(runner, expected_descriptor=descriptor)
    with pytest.raises(ModelExecutionError, match="unavailable"):
        catalog.register_multimodal_runner(runner, expected_descriptor=descriptor)

    reserved = _FakeRunner(_descriptor())
    with pytest.raises(ModelExecutionError, match="unavailable"):
        catalog.register_multimodal_runner(
            reserved, expected_descriptor=reserved._descriptor
        )

    changed = MultimodalRunnerDescriptor(
        **{
            **descriptor.to_mapping(),
            "material_lock_digest": _digest("changed"),
            "contract_digest": "",
        }
    )
    with pytest.raises(ModelExecutionError, match="unavailable"):
        catalog.register_multimodal_runner(
            _FakeRunner(descriptor), expected_descriptor=changed
        )


def test_binding_consumes_one_invocation_and_rejects_replay_before_dispatch() -> None:
    runner = _FakeRunner(_descriptor())
    binding = admit_multimodal_runner(runner, expected_descriptor=_descriptor())
    context = DARGenerationRequestContext(
        invocation_id="invocation-1",
        invocation_digest=_digest("invocation"),
        execution_device="mps",
        generation_budget={
            "max_new_tokens_per_fragment": 32,
            "max_continuations": 0,
            "max_total_generated_tokens": 32,
            "max_total_output_bytes": 4_096,
            "max_effective_context_tokens": 4_096,
            "max_runtime_milliseconds": 60_000,
            "max_memory_bytes": 2_000_000_000,
        },
        cancellation_supported=False,
        worker_protocol="generation-worker-v1",
    )
    binding.run(_request(), context=context)
    with pytest.raises(MultimodalRunnerAdmissionError):
        binding.run(_request(), context=context)
    assert runner.run_calls == 1


def test_option1_resolves_one_sealed_converter_input_before_runner_dispatch() -> None:
    descriptor = _descriptor()
    revision = _digest("revision")
    request = replace(
        _request(),
        handles=(
            *_request().handles,
            SealedMultimodalHandle(
                value="sealed:converter-input",
                role="converter_input",
                package_id="floorplan-from-image",
                package_revision_digest=revision,
                invocation_id="invocation-1",
                material_lock_digest=descriptor.material_lock_digest,
                converter_digest=descriptor.converter_digest,
            ),
        ),
    )
    resolved: list[bytes] = []

    class Materializer(SealedMultimodalInputMaterializer):
        def resolve(self, handle, **kwargs):
            assert handle.role == "converter_input"
            assert kwargs == {
                "package_id": request.package_id,
                "package_revision_digest": request.package_revision_digest,
                "invocation_id": request.invocation_id,
                "descriptor_digest": descriptor.contract_digest,
                "expires_at": _PUBLICATION_NOW + timedelta(minutes=5),
                "now": _PUBLICATION_NOW,
            }
            resolved.append(b"private-canonical-payload")
            return resolved[-1]

    class Runner(_FakeRunner):
        def run(self, request, *, context, input_materializer):
            assert callable(getattr(input_materializer, "resolve", None))
            assert input_materializer.resolve(
                next(handle for handle in request.handles if handle.role == "converter_input"),
                package_id=request.package_id,
                package_revision_digest=request.package_revision_digest,
                invocation_id=request.invocation_id,
                descriptor_digest=request.descriptor.contract_digest,
                expires_at=_PUBLICATION_NOW + timedelta(minutes=5),
                now=_PUBLICATION_NOW,
            ) == b"private-canonical-payload"
            return super().run(request, context=context)

    runner = Runner(descriptor)
    binding = admit_multimodal_runner(runner, expected_descriptor=descriptor)
    binding.dispatch(
        request,
        context=_context(),
        input_materializer=Materializer(),
        clear_inputs=lambda: None,
        release_reservation=lambda: None,
        reap_worker=lambda: None,
    )
    assert resolved == [b"private-canonical-payload"]


def test_option1_rejects_converter_input_without_receiver_materializer() -> None:
    descriptor = _descriptor()
    request = replace(
        _request(),
        handles=(
            *_request().handles,
            SealedMultimodalHandle(
                value="sealed:converter-input",
                role="converter_input",
                package_id="floorplan-from-image",
                package_revision_digest=_digest("revision"),
                invocation_id="invocation-1",
                material_lock_digest=descriptor.material_lock_digest,
                converter_digest=descriptor.converter_digest,
            ),
        ),
    )
    binding = admit_multimodal_runner(
        _FakeRunner(descriptor), expected_descriptor=descriptor
    )

    with pytest.raises(
        MultimodalRunnerAdmissionError, match="materializer is unavailable"
    ):
        binding.run(request, context=_context())


def test_transformers_option1_runner_enters_through_protocol_with_private_payload() -> None:
    from dynamic_agent_runner.openai_client import ModelResponse
    from dynamic_agent_runner.workflow_host.transformers_peft_model import (
        TransformersPeftMultimodalRunner,
    )

    descriptor = _descriptor()
    request = replace(
        _request(),
        handles=(
            *_request().handles,
            SealedMultimodalHandle(
                value="sealed:converter-input",
                role="converter_input",
                package_id="floorplan-from-image",
                package_revision_digest=_digest("revision"),
                invocation_id="invocation-1",
                material_lock_digest=descriptor.material_lock_digest,
                converter_digest=descriptor.converter_digest,
            ),
        ),
    )
    seen: list[bytes] = []

    class Adapter:
        def create_response_from_canonical_payload(self, *, content: bytes):
            seen.append(content)
            return ModelResponse(content='{"walls":[]}', metadata={})

    class Materializer:
        expires_at = _PUBLICATION_NOW + timedelta(minutes=5)
        now = _PUBLICATION_NOW

        def resolve(self, _handle, **_kwargs):
            return b"private-canonical-payload"

    runner = TransformersPeftMultimodalRunner(
        descriptor=descriptor,
        adapter=Adapter(),
    )
    binding = admit_multimodal_runner(runner, expected_descriptor=descriptor)
    result = binding.dispatch(
        request,
        context=_context(),
        input_materializer=Materializer(),
        clear_inputs=lambda: None,
        release_reservation=lambda: None,
        reap_worker=lambda: None,
    )

    assert result.text == '{"walls":[]}'
    assert seen == [b"private-canonical-payload"]


def test_binding_rejects_foreign_result_identity() -> None:
    class ForeignRunner(_FakeRunner):
        def run(
            self,
            request: SealedMultimodalRequest,
            *,
            context: DARGenerationRequestContext,
        ) -> MultimodalRunnerResult:
            result = super().run(request, context=context)
            return MultimodalRunnerResult(
                **{**result.to_mapping(), "package_id": "other-package"}
            )

    runner = ForeignRunner(_descriptor())
    binding = admit_multimodal_runner(runner, expected_descriptor=_descriptor())
    context = DARGenerationRequestContext(
        invocation_id="invocation-1",
        invocation_digest=_digest("invocation"),
        execution_device="mps",
        generation_budget={
            "max_new_tokens_per_fragment": 32,
            "max_continuations": 0,
            "max_total_generated_tokens": 32,
            "max_total_output_bytes": 4_096,
            "max_effective_context_tokens": 4_096,
            "max_runtime_milliseconds": 60_000,
            "max_memory_bytes": 2_000_000_000,
        },
        cancellation_supported=False,
        worker_protocol="generation-worker-v1",
    )
    with pytest.raises(MultimodalRunnerProtocolError, match="identity"):
        binding.run(_request(), context=context)


def test_dispatch_runs_once_and_reaps_before_returning_result() -> None:
    runner = _FakeRunner(_descriptor())
    binding = admit_multimodal_runner(runner, expected_descriptor=_descriptor())
    events: list[str] = []
    result = binding.dispatch(
        _request(),
        context=_context(),
        clear_inputs=lambda: events.append("clear"),
        release_reservation=lambda: events.append("release"),
        reap_worker=lambda: events.append("reap"),
    )
    assert result.status == "completed"
    assert events == ["clear", "release", "reap"]


def test_dispatch_maps_cleanup_failure_without_returning_output() -> None:
    runner = _FakeRunner(_descriptor())
    binding = admit_multimodal_runner(runner, expected_descriptor=_descriptor())
    events: list[str] = []
    with pytest.raises(MultimodalRunnerProtocolError, match="cleanup_failed"):
        binding.dispatch(
            _request(),
            context=_context(),
            clear_inputs=lambda: events.append("clear"),
            release_reservation=lambda: events.append("release"),
            reap_worker=lambda: (_ for _ in ()).throw(RuntimeError("private")),
        )
    assert events == ["clear", "release"]


def test_result_receipt_is_redacted_to_normalized_fields_and_limits() -> None:
    request = _request()
    result = MultimodalRunnerResult(
        status="completed",
        text="<svg />",
        output_handles=(),
        generated_tokens=4,
        output_bytes=7,
        coverage={"image": 1},
        worker_reaped=True,
        package_id=request.package_id,
        package_revision_digest=request.package_revision_digest,
        material_lock_digest=request.descriptor.material_lock_digest,
        converter_digest=request.descriptor.converter_digest,
        contract_digest=request.descriptor.contract_digest,
    )
    receipt = result.to_redacted_mapping()
    assert set(receipt) == {
        "status",
        "text",
        "output_handles",
        "generated_tokens",
        "output_bytes",
        "coverage",
        "worker_reaped",
        "package_id",
        "package_revision_digest",
        "material_lock_digest",
        "converter_digest",
        "contract_digest",
    }
    assert "/private" not in json.dumps(receipt)


def test_host_dispatch_publishes_only_after_completed_cleanup() -> None:
    descriptor = MultimodalRunnerDescriptor(
        **{
            **_descriptor().to_mapping(),
            "runner_id": "multimodal-host-test",
            "contract_digest": "",
        }
    )
    runner = _FakeRunner(descriptor)
    catalog = LocalModelRunnerCatalog(())
    catalog.register_multimodal_runner(runner, expected_descriptor=descriptor)
    host = object.__new__(LocalWorkflowHost)
    host._multimodal_runner_catalog = catalog
    events: list[str] = []
    published: list[MultimodalRunnerResult] = []
    result = host.dispatch_multimodal_runner(
        descriptor.runner_id,
        expected_descriptor=descriptor,
        request=_request_for_descriptor(descriptor),
        context=_context(),
        clear_inputs=lambda: events.append("clear"),
        release_reservation=lambda: events.append("release"),
        reap_worker=lambda: events.append("reap"),
        publish_result=published.append,
    )
    assert result.status == "completed"
    assert published == [result]
    assert events == ["clear", "release", "reap"]


@pytest.mark.parametrize(
    ("status", "should_cancel", "deadline_expired"),
    (
        ("cancelled", lambda: True, lambda: False),
        ("deadline_exceeded", lambda: False, lambda: True),
    ),
)
def test_dispatch_terminal_gate_cleans_up_without_runner_call(
    status: str,
    should_cancel: object,
    deadline_expired: object,
) -> None:
    runner = _FakeRunner(_descriptor())
    binding = admit_multimodal_runner(runner, expected_descriptor=_descriptor())
    events: list[str] = []
    result = binding.dispatch(
        _request(),
        context=_context(),
        clear_inputs=lambda: events.append("clear"),
        release_reservation=lambda: events.append("release"),
        reap_worker=lambda: events.append("reap"),
        should_cancel=should_cancel,  # type: ignore[arg-type]
        deadline_expired=deadline_expired,  # type: ignore[arg-type]
    )
    assert result.status == status
    assert runner.run_calls == 0
    assert events == ["clear", "release", "reap"]


def test_dispatch_with_worker_cleanup_uses_existing_launcher_contract() -> None:
    class Controller:
        def terminate(self, _child: object) -> None:
            pass

        def kill(self, _child: object) -> None:
            pass

        def reap(self, _child: object, _timeout: float) -> bool:
            return True

    runner = _FakeRunner(_descriptor())
    binding = admit_multimodal_runner(runner, expected_descriptor=_descriptor())
    result = binding.dispatch_with_worker_cleanup(
        _request(),
        context=_context(),
        clear_inputs=lambda: None,
        release_reservation=lambda: None,
        launcher=GenerationWorkerLauncher(),
        child=object(),
        controller=Controller(),
        deadline=GenerationDeadline.start(0.0, max_runtime_milliseconds=1_000),
        clock=lambda: 0.0,
    )
    assert result.status == "completed"


def test_dispatch_maps_runner_failure_after_cleanup() -> None:
    class FailingRunner(_FakeRunner):
        def run(
            self,
            request: SealedMultimodalRequest,
            *,
            context: DARGenerationRequestContext,
        ) -> MultimodalRunnerResult:
            raise RuntimeError("private provider failure")

    runner = FailingRunner(_descriptor())
    binding = admit_multimodal_runner(runner, expected_descriptor=_descriptor())
    events: list[str] = []
    with pytest.raises(MultimodalRunnerProtocolError, match="runner_failed"):
        binding.dispatch(
            _request(),
            context=_context(),
            clear_inputs=lambda: events.append("clear"),
            release_reservation=lambda: events.append("release"),
            reap_worker=lambda: events.append("reap"),
        )
    assert events == ["clear", "release", "reap"]


def test_dispatch_preserves_budget_exhausted_terminal_result() -> None:
    class BudgetRunner(_FakeRunner):
        def run(
            self,
            request: SealedMultimodalRequest,
            *,
            context: DARGenerationRequestContext,
        ) -> MultimodalRunnerResult:
            return MultimodalRunnerResult(
                status="budget_exhausted",
                text=None,
                output_handles=(),
                generated_tokens=32,
                output_bytes=0,
                coverage={},
                worker_reaped=True,
                package_id=request.package_id,
                package_revision_digest=request.package_revision_digest,
                material_lock_digest=request.descriptor.material_lock_digest,
                converter_digest=request.descriptor.converter_digest,
                contract_digest=request.descriptor.contract_digest,
            )

    runner = BudgetRunner(_descriptor())
    binding = admit_multimodal_runner(runner, expected_descriptor=_descriptor())
    result = binding.dispatch(
        _request(),
        context=_context(),
        clear_inputs=lambda: None,
        release_reservation=lambda: None,
        reap_worker=lambda: None,
    )
    assert result.status == "budget_exhausted"


def test_host_materializer_publishes_opaque_output_handles(tmp_path) -> None:
    request = _publication_request()
    result = _publication_result()
    materializer = _PublicationMaterializer()
    handles = object.__new__(LocalWorkflowHost).publish_multimodal_result(
        result,
        request=request,
        workflow_id="floorplan",
        receiver_id="host",
        descriptor_digest=_PUBLICATION_DESCRIPTOR,
        expires_at=_PUBLICATION_NOW + timedelta(minutes=1),
        now=_PUBLICATION_NOW,
        materializer=materializer,
        output_handler=_publication_handler(tmp_path),
    )
    assert len(handles) == 1
    assert handles[0].role == "result"
    assert handles[0].media_type == "image/png"
    assert materializer.calls == [result.output_handles[0]]


def test_host_publication_bypasses_materializer_for_text_result(tmp_path) -> None:
    request = _request()
    materializer = _PublicationMaterializer()
    result = MultimodalRunnerResult(
        status="completed",
        text="ok",
        output_handles=(),
        generated_tokens=1,
        output_bytes=2,
        coverage={},
        worker_reaped=True,
        package_id=request.package_id,
        package_revision_digest=request.package_revision_digest,
        material_lock_digest=request.descriptor.material_lock_digest,
        converter_digest=request.descriptor.converter_digest,
        contract_digest=request.descriptor.contract_digest,
    )
    handles = object.__new__(LocalWorkflowHost).publish_multimodal_result(
        result,
        request=request,
        workflow_id="floorplan",
        receiver_id="host",
        descriptor_digest=_PUBLICATION_DESCRIPTOR,
        expires_at=_PUBLICATION_NOW + timedelta(minutes=1),
        now=_PUBLICATION_NOW,
        materializer=materializer,
        output_handler=_publication_handler(tmp_path),
    )
    assert handles == ()
    assert materializer.calls == []


def test_host_publication_rejects_foreign_result_before_materialization(tmp_path) -> None:
    request = _publication_request()
    result = replace(
        _publication_result(),
        package_id="foreign-package",
        output_handles=(
            replace(
                _publication_result().output_handles[0],
                package_id="foreign-package",
            ),
        ),
    )
    materializer = _PublicationMaterializer()
    with pytest.raises(ValueError, match="publication failed"):
        object.__new__(LocalWorkflowHost).publish_multimodal_result(
            result,
            request=request,
            workflow_id="floorplan",
            receiver_id="host",
            descriptor_digest=_PUBLICATION_DESCRIPTOR,
            expires_at=_PUBLICATION_NOW + timedelta(minutes=1),
            now=_PUBLICATION_NOW,
            materializer=materializer,
            output_handler=_publication_handler(tmp_path),
        )
    assert materializer.calls == []


def test_host_publication_redacts_materializer_failure(tmp_path) -> None:
    class FailingMaterializer(_PublicationMaterializer):
        def resolve(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("/private/model/output-bytes")

    with pytest.raises(ValueError, match="publication failed") as error:
        object.__new__(LocalWorkflowHost).publish_multimodal_result(
            _publication_result(),
            request=_publication_request(),
            workflow_id="floorplan",
            receiver_id="host",
            descriptor_digest=_PUBLICATION_DESCRIPTOR,
            expires_at=_PUBLICATION_NOW + timedelta(minutes=1),
            now=_PUBLICATION_NOW,
            materializer=FailingMaterializer(),
            output_handler=_publication_handler(tmp_path),
        )
    assert "/private" not in str(error.value)


def test_host_publication_orders_cleanup_materialize_stage_and_promote(tmp_path) -> None:
    events = ["clear", "release", "reap"]
    materializer = _PublicationMaterializer(events=events)
    handles = object.__new__(LocalWorkflowHost).publish_multimodal_result(
        _publication_result(),
        request=_publication_request(),
        workflow_id="floorplan",
        receiver_id="host",
        descriptor_digest=_PUBLICATION_DESCRIPTOR,
        expires_at=_PUBLICATION_NOW + timedelta(minutes=1),
        now=_PUBLICATION_NOW,
        materializer=materializer,
        output_handler=_recording_publication_handler(tmp_path, events),
    )
    assert len(handles) == 1
    assert events == ["clear", "release", "reap", "materialize", "stage", "promote"]


def test_host_publication_discards_staged_output_on_promotion_failure(tmp_path) -> None:
    events = ["clear", "release", "reap"]
    with pytest.raises(ValueError, match="publication failed") as error:
        object.__new__(LocalWorkflowHost).publish_multimodal_result(
            _publication_result(),
            request=_publication_request(),
            workflow_id="floorplan",
            receiver_id="host",
            descriptor_digest=_PUBLICATION_DESCRIPTOR,
            expires_at=_PUBLICATION_NOW + timedelta(minutes=1),
            now=_PUBLICATION_NOW,
            materializer=_PublicationMaterializer(events=events),
            output_handler=_recording_publication_handler(
                tmp_path, events, fail_promote=True
            ),
        )
    assert str(error.value) == "multimodal result publication failed"
    assert events == [
        "clear",
        "release",
        "reap",
        "materialize",
        "stage",
        "promote",
        "discard",
    ]


def test_host_publication_rejects_aggregate_byte_mismatch(tmp_path) -> None:
    result = replace(_publication_result(), output_bytes=4)
    with pytest.raises(ValueError, match="publication failed"):
        object.__new__(LocalWorkflowHost).publish_multimodal_result(
            result,
            request=_publication_request(),
            workflow_id="floorplan",
            receiver_id="host",
            descriptor_digest=_PUBLICATION_DESCRIPTOR,
            expires_at=_PUBLICATION_NOW + timedelta(minutes=1),
            now=_PUBLICATION_NOW,
            materializer=_PublicationMaterializer(),
            output_handler=_publication_handler(tmp_path),
        )


def test_host_publication_rejects_candidate_over_declared_limit(tmp_path) -> None:
    content = b"x" * 17
    result = replace(_publication_result(), output_bytes=len(content))
    with pytest.raises(ValueError, match="publication failed") as error:
        object.__new__(LocalWorkflowHost).publish_multimodal_result(
            result,
            request=_publication_request(),
            workflow_id="floorplan",
            receiver_id="host",
            descriptor_digest=_PUBLICATION_DESCRIPTOR,
            expires_at=_PUBLICATION_NOW + timedelta(minutes=1),
            now=_PUBLICATION_NOW,
            materializer=_PublicationMaterializer(content),
            output_handler=_publication_handler(tmp_path),
        )
    assert content.decode() not in str(error.value)
