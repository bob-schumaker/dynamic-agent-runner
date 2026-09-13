"""Package-bound synthetic reference evidence for the MLE7 E5 workflow."""

from __future__ import annotations

import base64
import json
import math
import struct
from hashlib import sha256
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_embedding_abi import (
    BertEncoderMlxV4DescriptorValidator,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)


_PACKAGE = (
    Path(__file__).parent / "fixtures" / "mlx-multilingual-e5-small" / "mle7-package"
)
_GENERATOR = (
    Path(__file__).parent
    / "manual"
    / "generate_mlx_multilingual_e5_small_mle7_conformance.py"
)
_RUNTIME = {
    "device": "cpu",
    "inference_mode": True,
    "local_files_only": True,
    "model_eval": True,
    "torch": {"version": "2.13.0"},
    "transformers": {"version": "5.16.1"},
    "trust_remote_code": False,
}


def _fixture() -> dict[str, object]:
    value = json.loads((_PACKAGE / "conformance-fixture.json").read_text("utf-8"))
    assert isinstance(value, dict)
    return value


def _validate(fixture: dict[str, object]) -> None:
    descriptor = parse_execution_descriptor(
        json.loads((_PACKAGE / "execution-descriptor.json").read_text("utf-8"))
    )
    lock = parse_model_dependency_lock(
        json.loads((_PACKAGE / "model-materials.json").read_text("utf-8"))
    )
    BertEncoderMlxV4DescriptorValidator().validate(descriptor)
    assert lock.execution_descriptor is not None
    assert lock.execution_descriptor.sha256 == descriptor.digest
    conformance = descriptor.abi_fields["conformance"]
    assert isinstance(conformance, dict)
    assert (
        conformance["fixture_sha256"]
        == sha256((_PACKAGE / "conformance-fixture.json").read_bytes()).hexdigest()
    )
    assert fixture["format_version"] == 1
    assert (
        fixture["generator_script_sha256"]
        == sha256(_GENERATOR.read_bytes()).hexdigest()
    )
    assert fixture["reference_runtime"] == _RUNTIME
    assert (
        fixture["synthetic_documents_sha256"]
        == sha256((_PACKAGE / "synthetic-documents.json").read_bytes()).hexdigest()
    )
    vectors = fixture["expected_vectors"]
    assert isinstance(vectors, list)
    assert [case["id"] for case in vectors if isinstance(case, dict)] == [
        "empty",
        "query",
        "passage",
    ]
    for case in vectors:
        assert isinstance(case, dict)
        assert set(case) == {
            "attention_mask_sha256",
            "id",
            "input_ids_sha256",
            "token_type_ids_sha256",
            "vector_f32le_base64",
        }
        vector = base64.b64decode(case["vector_f32le_base64"], validate=True)
        assert len(vector) == 384 * 4
        values = struct.unpack("<384f", vector)
        assert all(math.isfinite(value) for value in values)
        assert math.isclose(
            math.sqrt(sum(value * value for value in values)),
            1.0,
            abs_tol=1e-5,
            rel_tol=0.0,
        )
        for name in (
            "attention_mask_sha256",
            "input_ids_sha256",
            "token_type_ids_sha256",
        ):
            assert isinstance(case[name], str) and len(case[name]) == 64


def test_package_bound_fixture_has_synthetic_vectors_and_locked_runtime_identity() -> (
    None
):
    _validate(_fixture())


def test_altered_fixture_or_reference_runtime_identity_is_rejected() -> None:
    fixture = _fixture()
    fixture["reference_runtime"] = {"trust_remote_code": True}

    with pytest.raises(AssertionError):
        _validate(fixture)
