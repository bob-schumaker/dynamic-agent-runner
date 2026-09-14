"""Generate candidate GTE Tiny reference vectors during the authorized MLE4 gate."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import stat
import sys
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).parents[2]
_PROFILE_FIXTURE = (
    _PROJECT_ROOT / "tests" / "fixtures" / "mlx-gte-tiny" / "profile.json"
)
_PROFILE = {
    "fixture_sha256": "0c78f156a9bd878ad80da1e3ac5e223f26fa9a144ed5e0b618bd279df324bd20",
    "id": "mlx-gte-tiny-v1",
    "model_material_lock_digest": (
        "c2fc8b91d1b4514f2411f30c4d81fa3a702e902b70ae8a7eb83567696a158c87"
    ),
    "version": "1",
}
_COMPARISON = {
    "attention_mask": "exact",
    "coordinate_atol": 0.0005,
    "coordinate_rtol": 0.005,
    "minimum_cosine_similarity": 0.9999,
    "token_ids": "exact",
    "token_type_ids": "all_zero_exact",
}
_CASES = [
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
_RUNTIME = {
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


def main() -> int:
    """Generate a candidate fixture from verified local material only."""

    arguments = _arguments()
    contract_path = arguments.contract.resolve()
    contract = _load_contract(contract_path)
    _validate_contract(contract, contract_path)
    model_root = arguments.model_root.absolute()
    _validate_materials(model_root, contract)

    try:
        import torch
        import transformers
        from transformers import AutoModel, AutoTokenizer
    except ImportError as error:
        raise RuntimeError("locked reference runtime is unavailable") from error
    _validate_runtime(contract, torch, transformers)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)

    tokenizer = AutoTokenizer.from_pretrained(
        model_root,
        trust_remote_code=False,
        local_files_only=True,
        use_fast=True,
    )
    model = AutoModel.from_pretrained(
        model_root,
        trust_remote_code=False,
        local_files_only=True,
        torch_dtype=torch.float32,
    )
    model.eval()

    expected_vectors = []
    with torch.inference_mode():
        for case in contract["cases"]:
            encoded = tokenizer(
                _case_text(case),
                add_special_tokens=True,
                truncation=True,
                max_length=512,
                padding="max_length",
                return_attention_mask=True,
                return_token_type_ids=True,
                return_tensors="pt",
            )
            output = model(**encoded).last_hidden_state.to(dtype=torch.float32)
            mask = encoded["attention_mask"].to(dtype=torch.float32).unsqueeze(-1)
            vector = (output * mask).sum(dim=1) / mask.sum(dim=1)
            _validate_candidate(case, encoded, vector, torch)
            expected_vectors.append(
                {
                    "id": case["id"],
                    "input_ids": encoded["input_ids"].tolist()[0],
                    "attention_mask": encoded["attention_mask"].tolist()[0],
                    "token_type_ids": encoded["token_type_ids"].tolist()[0],
                    "vector_f32le_base64": base64.b64encode(
                        vector.numpy().astype("<f4", copy=False).tobytes()
                    ).decode("ascii"),
                }
            )

    result = dict(contract)
    result["status"] = "candidate"
    result["generator_script_sha256"] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    result["expected_vectors"] = expected_vectors
    arguments.output.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _load_contract(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("reference contract is invalid")
    return value


def _validate_contract(contract: dict[str, Any], path: Path) -> None:
    expected_digest = contract.get("generator_script_sha256")
    if (
        not isinstance(expected_digest, str)
        or expected_digest != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ):
        raise RuntimeError("reference generator is not the locked script")
    if (
        contract.get("status") != "unpopulated"
        or contract.get("expected_vectors") != []
    ):
        raise RuntimeError("reference contract is not ready for generation")
    if path.name != "reference-vector-contract.json":
        raise RuntimeError("reference contract path is invalid")
    if (
        set(contract)
        != {
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
        or contract.get("format_version") != 1
    ):
        raise RuntimeError("reference contract is invalid")
    if contract.get("profile") != _PROFILE:
        raise RuntimeError("reference profile contract is invalid")
    if contract.get("comparison") != _COMPARISON or contract.get("cases") != _CASES:
        raise RuntimeError("reference case contract is invalid")
    if contract.get("reference_runtime") != _RUNTIME:
        raise RuntimeError("reference runtime contract is invalid")
    if contract.get("model") != {
        "repository": "TaylorAI/gte-tiny",
        "revision": "4cc5e73d86a67c601897257b467187234aa3bca3",
        "trust_remote_code": False,
        "local_files_only": True,
    }:
        raise RuntimeError("reference model contract is invalid")
    if contract.get("pooling") != {
        "source": "last_hidden_state",
        "accumulation_dtype": "float32",
        "normalization": "none",
    }:
        raise RuntimeError("reference pooling contract is invalid")


def _validate_materials(model_root: Path, contract: dict[str, Any]) -> None:
    if model_root.is_symlink() or not model_root.is_dir():
        raise RuntimeError("reference material set is invalid")
    expected = _profile_files(contract)
    discovered = tuple(model_root.rglob("*"))
    if any(path.is_symlink() for path in discovered):
        raise RuntimeError("reference material set is invalid")
    found = {
        str(path.relative_to(model_root))
        for path in discovered
        if stat.S_ISREG(path.lstat().st_mode)
    }
    if set(expected) != found:
        raise RuntimeError("reference material set is invalid")
    for filename, item in expected.items():
        path = model_root / filename
        if not _is_regular_without_symlinked_parent(model_root, path):
            raise RuntimeError("reference material set is invalid")
        if path.stat().st_size != item.get("bytes"):
            raise RuntimeError("reference material set is invalid")
        if _sha256_file(path) != item.get("sha256"):
            raise RuntimeError("reference material set is invalid")


def _profile_files(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    try:
        profile = json.loads(_PROFILE_FIXTURE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("reference material profile is unavailable") from error
    if (
        hashlib.sha256(_PROFILE_FIXTURE.read_bytes()).hexdigest()
        != contract["profile"]["fixture_sha256"]
    ):
        raise RuntimeError("reference material profile is invalid")
    files = profile.get("files") if isinstance(profile, dict) else None
    if not isinstance(files, list):
        raise RuntimeError("reference material profile is invalid")
    return {item["filename"]: item for item in files if isinstance(item, dict)}


def _is_regular_without_symlinked_parent(root: Path, path: Path) -> bool:
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            return False
    return stat.S_ISREG(path.lstat().st_mode)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_runtime(contract: dict[str, Any], torch: Any, transformers: Any) -> None:
    runtime = contract.get("reference_runtime")
    if runtime != _RUNTIME:
        raise RuntimeError("reference runtime is invalid")
    if runtime.get("python") != ".".join(map(str, sys.version_info[:3])):
        raise RuntimeError("reference Python version is unavailable")
    if (
        runtime.get("poetry_lock_sha256")
        != hashlib.sha256((_PROJECT_ROOT / "poetry.lock").read_bytes()).hexdigest()
    ):
        raise RuntimeError("reference environment lock is unavailable")
    if (
        runtime.get("device") != "cpu"
        or torch.__version__ != runtime["torch"]["version"]
    ):
        raise RuntimeError("reference Torch runtime is unavailable")
    if transformers.__version__ != runtime["transformers"]["version"]:
        raise RuntimeError("reference Transformers runtime is unavailable")


def _validate_candidate(
    case: dict[str, Any], encoded: Any, vector: Any, torch: Any
) -> None:
    type_ids = encoded["token_type_ids"]
    if bool(torch.any(type_ids != 0)):
        raise RuntimeError("reference token type IDs are invalid")
    expected_tokens = case.get("expected_postprocessor_token_count")
    if (
        expected_tokens is not None
        and int(encoded["attention_mask"].sum()) != expected_tokens
    ):
        raise RuntimeError("reference truncation tokens are invalid")
    if (
        vector.shape != (1, 384)
        or vector.dtype != torch.float32
        or not bool(torch.all(torch.isfinite(vector)))
    ):
        raise RuntimeError("reference vector is invalid")


def _case_text(case: dict[str, Any]) -> str:
    text = case.get("text")
    if isinstance(text, str):
        return text
    recipe = case.get("text_recipe")
    if not isinstance(recipe, dict):
        raise RuntimeError("reference case is invalid")
    unit, repetitions = recipe.get("unit"), recipe.get("repetitions")
    if not isinstance(unit, str) or not isinstance(repetitions, int):
        raise RuntimeError("reference case is invalid")
    return unit * repetitions


if __name__ == "__main__":
    raise SystemExit(main())
