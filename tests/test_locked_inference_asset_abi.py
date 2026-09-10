from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.locked_inference_asset_abi import (
    LockedInferenceAssetAbi,
    LockedInferenceAssetAbiError,
)
from dynamic_agent_runner.workflow_host.sandbox_result_location import (
    ResultLocationError,
)


def test_callback_asset_abi_binds_exact_asset_roles_and_result_slots() -> None:
    abi = LockedInferenceAssetAbi.from_mapping(
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
                    "max_bytes": 128,
                }
            ],
        }
    )
    assert abi.result_declarations[0].name == "answer"


def test_callback_asset_abi_creates_only_declared_atomic_result_location() -> None:
    abi = LockedInferenceAssetAbi.from_mapping(
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
                    "max_bytes": 128,
                }
            ],
        }
    )
    location = abi.create_result_location()
    location.write("answer", b"{}")
    assert location.seal()[0].byte_count == 2
    with pytest.raises(ResultLocationError):
        location.write("other", b"{}")


@pytest.mark.parametrize("field", ("authorized_roles", "sealed_inputs", "result_slots"))
def test_callback_asset_abi_rejects_empty_or_unordered_contracts(field: str) -> None:
    value = {
        "format_version": 1,
        "asset_digest": "a" * 64,
        "authorized_roles": ["suggest"],
        "sealed_inputs": ["snapshot"],
        "result_slots": [
            {
                "name": "answer",
                "media_type": "application/json",
                "schema_digest": "b" * 64,
                "max_bytes": 128,
            }
        ],
    }
    value[field] = []
    with pytest.raises(LockedInferenceAssetAbiError):
        LockedInferenceAssetAbi.from_mapping(value)
