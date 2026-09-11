"""Static construction-time lock for the closed MLX GTE Tiny profile."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)


_FIXTURE = (
    Path(__file__).parent / "fixtures" / "mlx-gte-tiny" / "model-material-lock.json"
)
_PROFILE = Path(__file__).parent / "fixtures" / "mlx-gte-tiny" / "profile.json"
_REVISION = "4cc5e73d86a67c601897257b467187234aa3bca3"


def test_gte_tiny_material_lock_is_a_closed_pinned_source_set() -> None:
    lock = parse_model_dependency_lock(_FIXTURE.read_bytes())

    assert lock.logical_model_id == "mlx-gte-tiny-v1"
    assert lock.runner_contract.to_mapping() == {
        "id": "mlx-gte-tiny-v1",
        "version": "1",
    }
    assert lock.loader_profile_contract.to_mapping() == {
        "id": "mlx-gte-tiny-v1",
        "version": "1",
    }
    assert [(source.role, source.filename) for source in lock.sources] == [
        ("bert_config", "config.json"),
        ("bert_weights", "model.safetensors"),
        ("modules_manifest", "modules.json"),
        ("pooling_config", "1_Pooling/config.json"),
        ("sentence_transformer_config", "sentence_bert_config.json"),
        ("tokenizer_added_tokens", "added_tokens.json"),
        ("tokenizer_config", "tokenizer_config.json"),
        ("tokenizer_json", "tokenizer.json"),
        ("tokenizer_special_tokens", "special_tokens_map.json"),
        ("tokenizer_vocab", "vocab.txt"),
    ]
    assert all(
        source.repository == "TaylorAI/gte-tiny" and source.revision == _REVISION
        for source in lock.sources
    )
    assert lock.preparation == ()
    assert (
        lock.digest
        == "c2fc8b91d1b4514f2411f30c4d81fa3a702e902b70ae8a7eb83567696a158c87"
    )


def test_gte_tiny_machine_profile_matches_the_closed_lock() -> None:
    lock = parse_model_dependency_lock(_FIXTURE.read_bytes())
    profile = json.loads(_PROFILE.read_text(encoding="utf-8"))

    _assert_profile_matches_lock(profile, lock)


@pytest.mark.parametrize("field", ("bytes", "filename", "sha256"))
def test_gte_tiny_machine_profile_rejects_changed_source_identity(field: str) -> None:
    lock = parse_model_dependency_lock(_FIXTURE.read_bytes())
    profile = json.loads(_PROFILE.read_text(encoding="utf-8"))
    changed = dict(profile)
    changed["files"] = [dict(item) for item in profile["files"]]
    if field == "bytes":
        changed["files"][0][field] += 1
    else:
        changed["files"][0][field] = "changed" if field == "filename" else "e" * 64

    with pytest.raises(AssertionError):
        _assert_profile_matches_lock(changed, lock)


def _assert_profile_matches_lock(profile: object, lock: object) -> None:
    assert isinstance(profile, dict)
    assert profile["format_version"] == 1
    assert profile["profile_id"] == "mlx-gte-tiny-v1"
    assert profile["profile_version"] == "1"
    assert profile["model_material_lock_digest"] == lock.digest
    assert profile["files"] == [
        {
            "role": source.role,
            "filename": source.filename,
            "sha256": source.sha256,
            "bytes": expected_bytes,
        }
        for source, expected_bytes in zip(
            lock.sources,
            (669, 45457576, 229, 190, 53, 82, 1536, 711661, 228, 231508),
            strict=True,
        )
    ]
