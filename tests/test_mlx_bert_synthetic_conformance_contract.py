"""Static contract checks for the manual generic MLX BERT competency fixture."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path


_ROOT = Path(__file__).parent
_FIXTURE_ROOT = _ROOT / "fixtures" / "mlx-bert-synthetic"
_DESCRIPTOR = _FIXTURE_ROOT / "execution-descriptor.json"
_FIXTURE = _FIXTURE_ROOT / "conformance-fixture.json"
_SCRIPT = _ROOT / "manual" / "run_mlx_bert_synthetic_conformance.py"


def test_manual_synthetic_fixture_is_bound_to_its_generic_descriptor() -> None:
    descriptor = json.loads(_DESCRIPTOR.read_text(encoding="utf-8"))
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    assert descriptor["architecture_abi"]["id"] == "bert-encoder-mlx-v1"
    assert descriptor["material_roles"] == ["tokenizer", "weights"]
    assert descriptor["abi_fields"]["conformance"]["fixture_filename"] == (
        "conformance-fixture.json"
    )
    assert descriptor["abi_fields"]["conformance"]["fixture_sha256"] == (
        hashlib.sha256(_FIXTURE.read_bytes()).hexdigest()
    )
    assert fixture["format_version"] == 1
    assert fixture["expected_vectors"] == [
        {"id": "padded", "vector": [1.0, -1.0]},
        {"id": "truncated", "vector": [1.0, -1.0]},
    ]


def test_manual_runner_rejects_changed_fixture_before_mlx_import() -> None:
    runner = runpy.run_path(str(_SCRIPT))
    descriptor = json.loads(_DESCRIPTOR.read_text(encoding="utf-8"))
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    runner["_validate_contract"](descriptor, fixture, _FIXTURE)
    fixture["max_error"] = 0.1
    try:
        runner["_validate_contract"](descriptor, fixture, _FIXTURE)
    except RuntimeError as error:
        assert str(error) == "synthetic conformance fixture is invalid"
    else:
        raise AssertionError("changed fixture must be rejected")
