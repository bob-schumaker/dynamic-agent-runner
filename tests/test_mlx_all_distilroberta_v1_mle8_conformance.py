"""Package-bound synthetic reference evidence for the MLE8 RoBERTa workflow."""

from __future__ import annotations

import base64
import json
import math
import struct
from hashlib import sha256
from pathlib import Path

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    parse_execution_descriptor,
)
from dynamic_agent_runner.workflow_host.mlx_roberta_embedding_abi import (
    RobertaEncoderMlxV1DescriptorValidator,
)


_PACKAGE = (
    Path(__file__).parent / "fixtures" / "mlx-all-distilroberta-v1" / "mle8-package"
)
_GENERATOR = (
    Path(__file__).parent
    / "manual"
    / "generate_mlx_all_distilroberta_v1_mle8_conformance.py"
)


def test_package_bound_roberta_fixture_has_unit_vectors_and_locked_identity() -> None:
    fixture = json.loads((_PACKAGE / "conformance-fixture.json").read_text("utf-8"))
    descriptor = parse_execution_descriptor(
        json.loads((_PACKAGE / "execution-descriptor.json").read_text("utf-8"))
    )
    RobertaEncoderMlxV1DescriptorValidator().validate(descriptor)
    assert (
        descriptor.abi_fields["conformance"]["fixture_sha256"]
        == sha256((_PACKAGE / "conformance-fixture.json").read_bytes()).hexdigest()
    )
    assert (
        fixture["generator_script_sha256"]
        == sha256(_GENERATOR.read_bytes()).hexdigest()
    )
    assert (
        fixture["synthetic_documents_sha256"]
        == sha256((_PACKAGE / "synthetic-documents.json").read_bytes()).hexdigest()
    )
    assert [item["id"] for item in fixture["expected_vectors"]] == [
        "empty",
        "space",
        "unicode",
    ]
    for item in fixture["expected_vectors"]:
        values = struct.unpack(
            "<768f", base64.b64decode(item["vector_f32le_base64"], validate=True)
        )
        assert all(math.isfinite(value) for value in values)
        assert math.isclose(
            math.sqrt(sum(value * value for value in values)), 1.0, abs_tol=1e-5
        )
