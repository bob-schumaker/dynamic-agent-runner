#!/usr/bin/env python3
"""Stage and quantize a pinned DMS-20 MLX candidate to uniform 4-bit."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "specs/decision-model-support/evaluation"
CORPUS_PATH = EVALUATION / "dms14-corpus-manifest.json"
ROWS = {
    "qwen35-08b-decision-mlx-4bit": {
        "matrix": EVALUATION / "dms20-qwen35-08b-4bit-conversion-matrix.json",
        "approval": EVALUATION / "dms20-qwen35-08b-4bit-conversion-approval.json",
        "cache": Path("/private/tmp/dms20-qwen35-08b-4bit-source"),
        "output": Path("/private/tmp/dms20-qwen35-08b-4bit-model"),
    },
    "d1a-e2b-mlx-4bit": {
        "matrix": EVALUATION / "dms20-d1a-e2b-4bit-conversion-matrix.json",
        "approval": EVALUATION / "dms20-d1a-e2b-4bit-conversion-approval.json",
        "cache": Path("/private/tmp/dms20-d1a-e2b-4bit-source"),
        "output": Path("/private/tmp/dms20-d1a-e2b-4bit-model"),
    },
}


class ConversionError(RuntimeError):
    """Raised when a frozen conversion contract does not match."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify(row_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config = ROWS[row_id]
    matrix = json.loads(config["matrix"].read_text(encoding="utf-8"))
    approval = json.loads(config["approval"].read_text(encoding="utf-8"))
    if (
        len(matrix.get("rows", [])) != 1
        or matrix["rows"][0].get("optimization_id") != row_id
    ):
        raise ConversionError("conversion matrix does not select this row")
    if _sha256(CORPUS_PATH) != matrix.get("corpus_manifest_sha256"):
        raise ConversionError(
            "DMS-20 corpus manifest differs from the conversion matrix"
        )
    source_matrix_path = EVALUATION / matrix["source_matrix_path"]
    source_approval_path = EVALUATION / matrix["source_approval_path"]
    if _sha256(source_matrix_path) != matrix["source_matrix_sha256"]:
        raise ConversionError("approved MLX source matrix differs")
    if _sha256(source_approval_path) != matrix["source_approval_sha256"]:
        raise ConversionError("approved MLX source approval differs")
    source_matrix = json.loads(source_matrix_path.read_text(encoding="utf-8"))
    if approval.get("approved") is not True or approval.get("matrix_sha256") != _sha256(
        config["matrix"]
    ):
        raise ConversionError("approval does not bind the conversion matrix")
    source_row = next(
        (
            item
            for item in source_matrix["rows"]
            if item["id"] == matrix["rows"][0]["id"]
        ),
        None,
    )
    if (
        source_row is None
        or source_row["model"] != matrix["rows"][0]["source_model"]
        or source_row["artifact_files"] != matrix["rows"][0]["source_artifacts"]
    ):
        raise ConversionError(
            "conversion source model or artifacts differ from the approved MLX matrix"
        )
    for item in matrix["harness_files"]:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise ConversionError("pinned conversion harness differs")
    return matrix, matrix["rows"][0], config


def _resources(
    row: dict[str, Any], cache: Path, *, before_stage: bool
) -> dict[str, int]:
    total = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    output = subprocess.run(
        ["memory_pressure"], capture_output=True, check=True, text=True, timeout=5
    ).stdout
    marker = "System-wide memory free percentage:"
    line = next(
        (value for value in output.splitlines() if value.startswith(marker)), None
    )
    if line is None:
        raise ConversionError("could not read macOS memory pressure")
    percent = int(line.removeprefix(marker).strip().rstrip("%"))
    free_memory = total * percent // 100
    floors = row["resource_floor"]
    if free_memory < floors["minimum_free_memory_bytes"]:
        raise ConversionError("free memory is below the conversion row floor")
    free_disk = shutil.disk_usage(cache.parent).free
    floor = (
        "minimum_free_disk_before_stage_bytes"
        if before_stage
        else "minimum_free_disk_after_stage_bytes"
    )
    if free_disk < floors[floor]:
        raise ConversionError("free disk is below the conversion row floor")
    return {
        "system_memory_free_percent": percent,
        "free_memory_bytes_estimate": free_memory,
        "free_disk_bytes": free_disk,
    }


def _snapshot(cache: Path, repository: str, revision: str) -> Path:
    return cache / f"models--{repository.replace('/', '--')}" / "snapshots" / revision


def stage(row_id: str) -> dict[str, Any]:
    from huggingface_hub import snapshot_download

    matrix, row, config = _verify(row_id)
    before = _resources(row, config["cache"], before_stage=True)
    config["cache"].mkdir(parents=True, exist_ok=True)
    for repository, revision in sorted(
        {(item["repository"], item["revision"]) for item in row["source_artifacts"]}
    ):
        snapshot_download(
            repository,
            revision=revision,
            cache_dir=str(config["cache"]),
            allow_patterns=matrix["artifact_download_allow_patterns"],
            ignore_patterns=matrix["artifact_download_ignore_patterns"],
        )
    source = _snapshot(
        config["cache"], row["source_model"]["id"], row["source_model"]["revision"]
    )
    for item in row["source_artifacts"]:
        path = (
            _snapshot(config["cache"], item["repository"], item["revision"])
            / item["path"]
        )
        if (
            not path.is_file()
            or path.stat().st_size != item["size_bytes"]
            or _sha256(path) != item["sha256"]
        ):
            raise ConversionError(f"pinned source artifact differs: {item['path']}")
    after = _resources(row, config["cache"], before_stage=False)
    receipt = {
        "optimization_id": row_id,
        "source_model": str(source),
        "source_artifacts_verified": True,
        "matrix_sha256": _sha256(config["matrix"]),
        "resource_preflight": {"before_stage": before, "after_stage": after},
    }
    out = EVALUATION / f"{row_id}-conversion-2026-10-24"
    out.mkdir(parents=True, exist_ok=True)
    (out / "stage-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    return receipt


def convert(row_id: str) -> dict[str, Any]:  # noqa: C901 - one gated conversion lifecycle.
    import mlx.core as mx
    from mlx_lm.utils import dequantize_model, load, quantize_model, save

    matrix, row, config = _verify(row_id)
    runtime = row["runtime"]
    if sys.version.split()[0] != runtime["python_version"]:
        raise ConversionError("Python version differs from the conversion matrix")
    if _sha256(ROOT / runtime["lock_path"]) != runtime["lock_sha256"]:
        raise ConversionError("runtime lock differs from the conversion matrix")
    for package, version in runtime["packages"].items():
        if importlib.metadata.version(package) != version:
            raise ConversionError(f"runtime package differs: {package}")
    if (
        platform.system() != "Darwin"
        or platform.machine() != "arm64"
        or mx.default_device().type != mx.DeviceType.gpu
    ):
        raise ConversionError("Apple Silicon MLX GPU is required")
    _resources(row, config["cache"], before_stage=False)
    source = _snapshot(
        config["cache"], row["source_model"]["id"], row["source_model"]["revision"]
    )
    if config["output"].exists():
        raise ConversionError(
            "conversion output already exists; remove only this DMS-20 temporary model before retrying"
        )
    os.environ.update(
        HF_HOME=str(config["cache"]),
        HF_HUB_CACHE=str(config["cache"]),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    model, tokenizer, model_config = load(str(source), return_config=True)
    was_quantized = bool(model_config.get("quantization"))
    if was_quantized:
        model = dequantize_model(model)
    model_config.pop("quantization", None)
    model_config.pop("quantization_config", None)
    model, model_config = quantize_model(
        model, model_config, group_size=64, bits=4, mode="affine"
    )
    save(
        str(config["output"]),
        str(source),
        model,
        tokenizer,
        model_config,
        donate_model=False,
    )
    for path in source.iterdir():
        if (
            path.is_file()
            and path.name
            not in {"config.json", "model.safetensors", "model.safetensors.index.json"}
            and not path.name.startswith(("model-", "model.safetensors-"))
        ):
            shutil.copy2(path, config["output"] / path.name)
    saved_config = json.loads(
        (config["output"] / "config.json").read_text(encoding="utf-8")
    )
    quant = saved_config.get("quantization", {})
    bits = {
        value.get("bits")
        for value in quant.values()
        if isinstance(value, dict) and "bits" in value
    }
    if quant.get("bits") != 4 and bits != {4}:
        raise ConversionError(
            "saved artifact does not record 4-bit quantization for all quantized layers"
        )
    artifacts = []
    for path in sorted(config["output"].rglob("*")):
        if path.is_file():
            artifacts.append(
                {
                    "path": str(path.relative_to(config["output"])),
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    receipt = {
        "optimization_id": row_id,
        "source_model": str(source),
        "source_was_quantized": was_quantized,
        "quantization": {"bits": 4, "group_size": 64, "mode": "affine"},
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "source_matrix_sha256": row["source_matrix_sha256"],
        "conversion_matrix_sha256": _sha256(config["matrix"]),
    }
    out = EVALUATION / f"{row_id}-conversion-2026-10-24"
    out.mkdir(parents=True, exist_ok=True)
    (out / "conversion-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    return {
        "optimization_id": row_id,
        "output": str(config["output"]),
        "artifact_count": len(artifacts),
        "quantization": receipt["quantization"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--row", choices=sorted(ROWS), required=True)
    parser.add_argument("--stage-only", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            stage(args.row) if args.stage_only else convert(args.row), sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
