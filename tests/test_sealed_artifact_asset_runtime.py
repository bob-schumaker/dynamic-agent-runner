"""Contract tests for the sealed artifact Python ABI."""

from __future__ import annotations

from dataclasses import replace
from threading import Event
from time import monotonic

import pytest

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactAssetRuntime,
    SealedArtifactCallback,
    SealedArtifactExecutionContext,
    SealedArtifactExecutionError,
    SealedArtifactInput,
    SealedArtifactLimits,
    SealedArtifactOutput,
    SealedArtifactOutputCollector,
    SealedArtifactOutputCollectorError,
    SealedArtifactRunnerDescriptor,
)


def _descriptor() -> SealedArtifactRunnerDescriptor:
    return SealedArtifactRunnerDescriptor(
        digest="a" * 64,
        asset_path="assets/runner.py",
        asset_digest="b" * 64,
        capability_requirements_digest="c" * 64,
        profile_digest="d" * 64,
        inputs=(
            SealedArtifactInput(
                role="snapshot",
                media_type="application/octet-stream",
                max_bytes=10,
                required=True,
                schema_digest=None,
            ),
        ),
        outputs=(
            SealedArtifactOutput(
                role="result",
                media_type="application/octet-stream",
                max_bytes=10,
                schema_digest=None,
            ),
        ),
        limits=SealedArtifactLimits(1, 1, 100, 1, 1),
        schema_assets=(),
        child_contract_digests=(),
        callbacks=(),
        output_roles=("result",),
    )


def _context(descriptor: SealedArtifactRunnerDescriptor):
    collector = SealedArtifactOutputCollector(descriptor=descriptor)

    class Callbacks:
        def revalidate(self, _callback: SealedArtifactCallback) -> None:
            return None

        def invoke(self, _name: str, _request: bytes) -> bytes:
            return b""

    context = SealedArtifactExecutionContext(
        descriptor=descriptor,
        read_input=lambda role: b"snapshot" if role == "snapshot" else b"",
        callback_provider=Callbacks(),
        collector=collector,
    )
    return context, collector


def test_asset_runtime_runs_only_fixed_context_abi() -> None:
    descriptor = _descriptor()
    context, collector = _context(descriptor)
    runtime = SealedArtifactAssetRuntime()

    sealed = runtime.execute(
        asset=b"def run(context):\n    context.write_output('result', 'application/octet-stream', context.read_input('snapshot'))\n",
        context=context,
    )

    assert sealed == (("result", "application/octet-stream", b"snapshot"),)
    assert runtime.receipts() == (
        {
            "callback_count": 0,
            "descriptor_digest": descriptor.digest,
            "output_bytes": len(b"snapshot"),
            "output_count": 1,
            "status": "completed",
        },
    )


def test_asset_runtime_receipt_is_redacted_after_failure() -> None:
    descriptor = _descriptor()
    context, _collector = _context(descriptor)
    runtime = SealedArtifactAssetRuntime()

    with pytest.raises(SealedArtifactExecutionError, match="unavailable"):
        runtime.execute(asset=b"def run(context):\n    return None\n", context=context)

    receipt = runtime.receipts()[0]
    assert receipt["status"] == "failed"
    assert receipt["descriptor_digest"] == descriptor.digest
    assert "snapshot" not in repr(receipt)


def test_asset_runtime_rejects_missing_declared_output() -> None:
    descriptor = _descriptor()
    context, _collector = _context(descriptor)

    with pytest.raises(SealedArtifactExecutionError, match="unavailable"):
        SealedArtifactAssetRuntime().execute(
            asset=b"def run(context):\n    return None\n", context=context
        )


def test_asset_runtime_rejects_imports_before_execution() -> None:
    descriptor = _descriptor()
    context, _collector = _context(descriptor)

    with pytest.raises(SealedArtifactExecutionError, match="unavailable"):
        SealedArtifactAssetRuntime().execute(
            asset=b"import os\ndef run(context):\n    return None\n", context=context
        )


def test_context_rejects_oversized_callback_request_before_provider_entry() -> None:
    descriptor = replace(
        _descriptor(),
        callbacks=(
            SealedArtifactCallback(
                name="generate",
                requirement="model.generate.v1",
                child_contract_digest="d" * 64,
                max_calls=1,
                max_concurrency=1,
                max_request_bytes=3,
                max_response_bytes=4,
                max_total_request_bytes=3,
                max_total_response_bytes=4,
                timeout_milliseconds=1,
            ),
        ),
    )
    context, _collector = _context(descriptor)

    with pytest.raises(SealedArtifactExecutionError, match="callback"):
        context.invoke_callback("generate", b"long")


def test_context_revalidates_callback_provider_immediately_before_entry() -> None:
    descriptor = replace(
        _descriptor(),
        callbacks=(
            SealedArtifactCallback(
                name="generate",
                requirement="model.generate.v1",
                child_contract_digest="d" * 64,
                max_calls=1,
                max_concurrency=1,
                max_request_bytes=3,
                max_response_bytes=4,
                max_total_request_bytes=3,
                max_total_response_bytes=4,
                timeout_milliseconds=1,
            ),
        ),
    )
    calls: list[str] = []

    class Callbacks:
        def revalidate(self, callback: SealedArtifactCallback) -> None:
            assert callback.name == "generate"
            calls.append("revalidate")

        def invoke(self, name: str, request: bytes) -> bytes:
            assert (name, request) == ("generate", b"ok")
            calls.append("invoke")
            return b"done"

    collector = SealedArtifactOutputCollector(descriptor=descriptor)
    context = SealedArtifactExecutionContext(
        descriptor=descriptor,
        read_input=lambda _role: b"",
        callback_provider=Callbacks(),
        collector=collector,
    )

    assert context.invoke_callback("generate", b"ok") == b"done"
    assert calls == ["revalidate", "invoke"]


def test_context_discards_a_callback_response_after_its_deadline() -> None:
    descriptor = replace(
        _descriptor(),
        callbacks=(
            SealedArtifactCallback(
                name="generate",
                requirement="model.generate.v1",
                child_contract_digest="d" * 64,
                max_calls=1,
                max_concurrency=1,
                max_request_bytes=3,
                max_response_bytes=4,
                max_total_request_bytes=3,
                max_total_response_bytes=4,
                timeout_milliseconds=1,
            ),
        ),
    )
    release = Event()
    completed = Event()

    class Callbacks:
        def revalidate(self, _callback: SealedArtifactCallback) -> None:
            return None

        def invoke(self, _name: str, _request: bytes) -> bytes:
            release.wait(1)
            completed.set()
            return b"done"

    collector = SealedArtifactOutputCollector(descriptor=descriptor)
    context = SealedArtifactExecutionContext(
        descriptor=descriptor,
        read_input=lambda _role: b"",
        callback_provider=Callbacks(),
        collector=collector,
    )

    with pytest.raises(SealedArtifactExecutionError, match="callback"):
        context.invoke_callback("generate", b"ok")

    release.set()
    assert completed.wait(1)


def test_runtime_deadline_revokes_late_callback_and_discards_output() -> None:
    descriptor = replace(
        _descriptor(),
        limits=SealedArtifactLimits(1, 1, 100, 1, 25),
        callbacks=(
            SealedArtifactCallback(
                name="generate",
                requirement="model.generate.v1",
                child_contract_digest="d" * 64,
                max_calls=1,
                max_concurrency=1,
                max_request_bytes=3,
                max_response_bytes=4,
                max_total_request_bytes=3,
                max_total_response_bytes=4,
                timeout_milliseconds=1_000,
            ),
        ),
    )
    release = Event()
    completed = Event()

    class Callbacks:
        def revalidate(self, _callback: SealedArtifactCallback) -> None:
            return None

        def invoke(self, _name: str, _request: bytes) -> bytes:
            release.wait(1)
            completed.set()
            return b"done"

    collector = SealedArtifactOutputCollector(descriptor=descriptor)
    context = SealedArtifactExecutionContext(
        descriptor=descriptor,
        read_input=lambda _role: b"",
        callback_provider=Callbacks(),
        collector=collector,
    )
    started = monotonic()

    with pytest.raises(SealedArtifactExecutionError, match="unavailable"):
        SealedArtifactAssetRuntime().execute(
            asset=(
                b"def run(context):\n"
                b"    result = context.invoke_callback('generate', b'ok')\n"
                b"    context.write_output('result', 'application/octet-stream', result)\n"
            ),
            context=context,
        )

    assert monotonic() - started < 0.5
    with pytest.raises(SealedArtifactOutputCollectorError, match="unavailable"):
        collector.seal()
    release.set()
    assert completed.wait(1)
    with pytest.raises(SealedArtifactOutputCollectorError, match="unavailable"):
        collector.seal()


def test_context_enforces_aggregate_io_before_input_return() -> None:
    descriptor = replace(_descriptor(), limits=SealedArtifactLimits(1, 1, 3, 1, 1))
    context, _collector = _context(descriptor)

    with pytest.raises(SealedArtifactExecutionError, match="input"):
        context.read_input("snapshot")
