"""Tests for canonical named model-material sets."""

from __future__ import annotations

from hashlib import sha256

import pytest

from dynamic_agent_runner.workflow_host.material_sets import (
    MaterialSetsError,
    parse_model_material_sets,
)


def _lock(*, logical_model_id: str) -> dict[str, object]:
    return {
        "format_version": 1,
        "logical_model_id": logical_model_id,
        "runner_contract": {"id": "llama-cpp-v1", "version": "1"},
        "loader_profile_contract": {"id": "llama-cpp-text-v1", "version": "1"},
        "sources": [
            {
                "role": "base_model",
                "group": "base",
                "source_type": "huggingface_file",
                "repository": "example/model",
                "revision": "a" * 40,
                "filename": f"{logical_model_id}.gguf",
                "sha256": "b" * 64,
            }
        ],
        "preparation": [],
    }


def _sets() -> dict[str, object]:
    return {
        "format_version": 1,
        "material_sets": [
            {"role": "extract", "model_materials": _lock(logical_model_id="extract")},
            {"role": "suggest", "model_materials": _lock(logical_model_id="suggest")},
        ],
    }


def test_material_sets_have_canonical_bytes_and_digest() -> None:
    sets = parse_model_material_sets(_sets())

    assert sets.roles == ("extract", "suggest")
    assert sets.digest == sha256(sets.canonical_bytes).hexdigest()
    assert sets.for_role("extract").logical_model_id == "extract"


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.update(unexpected=True),
        lambda value: value.update(
            material_sets=list(reversed(value["material_sets"]))
        ),
        lambda value: value.update(
            material_sets=[value["material_sets"][0], value["material_sets"][0]]
        ),
        lambda value: value["material_sets"][0].update(role="bad-role"),
        lambda value: value["material_sets"][0].update(model_materials={}),
    ),
)
def test_material_sets_reject_malformed_duplicate_or_substituted_roles(mutate) -> None:
    value = _sets()
    mutate(value)

    with pytest.raises(MaterialSetsError):
        parse_model_material_sets(value)


def test_material_sets_verify_declared_digest_and_do_not_accept_legacy_shape() -> None:
    value = _sets()
    parsed = parse_model_material_sets(value)
    value["material_sets_digest"] = parsed.digest
    assert parse_model_material_sets(value).digest == parsed.digest

    value["material_sets_digest"] = "a" * 64
    with pytest.raises(MaterialSetsError, match="digest"):
        parse_model_material_sets(value)
