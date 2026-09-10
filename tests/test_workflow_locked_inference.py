"""Fake-only contract vectors for sealed locked inference roles."""

from __future__ import annotations

from hashlib import sha256

import pytest

from dynamic_agent_runner.workflow_host.locked_inference import (
    LockedInferenceError,
    derive_locked_inference_bindings,
    parse_inference_roles,
    validate_inference_material_roles,
)
from dynamic_agent_runner.workflow_host.material_sets import parse_model_material_sets


def _asset(path: str, character: str) -> dict[str, str]:
    return {"path": path, "sha256": character * 64}


def _role(
    *, role: str = "suggest", material_role: str = "suggest"
) -> dict[str, object]:
    return {
        "role": role,
        "material_role": material_role,
        "capability_id": "model.generate.v1",
        "instruction_asset": _asset("assets/instruction.txt", "a"),
        "request_schema_asset": _asset("assets/request-schema.json", "b"),
        "response_schema_asset": _asset("assets/response-schema.json", "c"),
        "authorized_asset_digests": ["d" * 64],
        "limits": {
            "max_calls": 1,
            "max_input_bytes": 1024,
            "max_output_bytes": 1024,
            "timeout_milliseconds": 1000,
            "max_concurrency": 1,
        },
    }


def _roles() -> dict[str, object]:
    return {"format_version": 1, "roles": [_role()]}


def test_inference_roles_have_canonical_bytes_and_exact_material_relation() -> None:
    roles = parse_inference_roles(_roles())

    assert roles.digest == sha256(roles.canonical_bytes).hexdigest()
    assert roles.for_role("suggest").material_role == "suggest"


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.update(unknown=True),
        lambda value: value.update(roles=[_role(role="z"), _role(role="a")]),
        lambda value: value.update(roles=[_role(), _role()]),
        lambda value: value["roles"][0].update(capability_id="other.generate.v1"),
        lambda value: value["roles"][0]["instruction_asset"].update(path="../escape"),
        lambda value: value["roles"][0]["limits"].update(max_calls=0),
    ),
)
def test_inference_roles_reject_malformed_or_noncanonical_values(mutate) -> None:
    value = _roles()
    mutate(value)

    with pytest.raises(LockedInferenceError):
        parse_inference_roles(value)


def test_inference_roles_require_distinct_declared_material_roles() -> None:
    materials = parse_model_material_sets(
        {
            "format_version": 1,
            "material_sets": [
                {
                    "role": "extract",
                    "model_materials": {
                        "format_version": 1,
                        "logical_model_id": "example",
                        "runner_contract": {"id": "runner", "version": "1"},
                        "loader_profile_contract": {"id": "profile", "version": "1"},
                        "sources": [
                            {
                                "role": "model",
                                "group": "base",
                                "source_type": "huggingface_file",
                                "repository": "example/model",
                                "revision": "a" * 40,
                                "filename": "model.gguf",
                                "sha256": "b" * 64,
                            }
                        ],
                        "preparation": [],
                    },
                }
            ],
        }
    )
    roles = parse_inference_roles(_roles())

    with pytest.raises(LockedInferenceError, match="material"):
        validate_inference_material_roles(roles, materials)


def test_inference_roles_verify_declared_digest() -> None:
    value = _roles()
    parsed = parse_inference_roles(value)
    value["inference_roles_digest"] = parsed.digest
    assert parse_inference_roles(value).digest == parsed.digest

    value["inference_roles_digest"] = "f" * 64
    with pytest.raises(LockedInferenceError, match="digest"):
        parse_inference_roles(value)


def test_inference_bindings_keep_each_role_material_and_generation_contract_private() -> (
    None
):
    from dynamic_agent_runner.workflow_host.capabilities import (
        CapabilityRequirement,
        CapabilityRequirements,
    )

    roles = parse_inference_roles(_roles())
    materials = parse_model_material_sets(
        {
            "format_version": 1,
            "material_sets": [
                {
                    "role": "suggest",
                    "model_materials": {
                        "format_version": 1,
                        "logical_model_id": "example",
                        "runner_contract": {"id": "runner", "version": "1"},
                        "loader_profile_contract": {"id": "profile", "version": "1"},
                        "sources": [
                            {
                                "role": "model",
                                "group": "base",
                                "source_type": "huggingface_file",
                                "repository": "example/model",
                                "revision": "a" * 40,
                                "filename": "model.gguf",
                                "sha256": "b" * 64,
                            }
                        ],
                        "preparation": [],
                    },
                }
            ],
        }
    )
    requirements = CapabilityRequirements(
        (
            CapabilityRequirement("model.execution.test.v1", "1", "e" * 64, ()),
            CapabilityRequirement("model.generate.v1", "1", "f" * 64, ("structured",)),
        ),
        {"runner": "model.execution.test.v1"},
    )

    bindings = derive_locked_inference_bindings(
        roles=roles, material_sets=materials, requirements=requirements
    )

    assert tuple(binding.role for binding in bindings) == ("suggest",)
    assert bindings[0].material_lock_digest == materials.for_role("suggest").digest
    assert bindings[0].capability_contract_digest == "f" * 64
    assert "provider" not in repr(bindings[0])


def test_inference_bindings_reject_missing_or_duplicate_generation_requirement() -> (
    None
):
    from dynamic_agent_runner.workflow_host.capabilities import (
        CapabilityRequirement,
        CapabilityRequirements,
    )

    roles = parse_inference_roles(_roles())
    materials = parse_model_material_sets(
        {
            "format_version": 1,
            "material_sets": [{"role": "suggest", "model_materials": _material_lock()}],
        }
    )
    missing = CapabilityRequirements(
        (CapabilityRequirement("model.execution.test.v1", "1", "e" * 64, ()),),
        {"runner": "model.execution.test.v1"},
    )

    with pytest.raises(LockedInferenceError, match="capability"):
        derive_locked_inference_bindings(
            roles=roles, material_sets=materials, requirements=missing
        )


def _material_lock() -> dict[str, object]:
    return {
        "format_version": 1,
        "logical_model_id": "example",
        "runner_contract": {"id": "runner", "version": "1"},
        "loader_profile_contract": {"id": "profile", "version": "1"},
        "sources": [
            {
                "role": "model",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example/model",
                "revision": "a" * 40,
                "filename": "model.gguf",
                "sha256": "b" * 64,
            }
        ],
        "preparation": [],
    }
