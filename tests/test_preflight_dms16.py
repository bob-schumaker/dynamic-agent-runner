from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).parent / "manual" / "preflight_dms16.py"
_SPEC = importlib.util.spec_from_file_location("preflight_dms16", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_PREFLIGHT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PREFLIGHT)


def test_git_blob_sha1_matches_git_object_format(tmp_path: Path) -> None:
    material = tmp_path / "config.json"
    material.write_bytes(b"abc")

    assert (
        _PREFLIGHT._git_blob_sha1(material)
        == "f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f"
    )


def test_file_receipt_verifies_sha256_and_git_blob_sha1(tmp_path: Path) -> None:
    material = tmp_path / "config.json"
    material.write_bytes(b"abc")

    sha256 = _PREFLIGHT._file_receipt(
        material,
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        "sha256",
    )
    git_blob = _PREFLIGHT._file_receipt(
        material, "f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f", "git-blob-sha1"
    )

    assert sha256["match"] is True
    assert git_blob["match"] is True


def test_file_receipt_blocks_missing_or_changed_material(tmp_path: Path) -> None:
    absent = _PREFLIGHT._file_receipt(
        tmp_path / "missing.json", "0" * 40, "git-blob-sha1"
    )
    changed = tmp_path / "changed.json"
    changed.write_text("{}", encoding="utf-8")

    assert absent["match"] is False
    assert absent["actual"] is None
    assert (
        _PREFLIGHT._file_receipt(changed, "0" * 40, "git-blob-sha1")["match"] is False
    )


def test_profiles_pin_runtime_required_config_and_tokenizer_files() -> None:
    assert set(_PREFLIGHT.PROFILES["von"]["git_files"]) == {
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
    }
    assert set(_PREFLIGHT.PROFILES["laya-mlx"]["git_files"]) == {
        "encoder/config.json",
        "mlx_config.json",
        "rl_agent_config.json",
        "tokenizer/tokenizer.json",
        "tokenizer/tokenizer_config.json",
    }
