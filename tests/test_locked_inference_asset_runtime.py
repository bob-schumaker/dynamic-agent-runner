from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.locked_inference_asset_abi import (
    LockedInferenceAssetAbi,
)
from dynamic_agent_runner.workflow_host.locked_inference_asset_runtime import (
    LockedInferenceAssetRuntime,
    LockedInferenceAssetRuntimeError,
)


def _abi() -> LockedInferenceAssetAbi:
    return LockedInferenceAssetAbi.from_mapping(
        {
            "format_version": 1,
            "asset_digest": "a" * 64,
            "authorized_roles": ["suggest"],
            "sealed_inputs": ["snapshot"],
            "result_slots": [
                {
                    "name": "answer",
                    "media_type": "application/json",
                    "schema_digest": "b" * 64,
                    "max_bytes": 64,
                }
            ],
        }
    )


def test_runtime_exposes_only_authorized_role_and_seals_results() -> None:
    runtime = LockedInferenceAssetRuntime(
        abi=_abi(),
        asset_digest="a" * 64,
        generate=lambda role, value: b'{"value":"ok"}',
    )
    sealed = runtime.run(
        role="suggest",
        sealed_inputs={"snapshot": b"data"},
        asset=lambda generate, inputs, results: results.write(
            "answer", generate("suggest", b'{"value":"request"}')
        ),
    )
    assert sealed[0].byte_count == 14


def test_runtime_rejects_wrong_asset_role_or_input_before_asset() -> None:
    called = False
    runtime = LockedInferenceAssetRuntime(
        abi=_abi(), asset_digest="a" * 64, generate=lambda *_: b"{}"
    )
    for digest, role, inputs in (
        ("b" * 64, "suggest", {"snapshot": b"x"}),
        ("a" * 64, "other", {"snapshot": b"x"}),
        ("a" * 64, "suggest", {}),
    ):
        runtime.asset_digest = digest
        with pytest.raises(LockedInferenceAssetRuntimeError):
            runtime.run(role=role, sealed_inputs=inputs, asset=lambda *_: called)
    assert called is False
