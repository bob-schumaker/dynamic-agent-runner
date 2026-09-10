"""Contract tests for the sealed artifact Python ABI."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactAssetRuntime,
    SealedArtifactExecutionContext,
    SealedArtifactExecutionError,
    SealedArtifactInput,
    SealedArtifactOutput,
    SealedArtifactOutputCollector,
    SealedArtifactRunnerDescriptor,
)


def _descriptor() -> SealedArtifactRunnerDescriptor:
    return SealedArtifactRunnerDescriptor(
        digest="a" * 64,
        asset_path="assets/runner.py",
        asset_digest="b" * 64,
        capability_requirements_digest="c" * 64,
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
        schema_assets=(),
        child_contract_digests=(),
        callbacks=(),
        output_roles=("result",),
    )


def _context(descriptor: SealedArtifactRunnerDescriptor):
    collector = SealedArtifactOutputCollector(descriptor=descriptor)
    context = SealedArtifactExecutionContext(
        descriptor=descriptor,
        read_input=lambda role: b"snapshot" if role == "snapshot" else b"",
        invoke_callback=lambda _name, _request: b"",
        collector=collector,
    )
    return context, collector


def test_asset_runtime_runs_only_fixed_context_abi() -> None:
    descriptor = _descriptor()
    context, collector = _context(descriptor)

    sealed = SealedArtifactAssetRuntime().execute(
        asset=b"def run(context):\n    context.write_output('result', 'application/octet-stream', context.read_input('snapshot'))\n",
        context=context,
    )

    assert sealed == (("result", "application/octet-stream", b"snapshot"),)


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
