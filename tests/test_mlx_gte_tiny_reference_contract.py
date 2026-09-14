"""Static conformance-contract checks for the MLX GTE Tiny reference fixture."""

from __future__ import annotations

import json
import runpy
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest


_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "mlx-gte-tiny"
    / "reference-vector-contract.json"
)
_SCRIPT = (
    Path(__file__).parent / "manual" / "generate_mlx_gte_tiny_reference_vectors.py"
)


def test_gte_tiny_reference_vector_contract_is_closed_and_unpopulated() -> None:
    contract = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    _assert_contract(contract)


@pytest.mark.parametrize(
    "path,value",
    (
        (("reference_runtime", "poetry_lock_sha256"), "e" * 64),
        (("reference_runtime", "tokenizer", "use_fast"), False),
        (("pooling", "accumulation_dtype"), "float16"),
        (("comparison", "coordinate_atol"), 0.001),
        (("cases", 4, "text_recipe", "repetitions"), 599),
    ),
)
def test_gte_tiny_reference_contract_rejects_changed_recipe(
    path: tuple[str | int, ...], value: object
) -> None:
    contract = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    changed = deepcopy(contract)
    target = changed
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    with pytest.raises(AssertionError):
        _assert_contract(changed)


def test_manual_generator_rejects_changed_contract_before_runtime_import() -> None:
    generator = runpy.run_path(str(_SCRIPT))
    contract = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    generator["_validate_contract"](contract, _FIXTURE)
    changed = deepcopy(contract)
    changed["comparison"]["coordinate_rtol"] = 0.01
    with pytest.raises(RuntimeError, match="case contract"):
        generator["_validate_contract"](changed, _FIXTURE)
    changed = deepcopy(contract)
    changed["reference_runtime"]["inference_mode"] = False
    with pytest.raises(RuntimeError, match="runtime contract"):
        generator["_validate_contract"](changed, _FIXTURE)


def test_manual_generator_rejects_unverified_materials_before_runtime_import(
    tmp_path: Path,
) -> None:
    generator = runpy.run_path(str(_SCRIPT))
    contract = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    with pytest.raises(RuntimeError, match="material set"):
        generator["_validate_materials"](tmp_path, contract)


def test_manual_generator_rejects_a_symlinked_material_root(tmp_path: Path) -> None:
    generator = runpy.run_path(str(_SCRIPT))
    contract = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "linked-root"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(RuntimeError, match="material set"):
        generator["_validate_materials"](link, contract)


def _assert_contract(contract: object) -> None:
    assert isinstance(contract, dict)
    assert set(contract) == {
        "cases",
        "comparison",
        "expected_vectors",
        "format_version",
        "generator_script_sha256",
        "model",
        "pooling",
        "profile",
        "reference_runtime",
        "status",
    }
    assert contract["format_version"] == 1
    assert contract["status"] == "unpopulated"
    assert (
        contract["generator_script_sha256"] == sha256(_SCRIPT.read_bytes()).hexdigest()
    )
    assert contract["profile"] == {
        "fixture_sha256": (
            "0c78f156a9bd878ad80da1e3ac5e223f26fa9a144ed5e0b618bd279df324bd20"
        ),
        "id": "mlx-gte-tiny-v1",
        "version": "1",
        "model_material_lock_digest": (
            "c2fc8b91d1b4514f2411f30c4d81fa3a702e902b70ae8a7eb83567696a158c87"
        ),
    }
    assert contract["model"] == {
        "repository": "TaylorAI/gte-tiny",
        "revision": "4cc5e73d86a67c601897257b467187234aa3bca3",
        "trust_remote_code": False,
        "local_files_only": True,
    }
    assert contract["reference_runtime"] == {
        "device": "cpu",
        "inference_mode": True,
        "model_eval": True,
        "poetry_lock_sha256": (
            "ff9c0a61e8307b80c7ed43c92d958d2422c09f584dd9d8668fd7c90b41e41149"
        ),
        "python": "3.14.7",
        "tokenizer": {
            "add_special_tokens": True,
            "max_length": 512,
            "padding": "max_length",
            "truncation": True,
            "use_fast": True,
        },
        "torch": {
            "version": "2.13.0",
            "wheel_sha256": (
                "d849b390e07d8d333ce8ecaf91b273c656c598379a19c9acf1318a883f6b391c"
            ),
        },
        "transformers": {
            "version": "5.16.1",
            "wheel_sha256": (
                "2f2d5b98a5ad3718713653734298fa620754ed683702a635ebb587df3ed29c7e"
            ),
        },
    }
    assert contract["pooling"] == {
        "source": "last_hidden_state",
        "accumulation_dtype": "float32",
        "normalization": "none",
    }
    assert contract["comparison"] == {
        "token_ids": "exact",
        "attention_mask": "exact",
        "token_type_ids": "all_zero_exact",
        "coordinate_atol": 0.0005,
        "coordinate_rtol": 0.005,
        "minimum_cosine_similarity": 0.9999,
    }
    assert contract["cases"] == [
        {"id": "empty", "text": ""},
        {"id": "ascii", "text": "The quick brown fox jumps over the lazy dog."},
        {"id": "unicode", "text": "Café naïve — punctuation!"},
        {"id": "chinese", "text": "北京的秋天很美。"},
        {
            "expected_postprocessor_token_count": 512,
            "id": "truncation",
            "text_recipe": {"repetitions": 600, "unit": "a "},
        },
    ]
    assert contract["expected_vectors"] == []
