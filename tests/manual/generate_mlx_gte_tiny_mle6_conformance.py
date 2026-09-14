"""Generate MLE6 GTE Tiny synthetic reference evidence from verified local bytes."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)


_PROJECT_ROOT = Path(__file__).parents[2]
_PACKAGE = _PROJECT_ROOT / "tests" / "fixtures" / "mlx-gte-tiny" / "mle6-package"
_RUNTIME = {
    "device": "cpu",
    "inference_mode": True,
    "local_files_only": True,
    "model_eval": True,
    "torch": {"version": "2.13.0"},
    "transformers": {"version": "5.16.1"},
    "trust_remote_code": False,
}


def main() -> int:
    """Write one fixture from the exact package-selected local closure."""

    arguments = _arguments()
    model_root = arguments.model_root.resolve()
    _validate_materials(model_root)
    documents = _load_documents()
    try:
        import torch
        import transformers
        from transformers import AutoModel, AutoTokenizer
    except ImportError as error:
        raise RuntimeError("locked reference runtime is unavailable") from error
    _validate_runtime(torch, transformers)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(
        model_root, local_files_only=True, trust_remote_code=False, use_fast=True
    )
    model = AutoModel.from_pretrained(
        model_root,
        local_files_only=True,
        trust_remote_code=False,
        torch_dtype=torch.float32,
    )
    model.eval()
    vectors = []
    with torch.inference_mode():
        for document in documents:
            encoded = tokenizer(
                document["text"],
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
            values = vector.numpy().astype("<f4", copy=False).tobytes()
            vectors.append(
                {
                    "attention_mask_sha256": _tensor_digest(encoded["attention_mask"]),
                    "id": document["id"],
                    "input_ids_sha256": _tensor_digest(encoded["input_ids"]),
                    "token_type_ids_sha256": _tensor_digest(encoded["token_type_ids"]),
                    "vector_f32le_base64": base64.b64encode(values).decode("ascii"),
                }
            )
    fixture = {
        "expected_vectors": vectors,
        "format_version": 1,
        "generator_script_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "reference_runtime": _RUNTIME,
        "synthetic_documents_sha256": hashlib.sha256(
            (_PACKAGE / "synthetic-documents.json").read_bytes()
        ).hexdigest(),
    }
    arguments.output.write_text(
        json.dumps(fixture, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _validate_materials(model_root: Path) -> None:
    lock = parse_model_dependency_lock(
        json.loads((_PACKAGE / "model-materials.json").read_text(encoding="utf-8"))
    )
    for source in lock.sources:
        path = model_root / source.filename
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != source.sha256
        ):
            raise RuntimeError("locked material is unavailable")


def _load_documents() -> list[dict[str, str]]:
    value: Any = json.loads((_PACKAGE / "synthetic-documents.json").read_text())
    if not isinstance(value, dict) or value.get("format_version") != 1:
        raise RuntimeError("synthetic documents are invalid")
    documents = value.get("documents")
    if not isinstance(documents, list):
        raise RuntimeError("synthetic documents are invalid")
    expected_ids = ("empty", "ascii", "unicode")
    if [item.get("id") for item in documents if isinstance(item, dict)] != list(
        expected_ids
    ):
        raise RuntimeError("synthetic documents are invalid")
    if not all(
        isinstance(item, dict)
        and set(item) == {"id", "text"}
        and isinstance(item["id"], str)
        and isinstance(item["text"], str)
        for item in documents
    ):
        raise RuntimeError("synthetic documents are invalid")
    return documents


def _validate_runtime(torch: object, transformers: object) -> None:
    if (
        getattr(torch, "__version__", None) != _RUNTIME["torch"]["version"]
        or getattr(transformers, "__version__", None)
        != _RUNTIME["transformers"]["version"]
    ):
        raise RuntimeError("locked reference runtime is unavailable")


def _tensor_digest(value: object) -> str:
    tolist = getattr(value, "tolist", None)
    if not callable(tolist):
        raise RuntimeError("reference tensor is invalid")
    return hashlib.sha256(
        json.dumps(tolist(), separators=(",", ":")).encode("utf-8")
    ).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
