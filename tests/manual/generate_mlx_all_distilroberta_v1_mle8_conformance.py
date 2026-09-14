"""Generate MLE8 RoBERTa synthetic reference evidence from locked local bytes."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)


_ROOT = Path(__file__).parents[2]
_PACKAGE = _ROOT / "tests" / "fixtures" / "mlx-all-distilroberta-v1" / "mle8-package"
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
    arguments = _arguments()
    _validate_materials(arguments.model_root)
    import torch
    import transformers
    from transformers import AutoModel, AutoTokenizer

    if torch.__version__ != "2.13.0" or transformers.__version__ != "5.16.1":
        raise RuntimeError("locked reference runtime is unavailable")
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(
        arguments.model_root,
        local_files_only=True,
        trust_remote_code=False,
        use_fast=True,
    )
    model = AutoModel.from_pretrained(
        arguments.model_root,
        local_files_only=True,
        trust_remote_code=False,
        torch_dtype=torch.float32,
    )
    model.eval()
    documents = json.loads((_PACKAGE / "synthetic-documents.json").read_text("utf-8"))[
        "documents"
    ]
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
            norm = torch.linalg.vector_norm(vector, dim=1, keepdim=True)
            if not bool(torch.isfinite(norm).all()) or bool((norm == 0).any()):
                raise RuntimeError("reference vector normalization is invalid")
            values = (vector / norm).numpy().astype("<f4", copy=False).tobytes()
            vectors.append(
                {
                    "id": document["id"],
                    "input_ids_sha256": _digest(encoded["input_ids"]),
                    "attention_mask_sha256": _digest(encoded["attention_mask"]),
                    "token_type_ids_sha256": _digest(encoded["token_type_ids"]),
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
        json.dumps(fixture, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _validate_materials(root: Path) -> None:
    lock = parse_model_dependency_lock(
        json.loads((_PACKAGE / "model-materials.json").read_text("utf-8"))
    )
    for source in lock.sources:
        path = root / source.filename
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != source.sha256
        ):
            raise RuntimeError("locked material is unavailable")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value.tolist(), separators=(",", ":")).encode("utf-8")
    ).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
