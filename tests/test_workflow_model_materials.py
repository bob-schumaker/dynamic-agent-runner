"""Tests for canonical sealed workflow model-material locks."""

from __future__ import annotations

from hashlib import sha256

import pytest

from dynamic_agent_runner.workflow_host.model_materials import (
    ModelMaterialsError,
    ModelDependencyLock,
    parse_model_dependency_lock,
    transformation_digest,
)


def _source(
    *, role: str = "base_model", filename: str = "model.gguf"
) -> dict[str, str]:
    return {
        "role": role,
        "group": "base",
        "source_type": "huggingface_file",
        "repository": "example-org/example-model",
        "revision": "a" * 40,
        "filename": filename,
        "sha256": "b" * 64,
    }


def _lock(*, sources: list[dict[str, str]] | None = None, preparation=None):
    return {
        "format_version": 1,
        "logical_model_id": "example-model",
        "runner_contract": {"id": "llama-cpp-v1", "version": "1"},
        "loader_profile_contract": {"id": "llama-cpp-text-v1", "version": "1"},
        "sources": sources or [_source()],
        "preparation": [] if preparation is None else preparation,
    }


def _v2_lock(
    *,
    sources: list[dict[str, str]] | None = None,
    execution_descriptor: dict[str, str] | None = None,
):
    return {
        "format_version": 2,
        "logical_model_id": "example-embedding-model",
        "runner_contract": {"id": "mlx-embedding-v1", "version": "1"},
        "execution_descriptor": execution_descriptor
        or {"filename": "execution-descriptor.json", "sha256": "c" * 64},
        "sources": sources or [_source()],
        "preparation": [],
    }


def test_model_material_lock_has_canonical_bytes_and_digest() -> None:
    lock = parse_model_dependency_lock(_lock())

    assert isinstance(lock, ModelDependencyLock)
    assert lock.canonical_bytes == (
        b'{"format_version":1,"loader_profile_contract":{"id":"llama-cpp-text-v1",'
        b'"version":"1"},"logical_model_id":"example-model","preparation":[],"'
        b'runner_contract":{"id":"llama-cpp-v1","version":"1"},"sources":[{"filename":'
        b'"model.gguf","group":"base","repository":"example-org/example-model","revision":"'
        + b"a" * 40
        + b'","role":"base_model","sha256":"'
        + b"b" * 64
        + b'","source_type":"huggingface_file"}]}'
    )
    assert lock.digest == sha256(lock.canonical_bytes).hexdigest()


def test_v2_model_material_lock_binds_an_abi_neutral_descriptor_without_cycle() -> None:
    lock = parse_model_dependency_lock(_v2_lock())

    assert lock.format_version == 2
    assert lock.loader_profile_contract is None
    assert lock.execution_descriptor is not None
    assert lock.execution_descriptor.filename == "execution-descriptor.json"
    assert lock.execution_descriptor.sha256 == "c" * 64
    assert b'"execution_descriptor"' in lock.canonical_bytes
    assert b'"loader_profile_contract"' not in lock.canonical_bytes


@pytest.mark.parametrize(
    "execution_descriptor",
    (
        {"filename": "embedding-execution-descriptor.json", "sha256": "c" * 64},
        {"filename": "execution-descriptor.json", "sha256": "C" * 64},
        {"filename": "execution-descriptor.json", "sha256": "c" * 64, "extra": "x"},
    ),
)
def test_v2_model_material_lock_rejects_invalid_descriptor_reference(
    execution_descriptor: dict[str, str],
) -> None:
    with pytest.raises(ModelMaterialsError):
        parse_model_dependency_lock(_v2_lock(execution_descriptor=execution_descriptor))


def test_v2_model_material_lock_rejects_v1_profile_mixing() -> None:
    value = _v2_lock()
    value["loader_profile_contract"] = {"id": "bad", "version": "1"}

    with pytest.raises(ModelMaterialsError):
        parse_model_dependency_lock(value)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.update(unexpected="value"),
        lambda value: value.update(sources=[_source(role="z"), _source(role="a")]),
        lambda value: value.update(sources=[_source(), _source()]),
        lambda value: value["sources"][0].update(revision="main"),
        lambda value: value["sources"][0].update(group=1),
        lambda value: value.update(format_version=True),
    ),
)
def test_model_material_lock_rejects_noncanonical_or_malformed_values(mutate) -> None:
    value = _lock()
    mutate(value)

    with pytest.raises(ModelMaterialsError):
        parse_model_dependency_lock(value)


def test_preparation_digest_and_role_closure_are_verified() -> None:
    operation = {
        "capability_id": "model.prepare.gguf.quantize.q4-k-m.v1",
        "contract_version": "1",
        "contract_digest": "c" * 64,
        "inputs": ["base_model_f16"],
        "output": {
            "role": "base_model",
            "group": "base",
            "filename": "model-q4_k_m.gguf",
            "sha256": "d" * 64,
        },
    }
    operation["transformation_digest"] = transformation_digest(operation)
    lock = parse_model_dependency_lock(
        _lock(sources=[_source(role="base_model_f16")], preparation=[operation])
    )

    assert (
        lock.preparation[0].transformation_digest == operation["transformation_digest"]
    )

    operation["inputs"] = ["missing"]
    operation["transformation_digest"] = transformation_digest(operation)
    with pytest.raises(ModelMaterialsError, match="input"):
        parse_model_dependency_lock(
            _lock(sources=[_source(role="base_model_f16")], preparation=[operation])
        )


@pytest.mark.parametrize(
    "value",
    (
        None,
        b'\xef\xbb\xbf{"format_version":1}',
        b'{"format_version":1,"format_version":1}',
    ),
)
def test_model_material_parser_rejects_absent_or_noncanonical_json(value) -> None:
    with pytest.raises(ModelMaterialsError):
        parse_model_dependency_lock(value)


def test_preparation_rejects_self_reference_and_orphaned_intermediate_output() -> None:
    operation = {
        "capability_id": "model.prepare.v1",
        "contract_version": "1",
        "contract_digest": "c" * 64,
        "inputs": ["generated"],
        "output": {
            "role": "generated",
            "group": "base",
            "filename": "generated.gguf",
            "sha256": "d" * 64,
        },
    }
    operation["transformation_digest"] = transformation_digest(operation)
    with pytest.raises(ModelMaterialsError, match="input"):
        parse_model_dependency_lock(_lock(preparation=[operation]))

    first = dict(operation)
    first["inputs"] = ["base_model"]
    first["output"] = {**operation["output"], "role": "intermediate"}
    first["transformation_digest"] = transformation_digest(first)
    second = dict(operation)
    second["inputs"] = ["base_model"]
    second["output"] = {**operation["output"], "role": "terminal"}
    second["transformation_digest"] = transformation_digest(second)
    with pytest.raises(ModelMaterialsError, match="orphaned"):
        parse_model_dependency_lock(_lock(preparation=[first, second]))
